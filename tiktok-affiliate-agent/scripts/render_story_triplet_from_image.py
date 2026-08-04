#!/usr/bin/env python3
"""Render three TikTok story clips from one ChatGPT-generated image."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import wave
import struct
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
W, H = 720, 1280
FPS = 30
DEFAULT_CLIP_DURATION = 22
SR = 44100

INK = "#f4f7fb"
MUTED = "#aab3c2"
RED = "#ff315c"
BLACK = "#050507"
GREEN = "#91ffc2"


EPISODES = []


def load_episodes(story_path: str, series_id: str, hook: str = "", only_episode: int = 0) -> tuple:
    """Beats come from the selected series, so a rerun renders what the plan says."""
    config = json.loads(Path(story_path).read_text(encoding="utf-8"))
    series_list = config.get("series", [])
    series = next((item for item in series_list if item.get("id") == series_id), None) if series_id else (series_list[0] if series_list else None)
    if not series:
        raise SystemExit(f"ไม่พบ series `{series_id}` ใน {story_path}")
    render_beats = series.get("render_beats") or []
    if not render_beats:
        raise SystemExit(
            f"series `{series['id']}` ยังไม่มี `render_beats` ใน {story_path}\n"
            f"renderer วาดข้อความตามบีทที่กำหนดไว้ในไฟล์นั้น ให้เพิ่มก่อนถึงจะเรนเดอร์ได้"
        )
    if hook and not only_episode:
        raise SystemExit("--hook ต้องใช้คู่กับ --episode เพราะ hook ใหม่เป็นของตอนเดียว ไม่ใช่ทั้งซีรีส์")
    episodes = []
    for item in render_beats:
        number = int(item.get("episode", len(episodes) + 1))
        if only_episode and number != only_episode:
            continue
        beats = [(as_seconds(beat["start"]), as_seconds(beat["end"]), beat["title"], beat["sub"])
                 for beat in item.get("beats", [])]
        if hook and beats:
            first = beats[0]
            beats[0] = (first[0], first[1], hook, first[3])
        episodes.append({
            "number": number,
            "id": f"{series['id']}-ep{number}",
            "title": item.get("title", ""),
            "beats": beats,
            "phone_beats": item.get("phone_beats", []),
            "phone_context": tuple(item.get("phone_context") or ("ไม่ทราบชื่อ", "")),
            "caption": item.get("caption", ""),
        })
    if only_episode and not episodes:
        raise SystemExit(f"ไม่พบตอน {only_episode} ใน series `{series['id']}`")
    return series, episodes


def as_seconds(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/Supplemental/Thonburi.ttc",
    "/System/Library/Fonts/ThonburiUI.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansThai-Regular.ttf",
    "/usr/share/fonts/truetype/tlwg/Sarabun-Regular.ttf",
    "/usr/share/fonts/truetype/tlwg/Loma.ttf",
    "/usr/share/fonts/truetype/tlwg/Garuda.ttf",
    # Windows
    "C:/Windows/Fonts/leelawui.ttf",
    "C:/Windows/Fonts/leelawad.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
]

FONT_HELP = (
    "renderer ต้องใช้ฟอนต์ที่รองรับภาษาไทย\n"
    "macOS: มีมากับเครื่องอยู่แล้ว\n"
    "Ubuntu/Debian: sudo apt install fonts-thai-tlwg หรือ fonts-noto-core\n"
    "Windows: ใช้ Leelawadee UI ที่มีมากับ Windows\n"
    "หรือชี้ไฟล์ฟอนต์เองด้วย --font /path/to/font.ttf"
)

_FONT_PATH = ""
HANDLE = "@thatslife6969"
SERIES_TITLE = "ห้อง 407"
F22 = F26 = F30 = F38 = F48 = F60 = None


def find_thai_font(explicit: str = "") -> str:
    """A font that can actually draw Thai, or nothing."""
    if explicit:
        if not Path(explicit).exists():
            raise SystemExit(f"ไม่พบไฟล์ฟอนต์: {explicit}")
        if not renders_thai(explicit):
            raise SystemExit(f"{explicit} วาดตัวอักษรไทยไม่ได้ ตัวหนังสือจะกลายเป็นกล่องสี่เหลี่ยม\n{FONT_HELP}")
        return explicit
    for item in FONT_CANDIDATES:
        if Path(item).exists() and renders_thai(item):
            return item
    lister = shutil.which("fc-list")
    if lister:
        # fc-list filters by language; fc-match would hand back a best-effort
        # substitute even when nothing on the system covers Thai.
        try:
            output = subprocess.run(
                [lister, ":lang=th", "--format=%{file}\n"], capture_output=True, text=True, timeout=10
            ).stdout
        except (OSError, subprocess.SubprocessError):
            output = ""
        for line in output.splitlines():
            candidate = line.strip()
            if candidate and Path(candidate).exists() and renders_thai(candidate):
                return candidate
    return ""


def renders_thai(path: str) -> bool:
    """A font that has no Thai glyph draws the same .notdef box for any missing code point."""
    try:
        probe = ImageFont.truetype(path, size=40)
        thai = probe.getmask("ก")
        missing = probe.getmask("\ue001")
    except (OSError, ValueError):
        return False
    if not thai.getbbox():
        return False
    return bytes(thai) != bytes(missing)


def font(size: int, bold: bool = False):
    path = _FONT_PATH
    return ImageFont.truetype(path, size=size, index=1 if bold and path.endswith(".ttc") else 0)


def load_fonts(explicit: str = "") -> None:
    global _FONT_PATH, F22, F26, F30, F38, F48, F60
    _FONT_PATH = find_thai_font(explicit)
    if not _FONT_PATH:
        raise SystemExit(FONT_HELP)
    F22, F26, F30 = font(22), font(26), font(30)
    F38, F48, F60 = font(38, True), font(48, True), font(60, True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render three story clips from one image.")
    parser.add_argument(
        "--image",
        default=str(ROOT / "outputs" / "2026-05-14" / "room-407-chatgpt-keyvisual.png"),
        help="Input key visual.",
    )
    parser.add_argument("--out", default=str(ROOT / "outputs" / "2026-05-14"), help="Output date directory.")
    parser.add_argument("--font", default="", help="ไฟล์ฟอนต์ภาษาไทยที่จะใช้ ถ้าไม่ใส่จะหาให้เอง.")
    parser.add_argument("--account", default=str(ROOT / "data" / "tiktok_account.json"), help="ไฟล์บัญชี TikTok ที่จะใช้ handle.")
    parser.add_argument("--handle", default="", help="ทับ handle ที่จะพิมพ์ลงบนคลิป.")
    parser.add_argument("--story", default=str(ROOT / "data" / "story_series.json"), help="ไฟล์ series ที่มี render_beats.")
    parser.add_argument("--series-id", default="room-407", help="series ที่จะเรนเดอร์.")
    parser.add_argument("--episode", type=int, default=0, help="เรนเดอร์เฉพาะตอนนี้ เช่น 2.")
    parser.add_argument("--hook", default="", help="hook ใหม่ ใช้ได้เฉพาะตอนที่ระบุด้วย --episode.")
    parser.add_argument("--frames-only", action="store_true", help="สร้างเฉพาะเฟรมกับเสียง ไม่ encode เป็น MP4.")
    return parser.parse_args()


def encode_clip(frames_dir: Path, audio_path: Path, output_path: Path) -> None:
    """Mux the frames and the ambient bed into a TikTok-ready MP4."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit(
            "ต้องมี ffmpeg เพื่อรวมเฟรมเป็น MP4\n"
            "macOS: brew install ffmpeg | Ubuntu: sudo apt install ffmpeg\n"
            "ถ้าอยากได้เฉพาะเฟรมไว้ไปตัดต่อเอง ให้ใส่ --frames-only"
        )
    # Encode beside the target and swap only on success, so a failed rerun cannot
    # truncate a clip that was already post-ready.
    staging = output_path.with_name(output_path.name + ".part.mp4")
    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-framerate", str(FPS), "-i", str(frames_dir / "frame_%04d.jpg"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(staging),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        staging.unlink(missing_ok=True)
        raise SystemExit(f"ffmpeg ล้มเหลว:\n{result.stderr.strip()[-800:]}")
    os.replace(staging, output_path)


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def active_beat(episode: dict, sec: float):
    for index, (start, end, title, sub) in enumerate(episode["beats"]):
        if start <= sec < end:
            return index, title, sub, (sec - start) / (end - start)
    start, end, title, sub = episode["beats"][-1]
    return len(episode["beats"]) - 1, title, sub, 1.0


def rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center(draw: ImageDraw.ImageDraw, text: str, y: int, fnt, fill=INK, spacing=8, stroke=0):
    lines = text.split("\n")
    boxes = [draw.textbbox((0, 0), line, font=fnt, stroke_width=stroke) for line in lines]
    total = sum(b[3] - b[1] for b in boxes) + spacing * (len(lines) - 1)
    cy = y - total // 2
    for line, b in zip(lines, boxes):
        tw = b[2] - b[0]
        draw.text(((W - tw) / 2, cy), line, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=BLACK)
        cy += b[3] - b[1] + spacing


def prepare_bg(path: Path) -> Image.Image:
    src = Image.open(path).convert("RGB")
    src_ratio = src.width / src.height
    target_ratio = W / H
    if src_ratio > target_ratio:
        new_h = H
        new_w = int(H * src_ratio)
    else:
        new_w = W
        new_h = int(W / src_ratio)
    src = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = max(0, (new_w - W) // 2)
    top = max(0, (new_h - H) // 2)
    return src.crop((left, top, left + W, top + H))


def background(bg: Image.Image, sec: float, episode_index: int, beat_index: int, span: float = DEFAULT_CLIP_DURATION) -> Image.Image:
    # Cycle instead of indexing: a series may hold more than three episodes.
    zoom_steps = [1.0, 1.035, 1.065]
    zoom_base = zoom_steps[episode_index % len(zoom_steps)]
    # Never below 1.0: a smaller resize would leave black padding at the crop edges.
    zoom = max(1.0, zoom_base + 0.025 * (sec / span) + 0.012 * math.sin(sec * 0.45 + episode_index))
    resized = bg.resize((int(W * zoom), int(H * zoom)), Image.Resampling.LANCZOS)
    max_x = resized.width - W
    max_y = resized.height - H
    x = int(max_x * (0.46 + 0.12 * math.sin(sec * 0.18 + beat_index)))
    y = int(max_y * (0.50 + 0.10 * math.cos(sec * 0.22 + episode_index)))
    crop = resized.crop((x, y, x + W, y + H)).convert("RGBA")
    shade_alpha = 52 + int(18 * math.sin(sec * 7.1))
    crop = Image.alpha_composite(crop, Image.new("RGBA", (W, H), (0, 0, 0, shade_alpha)))
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-120, -80, W + 120, H + 160), fill=175)
    vignette = Image.eval(vignette.filter(ImageFilter.GaussianBlur(78)), lambda p: 188 - p)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(vignette)
    return Image.alpha_composite(crop, dark)


