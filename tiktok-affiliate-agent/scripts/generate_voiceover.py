#!/usr/bin/env python3
"""Render ElevenLabs voice-over for every scene listed in a job's voiceover/lines.csv."""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIELDS = ROOT / "data" / "client_intake_fields.json"
DEFAULT_JOBS = ROOT / "outputs" / "clients"
API_BASE = "https://api.elevenlabs.io/v1/text-to-speech"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def resolve_job(jobs_root: str, job_id: str) -> Path:
    """A bare id resolves under --jobs first; only an explicit path is taken as one."""
    if job_id == Path(job_id).name:
        candidate = Path(jobs_root) / job_id
        if candidate.is_dir():
            return candidate
    path = Path(job_id).expanduser()
    if path.is_dir():
        return path
    raise SystemExit(f"ไม่พบงาน: {job_id}")


AUDIO_SUFFIXES = [".mp3", ".wav", ".m4a", ".ulaw", ".opus", ".pcm", ".alaw"]
AUDIO_FORMAT_SUFFIXES = {"mp3": ".mp3", "pcm": ".pcm", "ulaw": ".ulaw", "alaw": ".alaw", "opus": ".opus"}


def audio_extension(settings: dict) -> str:
    """Name the file after what the API will actually return, or refuse to spend credits."""
    fmt = str(settings.get("output_format", "mp3_44100_128")).lower()
    suffix = AUDIO_FORMAT_SUFFIXES.get(fmt.split("_")[0])
    if not suffix:
        raise SystemExit(
            f"ไม่รองรับ output_format `{fmt}` ใน data/client_intake_fields.json "
            f"ที่รองรับคือ {', '.join(sorted(AUDIO_FORMAT_SUFFIXES))}"
        )
    return suffix


def text_fingerprint(text: str) -> str:
    return hashlib.sha1(str(text or "").strip().encode("utf-8")).hexdigest()[:12]


def voice_fingerprint(voice_id: str, settings: dict) -> str:
    """Voice and synthesis settings, so switching them retires the old takes."""
    parts = [
        f"voice={voice_id}",
        f"model={settings.get('model_id', 'eleven_multilingual_v2')}",
        f"stability={settings.get('stability', 0.45)}",
        f"similarity={settings.get('similarity_boost', 0.75)}",
        f"style={settings.get('style', 0.0)}",
        f"format={settings.get('output_format', 'mp3_44100_128')}",
    ]
    return text_fingerprint("|".join(parts))


def read_voice_override(voice_dir: Path) -> str:
    """The voice this job was rendered with, so a plain rerun keeps using it."""
    path = voice_dir / "settings.json"
    if not path.exists():
        return ""
    try:
        with path.open("r", encoding="utf-8") as handle:
            saved = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return ""
    return str(saved.get("voice_id") or "").strip() if isinstance(saved, dict) else ""


def write_voice_override(voice_dir: Path, voice_id: str) -> None:
    """Remember only an explicit `--voice-id`, so `sync` stops undoing it.

    Model, stability and format stay in the shared config on purpose: changing them
    there must still retire the takes rendered with the old values.
    """
    write_json_atomic(voice_dir / "settings.json", {"voice_id": voice_id})


def read_render_log(voice_dir: Path) -> dict:
    path = voice_dir / "rendered.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json_atomic(path: Path, payload: dict) -> None:
    """A truncated log reads as empty, which would quietly bless every old take."""
    staging = path.with_name(path.name + ".part")
    staging.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def write_render_log(voice_dir: Path, log: dict) -> None:
    write_json_atomic(voice_dir / "rendered.json", log)


def content_identity(asset: "Path | None") -> str:
    """Identity by bytes, so a manual take that reuses the filename is recognised."""
    if asset is None:
        return ""
    window = 262144
    try:
        size = asset.stat().st_size
        with asset.open("rb") as handle:
            head = handle.read(window)
            if size > window:
                handle.seek(max(size - window, window))
                tail = handle.read(window)
            else:
                tail = b""
    except OSError:
        return f"{asset.name}:unreadable"
    return f"{asset.name}:{size}:{hashlib.sha1(head + tail).hexdigest()[:16]}"


