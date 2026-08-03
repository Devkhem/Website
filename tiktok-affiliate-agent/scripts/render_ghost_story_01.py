#!/usr/bin/env python3
"""Render a generated Thai ghost-story TikTok video.

No product footage required. The clip is designed as a reusable story format:
hook, escalating evidence, final twist, and comment bait.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import random
import wave
import struct


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "videos"
W, H = 720, 1280
FPS = 30
DURATION = 32
FRAMES = FPS * DURATION
SR = 44100

BLACK = "#07080b"
INK = "#e8edf5"
DIM = "#8d96a6"
RED = "#f2385a"
GREEN = "#8dffb3"
BLUE = "#5ea1ff"
YELLOW = "#ffe066"


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
F52 = font(52, True)
F66 = font(66, True)
F82 = font(82, True)


STORY = [
    (0.0, 3.2, "ถ้าได้ยินเสียงเคาะประตู\nตอนตี 3...", "อย่าเพิ่งถามว่าใคร"),
    (3.2, 7.4, "เมื่อคืนผมนอนห้อง 407\nคนเดียวทั้งชั้น", "แต่แชตเด้งขึ้นมาแบบนี้"),
    (7.4, 12.0, "“เปิดหน่อย หนาวมาก”", "เบอร์นั้นเป็นเบอร์ของรูมเมตที่ย้ายออกไปแล้ว"),
    (12.0, 17.0, "ผมมองตาแมว...", "หน้าห้องไม่มีใคร"),
    (17.0, 22.8, "แต่ในกระจกหลังผม", "มีคนยืนใส่เสื้อกันหนาวสีเทา"),
    (22.8, 28.0, "ข้อความสุดท้ายส่งมา", "“ไม่ต้องเปิดแล้ว เราเข้ามาแล้ว”"),
    (28.0, 32.0, "ถ้าคุณอยู่ห้อง 407", "คืนนี้อย่าหันไปมองกระจก"),
]


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def active(sec: float):
    for idx, (start, end, title, sub) in enumerate(STORY):
        if start <= sec < end:
            return idx, start, end, title, sub, (sec - start) / (end - start)
    idx = len(STORY) - 1
    start, end, title, sub = STORY[-1]
    return idx, start, end, title, sub, 1.0


def rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center(draw: ImageDraw.ImageDraw, text: str, y: int, fnt, fill=INK, max_w=620, spacing=8, stroke=0):
    # Thai text can render poorly with naive character wrapping, so story copy
    # is line-broken intentionally in the script and preserved here.
    lines = text.split("\n")
    boxes = [draw.textbbox((0, 0), line, font=fnt, stroke_width=stroke) for line in lines]
    total = sum(b[3] - b[1] for b in boxes) + spacing * (len(lines) - 1)
    cy = y - total // 2
    for line, b in zip(lines, boxes):
        tw = b[2] - b[0]
        draw.text(((W - tw) / 2, cy), line, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=BLACK)
        cy += (b[3] - b[1]) + spacing


def noise_overlay(seed: int, alpha: int = 23) -> Image.Image:
    rng = random.Random(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pix = layer.load()
    for _ in range(3200):
        x = rng.randrange(W)
        y = rng.randrange(H)
        v = rng.randrange(80, 255)
        pix[x, y] = (v, v, v, alpha)
    return layer.filter(ImageFilter.GaussianBlur(0.35))


def bg_base(sec: float, scene: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BLACK).convert("RGBA")
    d = ImageDraw.Draw(img)
    flicker = 0.82 + 0.18 * math.sin(sec * 7.7) + 0.06 * math.sin(sec * 19.1)
    light = int(38 * max(0.45, min(1.0, flicker)))
    d.rectangle((0, 0, W, H), fill=(5, 7, 12, 255))
    d.polygon([(150, 0), (570, 0), (686, H), (34, H)], fill=(12 + light, 15 + light, 24 + light, 255))
    d.polygon([(248, 0), (472, 0), (514, H), (206, H)], fill=(22 + light, 26 + light, 36 + light, 255))
    for y in range(120, H, 142):
        d.line((0, y, W, y + 44), fill=(255, 255, 255, 14), width=2)
    d.rectangle((268, 250, 452, 1038), fill=(6, 7, 10, 235), outline=(85, 92, 105, 145), width=4)
    d.ellipse((332, 622, 356, 646), fill=(70, 74, 82, 255))
    d.text((360, 316), "407", font=F42, fill=(160, 168, 180, 160), anchor="ma")

    if scene >= 3:
        # Peephole glow.
        d.ellipse((262, 510, 458, 706), outline=(120, 148, 190, 160), width=5)
        d.ellipse((316, 564, 404, 652), fill=(3, 5, 8, 210))
    if scene >= 4:
        # Mirror silhouette behind viewer.
        d.rounded_rectangle((86, 224, 634, 940), radius=28, outline=(155, 170, 190, 120), width=5)
        d.rectangle((112, 254, 608, 910), fill=(18, 24, 32, 128))
        ghost_alpha = int(70 + 70 * abs(math.sin(sec * 1.5)))
        d.ellipse((318, 388, 402, 484), fill=(210, 216, 222, ghost_alpha))
        d.rounded_rectangle((276, 482, 444, 746), radius=58, fill=(170, 176, 185, ghost_alpha))
        d.line((318, 532, 242, 650), fill=(170, 176, 185, ghost_alpha), width=18)
        d.line((402, 532, 482, 650), fill=(170, 176, 185, ghost_alpha), width=18)

    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-220, -150, W + 220, H + 220), fill=180)
    vignette = Image.eval(vignette.filter(ImageFilter.GaussianBlur(95)), lambda p: 210 - p)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(vignette)
    img = Image.alpha_composite(img, dark)
    img = Image.alpha_composite(img, noise_overlay(int(sec * FPS)))
    return img


def draw_phone(draw: ImageDraw.ImageDraw, sec: float, local: float, message: str):
    x, y, w, h = 86, 250, 548, 650
    rounded(draw, (x, y, x + w, y + h), 42, (8, 9, 13, 245), (90, 100, 115, 220), 4)
    rounded(draw, (x + 22, y + 36, x + w - 22, y + h - 30), 28, (13, 18, 28, 255))
    draw.text((x + 48, y + 62), "ข้อความ", font=F34, fill=INK)
    draw.text((x + w - 52, y + 68), "03:07", font=F28, fill=DIM, anchor="ra")
    rounded(draw, (x + 48, y + 150, x + w - 48, y + 256), 28, (31, 42, 58, 255))
    draw.text((x + 76, y + 172), "ห้อง 407", font=F28, fill=DIM)
    draw.text((x + 76, y + 208), "คุณอยู่คนเดียวใช่ไหม", font=F34, fill=INK)
    show = int(len(message) * ease(local))
    rounded(draw, (x + 48, y + 310, x + w - 48, y + 444), 28, (68, 28, 43, 255), (242, 56, 90, 180), 3)
    draw.text((x + 76, y + 340), message[:show], font=F42, fill=INK)
    if int(sec * 2) % 2 == 0:
        draw.text((x + 76, y + 492), "กำลังพิมพ์...", font=F28, fill=GREEN)


def subtitle_card(draw: ImageDraw.ImageDraw, title: str, sub: str, scene: int, local: float):
    y = 1000 + int((1 - ease(local)) * 38)
    rounded(draw, (34, y, W - 34, y + 204), 30, (0, 0, 0, 190), (255, 255, 255, 42), 2)
    center(draw, title, y + 72, F42 if scene != 0 else F52, INK, max_w=610, stroke=1)
    center(draw, sub, y + 156, F28, RED if scene in {0, 5, 6} else DIM, max_w=610)


def draw_frame(frame: int) -> Image.Image:
    sec = frame / FPS
    scene, _start, _end, title, sub, local = active(sec)
    img = bg_base(sec, scene)
    draw = ImageDraw.Draw(img)

    progress = int((W - 56) * sec / DURATION)
    rounded(draw, (28, 26, W - 28, 38), 6, (58, 62, 70, 255))
    rounded(draw, (28, 26, 28 + progress, 38), 6, RED)
    draw.text((32, 54), "เรื่องเล่าห้อง 407", font=F22, fill=DIM)
    draw.text((W - 32, 54), "@thatslife6969", font=F22, fill=DIM, anchor="ra")

    if scene == 0:
        shake = int(math.sin(sec * 34) * 7 * (1 - local))
        center(draw, "อย่าเปิดประตู\nหลังตี 3", 430 + shake, F66, INK, 8, 2)
        rounded(draw, (132, 662, 588, 742), 40, RED, None)
        draw.text((360, 682), "ฟังให้จบก่อนนอน", font=F42, fill=INK, anchor="ma")
        for i in range(3):
            yy = 850 + i * 54 + int(math.sin(sec * 8 + i) * 5)
            draw.text((360, yy), "ก๊อก", font=F52, fill=(255, 255, 255, 80 + i * 45), anchor="ma")
    elif scene in {1, 2, 5}:
        msg = "เปิดหน่อย หนาวมาก" if scene != 5 else "ไม่ต้องเปิดแล้ว เราเข้ามาแล้ว"
        draw_phone(draw, sec, local, msg)
        subtitle_card(draw, title, sub, scene, local)
    elif scene == 3:
        center(draw, "หน้าห้องว่างเปล่า", 270, F66, INK, stroke=2)
        for r in range(0, 120, 18):
            alpha = max(0, 145 - r)
            draw.ellipse((360 - r, 602 - r, 360 + r, 602 + r), outline=(94, 138, 190, alpha), width=4)
        subtitle_card(draw, title, sub, scene, local)
    elif scene == 4:
        center(draw, "ในกระจก...", 150, F66, INK, stroke=2)
        draw.text((360, 842), "อย่าหัน", font=F82, fill=(242, 56, 90, int(160 + 60 * math.sin(sec * 6))), anchor="ma")
        subtitle_card(draw, title, sub, scene, local)
    else:
        center(draw, "คืนนี้", 210, F82, RED, stroke=2)
        center(draw, "อย่าหันไป\nมองกระจก", 380, F66, INK, stroke=2)
        rounded(draw, (70, 790, 650, 894), 52, (242, 56, 90, 220))
        draw.text((360, 818), "คอมเมนต์เลขห้องคุณ", font=F42, fill=INK, anchor="ma")
        draw.text((360, 930), "ตอนต่อไป: ห้องที่ไม่มีแม่บ้านกล้าเข้า", font=F28, fill=DIM, anchor="ma")

    # Glitch bars.
    if int(sec * 7) % 11 == 0:
        for i in range(3):
            y = 160 + ((frame * 37 + i * 211) % 880)
            draw.rectangle((0, y, W, y + 6), fill=(255, 255, 255, 38))
            draw.rectangle((0, y + 8, W, y + 12), fill=(242, 56, 90, 36))
    return img.convert("RGB")


def write_audio(path: Path) -> None:
    samples = int(DURATION * SR)
    rng = random.Random(407)
    with wave.open(str(path), "w") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        for n in range(samples):
            t = n / SR
            drone = 0.12 * math.sin(2 * math.pi * 43 * t) + 0.05 * math.sin(2 * math.pi * 58.7 * t)
            breath = 0.018 * rng.uniform(-1, 1)
            knock = 0.0
            for kt in [1.2, 1.55, 1.9, 13.2, 13.55, 23.7, 24.05]:
                dt = t - kt
                if 0 <= dt < 0.18:
                    knock += 0.72 * math.sin(2 * math.pi * 92 * dt) * math.exp(-dt * 28)
            beat = 0.0
            if t > 17:
                period = 0.82
                dt = (t - 17) % period
                if dt < 0.09:
                    beat += 0.26 * math.sin(2 * math.pi * 54 * dt) * math.exp(-dt * 32)
            val = max(-1, min(1, drone + breath + knock + beat))
            packed = struct.pack("<hh", int(val * 23000), int(val * 23000))
            f.writeframesraw(packed)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = OUT_DIR / "ghost_story_01_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(FRAMES):
        draw_frame(frame).save(frames_dir / f"frame_{frame:04d}.png", optimize=True)
    draw_frame(0).save(OUT_DIR / "ghost-story-01-thumb.png", optimize=True)
    write_audio(OUT_DIR / "ghost-story-01-ambient.wav")
    print(frames_dir)


if __name__ == "__main__":
    main()