def draw_phone_overlay(draw: ImageDraw.ImageDraw, local: float, message: str, context=None):
    x, y, w, h = 86, 326, 548, 480
    rounded(draw, (x, y, x + w, y + h), 38, (7, 9, 14, 224), (150, 160, 175, 118), 3)
    rounded(draw, (x + 24, y + 36, x + w - 24, y + h - 28), 26, (12, 17, 27, 238))
    draw.text((x + 52, y + 64), "ข้อความ", font=F30, fill=INK)
    draw.text((x + w - 54, y + 68), "03:07", font=F26, fill=MUTED, anchor="ra")
    rounded(draw, (x + 50, y + 144, x + w - 50, y + 236), 24, (30, 43, 62, 250))
    sender, previous = context or ("ไม่ทราบชื่อ", "คุณอยู่คนเดียวใช่ไหม")
    draw.text((x + 78, y + 163), sender, font=F26, fill=MUTED)
    draw.text((x + 78, y + 196), previous, font=F30, fill=INK)
    show = int(len(message) * ease(local))
    rounded(draw, (x + 50, y + 292, x + w - 50, y + 392), 26, (74, 25, 43, 255), (255, 49, 92, 210), 3)
    draw.text((x + 78, y + 322), message[:show], font=F38, fill=INK)
    draw.text((x + 78, y + 418), "กำลังพิมพ์...", font=F26, fill=GREEN)


def subtitle(draw: ImageDraw.ImageDraw, title: str, sub: str, local: float, danger: bool = False):
    y = 920 + int((1 - ease(local)) * 22)
    rounded(draw, (34, y, W - 34, y + 230), 34, (0, 0, 0, 202), (255, 255, 255, 52), 2)
    center(draw, title, y + 82, F48, INK, stroke=1)
    center(draw, sub, y + 170, F30, RED if danger else MUTED)


