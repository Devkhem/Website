#!/usr/bin/env python3
"""Drive the client video pipeline from a Google Form response to a review packet.

Pipeline stages:
    Google Form -> Drive -> Brand Bible -> Script -> Shot List -> Stills
    -> Google Flow animate -> ElevenLabs voice-over -> Premiere -> Review

Every stage that a machine can do is generated here. Every stage that needs a
human or an external tool gets a ready-to-paste prompt plus a drop folder, and
`sync` picks the work back up as soon as the files land.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIELDS = ROOT / "data" / "client_intake_fields.json"
DEFAULT_JOBS = ROOT / "outputs" / "clients"

STAGES = [
    "intake",
    "brand_bible",
    "script",
    "shot_list",
    "stills",
    "animate",
    "voiceover",
    "edit",
    "review",
]

STAGE_LABELS = {
    "intake": "รับ brief จาก Google Form",
    "brand_bible": "ChatGPT/Gemini สร้าง Brand Bible",
    "script": "เขียน Script",
    "shot_list": "แตก Shot List",
    "stills": "สร้าง Still Images",
    "animate": "Google Flow animate",
    "voiceover": "ElevenLabs voice-over",
    "edit": "ประกอบใน Premiere Pro",
    "review": "ส่ง Review",
}

IMAGE_SUFFIXES = [".png", ".jpg", ".jpeg", ".webp"]
CLIP_SUFFIXES = [".mp4", ".mov", ".webm"]
AUDIO_SUFFIXES = [".mp3", ".wav", ".m4a", ".ulaw", ".opus", ".pcm", ".alaw"]
# ElevenLabs output_format prefix -> the extension its bytes actually deserve.
AUDIO_FORMAT_SUFFIXES = {"mp3": ".mp3", "pcm": ".pcm", "ulaw": ".ulaw", "alaw": ".alaw", "opus": ".opus"}
FINAL_SUFFIXES = [".mp4", ".mov"]
ASSET_LOG_VERSION = 5
# Bump when a prompt template changes, so existing jobs adopt the new fingerprint
# instead of being told their script is stale by a tool update.
SOURCE_LOG_VERSION = 3


# ---------------------------------------------------------------- utilities


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    """Write through a sibling and swap it in, so a killed sync cannot truncate state.

    A half-written asset-log parses as broken, and a broken log silently adopts every
    stale asset as current.
    """
    staging = path.with_name(path.name + ".part")
    staging.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def slugify(value: str, fallback: str = "client") -> str:
    cleaned = re.sub(r"[\s/\\]+", "-", (value or "").strip())
    cleaned = re.sub(r"[^0-9A-Za-z฀-๿\-_]", "", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-_")
    return cleaned[:40] or fallback


def safe_component(value: str) -> str:
    """Reduce an id to something that can only ever name a file inside its folder.

    Scene and shot ids arrive from pasted LLM output, so `../..` or an absolute
    path would otherwise let `sync` write prompt files anywhere on disk.
    """
    cleaned = re.sub(r"[^0-9A-Za-z฀-๿._-]", "-", str(value or "").strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    if not cleaned or set(cleaned) <= {"."}:
        return ""
    return cleaned[:60]


def normalize_ids(entries: list, prefix: str, extra_keys: list = ()) -> None:
    """Rewrite ids in place so every downstream path and lookup uses the safe form."""
    for index, entry in enumerate(entries, start=1):
        for key in ["id"] + list(extra_keys):
            raw = str(entry.get(key) or "").strip()
            if key == "id":
                safe = safe_component(raw) or f"{prefix}-{index:02d}"
            else:
                safe = safe_component(raw)
            if safe != raw:
                print(f"[warn] `{key}` `{raw}` ใช้เป็นชื่อไฟล์ไม่ได้ เปลี่ยนเป็น `{safe}`")
                entry[key] = safe


REQUIRED_ENTRY_KEYS = {
    "scenes": ["id", "beat", "vo", "on_screen_text", "duration_sec"],
    "shots": ["id", "scene_id", "description", "duration_sec"],
}


def entries_are_valid(entries: list, key: str, name: str) -> bool:
    """Every entry must carry the schema keys, a unique id and a positive duration.

    A truncated scene without `vo` would otherwise pass as an intentionally silent
    scene, and a duplicate id would let one asset satisfy two entries.
    """
    ok = True
    seen = set()
    required = REQUIRED_ENTRY_KEYS.get(key, ["id", "duration_sec"])
    for entry in entries:
        missing = [field for field in required if field not in entry]
        if missing:
            print(f"[warn] {name} `{entry.get('id', '?')}` ขาดคีย์ {', '.join(missing)} ตาม schema")
            ok = False
        entry_id = str(entry.get("id") or "")
        if entry_id in seen:
            print(f"[warn] {name} มี id ซ้ำใน `{key}`: `{entry_id}` ต้องไม่ซ้ำเพราะใช้เป็นชื่อไฟล์")
            ok = False
        seen.add(entry_id)
        duration = as_float(entry.get("duration_sec"), None)
        if duration is None or not math.isfinite(duration) or duration <= 0:
            print(f"[warn] {name} `{entry_id}` ต้องมี duration_sec เป็นตัวเลขบวก แต่ได้: {entry.get('duration_sec')!r}")
            ok = False
    return ok


_WARNED = set()


def warn_once(key: str, message: str) -> None:
    """find_asset runs several times per sync; the operator needs the warning once."""
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(message)


MEDIA_SIGNATURES = {
    "image": [b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF", b"GIF8"],
    "clip": [b"ftyp", b"\x1a\x45\xdf\xa3", b"RIFF"],
    "audio": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3", b"RIFF", b"ftyp", b"OggS"],
}
RAW_AUDIO_SUFFIXES = {".pcm", ".ulaw", ".alaw"}
MIN_MEDIA_BYTES = 512


def decode_problem(path: Path, kind: str) -> str:
    """Empty when the file decodes; otherwise why it cannot be trusted."""
    if kind == "image":
        try:
            from PIL import Image
        except ImportError:
            return "ตรวจภาพไม่ได้เพราะยังไม่ได้ติดตั้ง Pillow (python3 -m pip install -r requirements.txt)"
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
        except Exception:
            return "เปิดภาพไม่ได้ ไฟล์อาจดาวน์โหลดไม่ครบ"
        return ""
    probe = shutil.which("ffprobe")
    if not probe:
        return "ตรวจไฟล์ไม่ได้เพราะเครื่องนี้ไม่มี ffprobe ให้ติดตั้ง ffmpeg ก่อน"
    stream = "v:0" if kind == "clip" else "a:0"
    result = subprocess.run(
        [probe, "-v", "error", "-select_streams", stream, "-show_entries",
         "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return "ถอดรหัสไม่ได้ ไฟล์อาจเสียหรือดาวน์โหลดไม่ครบ"
    return ""


_MEDIA_VERDICTS = {}
_DURATIONS = {}


def media_duration(path: Path) -> float:
    """Seconds of media, or 0 when ffprobe is unavailable or unsure."""
    probe = shutil.which("ffprobe")
    if not probe:
        return 0.0
    key = (str(path), asset_stamp(path))
    if key not in _DURATIONS:
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
        _DURATIONS[key] = as_float(result.stdout.strip(), 0) if result.returncode == 0 else 0.0
    return _DURATIONS[key]


def voice_duration_problem(scene: dict, asset: "Path | None", raw_bps: int = 0) -> str:
    """Empty when the take fits its scene; otherwise how it fails to."""
    planned = as_float(scene.get("duration_sec"), 0)
    if asset is None or planned <= 0:
        return ""
    if asset.suffix.lower() in RAW_AUDIO_SUFFIXES:
        spoken = asset.stat().st_size / raw_bps if raw_bps > 0 else 0.0
    else:
        spoken = media_duration(asset)
    if spoken <= 0:
        return ""
    if spoken - planned > max(1.0, planned * 0.2):
        return f"ยาวเกินซีนอยู่ {spoken - planned:.1f} วินาที"
    # A scene can end on silence, but a take covering almost none of it means the
    # narration or the scene length is wrong.
    floor = max(1.0, planned * 0.4)
    if spoken < floor:
        return f"ยาวแค่ {spoken:.1f} วินาที จากซีน {planned:g} วินาที เสียงหายไปเกือบทั้งซีน"
    return ""


def raw_bytes_per_second(fields_config: dict) -> int:
    """Bytes per second implied by the configured raw output format, 0 if unknown."""
    fmt = str((fields_config.get("elevenlabs") or {}).get("output_format", "")).lower()
    match = re.match(r"(pcm|ulaw|alaw)_(\d+)", fmt)
    if not match:
        return 0
    rate = int(match.group(2))
    return rate * 2 if match.group(1) == "pcm" else rate


def usable_asset(path: "Path | None", kind: str, raw_bps: int = 0) -> bool:
    """A placeholder, a saved error page or a half-finished download is not an asset."""
    if path is None:
        return False
    if path.stat().st_size < MIN_MEDIA_BYTES:
        return False
    if kind == "audio" and path.suffix.lower() in RAW_AUDIO_SUFFIXES:
        # No header to read: judge it by the length the configured format implies.
        if raw_bps <= 0:
            warn_once(
                f"rawfmt:{path}",
                f"[warn] {path.name} เป็นไฟล์ดิบที่ไม่มี header ตรวจไม่ได้ "
                f"เพราะ output_format ใน config ไม่ได้บอกอัตราสุ่ม",
            )
            return False
        return path.stat().st_size >= raw_bps * 0.5
    try:
        head = path.open("rb").read(16)
    except OSError:
        return False
    if not any(signature in head for signature in MEDIA_SIGNATURES.get(kind, [])):
        return False
    key = (str(path), asset_stamp(path), kind)
    if key not in _MEDIA_VERDICTS:
        _MEDIA_VERDICTS[key] = decode_problem(path, kind)
    return not _MEDIA_VERDICTS[key]


def checked_asset(directory: Path, stem: str, suffixes: list, kind: str, raw_bps: int = 0) -> "Path | None":
    asset = find_asset(directory, stem, suffixes)
    if asset is None:
        return None
    if not usable_asset(asset, kind, raw_bps):
        reason = _MEDIA_VERDICTS.get((str(asset), asset_stamp(asset), kind)) or "ไฟล์เสียหรือยังไม่สมบูรณ์"
        warn_once(f"broken:{asset}", f"[warn] {directory.name}/{asset.name} ใช้ไม่ได้: {reason}")
        return None
    return asset


def find_asset(directory: Path, stem: str, suffixes: list) -> "Path | None":
    """Find `<stem>.<suffix>` in a directory, matching the extension case-insensitively."""
    if not stem or not directory.exists():
        return None
    entries = [
        item
        for item in directory.iterdir()
        if item.is_file() and item.stem == stem and item.stat().st_size > 0
    ]
    wanted = [suffix.lower() for suffix in suffixes]
    entries = [item for item in entries if item.suffix.lower() in wanted]
    if not entries:
        return None
    if len(entries) > 1:
        # File times cannot order revisions once files are copied between machines.
        warn_once(
            f"duplicate:{directory}:{stem}",
            f"[warn] {directory.name}/{stem} มีหลายไฟล์: {', '.join(sorted(item.name for item in entries))} "
            f"ให้เหลือไฟล์เดียว ระบบจะไม่เดาว่าอันไหนใหม่กว่า",
        )
        return None
    return entries[0]


def matching_files(directory: Path, suffixes: list) -> list:
    if not directory.exists():
        return []
    wanted = [suffix.lower() for suffix in suffixes]
    return [
        item
        for item in sorted(directory.iterdir())
        if item.is_file() and item.suffix.lower() in wanted and item.stat().st_size > 0
    ]


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def text_fingerprint(text: str) -> str:
    return hashlib.sha1(str(text or "").strip().encode("utf-8")).hexdigest()[:12]


def read_render_log(voice_dir: Path) -> dict:
    """scene_id -> {text_sha, file} for audio this pipeline synthesized."""
    path = voice_dir / "rendered.json"
    if not path.exists():
        return {}
    try:
        payload = read_json(path)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def voice_fingerprint(fields_config: dict, voice_dir: "Path | None" = None) -> str:
    """Same recipe as generate_voiceover, so both agree on what a fresh take is.

    A job that recorded its own voice settings keeps them; only jobs without one
    follow the global .env value.
    """
    settings = dict(fields_config.get("elevenlabs") or {})
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if voice_dir is not None:
        chosen = voice_dir / "settings.json"
        if chosen.exists():
            try:
                saved = read_json(chosen)
            except json.JSONDecodeError:
                saved = {}
            # Only the voice override is per-job; model/stability/format stay live,
            # so changing them in the config still retires the old takes.
            if isinstance(saved, dict) and saved.get("voice_id"):
                voice_id = str(saved["voice_id"]).strip()
    parts = [
        f"voice={voice_id}",
        f"model={settings.get('model_id', 'eleven_multilingual_v2')}",
        f"stability={settings.get('stability', 0.45)}",
        f"similarity={settings.get('similarity_boost', 0.75)}",
        f"style={settings.get('style', 0.0)}",
        f"format={settings.get('output_format', 'mp3_44100_128')}",
    ]
    return text_fingerprint("|".join(parts))


def voice_is_stale(scene: dict, log: dict, asset: "Path | None", voice_sha: str = "") -> bool:
    """True when the recorded audio was synthesized from older script text.

    The log entry only applies to the file it names. Audio recorded by hand — or a
    manual take that replaced a synthesized one — is never called stale.
    """
    record = log.get(str(scene.get("id") or ""))
    if not isinstance(record, dict) or not record.get("text_sha"):
        return False
    if asset is not None and record.get("file") and record["file"] != asset.name:
        return False
    if asset is not None and record.get("stamp") and record["stamp"] != content_identity(asset):
        # Same name, different bytes: someone dropped their own take in.
        return False
    if voice_sha and record.get("voice_sha") and record["voice_sha"] != voice_sha:
        return True
    return record["text_sha"] != text_fingerprint(scene.get("vo"))


def has_content(path: Path) -> bool:
    return path.exists() and len(path.read_text(encoding="utf-8").strip()) > 0


def bullet_list(values, empty: str = "-") -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


# ------------------------------------------------------------------- intake


def read_responses(source: str) -> list:
    """Read Google Form responses from a local CSV export or a published CSV URL."""
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=30) as response:  # noqa: S310 - user supplied
            raw = response.read().decode("utf-8-sig")
        # StringIO keeps newlines inside quoted answers intact; splitlines() would drop them.
        return list(csv.DictReader(io.StringIO(raw, newline="")))
    path = Path(source)
    if not path.exists():
        raise SystemExit(f"ไม่พบไฟล์คำตอบฟอร์ม: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def select_response(rows: list, row_index: int, match: str) -> dict:
    if not rows:
        raise SystemExit("ไฟล์คำตอบฟอร์มว่าง")
    if match:
        needle = match.lower()
        for row in reversed(rows):
            if any(needle in str(value).lower() for value in row.values()):
                return row
        raise SystemExit(f"ไม่พบแถวที่ตรงกับ: {match}")
    try:
        return rows[row_index]
    except IndexError:
        raise SystemExit(f"ไม่มีแถวที่ {row_index} (มีทั้งหมด {len(rows)} แถว)")


def header_matches(header: str, needle: str) -> bool:
    """ASCII keywords must start a word, so `line` hits `Line ID` but not `Deadline`.

    The end is left open so `note` still matches `Notes`. Thai keywords stay plain
    substring matches because Thai text has no word separators.
    """
    lowered = str(header).lower()
    keyword = str(needle).lower().strip()
    if not keyword:
        return False
    if keyword.isascii():
        return re.search(r"\b" + re.escape(keyword), lowered) is not None
    return keyword in lowered


def map_response(row: dict, keywords: dict) -> dict:
    """Map arbitrary Google Form column headers onto canonical brief fields."""
    mapped = {}
    used_headers = set()
    for field, needles in keywords.items():
        for header, value in row.items():
            if header in used_headers or not str(value or "").strip():
                continue
            if any(header_matches(header, needle) for needle in needles):
                mapped[field] = str(value).strip()
                used_headers.add(header)
                break
    extras = {
        str(header): str(value).strip()
        for header, value in row.items()
        if header and header not in used_headers and str(value or "").strip()
    }
    if extras:
        mapped["form_extra"] = extras
    return mapped


def parse_duration(value, default: int) -> int:
    """Read a free-form duration answer without gluing separate numbers together."""
    text = str(value or "").strip()
    clock = re.fullmatch(r"\s*(\d+)\s*:\s*([0-5]?\d)\s*", text)
    if clock:
        seconds = int(clock.group(1)) * 60 + int(clock.group(2))
        return seconds if 3 <= seconds <= 900 else default
    numbers = [float(found) for found in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return default
    if re.search(r"นาที|minute|\bmin\b", text, re.IGNORECASE):
        minutes = numbers[0]
        seconds = minutes * 60
        # `1.5 minutes` is 90s; a second number only means seconds for whole minutes.
        if len(numbers) > 1 and float(minutes).is_integer():
            seconds += numbers[1]
        seconds = int(round(seconds))
    else:
        seconds = int(round(numbers[0]))
        if len(numbers) > 1:
            print(f"[warn] ความยาว `{text}` มีหลายตัวเลข ใช้ {seconds} วินาที ถ้าไม่ตรงให้ใส่ --field duration_sec=<วินาที>")
    if seconds < 3 or seconds > 900:
        print(f"[warn] ความยาว {seconds} วินาทีดูผิดปกติ ใช้ค่าเริ่มต้น {default} วินาทีแทน")
        return default
    return seconds


RATIO_LABELS = {
    "9:16": ["แนวตั้ง", "vertical", "portrait", "tiktok", "reels", "shorts"],
    "16:9": ["แนวนอน", "horizontal", "landscape", "youtube"],
    "1:1": ["จัตุรัส", "สี่เหลี่ยม", "square"],
    "4:5": ["4x5", "feed"],
}


def normalize_ratio(value, default: str) -> str:
    """Turn `แนวตั้ง` or `9:16 (แนวตั้ง)` into `9:16` while the brief is still cheap to fix."""
    text = str(value or "").strip()
    found = parse_ratio(text)
    if found:
        width, height = found
        return f"{width:g}:{height:g}"
    lowered = text.lower()
    for ratio, labels in RATIO_LABELS.items():
        if any(label in lowered for label in labels):
            return ratio
    if text:
        print(f"[warn] อ่านสัดส่วนภาพ {text!r} ไม่ออก ใช้ {default} ไปก่อน ถ้าไม่ใช่ให้ใส่ --field aspect_ratio=9:16")
    return default


def build_brief(mapped: dict, defaults: dict, overrides: dict) -> dict:
    brief = dict(defaults)
    brief.update(mapped)
    brief.update(overrides)
    brief["duration_sec"] = parse_duration(brief.get("duration_sec"), int(defaults.get("duration_sec", 45)))
    brief["scene_count"] = int(brief.get("scene_count") or defaults.get("scene_count", 6))
    brief["aspect_ratio"] = normalize_ratio(brief.get("aspect_ratio"), str(defaults.get("aspect_ratio", "9:16")))
    brief.setdefault("client_name", "ลูกค้าไม่ระบุชื่อ")
    brief["received_at"] = brief.get("received_at") or datetime.now().isoformat(timespec="seconds")
    return brief


def parse_overrides(pairs: list) -> dict:
    overrides = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--field ต้องเป็นรูปแบบ key=value แต่ได้: {pair}")
        key, value = pair.split("=", 1)
        overrides[key.strip()] = value.strip()
    return overrides


# ------------------------------------------------------------------ prompts


def intake_extras(brief: dict) -> str:
    """Everything the client typed that has no dedicated slot in the prompts.

    Free-text notes, the assets link, and answers from questions added to the form
    later must reach the LLM, otherwise a mandatory instruction stays in brief.json.
    """
    labels = [
        ("notes", "หมายเหตุจากลูกค้า"),
        ("assets_link", "ไฟล์/ภาพที่ลูกค้าส่งมา"),
        ("deadline", "กำหนดส่ง"),
    ]
    lines = []
    for key, label in labels:
        value = str(brief.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    extra = brief.get("form_extra")
    if isinstance(extra, dict):
        for header, value in extra.items():
            if re.search(r"timestamp|ประทับเวลา", str(header), re.IGNORECASE):
                continue
            lines.append(f"- {header}: {value}")
    return "\n".join(lines)


def extras_block(brief: dict) -> list:
    extras = intake_extras(brief)
    return ["", "ข้อมูลเพิ่มเติมจากฟอร์ม (ต้องอ่านและห้ามขัด):", extras] if extras else []


def brand_bible_prompt(brief: dict, rules: dict) -> str:
    return "\n".join(
        [
            "# 01 Brand Bible Prompt",
            "",
            "วางข้อความด้านล่างทั้งบล็อกใน ChatGPT หรือ Gemini",
            f"แล้วบันทึกคำตอบเป็นไฟล์ `brand-bible.md` ในโฟลเดอร์งานนี้",
            "",
            "```text",
            "คุณคือ Brand Strategist ที่ทำคอนเทนต์วิดีโอสั้นให้แบรนด์ไทย",
            "สร้าง Brand Bible จาก brief ด้านล่าง ตอบเป็นภาษาไทย",
            "",
            "Brief:",
            f"- ลูกค้า: {brief.get('client_name', '-')}",
            f"- สินค้า/บริการ: {brief.get('product', '-')}",
            f"- เป้าหมาย: {brief.get('goal', '-')}",
            f"- กลุ่มเป้าหมาย: {brief.get('audience', '-')}",
            f"- โทนที่ลูกค้าอยากได้: {brief.get('tone', '-')}",
            f"- แพลตฟอร์ม: {brief.get('platform', '-')} ({brief.get('aspect_ratio', '9:16')}, {brief.get('duration_sec', 45)} วินาที)",
            f"- ต้องมี: {brief.get('must_include', '-')}",
            f"- ห้ามมี: {brief.get('avoid', '-')}",
            f"- ตัวอย่างที่ลูกค้าชอบ: {brief.get('reference', '-')}",
        ]
        + extras_block(brief)
        + [
            "",
            "ให้ผลลัพธ์เป็นหัวข้อดังนี้",
            "1. Positioning หนึ่งประโยค",
            "2. Audience insight 3 ข้อ พร้อม pain point จริง",
            "3. Tone of voice: ทำอะไร / ไม่ทำอะไร อย่างละ 5 ข้อ",
            "4. Key message 3 ข้อ เรียงตามความสำคัญ",
            "5. Visual direction: สี แสง ระยะภาพ พร็อพ",
            "6. คำที่ห้ามใช้ และคำเคลมที่ต้องเลี่ยงตามกฎโฆษณาไทย",
            "7. Hook bank 10 อัน สำหรับ 3 วินาทีแรก",
            "",
            "ข้อบังคับด้านภาพที่ต้องใส่ในหัวข้อ Visual direction:",
            bullet_list(rules.get("prefer", [])),
            "สิ่งที่ต้องเลี่ยง:",
            bullet_list(rules.get("avoid", [])),
            "```",
        ]
    )


def script_prompt(brief: dict, brand_bible: str) -> str:
    scene_count = brief.get("scene_count", 6)
    duration = brief.get("duration_sec", 45)
    bible_block = brand_bible.strip() if brand_bible.strip() else "(ยังไม่มี brand-bible.md ให้ใช้ brief ด้านบนแทน)"
    return "\n".join(
        [
            "# 02 Script Prompt",
            "",
            "วางบล็อกด้านล่างใน ChatGPT หรือ Gemini",
            "แล้วบันทึกคำตอบ (JSON ล้วน) เป็นไฟล์ `script.json`",
            "",
            "```text",
            f"เขียนสคริปต์วิดีโอสั้นความยาว {duration} วินาที สำหรับ {brief.get('platform', 'TikTok')}",
            f"ลูกค้า: {brief.get('client_name', '-')} | สินค้า/บริการ: {brief.get('product', '-')}",
            f"เป้าหมาย: {brief.get('goal', '-')}",
            f"ต้องมี: {brief.get('must_include', '-')} | ห้ามมี: {brief.get('avoid', '-')}",
        ]
        + extras_block(brief)
        + [
            "",
            "ใช้ Brand Bible นี้เป็นกรอบ:",
            bible_block,
            "",
            f"แบ่งเป็น {scene_count} ซีน และเวลารวมทุกซีนต้องเท่ากับ {duration} วินาที "
            f"(คลาดได้ไม่เกิน {max(2.0, duration * 0.05):g} วินาที)",
            "ซีนแรกคือ hook ที่ทำให้หยุดนิ้วใน 3 วินาที ซีนสุดท้ายคือ CTA",
            "voiceover ต้องเป็นภาษาพูด อ่านออกเสียงแล้วลื่น ไม่มีอิโมจิ ไม่มีวงเล็บกำกับ",
            "on_screen_text ห้ามเกิน 2 บรรทัด" if wants_subtitles(brief) else "ห้ามใส่ตัวหนังสือบนจอเลย ให้ on_screen_text เป็นค่าว่างทุกซีน",
            "",
            "ตอบเป็น JSON ล้วน ไม่ต้องมีคำอธิบายอื่น ตาม schema นี้",
            "{",
            '  "title": "",',
            '  "language": "th",',
            f'  "total_duration_sec": {duration},',
            '  "scenes": [',
            '    {"id": "sc-01", "beat": "hook", "vo": "", "on_screen_text": "", "duration_sec": 3, "note": ""}',
            "  ],",
            '  "cta": ""',
            "}",
            "```",
        ]
    )


def shot_list_prompt(brief: dict, script: dict, rules: dict, brand_bible: str) -> str:
    scenes = script.get("scenes", [])
    scene_lines = [
        f"- {scene.get('id', '')} ({scene.get('duration_sec', 0)}s, {scene.get('beat', '')}): {scene.get('vo', '')}"
        for scene in scenes
    ]
    return "\n".join(
        [
            "# 03 Shot List Prompt",
            "",
            "วางบล็อกด้านล่างใน ChatGPT หรือ Gemini",
            "แล้วบันทึกคำตอบ (JSON ล้วน) เป็นไฟล์ `shot-list.json`",
            "",
            "```text",
            "แตกสคริปต์นี้เป็น shot list สำหรับผลิตด้วยภาพนิ่ง AI แล้วนำไป animate ต่อใน Google Flow",
            f"สัดส่วนภาพ: {brief.get('aspect_ratio', '9:16')} | สินค้า/บริการ: {brief.get('product', '-')}",
        ]
        + extras_block(brief)
        + [
            "",
            "ทุก image_prompt ต้องอยู่ในกรอบ Visual direction ของ Brand Bible นี้:",
            brand_bible.strip() if brand_bible.strip() else "(ยังไม่มี brand-bible.md ให้ยึดตาม brief ด้านบน)",
            "",
            "สคริปต์:",
            "\n".join(scene_lines) if scene_lines else "-",
            "",
            "กติกา",
            "- 1 ซีนมีได้ 1-2 ช็อต และเวลารวมของช็อตต้องเท่ากับเวลาซีน",
            "- image_prompt ต้องเขียนเป็นภาษาอังกฤษ บรรยายภาพนิ่งเฟรมแรกให้ครบ subject/setting/lighting/lens",
            "- motion_prompt ต้องเป็นการเคลื่อนไหวที่ทำได้จากภาพนิ่งภาพเดียว เช่น slow push in, parallax, hair moves",
            "- ห้ามให้มีตัวหนังสือหรือ watermark ในภาพ",
            "สิ่งที่ต้องเลี่ยงในภาพ:",
            bullet_list(rules.get("avoid", [])),
            "",
            "ตอบเป็น JSON ล้วน ตาม schema นี้",
            "{",
            '  "shots": [',
            "    {",
            '      "id": "sh-01", "scene_id": "sc-01", "description": "", "framing": "medium",',
            '      "camera_move": "slow push in", "duration_sec": 3,',
            '      "image_prompt": "", "motion_prompt": "", "negative": ""',
            "    }",
            "  ]",
            "}",
            "```",
        ]
    )


def wants_subtitles(brief: dict) -> bool:
    """`subtitles=none` in the brief means no burned-in text anywhere in the video."""
    return str(brief.get("subtitles", "auto")).strip().lower() not in {"none", "no", "off", "ไม่ใส่", "ไม่มี"}


def parse_ratio(value: str):
    """Read `9:16`, `9 x 16`, or `9:16 (แนวตั้ง)`; None when there is no ratio in it."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*[:xX/]\s*(\d+(?:\.\d+)?)", str(value or ""))
    if not match:
        return None
    width, height = float(match.group(1)), float(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def orientation_hint(aspect_ratio: str) -> str:
    ratio = parse_ratio(aspect_ratio)
    if not ratio:
        return "vertical"
    width, height = ratio
    if abs(width - height) < 0.001:
        return "square"
    return "vertical" if height > width else "horizontal"


def compose_image_prompt(shot: dict, brief: dict, rules: dict) -> str:
    base = str(shot.get("image_prompt") or "").strip()
    if not base:
        base = ", ".join(
            part
            for part in [
                str(shot.get("description") or "").strip(),
                str(shot.get("framing") or "").strip(),
                f"product: {brief.get('product', '')}".strip(),
            ]
            if part
        )
    negative = str(shot.get("negative") or "").strip() or "text, watermark, logo, extra fingers, distorted hands"
    return "\n".join(
        [
            f"[{shot.get('id', '')}] scene {shot.get('scene_id', '')} - {shot.get('duration_sec', 0)}s",
            "",
            "PROMPT",
            base,
            f"{orientation_hint(brief.get('aspect_ratio', '9:16'))} {brief.get('aspect_ratio', '9:16')}, photographic, natural light"
            + (", leave clean space for subtitles" if wants_subtitles(brief) else ", the frame must read on its own without any caption"),
            "",
            "NEGATIVE",
            negative,
            "",
            "ห้ามให้มีในภาพ",
            bullet_list(rules.get("avoid", [])),
            "",
            f"บันทึกภาพที่ได้เป็น: stills/{shot.get('id', 'sh-xx')}.png",
        ]
    )


def compose_flow_prompt(shot: dict, brief: dict, still_name: str) -> str:
    motion = str(shot.get("motion_prompt") or "").strip() or str(shot.get("camera_move") or "slow push in").strip()
    return "\n".join(
        [
            f"[{shot.get('id', '')}] Google Flow animate - {shot.get('duration_sec', 0)}s",
            "",
            f"ภาพต้นทาง: stills/{still_name}",
            "",
            "MOTION PROMPT",
            motion,
            "",
            "SETTINGS",
            f"- aspect ratio: {brief.get('aspect_ratio', '9:16')}",
            f"- duration: {shot.get('duration_sec', 0)} วินาที",
            "- ห้ามเปลี่ยนหน้าตัวละครหรือรูปทรงสินค้าจากภาพต้นทาง",
            "- ห้ามให้ระบบเติมตัวหนังสือหรือ watermark",
            "",
            f"บันทึกคลิปที่ได้เป็น: clips/{shot.get('id', 'sh-xx')}.mp4",
        ]
    )


# ------------------------------------------------------------------- stages


class Job:
    def __init__(self, path: Path):
        self.path = path
        self.brief_path = path / "brief.json"
        self.manifest_path = path / "manifest.json"
        self.brand_bible_path = path / "brand-bible.md"
        self.script_path = path / "script.json"
        self.shot_list_path = path / "shot-list.json"
        self.stills_dir = path / "stills"
        self.clips_dir = path / "clips"
        self.voice_dir = path / "voiceover"
        self.final_dir = path / "final"

    @property
    def brief(self) -> dict:
        return read_json(self.brief_path) if self.brief_path.exists() else {}

    def load_stage_json(self, path: Path, required_key: str) -> dict:
        if not path.exists():
            return {}
        try:
            payload = read_json(path)
        except json.JSONDecodeError as error:
            print(f"[warn] {path.name} ไม่ใช่ JSON ที่อ่านได้: {error}")
            return {}
        if not isinstance(payload, dict):
            print(f"[warn] {path.name} ต้องเป็น JSON object ที่มีคีย์ `{required_key}` ไม่ใช่ {type(payload).__name__}")
            return {}
        entries = payload.get(required_key)
        if not isinstance(entries, list) or not entries:
            print(f"[warn] {path.name} ต้องมีคีย์ `{required_key}` เป็น list ที่ไม่ว่าง")
            return {}
        bad = [index for index, entry in enumerate(entries, start=1) if not isinstance(entry, dict)]
        if bad:
            print(f"[warn] {path.name} รายการที่ {', '.join(str(index) for index in bad)} ใน `{required_key}` ไม่ใช่ object")
            return {}
        if required_key == "scenes":
            normalize_ids(entries, "sc")
        elif required_key == "shots":
            normalize_ids(entries, "sh", ["scene_id"])
        if not entries_are_valid(entries, required_key, path.name):
            return {}
        return payload


def shot_list_problems(script: dict, shots: list) -> list:
    """Everything that would make the assembly sheet unbuildable.

    Editing must not go ready while a scene has no visuals, a shot points at a
    scene that does not exist, or a scene's shots do not add up to its runtime.
    """
    if not script or not shots:
        return []
    scenes = {str(scene.get("id") or ""): scene for scene in script.get("scenes", []) if scene.get("id")}
    covered = {}
    for shot in shots:
        covered.setdefault(str(shot.get("scene_id") or ""), []).append(shot)

    problems = []
    missing = sorted(scene_id for scene_id in scenes if scene_id not in covered)
    if missing:
        problems.append(f"ซีนที่ยังไม่มีช็อต: {', '.join(missing)}")
    orphans = sorted(scene_id for scene_id in covered if scene_id not in scenes)
    if orphans:
        problems.append(f"ช็อตอ้างถึงซีนที่ไม่มีในสคริปต์: {', '.join(orphans) or '(ว่าง)'}")
    for scene_id in sorted(scene_id for scene_id in scenes if scene_id in covered):
        count = len(covered[scene_id])
        if count > 2:
            problems.append(f"{scene_id} มี {count} ช็อต เกินกติกาที่ให้ซีนละ 1-2 ช็อต")
        planned = as_float(scenes[scene_id].get("duration_sec"), 0)
        total = sum(as_float(shot.get("duration_sec"), 0) for shot in covered[scene_id])
        if planned and abs(total - planned) > 1:
            problems.append(f"{scene_id} เวลาช็อตรวม {total:g} วินาที ไม่ตรงกับซีน {planned:g} วินาที")
    script_total = sum(as_float(scene.get("duration_sec"), 0) for scene in scenes.values())
    shots_total = sum(as_float(shot.get("duration_sec"), 0) for shot in shots)
    # Per-scene slack can add up, so the whole video has to line up as well.
    if script_total and abs(shots_total - script_total) > 1:
        problems.append(
            f"เวลาช็อตรวมทั้งคลิป {shots_total:g} วินาที ไม่ตรงกับสคริปต์ {script_total:g} วินาที"
        )
    return problems


def shot_image_fingerprint(shot: dict, brief: dict, rules: dict) -> str:
    """Hash the prompt the artist actually receives, so brief or rule changes count."""
    return text_fingerprint(compose_image_prompt(shot, brief, rules))


def shot_motion_fingerprint(shot: dict, brief: dict, still_stamp: str = "") -> str:
    """A clip is only current while both its Flow prompt and its source still are."""
    return text_fingerprint(compose_flow_prompt(shot, brief, "") + "|" + still_stamp)


def asset_stamp(asset: "Path | None") -> str:
    """Identity of a file on disk. Nanoseconds plus size so a same-second rewrite counts."""
    if asset is None:
        return ""
    info = asset.stat()
    return f"{asset.name}:{info.st_mtime_ns}:{info.st_size}"


def script_scene_fingerprint(script: dict) -> str:
    """The script content the shot list was written against."""
    rows = [
        "|".join(str(scene.get(key) or "") for key in ("id", "beat", "vo", "on_screen_text", "duration_sec"))
        for scene in script.get("scenes", [])
    ]
    return text_fingerprint("\n".join(rows))


def read_source_log(job: Job) -> dict:
    log_path = job.path / "source-log.json"
    if not log_path.exists():
        return {}
    try:
        loaded = read_json(log_path)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def content_digest(path: Path) -> str:
    """Content identity without the filename, so a rename is not a new artifact."""
    identity = content_identity(path)
    return identity.split(":", 1)[1] if ":" in identity else identity


def derived_is_stale(job: Job, key: str, derived: Path, source_sha: str, stamp: str = "") -> bool:
    """True when the sources changed after `derived` was last written.

    Rewriting the derived file adopts whatever the sources say at that moment, so a
    fresh paste always clears the flag.
    """
    log = read_source_log(job)
    stamp = stamp or asset_stamp(derived if derived.exists() else None)
    entry = log.get(key) if isinstance(log.get(key), dict) else {}
    if entry.get("stamp") != stamp:
        # The derived file was just rewritten, so it matches its sources by definition.
        log[key] = {"stamp": stamp, "source_sha": source_sha, "v": SOURCE_LOG_VERSION, "stale": False}
        write_json(job.path / "source-log.json", log)
        return False
    if entry.get("v") != SOURCE_LOG_VERSION:
        # A tool-template change moved the fingerprint, so the old hash cannot be
        # compared. Carry the verdict we already recorded, and for a stale one leave
        # the hash empty so it stays stale until the derived file is rewritten.
        carried = bool(entry.get("stale"))
        log[key] = {
            "stamp": stamp,
            "source_sha": "" if carried else source_sha,
            "v": SOURCE_LOG_VERSION,
            "stale": carried,
        }
        write_json(job.path / "source-log.json", log)
        return carried
    stale = entry.get("source_sha") != source_sha
    if entry.get("stale") != stale:
        entry["stale"] = stale
        log[key] = entry
        write_json(job.path / "source-log.json", log)
    return stale


def brand_bible_source_fingerprint(brief: dict, rules: dict) -> str:
    """Hash the prompt itself, so nothing that reaches the model is left out."""
    return text_fingerprint(brand_bible_prompt(brief, rules))


def script_source_fingerprint(brief: dict, brand_bible: str) -> str:
    return text_fingerprint(script_prompt(brief, brand_bible))


def shot_list_source_fingerprint(brief: dict, script: dict, rules: dict, brand_bible: str) -> str:
    return text_fingerprint(shot_list_prompt(brief, script, rules, brand_bible))


def track_shot_assets(job: Job, shots: list, brief: dict, rules: dict) -> dict:
    """Report missing and stale stills/clips, remembering what each asset was made from.

    A file that appears or changes on disk is taken to match the definition current
    at that moment; if the definition changes afterwards the asset becomes stale.
    """
    log_path = job.path / "asset-log.json"
    log = {}
    if log_path.exists():
        try:
            loaded = read_json(log_path)
            log = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            log = {}

    result = {"missing_stills": [], "stale_stills": [], "missing_clips": [], "stale_clips": []}
    for shot in shots:
        shot_id = str(shot.get("id") or "")
        record = log.get(shot_id) if isinstance(log.get(shot_id), dict) else {}
        still = checked_asset(job.stills_dir, shot_id, IMAGE_SUFFIXES, "image")
        still_stamp = content_identity(still) if still else ""
        for kind, directory, suffixes, fingerprint in (
            ("still", job.stills_dir, IMAGE_SUFFIXES, shot_image_fingerprint(shot, brief, rules)),
            ("clip", job.clips_dir, CLIP_SUFFIXES, shot_motion_fingerprint(shot, brief, still_stamp)),
        ):
            asset = checked_asset(directory, shot_id, suffixes, "image" if kind == "still" else "clip")
            if not asset:
                result["missing_" + kind + "s"].append(shot_id)
                record.pop(kind, None)
                continue
            stamp = content_identity(asset)
            entry = record.get(kind) if isinstance(record.get(kind), dict) else {}
            if entry.get("asset") != stamp or entry.get("v") != ASSET_LOG_VERSION:
                # New asset, or a record written before the current fingerprint scheme:
                # adopt what is on disk instead of raising a false alarm.
                record[kind] = {"asset": stamp, "sha": fingerprint, "v": ASSET_LOG_VERSION}
            elif entry.get("sha") != fingerprint:
                result["stale_" + kind + "s"].append(shot_id)
        log[shot_id] = record
    write_json(log_path, log)
    return result


def export_problem(final_file: Path, brief: dict) -> str:
    """Reject an export that is broken, too short, or the wrong shape for the brief."""
    probe = shutil.which("ffprobe")
    if not probe:
        return "ตรวจไฟล์ไม่ได้เพราะเครื่องนี้ไม่มี ffprobe ให้ติดตั้ง ffmpeg ก่อน (brew install ffmpeg)"
    command = [
        probe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,duration",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(final_file),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return f"อ่านไฟล์ไม่ได้: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'ffprobe ล้มเหลว'}"
    audio = subprocess.run(
        [probe, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(final_file)],
        capture_output=True, text=True,
    )
    audio_values = [line.strip() for line in audio.stdout.splitlines() if line.strip()]
    if audio.returncode != 0 or not audio_values:
        return "ไฟล์ไม่มีเสียง ต้อง export พร้อม voice-over และเพลงประกอบ"
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(values) < 4:
        return "ไม่พบวิดีโอสตรีมในไฟล์"
    width, height = as_float(values[1], 0), as_float(values[2], 0)
    video_seconds = as_float(values[3], 0) if len(values) > 4 else 0
    duration = as_float(values[-1], 0)
    if duration < 1:
        return f"ความยาวไฟล์ {duration:g} วินาที ดูเหมือน export ค้าง"
    audio_seconds = as_float(audio_values[-1], 0)
    if duration and audio_seconds and duration - audio_seconds > max(1.5, duration * 0.1):
        return f"เสียงยาวแค่ {audio_seconds:g} วินาที จากคลิป {duration:g} วินาที คลิปเงียบเกือบทั้งเรื่อง"
    if duration and video_seconds and duration - video_seconds > max(1.5, duration * 0.1):
        return f"ภาพยาวแค่ {video_seconds:g} วินาที จากคลิป {duration:g} วินาที ภาพจบก่อนเสียง"
    target = as_float(brief.get("duration_sec"), 0)
    if target:
        tolerance = max(3.0, target * 0.1)
        if abs(duration - target) > tolerance:
            return f"ความยาว {duration:g} วินาที ไม่ตรงกับ brief {target:g} วินาที"
    wanted = str(brief.get("aspect_ratio") or "").strip()
    if wanted and width and height:
        ratio = parse_ratio(wanted)
        if not ratio:
            return f"อ่าน aspect_ratio ใน brief ไม่ออก: {wanted!r} ให้แก้เป็นรูปแบบ 9:16"
        want = ratio[0] / ratio[1]
        actual = width / height
        if abs(actual - want) / want > 0.02:
            return f"สัดส่วนภาพ {width:g}x{height:g} ไม่ตรงกับ brief {wanted}"
    return ""


def content_identity(path: Path) -> str:
    """Name, size and a digest of both ends — survives a copy that preserves mtime.

    Hashing whole clips on every sync would read hundreds of megabytes; head plus
    tail catches a re-render or a corrected ending, which is what actually happens.
    """
    window = 262144
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            head = handle.read(window)
            if size > window:
                handle.seek(max(size - window, window))
                tail = handle.read(window)
            else:
                tail = b""
    except OSError:
        return f"{path.name}:unreadable"
    digest = hashlib.sha1(head + tail).hexdigest()[:16]
    return f"{path.name}:{size}:{digest}"


def export_inputs_fingerprint(job: Job) -> str:
    """Everything a Premiere export is built from, by content rather than timestamp."""
    paths = [job.script_path, job.shot_list_path, job.brief_path, job.brand_bible_path]
    paths += matching_files(job.clips_dir, CLIP_SUFFIXES)
    paths += matching_files(job.voice_dir, AUDIO_SUFFIXES)
    return text_fingerprint("\n".join(sorted(content_identity(path) for path in paths if path.exists())))


def audio_extension(fields_config: dict) -> str:
    """File extension that matches what ElevenLabs will actually return."""
    fmt = str((fields_config.get("elevenlabs") or {}).get("output_format", "mp3_44100_128")).lower()
    suffix = AUDIO_FORMAT_SUFFIXES.get(fmt.split("_")[0])
    if not suffix:
        print(f"[warn] ไม่รู้จัก output_format `{fmt}` ตั้งชื่อไฟล์เป็น .mp3 ไปก่อน")
        return ".mp3"
    return suffix


def script_scene_count_problem(brief: dict, script: dict) -> str:
    wanted = int(as_float(brief.get("scene_count"), 0) or 0)
    actual = len(script.get("scenes", []))
    if wanted and actual != wanted:
        return f"สคริปต์มี {actual} ซีน แต่ brief ขอ {wanted} ซีน"
    return ""


def script_duration_problem(brief: dict, script: dict) -> str:
    """The delivered runtime has to match what the client asked for."""
    target = as_float(brief.get("duration_sec"), 0)
    if not target:
        return ""
    total = sum(as_float(scene.get("duration_sec"), 0) for scene in script.get("scenes", []))
    tolerance = max(2.0, target * 0.05)
    if abs(total - target) <= tolerance:
        return ""
    return f"เวลารวมของสคริปต์ {total:g} วินาที ไม่ตรงกับ brief {target:g} วินาที (คลาดได้ {tolerance:g} วินาที)"


def previous_created_at(manifest_path: Path) -> str:
    """The manifest is our own output; a truncated one must not wedge every later sync."""
    if manifest_path.exists():
        try:
            payload = read_json(manifest_path)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict) and payload.get("created_at"):
            return str(payload["created_at"])
    return datetime.now().isoformat(timespec="seconds")