AUDIO_SIGNATURES = [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3", b"RIFF", b"ftyp", b"OggS"]
RAW_AUDIO_SUFFIXES = {".pcm", ".ulaw", ".alaw"}
MIN_AUDIO_BYTES = 512


def raw_bytes_per_second(settings: dict) -> int:
    fmt = str(settings.get("output_format", "")).lower()
    match = re.match(r"(pcm|ulaw|alaw)_(\d+)", fmt)
    if not match:
        return 0
    rate = int(match.group(2))
    return rate * 2 if match.group(1) == "pcm" else rate


def looks_like_audio(path: Path, settings: dict) -> bool:
    """Same bar the pipeline applies, so a take it rejected is re-recorded here.

    Without that agreement, `sync` reports a scene as missing while this command
    says it already exists, and the operator is stuck in the middle.
    """
    if path.stat().st_size < MIN_AUDIO_BYTES:
        return False
    if path.suffix.lower() in RAW_AUDIO_SUFFIXES:
        bps = raw_bytes_per_second(settings)
        return bps > 0 and path.stat().st_size >= bps * 0.5
    try:
        head = path.open("rb").read(16)
    except OSError:
        return False
    if not any(signature in head for signature in AUDIO_SIGNATURES):
        return False
    probe = shutil.which("ffprobe")
    if not probe:
        return False  # the pipeline will not trust it either
    result = subprocess.run(
        [probe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def find_existing_audio(directory: Path, stem: str, settings: dict) -> "Path | None":
    """Any usable recording counts, whatever its case or extension."""
    if not stem or not directory.exists():
        return None
    matches = [
        item
        for item in directory.iterdir()
        if item.is_file() and item.stem == stem and item.suffix.lower() in AUDIO_SUFFIXES
        and looks_like_audio(item, settings)
    ]
    if not matches:
        return None
    # Newest wins, same as the pipeline's asset lookup.
    return max(matches, key=lambda item: (item.stat().st_mtime_ns, item.name))


def read_lines(path: Path) -> list:
    if not path.exists():
        raise SystemExit(f"ไม่พบ {path} ให้รัน run_client_pipeline.py sync ก่อน")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def synthesize(text: str, voice_id: str, api_key: str, settings: dict, timeout: int) -> bytes:
    output_format = settings.get("output_format", "mp3_44100_128")
    url = f"{API_BASE}/{voice_id}?output_format={output_format}"
    payload = {
        "text": text,
        "model_id": settings.get("model_id", "eleven_multilingual_v2"),
        "voice_settings": {
            "stability": settings.get("stability", 0.45),
            "similarity_boost": settings.get("similarity_boost", 0.75),
            "style": settings.get("style", 0.0),
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed API host
        return response.read()


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="สร้างไฟล์เสียง voice-over ด้วย ElevenLabs จาก voiceover/lines.csv")
    parser.add_argument("job_id", help="ชื่อโฟลเดอร์งาน หรือ path เต็ม.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="โฟลเดอร์เก็บงานลูกค้า.")
    parser.add_argument("--fields", default=str(DEFAULT_FIELDS), help="ไฟล์ config ที่มีค่า ElevenLabs.")
    parser.add_argument("--voice-id", default="", help="ทับค่า ELEVENLABS_VOICE_ID.")
    parser.add_argument("--scene", default="", help="ทำเฉพาะซีนนี้ เช่น sc-02.")
    parser.add_argument("--execute", action="store_true", help="เรียก API จริง (ค่าเริ่มต้นคือ dry run).")
    parser.add_argument("--overwrite", action="store_true", help="อัดทับไฟล์เสียงที่มีอยู่แล้ว.")
    parser.add_argument("--timeout", type=int, default=120, help="วินาทีที่รอ API ต่อหนึ่งซีน.")
    return parser.parse_args(argv)


def main(argv: "list | None" = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    load_dotenv(ROOT / ".env")

    settings = {}
    fields_path = Path(args.fields)
    if fields_path.exists():
        with fields_path.open("r", encoding="utf-8") as handle:
            settings = json.load(handle).get("elevenlabs", {})

    job_path = resolve_job(args.jobs, args.job_id)
    voice_dir = job_path / "voiceover"
    rows = read_lines(voice_dir / "lines.csv")
    if args.scene:
        rows = [row for row in rows if row.get("scene_id") == args.scene]
        if not rows:
            raise SystemExit(f"ไม่พบซีน {args.scene} ใน lines.csv")

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = (
        args.voice_id.strip()
        or read_voice_override(voice_dir)
        or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    )

    render_log = read_render_log(voice_dir)
    pending = []
    for row in rows:
        scene_id = str(row.get("scene_id") or "").strip()
        text = str(row.get("vo_text") or "").strip()
        named = Path(str(row.get("output_file") or "").strip() or f"{scene_id or 'sc-xx'}.mp3").name
        output = voice_dir / (Path(named).stem + audio_extension(settings))
        if not text:
            print(f"[skip] {scene_id} ไม่มีข้อความพูด")
            continue
        existing = (
            find_existing_audio(voice_dir, scene_id, settings)
            or find_existing_audio(voice_dir, output.stem, settings)
        )
        record = render_log.get(scene_id) if isinstance(render_log.get(scene_id), dict) else {}
        # A manual take is not ours to call stale, even when it kept our filename.
        record_matches = not record.get("file") or (existing is not None and record["file"] == existing.name)
        if record_matches and record.get("stamp") and existing is not None:
            record_matches = record["stamp"] == content_identity(existing)
        voice_sha = voice_fingerprint(voice_id, settings)
        text_changed = bool(record.get("text_sha")) and record["text_sha"] != text_fingerprint(text)
        voice_changed = bool(record.get("voice_sha")) and record["voice_sha"] != voice_sha
        stale = record_matches and (text_changed or voice_changed)
        if existing and stale:
            reason = "สคริปต์คนละเวอร์ชัน" if text_changed else "เสียงหรือค่า synthesis เปลี่ยนไป"
            print(f"[stale] {scene_id} เสียงเดิมอัดจาก{reason} จะอัดใหม่")
        elif existing and not args.overwrite:
            print(f"[skip] {scene_id} มีไฟล์อยู่แล้ว: {existing.name}")
            continue
        pending.append((scene_id, text, output))

    total_chars = sum(len(text) for _, text, _ in pending)
    print(f"งาน: {job_path}")
    print(f"ซีนที่ต้องอัด: {len(pending)} | ตัวอักษรรวม: {total_chars}")
    print(f"model: {settings.get('model_id', 'eleven_multilingual_v2')} | voice: {voice_id or '(ยังไม่ตั้งค่า)'}")

    if not pending:
        # Nothing to synthesize, so a rerun must not fail on missing credentials.
        print("ไม่มีซีนที่ต้องอัดเพิ่ม")
        return

    if not args.execute:
        print()
        for scene_id, text, output in pending:
            preview = text if len(text) <= 60 else text[:57] + "..."
            print(f"[dry] {scene_id} -> {output.name}: {preview}")
        print()
        print("นี่คือ dry run เท่านั้น ใส่ --execute เพื่อเรียก ElevenLabs จริง")
        return

    if not api_key:
        raise SystemExit("ยังไม่ได้ตั้ง ELEVENLABS_API_KEY ใน .env")
    if not voice_id:
        raise SystemExit("ยังไม่ได้ตั้ง ELEVENLABS_VOICE_ID ใน .env หรือส่ง --voice-id")

    failed = 0
    for scene_id, text, output in pending:
        try:
            audio = synthesize(text, voice_id, api_key, settings, args.timeout)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:300]
            print(f"[fail] {scene_id}: HTTP {error.code} {detail}")
            failed += 1
            continue
        except (urllib.error.URLError, TimeoutError, socket.timeout, http.client.HTTPException) as error:
            reason = getattr(error, "reason", error)
            print(f"[fail] {scene_id}: {reason}")
            failed += 1
            continue
        staging = output.with_name(output.name + ".part")
        staging.write_bytes(audio)
        os.replace(staging, output)
        for older in voice_dir.iterdir():
            if not older.is_file() or older == output:
                continue
            if older.stem != output.stem or older.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            parked = voice_dir / "superseded"
            parked.mkdir(exist_ok=True)
            older.rename(parked / older.name)
            print(f"[move] {older.name} -> superseded/ (ถูกแทนที่ด้วย {output.name})")
        # Recording the text lets `sync` spot audio left over from an edited script.
        render_log[scene_id] = {
            "text_sha": text_fingerprint(text),
            "voice_sha": voice_fingerprint(voice_id, settings),
            "file": output.name,
            "stamp": content_identity(output),
        }
        write_render_log(voice_dir, render_log)
        print(f"[ok] {scene_id} -> {output.name} ({len(audio)} bytes)")

    if failed < len(pending) and args.voice_id.strip():
        write_voice_override(voice_dir, voice_id)

    print()
    print(f"สำเร็จ {len(pending) - failed}/{len(pending)} ซีน")
    fields_flag = f' --fields "{args.fields}"' if Path(args.fields) != DEFAULT_FIELDS else ""
    print(f'รัน `python3 scripts/run_client_pipeline.py{fields_flag} sync "{job_path}"` เพื่ออัปเดตสถานะ')
    if failed:
        # Exit nonzero so a shell pipeline does not treat a failed batch as done.
        raise SystemExit(1)


if __name__ == "__main__":
    main()
