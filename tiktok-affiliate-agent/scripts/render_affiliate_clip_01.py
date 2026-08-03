#!/usr/bin/env python3
"""Render a vertical TikTok affiliate draft video for Clip 1."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "videos"
W, H = 1080, 1920
FPS = 24
DURATION = 26
FRAMES = FPS * DURATION

BG = "#f6fbff"
INK = "#12131a"
MUTED = "#566070"
PINK = "#fe2c55"
CYAN = "#25f4ee"
BLUE = "#2563eb"
WHITE = "#ffffff"


SCENES = [
    (0, 4.0, "ถ้าน้ำแข็งละลายเร็ว\nระหว่างวัน...", "ลองดูชิ้นนี้ก่อนซื้อ"),
    (4.0, 8.0, "แก้วเก็บความเย็น\nพกพา", "เหมาะกับใช้ทุกวัน"),
    (8.0, 14.0, "ลองใส่น้ำแข็ง\nแล้วพกออกไปข้างนอก", "ดูว่าระหว่างวันเป็นยังไง"),
    (14.0, 20.0, "จุดที่น่าสนใจ", "พกง่าย • ใช้ซ้ำได้ • ดูแลง่าย"),
    (20.0, 26.0, "ถ้ากำลังหาแก้วใช้ทุกวัน", "กดดูรายละเอียดในตะกร้าได้เลย"),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Thonburi.ttc",
        "/System/Library/Fonts/ThonburiUI.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size, index=1 if bold and p.endswith(".ttc") else 0)
    return ImageFont.load_default()


TITLE = font(86, True)
SUB = font(52)
SMALL = font(34)
CTA = font(48, True)


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def active_scene(sec: float):
    for start, end, title, sub in SCENES:
        if start <= sec < end:
            local = (sec - start) / (end - start)
            return start, end, title, sub, local
    start, end, title, sub = SCENES[-1]
    return start, end, title, sub, 1.0


def center_text(draw: ImageDraw.ImageDraw, text: str, y: int, fnt, fill: str, spacing: int = 12) -> int:
    lines = text.split("\n")
    total_h = 0
    boxes = []
    for line in lines:
        box = draw.textbbox((0, 0), line, font=fnt)
        boxes.append(box)
        total_h += (box[3] - box[1]) + spacing
    total_h -= spacing
    current_y = y
    for line, box in zip(lines, boxes):
        tw = box[2] - box[0]
        draw.text(((W - tw) / 2, current_y), line, font=fnt, fill=fill)
        current_y += (box[3] - box[1]) + spacing
    return y + total_h


def rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill: str, outline: str | None = None, width: int = 2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_cup(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float, sec: float):
    cup_w = int(300 * scale)
    cup_h = int(470 * scale)
    x0 = cx - cup_w // 2
    y0 = cy - cup_h // 2
    x1 = cx + cup_w // 2
    y1 = cy + cup_h // 2
    rounded(draw, (x0, y0, x1, y1), int(60 * scale), "#dff7ff", "#111827", int(5 * scale))
    rounded(draw, (x0 + 24, y0 + 28, x1 - 24, y0 + 88), int(24 * scale), WHITE, "#111827", int(4 * scale))
    draw.line((x0 + 34, y0 + 150, x1 - 34, y0 + 150), fill=CYAN, width=int(7 * scale))
    draw.line((x0 + 34, y0 + 220, x1 - 34, y0 + 220), fill=PINK, width=int(7 * scale))
    rounded(draw, (x0 + 60, y1 - 84, x1 - 60, y1 - 28), int(28 * scale), "#111827")

    # Ice cubes orbit lightly.
    for i in range(5):
        angle = sec * 1.8 + i * 1.25
        ix = cx + int(math.cos(angle) * 210 * scale)
        iy = cy - int(120 * scale) + int(math.sin(angle) * 70 * scale)
        size = int((42 + i * 4) * scale)
        rounded(draw, (ix - size, iy - size, ix + size, iy + size), int(14 * scale), WHITE, CYAN, int(3 * scale))


def draw_frame(frame: int) -> Image.Image:
    sec = frame / FPS
    _, _, title, sub, local = active_scene(sec)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Soft background blobs as blurred layer.
    blobs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    bd.ellipse((-180, 120, 360, 660), fill=(37, 244, 238, 70))
    bd.ellipse((760, 1160, 1240, 1700), fill=(254, 44, 85, 58))
    bd.ellipse((120, 1420, 480, 1780), fill=(37, 99, 235, 42))
    img = Image.alpha_composite(img.convert("RGBA"), blobs.filter(ImageFilter.GaussianBlur(45))).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw.text((64, 62), "@thatslife6969", font=SMALL, fill=MUTED)
    progress_w = int((W - 128) * min(sec / DURATION, 1))
    rounded(draw, (64, 118, W - 64, 132), 7, "#d8e0ea")
    rounded(draw, (64, 118, 64 + progress_w, 132), 7, PINK)

    pop = 0.88 + 0.12 * ease_out(min(local / 0.35, 1))
    draw_cup(draw, W // 2, 720, pop, sec)

    text_y = 1045 + int((1 - ease_out(min(local / 0.35, 1))) * 40)
    center_text(draw, title, text_y, TITLE, INK)
    sub_y = text_y + 230 if "\n" in title else text_y + 126
    center_text(draw, sub, sub_y, SUB, PINK)

    if sec >= 20:
        pulse = 1 + 0.035 * math.sin(sec * 7)
        bw, bh = int(760 * pulse), int(104 * pulse)
        rounded(draw, ((W - bw)//2, 1600, (W + bw)//2, 1600 + bh), 52, INK)
        center_text(draw, "ดูสินค้าในตะกร้า", 1624, CTA, WHITE)
    else:
        rounded(draw, (138, 1600, W - 138, 1704), 52, WHITE, "#d8e0ea", 3)
        center_text(draw, "ทดสอบสั้น ๆ ก่อนตัดสินใจซื้อ", 1628, CTA, INK)

    draw.text((64, 1812), "ตรวจราคาและรีวิวร้านค้าก่อนซื้อ", font=SMALL, fill=MUTED)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = OUT_DIR / "clip01_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(FRAMES):
        draw_frame(frame).save(frames_dir / f"frame_{frame:04d}.png")
    print(frames_dir)


if __name__ == "__main__":
    main()

