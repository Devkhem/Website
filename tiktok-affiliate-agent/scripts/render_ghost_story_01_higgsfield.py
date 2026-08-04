#!/usr/bin/env python3
"""Render the Room 407 ghost story using a Higgsfield key visual."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "videos"
KEYVISUAL = OUT_DIR / "higgsfield-room-407-keyvisual.png"
W, H = 720, 1280
FPS = 30
DURATION = 32
FRAMES = FPS * DURATION

INK = "#f3f6fb"
MUTED = "#aab3c2"
RED = "#ff315c"
BLACK = "#050507"
GREEN = "#91ffc2"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Thonburi.ttc",
        "/System/Library/Fonts/ThonburiUI.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for item in candidates:
        p = Path(item)
        if p.exists():
            return ImageFont.truetype(str(p), size=size, index=1 if bold and item.endswith(".ttc") else 0)
    return ImageFont.load_default()


F22 = font(22)
F28 = font(28)
F34 = font(34, True)
F42 = font(42, True)
F58 = font(58, True)
F72 = font(72, True)


SCENES = [
    (0.0, 3.2, "อย่าเปิดประตู\nหลังตี 3", "ฟังให้จบก่อนนอน"),
    (3.2, 7.4, "เมื่อคืนผมนอนห้อง 407\nคนเดียวทั้งชั้น", "แต่แชตเด้งขึ้นมาแบบนี้"),
    (7.4, 12.0, "“เปิดหน่อย หนาวมาก”", "เบอร์นั้นเป็นเบอร์ของรูมเมตเก่า"),
    (12.0, 17.0, "ผมมองตาแมว...", "หน้าห้องไม่มีใคร"),
    (17.0, 22.8, "แต่ในกระจกหลังผม", "มีคนยืนใส่เสื้อกันหนาวสีเทา"),
    (22.8, 28.0, "ข้อความสุดท้ายส่งมา", "“ไม่ต้องเปิดแล้ว เราเข้ามาแล้ว”"),
    (28.0, 32.0, "คืนนี้อย่าหันไป\nมองกระจก", "คอมเมนต์เลขห้องคุณ"),
]


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def active(sec: float):
    for idx, (start, end, title, sub) in enumerate(SCENES):
        if start <= sec < end:
            return idx, title, sub, (sec - start) / (end - start)
    idx = len(SCENES) - 1
    start, end, title, sub = SCENES[-1]
    return idx, title, sub, 1.0


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


def load_bg() -> Image.Image:
    src = Image.open(KEYVISUAL).convert("RGB")
    # Square Higgsfield output -> vertical crop that keeps mirror and room 407.
    src = src.resize((1280, 1280), Image.Resampling.LANCZOS)
    return src


BG = load_bg()


def background(sec: float) -> Image.Image:
    zoom = 1.0 + 0.028 * (sec / DURATION)
    resized = BG.resize((int(1280 * zoom), int(1280 * zoom)), Image.Resampling.LANCZOS)
    travel = math.sin(sec * 0.25) * 18
    x0 = int(260 * zoom + travel)
    y0 = int(0 * zoom)
    crop = resized.crop((x0, y0, x0 + W, y0 + H)).convert("RGBA")

    # Cinematic darkness plus subtle flicker.
    flicker = int(22 + 16 * math.sin(sec * 8.3) + 6 * math.sin(sec * 23.0))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 82 - min(35, max(0, flicker))))
    crop = Image.alpha_composite(crop, shade)
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-170, -80, W + 170, H + 160), fill=178)
    vignette = Image.eval(vignette.filter(ImageFilter.GaussianBlur(84)), lambda p: 205 - p)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(vignette)
    crop = Image.alpha_composite(crop, dark)
    return crop


def subtitle(draw: ImageDraw.ImageDraw, title: str, sub: str, scene: int, local: float):
    y = 994 + int((1 - ease(local)) * 26)
    rounded(draw, (34, y, W - 34, y + 206), 32, (0, 0, 0, 205), (255, 255, 255, 50), 2)
    center(draw, title, y + 78, F42 if scene != 0 else F58, INK, stroke=1)
    center(draw, sub, y + 160, F28, RED if scene in {0, 5, 6} else MUTED)


def draw_phone(draw: ImageDraw.ImageDraw, local: float, message: str):
    x, y, w, h = 82, 308, 556, 548
    rounded(draw, (x, y, x + w, y + h), 42, (7, 9, 14, 238), (150, 160, 175, 120), 3)
    rounded(draw, (x + 24, y + 38, x + w - 24, y + h - 30), 28, (12, 17, 27, 246))
    draw.text((x + 52, y + 66), "ข้อความ", font=F34, fill=INK)
    draw.text((x + w - 54, y + 72), "03:07", font=F28, fill=MUTED, anchor="ra")
    rounded(draw, (x + 50, y + 150, x + w - 50, y + 240), 26, (30, 43, 62, 255))
    draw.text((x + 78, y + 168), "ห้อง 407", font=F28, fill=MUTED)
    draw.text((x + 78, y + 202), "คุณอยู่คนเดียวใช่ไหม", font=F34, fill=INK)
    show = int(len(message) * ease(local))
    rounded(draw, (x + 50, y + 304, x + w - 50, y + 420), 28, (72, 25, 43, 255), (255, 49, 92, 210), 3)
    draw.text((x + 78, y + 336), message[:show], font=F42, fill=INK)
    draw.text((x + 78, y + 456), "กำลังพิมพ์...", font=F28, fill=GREEN)


def draw_frame(frame: int) -> Image.Image:
    sec = frame / FPS
    scene, title, sub, local = active(sec)
    img = background(sec)
    draw = ImageDraw.Draw(img)

    progress = int((W - 56) * sec / DURATION)
    rounded(draw, (28, 28, W - 28, 40), 6, (70, 75, 86, 185))
    rounded(draw, (28, 28, 28 + progress, 40), 6, RED)
    draw.text((32, 58), "เรื่องเล่าห้อง 407", font=F22, fill=MUTED)
    draw.text((W - 32, 58), "@thatslife6969", font=F22, fill=MUTED, anchor="ra")

    if scene == 0:
        shake = int(math.sin(sec * 36) * 8 * (1 - local))
        center(draw, title, 404 + shake, F72, INK, stroke=2)
        rounded(draw, (124, 642, 596, 726), 42, (255, 49, 92, 235))
        draw.text((360, 664), sub, font=F42, fill=INK, anchor="ma")
        for i in range(3):
            draw.text((360, 792 + i * 58), "ก๊อก", font=F58, fill=(255, 255, 255, 80 + i * 40), anchor="ma")
    elif scene in {1, 2, 5}:
        msg = "เปิดหน่อย หนาวมาก" if scene != 5 else "ไม่ต้องเปิดแล้ว"
        draw_phone(draw, local, msg)
        subtitle(draw, title, sub, scene, local)
    elif scene == 3:
        center(draw, "หน้าห้องว่างเปล่า", 260, F58, INK, stroke=2)
        for r in range(0, 145, 18):
            alpha = max(0, 145 - r)
            draw.ellipse((360 - r, 574 - r, 360 + r, 574 + r), outline=(130, 170, 220, alpha), width=4)
        subtitle(draw, title, sub, scene, local)
    elif scene == 4:
        center(draw, "ในกระจก...", 178, F72, INK, stroke=2)
        draw.text((360, 806), "อย่าหัน", font=F72, fill=(255, 49, 92, 215), anchor="ma", stroke_width=2, stroke_fill=BLACK)
        subtitle(draw, title, sub, scene, local)
    else:
        center(draw, title, 382, F58, INK, stroke=2)
        rounded(draw, (70, 804, 650, 902), 48, (255, 49, 92, 225))
        draw.text((360, 832), sub, font=F42, fill=INK, anchor="ma")
        draw.text((360, 936), "ตอนต่อไป: ลิฟต์ที่ไม่เคยลงชั้น 1", font=F28, fill=MUTED, anchor="ma")

    if int(sec * 9) % 17 == 0:
        for i in range(3):
            y = 150 + ((frame * 41 + i * 233) % 840)
            draw.rectangle((0, y, W, y + 5), fill=(255, 255, 255, 36))
            draw.rectangle((0, y + 7, W, y + 10), fill=(255, 49, 92, 42))
    return img.convert("RGB")


def main() -> None:
    frames_dir = OUT_DIR / "ghost_story_01_higgsfield_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(FRAMES):
        draw_frame(frame).save(frames_dir / f"frame_{frame:04d}.png", optimize=True)
    draw_frame(0).save(OUT_DIR / "ghost-story-01-higgsfield-thumb.png", optimize=True)
    print(frames_dir)


if __name__ == "__main__":
    main()