def draw_frame(bg: Image.Image, episode: dict, episode_index: int, frame: int) -> Image.Image:
    sec = frame / FPS
    beat_index, title, sub, local = active_beat(episode, sec)
    img = background(bg, sec, episode_index, beat_index, episode_duration(episode))
    draw = ImageDraw.Draw(img)

    progress = int((W - 56) * sec / episode_duration(episode))
    rounded(draw, (28, 28, W - 28, 40), 6, (70, 75, 86, 185))
    rounded(draw, (28, 28, 28 + progress, 40), 6, RED)
    draw.text((32, 58), f"{SERIES_TITLE} ตอน {episode.get('number', episode_index + 1)}", font=F22, fill=MUTED)
    draw.text((W - 32, 58), HANDLE, font=F22, fill=MUTED, anchor="ra")

    if beat_index == 0:
        shake = int(math.sin(sec * 34) * 6 * (1 - local))
        center(draw, title, 370 + shake, F60, INK, stroke=2)
        rounded(draw, (120, 636, 600, 722), 43, (255, 49, 92, 226))
        draw.text((360, 660), sub, font=F38, fill=INK, anchor="ma")
    elif beat_index in episode.get("phone_beats", ()):
        draw_phone_overlay(draw, local, sub.replace("“", "").replace("”", ""), episode.get("phone_context"))
        subtitle(draw, title, sub, local, danger=True)
    else:
        subtitle(draw, title, sub, local, danger=beat_index >= 4)

    if beat_index == 2 and episode.get("number", episode_index + 1) == 1:
        for i in range(3):
            draw.text((360, 430 + i * 68), "ก๊อก", font=F60, fill=(255, 255, 255, 92 + i * 42), anchor="ma")

    return img.convert("RGB")


def write_audio(path: Path, duration: float) -> None:
    samples = int(duration * SR)
    rng = random.Random(407)
    with wave.open(str(path), "w") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        for n in range(samples):
            t = n / SR
            drone = 0.10 * math.sin(2 * math.pi * 43 * t) + 0.04 * math.sin(2 * math.pi * 58.7 * t)
            hiss = 0.012 * rng.uniform(-1, 1)
            knock = 0.0
            for kt in [1.1, 1.42, 1.74, 7.2, 7.52, 14.1, 14.42, 20.1]:
                dt = t - kt
                if 0 <= dt < 0.16:
                    knock += 0.62 * math.sin(2 * math.pi * 92 * dt) * math.exp(-dt * 30)
            pulse = 0.0
            if t > 15:
                dt = (t - 15) % 0.8
                if dt < 0.08:
                    pulse += 0.22 * math.sin(2 * math.pi * 54 * dt) * math.exp(-dt * 32)
            val = max(-1, min(1, drone + hiss + knock + pulse))
            f.writeframesraw(struct.pack("<hh", int(val * 23000), int(val * 23000)))


def episode_duration(episode: dict) -> float:
    """The clip lasts as long as its last beat says it does."""
    beats = episode.get("beats") or []
    return max((beat[1] for beat in beats), default=DEFAULT_CLIP_DURATION)


def render_episode(bg: Image.Image, episode: dict, episode_index: int, out_dir: Path) -> Path:
    frames_dir = out_dir / f"{episode['id']}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(int(round(episode_duration(episode) * FPS))):
        draw_frame(bg, episode, episode_index, frame).save(frames_dir / f"frame_{frame:04d}.jpg", quality=92)
    return frames_dir


def resolve_handle(account_path: str, override: str) -> str:
    if override:
        return override if override.startswith("@") else f"@{override}"
    path = Path(account_path)
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle_file:
                handle = str(json.load(handle_file).get("handle") or "").strip()
        except (json.JSONDecodeError, OSError):
            handle = ""
        if handle:
            return handle if handle.startswith("@") else f"@{handle}"
    return HANDLE


def main() -> None:
    global HANDLE, EPISODES, SERIES_TITLE
    args = parse_args()
    series, EPISODES = load_episodes(args.story, args.series_id, args.hook.strip(), args.episode)
    SERIES_TITLE = series.get("title") or series.get("id", "")
    HANDLE = resolve_handle(args.account, args.handle)
    load_fonts(args.font)
    out_dir = Path(args.out)
    videos_dir = out_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    bg = prepare_bg(Path(args.image))
    for index, episode in enumerate(EPISODES):
        audio_path = videos_dir / f"{episode['id']}-ambient.wav"
        write_audio(audio_path, episode_duration(episode))
        frames_dir = render_episode(bg, episode, index, videos_dir)
        if args.frames_only:
            print(f"{episode['id']}|{frames_dir}|{audio_path}|{episode['caption']}")
            continue
        clip_path = videos_dir / f"{episode['id']}-tiktok.mp4"
        encode_clip(frames_dir, audio_path, clip_path)
        # 660 JPEGs per clip are scratch space once the MP4 exists.
        shutil.rmtree(frames_dir, ignore_errors=True)
        print(f"{episode['id']}|{clip_path}|{episode['caption']}")


if __name__ == "__main__":
    main()
