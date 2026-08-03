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
import json
import re
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
AUDIO_SUFFIXES = [".mp3", ".wav", ".m4a"]
FINAL_SUFFIXES = [".mp4", ".mov"]


# ---------------------------------------------------------------- utilities


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def slugify(value: str, fallback: str = "client") -> str:
    cleaned = re.sub(r"[\s/\\]+", "-", (value or "").strip())
    cleaned = re.sub(r"[^0-9A-Za-z฀-๿\-_]", "", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-_")
    return cleaned[:40] or fallback


def find_asset(directory: Path, stem: str, suffixes: list) -> "Path | None":
    for suffix in suffixes:
        candidate = directory / f"{stem}{suffix}"
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


def first_file(directory: Path, suffixes: list) -> "Path | None":
    if not directory.exists():
        return None
    for item in sorted(directory.iterdir()):
        if item.suffix.lower() in suffixes and item.stat().st_size > 0:
            return item
    return None


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
        return list(csv.DictReader(raw.splitlines()))
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


def map_response(row: dict, keywords: dict) -> dict:
    """Map arbitrary Google Form column headers onto canonical brief fields."""
    mapped = {}
    used_headers = set()
    for field, needles in keywords.items():
        for header, value in row.items():
            if header in used_headers or not str(value or "").strip():
                continue
            lowered = str(header).lower()
            if any(str(needle).lower() in lowered for needle in needles):
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


def build_brief(mapped: dict, defaults: dict, overrides: dict) -> dict:
    brief = dict(defaults)
    brief.update(mapped)
    brief.update(overrides)
    brief["duration_sec"] = int(re.sub(r"[^0-9]", "", str(brief.get("duration_sec", ""))) or defaults.get("duration_sec", 45))
    brief["scene_count"] = int(brief.get("scene_count") or defaults.get("scene_count", 6))
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
            "",
            "ใช้ Brand Bible นี้เป็นกรอบ:",
            bible_block,
            "",
            f"แบ่งเป็น {scene_count} ซีน รวมเวลาต้องไม่เกิน {duration} วินาที",
            "ซีนแรกคือ hook ที่ทำให้หยุดนิ้วใน 3 วินาที ซีนสุดท้ายคือ CTA",
            "voiceover ต้องเป็นภาษาพูด อ่านออกเสียงแล้วลื่น ไม่มีอิโมจิ ไม่มีวงเล็บกำกับ",
            "on_screen_text ห้ามเกิน 2 บรรทัด",
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


def shot_list_prompt(brief: dict, script: dict, rules: dict) -> str:
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
            f"vertical {brief.get('aspect_ratio', '9:16')}, photographic, natural light, leave clean space for subtitles",
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


def compose_flow_prompt(shot: dict, brief: dict) -> str:
    motion = str(shot.get("motion_prompt") or "").strip() or str(shot.get("camera_move") or "slow push in").strip()
    return "\n".join(
        [
            f"[{shot.get('id', '')}] Google Flow animate - {shot.get('duration_sec', 0)}s",
            "",
            f"ภาพต้นทาง: stills/{shot.get('id', 'sh-xx')}.png",
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
        if not payload.get(required_key):
            print(f"[warn] {path.name} ไม่มีคีย์ `{required_key}`")
            return {}
        return payload


def sync_job(job: Job, fields_config: dict) -> dict:
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
    if has_content(job.brand_bible_path):
        stages["brand_bible"] = "done"
    else:
        stages["brand_bible"] = "ready"
        actions.append("รัน prompt ใน `01-brand-bible-prompt.md` แล้วบันทึกผลเป็น `brand-bible.md`")

    # --- script ---
    write_text(job.path / "02-script-prompt.md", script_prompt(brief, brand_bible))
    script = job.load_stage_json(job.script_path, "scenes")
    if script:
        stages["script"] = "done"
    else:
        stages["script"] = "ready" if stages["brand_bible"] == "done" else "waiting"
        if stages["script"] == "ready":
            actions.append("รัน prompt ใน `02-script-prompt.md` แล้วบันทึกผลเป็น `script.json`")

    # --- shot list ---
    if script:
        write_text(job.path / "03-shot-list-prompt.md", shot_list_prompt(brief, script, rules))
    shot_list = job.load_stage_json(job.shot_list_path, "shots")
    shots = shot_list.get("shots", []) if shot_list else []
    if shots:
        stages["shot_list"] = "done"
    elif script:
        stages["shot_list"] = "ready"
        actions.append("รัน prompt ใน `03-shot-list-prompt.md` แล้วบันทึกผลเป็น `shot-list.json`")
    else:
        stages["shot_list"] = "blocked"

    # --- stills + animate prompts ---
    if shots:
        image_dir = job.path / "04-image-prompts"
        flow_dir = job.path / "05-flow-prompts"
        for shot in shots:
            shot_id = str(shot.get("id") or "").strip() or "sh-xx"
            write_text(image_dir / f"{shot_id}.txt", compose_image_prompt(shot, brief, rules))
            write_text(flow_dir / f"{shot_id}.txt", compose_flow_prompt(shot, brief))
        write_text(image_dir / "README.md", asset_index(shots, "stills", "png"))
        write_text(flow_dir / "README.md", asset_index(shots, "clips", "mp4"))

        missing_stills = [s for s in shots if not find_asset(job.stills_dir, str(s.get("id", "")), IMAGE_SUFFIXES)]
        missing_clips = [s for s in shots if not find_asset(job.clips_dir, str(s.get("id", "")), CLIP_SUFFIXES)]
        stages["stills"] = "done" if not missing_stills else "ready"
        stages["animate"] = "done" if not missing_clips else ("ready" if not missing_stills else "waiting")
        if missing_stills:
            actions.append(f"สร้างภาพนิ่ง {len(missing_stills)} ช็อตที่ยังขาด แล้ววางใน `stills/` (ดู `04-image-prompts/`)")
        if missing_clips and stages["animate"] == "ready":
            actions.append(f"animate {len(missing_clips)} ช็อตใน Google Flow แล้ววางใน `clips/` (ดู `05-flow-prompts/`)")
    else:
        stages["stills"] = "blocked"
        stages["animate"] = "blocked"

    # --- voiceover ---
    scenes = script.get("scenes", []) if script else []
    if scenes:
        write_voice_lines(job, brief, scenes, fields_config)
        missing_vo = [s for s in scenes if not find_asset(job.voice_dir, str(s.get("id", "")), AUDIO_SUFFIXES)]
        stages["voiceover"] = "done" if not missing_vo else "ready"
        if missing_vo:
            actions.append(f"อัดเสียง {len(missing_vo)} ซีนที่ยังขาด: `python3 scripts/generate_voiceover.py {job.path.name} --execute`")
    else:
        stages["voiceover"] = "blocked"

    # --- edit ---
    if shots and scenes:
        write_assembly_sheet(job, script, shots)
        write_text(job.path / "06-edit-notes.md", edit_notes(brief, script, shots))
        final_file = first_file(job.final_dir, FINAL_SUFFIXES)
        ready_to_cut = stages["animate"] == "done" and stages["voiceover"] == "done"
        stages["edit"] = "done" if final_file else ("ready" if ready_to_cut else "waiting")
        if stages["edit"] == "ready":
            actions.append("ตัดใน Premiere Pro ตาม `06-assembly-sheet.csv` แล้ว export ลง `final/`")
    else:
        stages["edit"] = "blocked"
        final_file = None

    # --- review ---
    if final_file:
        write_text(job.path / "07-review-packet.md", review_packet(job, brief, script, shots, final_file))
        stages["review"] = "ready"
        actions.append("ส่ง `07-review-packet.md` + ไฟล์ใน `final/` ให้ลูกค้ารีวิว")
    else:
        stages["review"] = "blocked"

    manifest = {
        "job_id": job.path.name,
        "client_name": brief.get("client_name", ""),
        "created_at": read_json(job.manifest_path).get("created_at") if job.manifest_path.exists() else datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "stages": stages,
        "next_actions": actions,
    }
    write_json(job.manifest_path, manifest)
    return manifest


def asset_index(shots: list, folder: str, suffix: str) -> str:
    lines = [f"# ไฟล์ที่ต้องได้จากขั้นตอนนี้", ""]
    for shot in shots:
        shot_id = shot.get("id", "")
        lines.append(f"- `{folder}/{shot_id}.{suffix}` — {shot.get('description', '')}")
    return "\n".join(lines)


def write_voice_lines(job: Job, brief: dict, scenes: list, fields_config: dict) -> None:
    path = job.voice_dir / "lines.csv"
    fields = ["scene_id", "beat", "duration_sec", "vo_text", "output_file", "status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for scene in scenes:
            scene_id = str(scene.get("id") or "").strip() or "sc-xx"
            existing = find_asset(job.voice_dir, scene_id, AUDIO_SUFFIXES)
            writer.writerow(
                {
                    "scene_id": scene_id,
                    "beat": scene.get("beat", ""),
                    "duration_sec": scene.get("duration_sec", ""),
                    "vo_text": str(scene.get("vo") or "").strip(),
                    "output_file": f"{scene_id}.mp3",
                    "status": "done" if existing else "todo",
                }
            )


def write_assembly_sheet(job: Job, script: dict, shots: list) -> None:
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
        for index, shot in enumerate(shots, start=1):
            shot_id = str(shot.get("id") or "")
            scene_id = str(shot.get("scene_id") or "")
            scene = scenes.get(scene_id, {})
            still = find_asset(job.stills_dir, shot_id, IMAGE_SUFFIXES)
            clip = find_asset(job.clips_dir, shot_id, CLIP_SUFFIXES)
            voice = find_asset(job.voice_dir, scene_id, AUDIO_SUFFIXES)
            writer.writerow(
                {
                    "order": index,
                    "shot_id": shot_id,
                    "scene_id": scene_id,
                    "beat": scene.get("beat", ""),
                    "duration_sec": shot.get("duration_sec", ""),
                    "still_file": f"stills/{still.name}" if still else "MISSING",
                    "clip_file": f"clips/{clip.name}" if clip else "MISSING",
                    "voice_file": f"voiceover/{voice.name}" if voice else "MISSING",
                    "on_screen_text": str(scene.get("on_screen_text") or "").replace("\n", " "),
                    "camera_move": shot.get("camera_move", ""),
                }
            )


def edit_notes(brief: dict, script: dict, shots: list) -> str:
    total = sum(float(shot.get("duration_sec") or 0) for shot in shots)
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
            "5. ใส่ subtitle จากคอลัมน์ `on_screen_text` ไม่เกิน 2 บรรทัด",
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
    job_path = Path(args.jobs) / job_id
    if job_path.exists() and not args.force:
        raise SystemExit(f"มีงานนี้อยู่แล้ว: {job_path} (ใช้ --force เพื่อเขียนทับ brief)")
    job_path.mkdir(parents=True, exist_ok=True)

    job = Job(job_path)
    write_json(job.brief_path, brief)
    manifest = sync_job(job, fields_config)
    print(f"สร้างงานใหม่: {job_path}")
    print_status(manifest)


def cmd_sync(args: argparse.Namespace) -> None:
    fields_config = read_json(Path(args.fields))
    job = Job(resolve_job(args.jobs, args.job_id))
    manifest = sync_job(job, fields_config)
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
        manifest = read_json(manifest_path)
        stages = manifest.get("stages", {})
        done = sum(1 for stage in STAGES if stages.get(stage) == "done")
        print(f"{item.name:<40} {done}/{len(STAGES)} stages  {manifest.get('client_name', '')}")


def resolve_job(jobs_root: str, job_id: str) -> Path:
    path = Path(job_id)
    if path.is_dir():
        return path
    candidate = Path(jobs_root) / job_id
    if candidate.is_dir():
        return candidate
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
    args = parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
