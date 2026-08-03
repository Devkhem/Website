#!/usr/bin/env python3
"""Render three TikTok story clips from one ChatGPT-generated image."""

from __future__ import annotations

import argparse
import math
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
CLIP_DURATION = 22
FRAMES = FPS * CLIP_DURATION
SR = 44100

INK = "#f4f7fb"
MUTED = "#aab3c2"
RED = "#ff315c"
BLACK = "#050507"
GREEN = "#91ffc2"


EPISODES = [
    {
        "id": "room-407-ep1",
        "title": "เสียงเคาะตอนตี 3",
        "beats": [
            (0.0, 2.6, "อย่าเปิดประตู\nหลังตี 3", "ฟังให้จบก่อนนอน"),
            (2.6, 6.4, "คืนนั้นผมนอน\nห้อง 407 คนเดียว", "ทั้งชั้นเงียบผิดปกติ"),
            (6.4, 10.8, "ก๊อก... ก๊อก... ก๊อก...", "เสียงมาจากหน้าประตู"),
            (10.8, 15.8, "ผมเปิดตาแมว", "หน้าห้องไม่มีใคร"),
            (15.8, 20.0, "แต่โทรศัพท์เด้งขึ้นมา", "“เปิดหน่อย หนาวมาก”"),
            (20.0, 22.0, "ถ้าเป็นคุณ", "จะเปิดไหม?"),
        ],
        "caption": "อย่าเปิดประตูหลังตี 3 ฟังให้จบแล้วบอกทีว่าคุณจะเปิดไหม",
    },
    {
        "id": "room-407-ep2",
        "title": "ข้อความจากรูมเมตเก่า",
        "beats": [
            (0.0, 2.6, "เบอร์ที่ปิดไปแล้ว\nส่งข้อความมา", "03:07"),
            (2.6, 6.8, "ข้อความแรกเขียนว่า", "“คุณอยู่คนเดียวใช่ไหม”"),
            (6.8, 11.2, "ผมจำเบอร์นั้นได้", "รูมเมตที่ย้ายออกไปเมื่อปีก่อน"),
            (11.2, 16.4, "ข้อความต่อมา", "“อย่ามองตาแมว”"),
            (16.4, 20.0, "แต่ผมมองไปแล้ว", "ในเงาประตูมีคนยืนอยู่"),
            (20.0, 22.0, "แล้วแชตสุดท้ายก็ขึ้น", "“เขาเห็นคุณแล้ว”"),
        ],
        "caption": "เบอร์ที่ปิดไปแล้ว ส่งข้อความมา ถ้าเจอแบบนี้คุณจะทำยังไง",
    },
    {
        "id": "room-407-ep3",
        "title": "เงาในกระจก",
        "beats": [
            (0.0, 2.8, "ผมไม่เห็นใคร\nหน้าห้อง", "แต่กระจกเห็น"),
            (2.8, 7.0, "ปลายทางเดินมีเงา", "ยืนนิ่งอยู่ในกรอบกระจก"),
            (7.0, 11.4, "ผมหันกลับไปดู", "ทางเดินว่างเปล่า"),
            (11.4, 16.2, "แต่ในจอมือถือ", "เงานั้นใกล้กว่าเดิม"),
            (16.2, 20.0, "ข้อความสุดท้ายส่งมา", "“ไม่ต้องเปิดแล้ว”"),
            (20.0, 22.0, "“เราเข้ามาแล้ว”", "คืนนี้อย่าหันไปมองกระจก"),
        ],
        "caption": "ผมไม่เห็นใครหน้าห้อง แต่กระจกเห็น ตอนจบคือไม่โอเคเลย",
    },
]


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
F22 = F26 = F30 = F38 = F48 = F60 = None