def sync_job(job: Job, fields_config: dict, fields_path: str = "") -> dict:
    brief = job.brief
    if not brief:
        raise SystemExit(f"ไม่พบ brief.json ใน {job.path}")

    rules = fields_config.get("visual_rules", {})
    stages = {}
    actions = []

    for directory in [job.stills_dir, job.clips_dir, job.voice_dir, job.final_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    stages["intake"] = "done"

    # --- brand bible ---
    write_text(job.path / "01-brand-bible-prompt.md", brand_bible_prompt(brief, rules))
    brand_bible = job.brand_bible_path.read_text(encoding="utf-8") if job.brand_bible_path.exists() else ""
    bible_stale = has_content(job.brand_bible_path) and derived_is_stale(
        job, "brand_bible", job.brand_bible_path, brand_bible_source_fingerprint(brief, rules)
    )
    if has_content(job.brand_bible_path) and not bible_stale:
        stages["brand_bible"] = "done"
    elif bible_stale:
        stages["brand_bible"] = "ready"
        actions.append("brief ถูกแก้หลังทำ brand bible ให้รัน prompt ใน `01-brand-bible-prompt.md` ใหม่ก่อน")
    else:
        stages["brand_bible"] = "ready"
        actions.append("รัน prompt ใน `01-brand-bible-prompt.md` แล้วบันทึกผลเป็น `brand-bible.md`")

    # --- script ---
    write_text(job.path / "02-script-prompt.md", script_prompt(brief, brand_bible))
    script = job.load_stage_json(job.script_path, "scenes")
    if script:
        runtime_problem = script_duration_problem(brief, script) or script_scene_count_problem(brief, script)
        script_stale = derived_is_stale(job, "script", job.script_path, script_source_fingerprint(brief, brand_bible))
        bible_ready = stages["brand_bible"] == "done"
        if not bible_ready:
            # Regenerating now would embed the Brand Bible that is about to change.
            stages["script"] = "waiting"
        elif runtime_problem or script_stale:
            stages["script"] = "ready"
        else:
            stages["script"] = "done"
        if runtime_problem and bible_ready:
            actions.append(f"แก้ `script.json` หรือปรับ `brief.json`: {runtime_problem}")
        if script_stale and bible_ready:
            actions.append("brief หรือ brand bible ถูกแก้หลังเขียนสคริปต์ ให้รัน prompt ใน `02-script-prompt.md` ใหม่")
    else:
        stages["script"] = "ready" if stages["brand_bible"] == "done" else "waiting"
        if stages["script"] == "ready":
            actions.append("รัน prompt ใน `02-script-prompt.md` แล้วบันทึกผลเป็น `script.json`")

    # --- shot list ---
    if script:
        write_text(job.path / "03-shot-list-prompt.md", shot_list_prompt(brief, script, rules, brand_bible))
    shot_list = job.load_stage_json(job.shot_list_path, "shots")
    shots = shot_list.get("shots", []) if shot_list else []
    script_ok = stages["script"] == "done"
    problems = shot_list_problems(script, shots)
    shot_list_sources = shot_list_source_fingerprint(brief, script, rules, brand_bible) if script else ""
    if shots and script_ok and derived_is_stale(job, "shot_list", job.shot_list_path, shot_list_sources):
        problems.append("สคริปต์ถูกแก้หลังจากสร้าง shot list ต้องรัน prompt 03 ใหม่")
    if shots and script_ok and not problems:
        stages["shot_list"] = "done"
    elif shots and not script_ok:
        # Fixing the script can change these scenes, so do not send anyone into paid work yet.
        stages["shot_list"] = "waiting"
        actions.append("`script.json` ยังไม่ผ่าน ต้องแก้ให้เรียบร้อยก่อนถึงจะเริ่มทำภาพตาม `shot-list.json`")
    elif shots:
        stages["shot_list"] = "ready"
        for problem in problems:
            actions.append(f"แก้ `shot-list.json`: {problem}")
    elif script_ok:
        stages["shot_list"] = "ready"
        actions.append("รัน prompt ใน `03-shot-list-prompt.md` แล้วบันทึกผลเป็น `shot-list.json`")
    elif script:
        stages["shot_list"] = "waiting"
    else:
        stages["shot_list"] = "blocked"

    # --- stills + animate prompts ---
    # Prompts are free, so they are always written; only the stages wait for a clean shot list.
    if shots and stages["shot_list"] == "done":
        image_dir = job.path / "04-image-prompts"
        flow_dir = job.path / "05-flow-prompts"
        current_ids = {str(shot.get("id") or "").strip() or "sh-xx" for shot in shots}
        for folder in (image_dir, flow_dir):
            for stale_prompt in folder.glob("*.txt"):
                if stale_prompt.stem not in current_ids:
                    stale_prompt.unlink()
                    print(f"[note] ลบ `{folder.name}/{stale_prompt.name}` เพราะช็อตนี้ไม่มีใน shot list แล้ว")
        image_prompts = {}
        flow_prompts = {}
        for shot in shots:
            shot_id = str(shot.get("id") or "").strip() or "sh-xx"
            still = checked_asset(job.stills_dir, shot_id, IMAGE_SUFFIXES, "image")
            image_prompts[shot_id] = compose_image_prompt(shot, brief, rules)
            flow_prompts[shot_id] = compose_flow_prompt(shot, brief, still.name if still else f"{shot_id}.png")
            write_text(image_dir / f"{shot_id}.txt", image_prompts[shot_id])
            write_text(flow_dir / f"{shot_id}.txt", flow_prompts[shot_id])
        write_text(image_dir / "README.md", prompt_sheet(shots, image_prompts, "stills", "png", "Prompt ภาพนิ่งทั้งหมด"))
        write_text(flow_dir / "README.md", prompt_sheet(shots, flow_prompts, "clips", "mp4", "Prompt สำหรับ Google Flow ทั้งหมด"))

        tracked = track_shot_assets(job, shots, brief, rules)
        short_clips = []
        for shot in shots:
            shot_id = str(shot.get("id") or "")
            planned = as_float(shot.get("duration_sec"), 0)
            clip = checked_asset(job.clips_dir, shot_id, CLIP_SUFFIXES, "clip")
            if not clip or planned <= 0:
                continue
            actual = media_duration(clip)
            if actual and planned - actual > max(0.5, planned * 0.1):
                short_clips.append((shot_id, planned - actual))
        stills_pending = tracked["missing_stills"] + tracked["stale_stills"]
        clips_pending = tracked["missing_clips"] + tracked["stale_clips"] + [item[0] for item in short_clips]
        stages["stills"] = "done" if not stills_pending else "ready"
        stages["animate"] = "done" if not clips_pending else ("ready" if not stills_pending else "waiting")
        for kind, label, pending, stale in (
            ("stills", "สร้างภาพนิ่ง", stills_pending, tracked["stale_stills"]),
            ("clips", "animate ใน Google Flow", clips_pending, tracked["stale_clips"]),
        ):
            if not pending:
                continue
            if stale:
                print(f"[note] {kind} ของช็อต {', '.join(stale)} ทำมาจาก shot list เวอร์ชันเก่า ต้องทำใหม่")
            if kind == "clips" and short_clips:
                for shot_id, missing_seconds in short_clips:
                    print(f"[note] clips/{shot_id} สั้นกว่าช็อตอยู่ {missing_seconds:.1f} วินาที ต้อง animate ใหม่ให้ครบ")
            if kind == "stills" or stages["animate"] == "ready":
                folder = "04-image-prompts" if kind == "stills" else "05-flow-prompts"
                actions.append(f"{label} {len(pending)} ช็อตที่ยังไม่พร้อม แล้ววางใน `{kind}/` (ดู `{folder}/`)")
    else:
        stages["stills"] = "blocked"
        stages["animate"] = "blocked"

    # --- voiceover ---
    scenes = script.get("scenes", []) if script else []
    if scenes and not script_ok:
        write_voice_lines(job, brief, scenes, fields_config)
        stages["voiceover"] = "waiting"
    elif scenes:
        write_voice_lines(job, brief, scenes, fields_config)
        voiced = [s for s in scenes if str(s.get("vo") or "").strip()]
        render_log = read_render_log(job.voice_dir)
        voice_sha = voice_fingerprint(fields_config, job.voice_dir)
        raw_bps = raw_bytes_per_second(fields_config)
        voice_assets = {
            str(s.get("id", "")): checked_asset(job.voice_dir, str(s.get("id", "")), AUDIO_SUFFIXES, "audio", raw_bps)
            for s in voiced
        }
        mismatched = [
            (s, voice_duration_problem(s, voice_assets[str(s.get("id", ""))], raw_bps))
            for s in voiced
        ]
        mismatched = [(s, problem) for s, problem in mismatched if problem]
        stale_vo = [s for s in voiced if voice_assets[str(s.get("id", ""))] and voice_is_stale(s, render_log, voice_assets[str(s.get("id", ""))], voice_sha)]
        missing_vo = [
            s
            for s in voiced
            if not voice_assets[str(s.get("id", ""))] or voice_is_stale(s, render_log, voice_assets[str(s.get("id", ""))], voice_sha)
        ]
        stages["voiceover"] = "done" if not (missing_vo or mismatched) else "ready"
        for scene, problem in mismatched:
            actions.append(
                f"เสียงของ {scene.get('id')} {problem} "
                f"ให้แก้บทหรือปรับ duration_sec ของซีนให้ตรงกัน"
            )
        if stale_vo:
            print(f"[note] {len(stale_vo)} ซีนมีเสียงเก่าที่อัดจากสคริปต์คนละเวอร์ชัน ต้องอัดใหม่: {', '.join(str(s.get('id')) for s in stale_vo)}")
        if missing_vo:
            fields_flag = f' --fields "{fields_path}"' if fields_path and Path(fields_path) != DEFAULT_FIELDS else ""
            actions.append(
                f'อัดเสียง {len(missing_vo)} ซีนที่ยังขาด: '
                f'`python3 scripts/generate_voiceover.py "{job.path}"{fields_flag} --execute`'
            )
    else:
        stages["voiceover"] = "blocked"

    # --- edit ---
    if shots and scenes:
        write_assembly_sheet(job, brief, script, shots, raw_bytes_per_second(fields_config))
        write_text(job.path / "06-edit-notes.md", edit_notes(brief, script, shots))
        exports = matching_files(job.final_dir, FINAL_SUFFIXES)
        chosen = str(brief.get("final_file") or "").strip()
        final_file = None
        ambiguous = ""
        if chosen:
            final_file = next((item for item in exports if item.name == chosen), None)
            if not final_file:
                ambiguous = f"brief ระบุ final_file `{chosen}` แต่ไม่มีไฟล์นั้นใน `final/`"
        elif len(exports) > 1:
            # mtime cannot be trusted as a revision order once files are copied around.
            ambiguous = (
                f"มีไฟล์ใน `final/` {len(exports)} ไฟล์ ({', '.join(item.name for item in exports)}) "
                f"ให้เหลือไฟล์เดียว หรือระบุ `final_file` ใน `brief.json`"
            )
        elif exports:
            final_file = exports[0]
        if ambiguous:
            print(f"[note] {ambiguous}")
            actions.append(ambiguous)
        ready_to_cut = (
            stages["script"] == "done"
            and stages["shot_list"] == "done"
            and stages["stills"] == "done"
            and stages["animate"] == "done"
            and stages["voiceover"] == "done"
        )
        stale_export = bool(final_file) and derived_is_stale(
            job, "final", final_file, export_inputs_fingerprint(job), content_digest(final_file)
        )
        broken_export = export_problem(final_file, brief) if (final_file and not stale_export) else ""
        if broken_export:
            print(f"[note] `final/{final_file.name}` {broken_export} ต้อง export ใหม่")
            actions.append(f"ไฟล์ `final/{final_file.name}` ใช้ไม่ได้: {broken_export}")
        if final_file and ready_to_cut and not stale_export and not broken_export and not ambiguous:
            stages["edit"] = "done"
        elif ready_to_cut:
            stages["edit"] = "ready"
        else:
            stages["edit"] = "waiting"
        if stale_export:
            print(f"[note] `final/{final_file.name}` เก่ากว่าสคริปต์หรือไฟล์ที่ใช้ตัด ต้อง export ใหม่ก่อนส่งรีวิว")
        if stages["edit"] == "ready":
            actions.append("ตัดใน Premiere Pro ตาม `06-assembly-sheet.csv` แล้ว export ลง `final/`")
    else:
        stages["edit"] = "blocked"
        final_file = None

    # --- review ---
    if final_file and stages["edit"] == "done":
        write_text(job.path / "07-review-packet.md", review_packet(job, brief, script, shots, final_file))
        stages["review"] = "ready"
        actions.append("ส่ง `07-review-packet.md` + ไฟล์ใน `final/` ให้ลูกค้ารีวิว")
    else:
        stages["review"] = "blocked"
        packet = job.path / "07-review-packet.md"
        if packet.exists():
            packet.unlink()
            print("[note] ลบ `07-review-packet.md` เดิมทิ้ง เพราะยังส่งรีวิวไม่ได้แล้ว")

    manifest = {
        "job_id": job.path.name,
        "client_name": brief.get("client_name", ""),
        "created_at": previous_created_at(job.manifest_path),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "stages": stages,
        "next_actions": actions,
    }
    write_json(job.manifest_path, manifest)
    return manifest


def prompt_sheet(shots: list, prompts: dict, folder: str, suffix: str, title: str) -> str:
    """One file with every prompt in order, so a long shot list is one pass of work."""
    lines = [f"# {title}", "", f"ทั้งหมด {len(shots)} ช็อต ทำตามลำดับแล้ววางไฟล์ใน `{folder}/`", ""]
    lines.append("## เช็กลิสต์")
    lines.append("")
    for shot in shots:
        shot_id = str(shot.get("id", ""))
        lines.append(f"- [ ] `{folder}/{shot_id}.{suffix}` — {shot.get('description', '')}")
    lines.append("")
    for shot in shots:
        shot_id = str(shot.get("id", ""))
        lines.extend(["---", "", f"## {shot_id}", "", "```text", prompts.get(shot_id, ""), "```", ""])
    return "\n".join(lines)


def write_voice_lines(job: Job, brief: dict, scenes: list, fields_config: dict) -> None:
    path = job.voice_dir / "lines.csv"
    render_log = read_render_log(job.voice_dir)
    fields = ["scene_id", "beat", "duration_sec", "vo_text", "output_file", "status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for scene in scenes:
            scene_id = str(scene.get("id") or "").strip() or "sc-xx"
            vo_text = str(scene.get("vo") or "").strip()
            existing = checked_asset(job.voice_dir, scene_id, AUDIO_SUFFIXES, "audio", raw_bytes_per_second(fields_config))
            if not vo_text:
                status = "no-vo"
            elif not existing:
                status = "todo"
            else:
                status = "stale" if voice_is_stale(scene, render_log, existing, voice_fingerprint(fields_config, job.voice_dir)) else "done"
            writer.writerow(
                {
                    "scene_id": scene_id,
                    "beat": scene.get("beat", ""),
                    "duration_sec": scene.get("duration_sec", ""),
                    "vo_text": vo_text,
                    # Always the synthesis target, never an existing .wav: writing MP3
                    # bytes into a .wav name would break decoders downstream.
                    "output_file": f"{scene_id}{audio_extension(fields_config)}",
                    "status": status,
                }
            )


def write_assembly_sheet(job: Job, brief: dict, script: dict, shots: list, raw_bps: int = 0) -> None:
    scenes = {str(scene.get("id")): scene for scene in script.get("scenes", [])}
    path = job.path / "06-assembly-sheet.csv"
    fields = [
        "order",
        "shot_id",
        "scene_id",
        "beat",
        "duration_sec",
        "still_file",
        "clip_file",
        "voice_file",
        "on_screen_text",
        "camera_move",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        scene_order = {str(scene.get("id")): position for position, scene in enumerate(script.get("scenes", []))}
        ordered = sorted(
            enumerate(shots),
            key=lambda pair: (scene_order.get(str(pair[1].get("scene_id") or ""), len(scene_order)), pair[0]),
        )
        voiced_rows = set()
        for index, (_, shot) in enumerate(ordered, start=1):
            shot_id = str(shot.get("id") or "")
            scene_id = str(shot.get("scene_id") or "")
            scene = scenes.get(scene_id, {})
            still = checked_asset(job.stills_dir, shot_id, IMAGE_SUFFIXES, "image")
            clip = checked_asset(job.clips_dir, shot_id, CLIP_SUFFIXES, "clip")
            voice = checked_asset(job.voice_dir, scene_id, AUDIO_SUFFIXES, "audio", raw_bps)
            silent = not str(scene.get("vo") or "").strip()
            first_of_scene = scene_id not in voiced_rows
            voiced_rows.add(scene_id)
            writer.writerow(
                {
                    "order": index,
                    "shot_id": shot_id,
                    "scene_id": scene_id,
                    "beat": scene.get("beat", ""),
                    "duration_sec": shot.get("duration_sec", ""),
                    "still_file": f"stills/{still.name}" if still else "MISSING",
                    "clip_file": f"clips/{clip.name}" if clip else "MISSING",
                    # A cleared `vo` wins over any audio left behind by an earlier take,
                    # and the narration is placed once, on the scene's first shot.
                    "voice_file": (
                        "no-vo" if silent
                        else "" if not first_of_scene
                        else f"voiceover/{voice.name}" if voice
                        else "MISSING"
                    ),
                    "on_screen_text": (
                        str(scene.get("on_screen_text") or "").replace("\n", " ") if wants_subtitles(brief) else ""
                    ),
                    "camera_move": shot.get("camera_move", ""),
                }
            )


def edit_notes(brief: dict, script: dict, shots: list) -> str:
    total = sum(as_float(shot.get("duration_sec"), 0) for shot in shots)
    return "\n".join(
        [
            "# 06 Premiere Pro Edit Notes",
            "",
            f"ลูกค้า: {brief.get('client_name', '-')}",
            f"ความยาวเป้าหมาย: {brief.get('duration_sec', '-')} วินาที | รวมจาก shot list: {total:.0f} วินาที",
            f"สัดส่วน: {brief.get('aspect_ratio', '9:16')} | แพลตฟอร์ม: {brief.get('platform', 'TikTok')}",
            "",
            "## ลำดับงาน",
            "",
            "1. import โฟลเดอร์ `clips/` และ `voiceover/` เข้า Premiere",
            "2. เรียงคลิปตามคอลัมน์ `order` ใน `06-assembly-sheet.csv`",
            "3. วาง voice-over ของแต่ละซีนให้ตรงกับช็อตแรกของซีนนั้น",
            "4. ตัดความยาวคลิปให้ตรงกับ `duration_sec`",
            "5. ใส่ subtitle จากคอลัมน์ `on_screen_text` ไม่เกิน 2 บรรทัด"
            if wants_subtitles(brief)
            else "5. ไม่ใส่ subtitle และไม่ใส่ตัวหนังสือใด ๆ บนภาพ ตามที่ตกลงกับลูกค้า",
            "6. ใส่เพลงประกอบระดับ -18 dB และ duck ตอนมีเสียงพูด",
            f"7. export ลงโฟลเดอร์ `final/` ชื่อ `{slugify(str(brief.get('client_name', 'client')))}-v1.mp4`",
            "",
            "## ข้อควรระวัง",
            "",
            bullet_list(
                [
                    str(brief.get("avoid", "")).strip(),
                    "ตรวจว่าคำเคลมในเสียงพูดตรงกับที่ลูกค้าอนุมัติ",
                    "ตรวจว่าไม่มี watermark หรือตัวหนังสือหลุดจาก AI",
                    f"CTA ปิดท้าย: {script.get('cta', '-')}",
                ]
            ),
        ]
    )


def review_packet(job: Job, brief: dict, script: dict, shots: list, final_file: Path) -> str:
    return "\n".join(
        [
            f"# Review Packet: {brief.get('client_name', '-')}",
            "",
            f"Job: `{job.path.name}`",
            f"ไฟล์ที่ส่งรีวิว: `final/{final_file.name}`",
            f"ความยาวเป้าหมาย: {brief.get('duration_sec', '-')} วินาที | สัดส่วน: {brief.get('aspect_ratio', '9:16')}",
            f"รอบแก้ที่ตกลงไว้: {brief.get('revision_rounds', 2)}",
            "",
            "## สิ่งที่ทำตาม brief",
            "",
            bullet_list(
                [
                    f"เป้าหมาย: {brief.get('goal', '-')}",
                    f"กลุ่มเป้าหมาย: {brief.get('audience', '-')}",
                    f"ต้องมี: {brief.get('must_include', '-')}",
                    f"CTA: {script.get('cta', '-')}",
                    f"จำนวนช็อต: {len(shots)}",
                ]
            ),
            "",
            "## ขอให้ลูกค้าเช็ก",
            "",
            "- [ ] ชื่อแบรนด์ ชื่อสินค้า และการออกเสียงถูกต้อง",
            "- [ ] ตัวเลข ราคา และโปรโมชันตรงกับที่ใช้จริง",
            "- [ ] คำเคลมเกี่ยวกับผลลัพธ์อยู่ในระดับที่ยอมรับได้",
            "- [ ] โลโก้และสีแบรนด์ถูกต้อง",
            "- [ ] CTA ปลายทางถูกต้อง",
            "",
            "## วิธีส่งฟีดแบ็ก",
            "",
            "ระบุเป็น timecode เช่น `0:07 เปลี่ยนคำว่า X เป็น Y` เพื่อให้แก้ได้ในรอบเดียว",
        ]
    )


# ----------------------------------------------------------------- commands


def archive_derived(job: Job) -> list:
    """Move everything produced from the previous brief into archive-<timestamp>/.

    A forced re-intake must never leave an old Brand Bible, script, or final cut
    in place, or `sync` would mark those stages done and build a review packet
    that mixes the new brief with the previous deliverable.
    """
    if not job.path.exists():
        return []
    items = [
        item
        for item in sorted(job.path.iterdir())
        if item.name != job.brief_path.name and not item.name.startswith("archive-")
    ]
    if not items:
        return []
    # The old brief stays in place for cmd_new to overwrite, but the archive keeps a
    # copy so the archived work can still be audited against what was asked for.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = job.path / f"archive-{stamp}"
    counter = 2
    while target.exists():
        target = job.path / f"archive-{stamp}-{counter}"
        counter += 1
    target.mkdir()
    moved = []
    for item in items:
        item.rename(target / item.name)
        moved.append(item.name)
    if job.brief_path.exists():
        shutil.copy2(job.brief_path, target / job.brief_path.name)
        moved.append(f"{job.brief_path.name} (คัดลอก)")
    return moved


def resolve_new_job_path(jobs_root: str, job_id: str) -> Path:
    """A job id names one folder inside the jobs root — never a path elsewhere.

    `--force` archives everything in the target folder, so a stray `..` or absolute
    path could rearrange an unrelated directory.
    """
    if job_id != Path(job_id).name or job_id in {"", ".", ".."}:
        raise SystemExit(f"--job-id ต้องเป็นชื่อโฟลเดอร์เดียว ห้ามมี / หรือ .. : {job_id}")
    root = Path(jobs_root).expanduser().resolve()
    candidate = (root / job_id).resolve()
    if candidate != root and root not in candidate.parents:
        raise SystemExit(f"--job-id ต้องอยู่ใต้ {root}")
    return candidate


def cmd_new(args: argparse.Namespace) -> None:
    fields_config = read_json(Path(args.fields))
    defaults = fields_config.get("defaults", {})
    overrides = parse_overrides(args.field)

    if args.brief:
        mapped = read_json(Path(args.brief))
    elif args.responses:
        rows = read_responses(args.responses)
        row = select_response(rows, args.row, args.match)
        mapped = map_response(row, fields_config.get("field_keywords", {}))
    else:
        mapped = {}
        if not overrides:
            raise SystemExit("ต้องระบุ --responses, --brief หรือ --field อย่างน้อยหนึ่งอย่าง")

    brief = build_brief(mapped, defaults, overrides)
    job_id = args.job_id or f"{args.date}-{slugify(str(brief.get('client_name', '')))}"
    job_path = resolve_new_job_path(args.jobs, job_id)
    if job_path.exists() and not args.force:
        raise SystemExit(f"มีงานนี้อยู่แล้ว: {job_path} (ใช้ --force เพื่อรับ brief ใหม่ ของเดิมจะถูกย้ายเข้า archive)")
    job_path.mkdir(parents=True, exist_ok=True)

    job = Job(job_path)
    if args.force:
        moved = archive_derived(job)
        if moved:
            print(f"ย้ายงานเดิม {len(moved)} รายการเข้า archive แล้ว: {', '.join(moved)}")
    write_json(job.brief_path, brief)
    manifest = sync_job(job, fields_config, args.fields)
    print(f"สร้างงานใหม่: {job_path}")
    print_status(manifest)


def cmd_sync(args: argparse.Namespace) -> None:
    fields_config = read_json(Path(args.fields))
    job = Job(resolve_job(args.jobs, args.job_id))
    manifest = sync_job(job, fields_config, args.fields)
    print(f"อัปเดตงาน: {job.path}")
    print_status(manifest)


def cmd_status(args: argparse.Namespace) -> None:
    job_path = resolve_job(args.jobs, args.job_id)
    manifest_path = job_path / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"ยังไม่มี manifest.json ใน {job_path} ให้รัน sync ก่อน")
    print(f"งาน: {job_path}")
    print_status(read_json(manifest_path))


def cmd_list(args: argparse.Namespace) -> None:
    root = Path(args.jobs)
    if not root.exists():
        print(f"ยังไม่มีโฟลเดอร์งาน: {root}")
        return
    for item in sorted(root.iterdir()):
        manifest_path = item / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = read_json(manifest_path)
        except json.JSONDecodeError:
            print(f"{item.name:<40} (manifest.json เสีย ให้รัน sync ใหม่)")
            continue
        stages = manifest.get("stages", {}) if isinstance(manifest, dict) else {}
        done = sum(1 for stage in STAGES if stages.get(stage) == "done")
        print(f"{item.name:<40} {done}/{len(STAGES)} stages  {manifest.get('client_name', '')}")


def resolve_job(jobs_root: str, job_id: str) -> Path:
    """A bare id resolves under --jobs first; only an explicit path is taken as one."""
    looks_like_path = job_id != Path(job_id).name
    if not looks_like_path:
        candidate = Path(jobs_root) / job_id
        if candidate.is_dir():
            return candidate
    path = Path(job_id).expanduser()
    if path.is_dir():
        return path
    raise SystemExit(f"ไม่พบงาน: {job_id}")


def print_status(manifest: dict) -> None:
    stages = manifest.get("stages", {})
    print()
    for stage in STAGES:
        state = stages.get(stage, "blocked")
        marker = {"done": "[x]", "ready": "[>]", "waiting": "[.]", "blocked": "[ ]"}.get(state, "[ ]")
        print(f"{marker} {stage:<12} {STAGE_LABELS.get(stage, '')} ({state})")
    actions = manifest.get("next_actions", [])
    if actions:
        print()
        print("ต้องทำต่อ:")
        for action in actions:
            print(f"- {action}")


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Form -> Brand Bible -> Script -> Shot List -> Flow -> ElevenLabs -> Premiere -> Review")
    parser.add_argument("--fields", default=str(DEFAULT_FIELDS), help="ไฟล์ mapping ของ Google Form.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="โฟลเดอร์เก็บงานลูกค้า (ชี้ไปที่โฟลเดอร์ Google Drive ได้).")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="สร้างงานใหม่จากคำตอบ Google Form")
    new.add_argument("--responses", default="", help="ไฟล์ CSV ที่ export จาก Google Form หรือ URL แบบ publish CSV.")
    new.add_argument("--brief", default="", help="ใช้ไฟล์ brief JSON ที่มีอยู่แล้วแทนฟอร์ม.")
    new.add_argument("--row", type=int, default=-1, help="แถวที่ต้องการ (ค่าเริ่มต้น -1 คือแถวล่าสุด).")
    new.add_argument("--match", default="", help="เลือกแถวที่มีข้อความนี้ เช่น ชื่อลูกค้าหรืออีเมล.")
    new.add_argument("--field", action="append", default=[], help="แก้ค่าใน brief แบบ key=value ใส่ได้หลายครั้ง.")
    new.add_argument("--job-id", default="", help="กำหนดชื่อโฟลเดอร์งานเอง.")
    new.add_argument("--date", default=date.today().isoformat(), help="วันที่รับงาน YYYY-MM-DD.")
    new.add_argument("--force", action="store_true", help="เขียนทับงานเดิมที่ชื่อซ้ำ.")
    new.set_defaults(func=cmd_new)

    sync = sub.add_parser("sync", help="อ่านไฟล์ที่มีอยู่แล้วสร้างขั้นถัดไปให้อัตโนมัติ")
    sync.add_argument("job_id", help="ชื่อโฟลเดอร์งาน หรือ path เต็ม.")
    sync.set_defaults(func=cmd_sync)

    status = sub.add_parser("status", help="ดูสถานะงาน")
    status.add_argument("job_id")
    status.set_defaults(func=cmd_status)

    listing = sub.add_parser("list", help="ดูงานทั้งหมด")
    listing.set_defaults(func=cmd_list)

    return parser.parse_args(argv)


def main(argv: "list | None" = None) -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
