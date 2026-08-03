#!/usr/bin/env python3
"""Render ElevenLabs voice-over for every scene listed in a job's voiceover/lines.csv."""

from __future__ import annotations

import argparse
import csv
import json
import os
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
    path = Path(job_id)
    if path.is_dir():
        return path
    candidate = Path(jobs_root) / job_id
    if candidate.is_dir():
        return candidate
    raise SystemExit(f"ไม่พบงาน: {job_id}")


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
    voice_id = (args.voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "")).strip()

    pending = []
    for row in rows:
        text = str(row.get("vo_text") or "").strip()
        output = voice_dir / (row.get("output_file") or f"{row.get('scene_id', 'sc-xx')}.mp3")
        if not text:
            print(f"[skip] {row.get('scene_id')} ไม่มีข้อความพูด")
            continue
        if output.exists() and output.stat().st_size > 0 and not args.overwrite:
            print(f"[skip] {row.get('scene_id')} มีไฟล์อยู่แล้ว: {output.name}")
            continue
        pending.append((row.get("scene_id", ""), text, output))

    total_chars = sum(len(text) for _, text, _ in pending)
    print(f"งาน: {job_path}")
    print(f"ซีนที่ต้องอัด: {len(pending)} | ตัวอักษรรวม: {total_chars}")
    print(f"model: {settings.get('model_id', 'eleven_multilingual_v2')} | voice: {voice_id or '(ยังไม่ตั้งค่า)'}")

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
        except urllib.error.URLError as error:
            print(f"[fail] {scene_id}: {error.reason}")
            failed += 1
            continue
        output.write_bytes(audio)
        print(f"[ok] {scene_id} -> {output.name} ({len(audio)} bytes)")

    print()
    print(f"สำเร็จ {len(pending) - failed}/{len(pending)} ซีน")
    print("รัน `python3 scripts/run_client_pipeline.py sync <job>` เพื่ออัปเดตสถานะ")


if __name__ == "__main__":
    main()