def find_thai_font(explicit: str = "") -> str:
    """A font that can actually draw Thai, or nothing."""
    if explicit:
        if not Path(explicit).exists():
            raise SystemExit(f"ไม่พบไฟล์ฟอนต์: {explicit}")
        return explicit
    for item in FONT_CANDIDATES:
        if Path(item).exists():
            return item
    matcher = shutil.which("fc-match")
    if matcher:
        try:
            found = subprocess.run(
                [matcher, "-f", "%{file}", ":lang=th"], capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            found = ""
        if found and Path(found).exists():
            return found
    return ""


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
    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-framerate", str(FPS), "-i", str(frames_dir / "frame_%04d.jpg"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"ffmpeg ล้มเหลว:\n{result.stderr.strip()[-800:]}")


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


def background(bg: Image.Image, sec: float, episode_index: int, beat_index: int) -> Image.Image:
    zoom_base = [1.0, 1.035, 1.065][episode_index]
    zoom = zoom_base + 0.025 * (sec / CLIP_DURATION) + 0.012 * math.sin(sec * 0.45 + episode_index)
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


def draw_phone_overlay(draw: ImageDraw.ImageDraw, local: float, message: str):
    x, y, w, h = 86, 326, 548, 480
    rounded(draw, (x, y, x + w, y + h), 38, (7, 9, 14, 224), (150, 160, 175, 118), 3)
    rounded(draw, (x + 24, y + 36, x + w - 24, y + h - 28), 26, (12, 17, 27, 238))
    draw.text((x + 52, y + 64), "ข้อความ", font=F30, fill=INK)
    draw.text((x + w - 54, y + 68), "03:07", font=F26, fill=MUTED, anchor="ra")
    rounded(draw, (x + 50, y + 144, x + w - 50, y + 236), 24, (30, 43, 62, 250))
    draw.text((x + 78, y + 163), "ห้อง 407", font=F26, fill=MUTED)
    draw.text((x + 78, y + 196), "คุณอยู่คนเดียวใช่ไหม", font=F30, fill=INK)
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
    img = background(bg, sec, episode_index, beat_index)
    draw = ImageDraw.Draw(img)

    progress = int((W - 56) * sec / CLIP_DURATION)
    rounded(draw, (28, 28, W - 28, 40), 6, (70, 75, 86, 185))
    rounded(draw, (28, 28, 28 + progress, 40), 6, RED)
    draw.text((32, 58), f"ห้อง 407 ตอน {episode_index + 1}", font=F22, fill=MUTED)
    draw.text((W - 32, 58), "@thatslife6969", font=F22, fill=MUTED, anchor="ra")

    if beat_index == 0:
        shake = int(math.sin(sec * 34) * 6 * (1 - local))
        center(draw, title, 370 + shake, F60, INK, stroke=2)
        rounded(draw, (120, 636, 600, 722), 43, (255, 49, 92, 226))
        draw.text((360, 660), sub, font=F38, fill=INK, anchor="ma")
    elif episode_index in {1, 2} and beat_index in {1, 4, 5}:
        draw_phone_overlay(draw, local, sub.replace("“", "").replace("”", ""))
        subtitle(draw, title, sub, local, danger=True)
    else:
        subtitle(draw, title, sub, local, danger=beat_index >= 4)

    if beat_index == 2 and episode_index == 0:
        for i in range(3):
            draw.text((360, 430 + i * 68), "ก๊อก", font=F60, fill=(255, 255, 255, 92 + i * 42), anchor="ma")

    return img.convert("RGB")


def write_audio(path: Path, duration: int) -> None:
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


def render_episode(bg: Image.Image, episode: dict, episode_index: int, out_dir: Path) -> Path:
    frames_dir = out_dir / f"{episode['id']}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(FRAMES):
        draw_frame(bg, episode, episode_index, frame).save(frames_dir / f"frame_{frame:04d}.jpg", quality=92)
    return frames_dir


def main() -> None:
    args = parse_args()
    load_fonts(args.font)
    out_dir = Path(args.out)
    videos_dir = out_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    bg = prepare_bg(Path(args.image))
    audio_path = videos_dir / "room-407-triplet-ambient.wav"
    write_audio(audio_path, CLIP_DURATION)
    for index, episode in enumerate(EPISODES):
        frames_dir = render_episode(bg, episode, index, videos_dir)
        if args.frames_only:
            print(f"{episode['id']}|{frames_dir}|{audio_path}|{episode['caption']}")
            continue
        clip_path = videos_dir / f"{episode['id']}-tiktok.mp4"
        encode_clip(frames_dir, audio_path, clip_path)
        print(f"{episode['id']}|{clip_path}|{episode['caption']}")


if __name__ == "__main__":
    main()
