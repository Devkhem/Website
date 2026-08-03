#!/usr/bin/env python3
"""Render a sharper TikTok affiliate video for Clip 1.

This version is intentionally more sales-oriented than the first draft:
fast hook, product proof frames, stronger contrast, and TikTok-safe claims.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "videos"
W, H = 720, 1280
FPS = 30
DURATION = 19
FRAMES = FPS * DURATION

INK = "#101114"
PAPER = "#f8f7f2"
CREAM = "#fff8df"
MINT = "#3ee6c4"
RED = "#ff2f5f"
YELLOW = "#ffe35b"
BLUE = "#2d6df6"
BLACK = "#08090b"
WHITE = "#ffffff"
GRAY = "#6b7280"
GREEN = "#18a558"


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


F_26 = font(26)
F_30 = font(30, True)
F_34 = font(34, True)
F_42 = font(42, True)
F_54 = font(54, True)
F_66 = font(66, True)
F_82 = font(82, True)
F_96 = font(96, True)


def ease(t: float) -> float:
    t = max(0, min(1, t))
    return 1 - (1 - t) ** 3


def smooth(t: float) -> float:
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill: str, outline: str | None = None, width: int = 1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_box(draw: ImageDraw.ImageDraw, text: str, xy, fnt, fill: str, anchor: str = "la", stroke=0):
    draw.text(xy, text, font=fnt, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=BLACK)


def center_text(draw: ImageDraw.ImageDraw, text: str, y: int, fnt, fill: str, spacing: int = 6, stroke: int = 0):
    lines = text.split("\n")
    boxes = [draw.textbbox((0, 0), line, font=fnt, stroke_width=stroke) for line in lines]
    total = sum(b[3] - b[1] for b in boxes) + spacing * (len(lines) - 1)
    cy = y
    for line, b in zip(lines, boxes):
        tw = b[2] - b[0]
        draw.text(((W - tw) / 2, cy), line, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=BLACK)
        cy += (b[3] - b[1]) + spacing
    return y + total


def add_shadow_layer(img: Image.Image, rect, radius: int = 32, blur: int = 18, alpha: int = 70):
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x0, y0, x1, y1 = rect
    sd.rounded_rectangle((x0, y0 + 10, x1, y1 + 10), radius=radius, fill=(0, 0, 0, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(img.convert("RGBA"), shadow)


def background(sec: float) -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    shift = int(math.sin(sec * 0.9) * 18)
    d.rectangle((0, 0, W, 128), fill=(8, 9, 11, 255))
    d.polygon([(0, 166 + shift), (W, 82 - shift), (W, 246), (0, 330)], fill=(255, 227, 91, 220))
    d.polygon([(0, 1010), (W, 910 + shift), (W, H), (0, H)], fill=(62, 230, 196, 150))
    for x in range(-120, W + 120, 92):
        d.line((x + shift, 260, x + 210 + shift, 980), fill=(0, 0, 0, 26), width=3)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def draw_product(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float, sec: float):
    # Hand, cup, lid, straw: stylized but more tactile than the first draft.
    wobble = math.sin(sec * 5.4) * 4
    hand_y = cy + int(228 * scale)
    rounded(draw, (cx - int(186 * scale), hand_y - int(32 * scale), cx + int(152 * scale), hand_y + int(56 * scale)), int(38 * scale), "#f0bd91")
    rounded(draw, (cx + int(92 * scale), hand_y - int(86 * scale), cx + int(182 * scale), hand_y + int(28 * scale)), int(44 * scale), "#f0bd91")

    cup_w = int(218 * scale)
    cup_h = int(476 * scale)
    x0, y0 = cx - cup_w // 2, cy - cup_h // 2 + int(wobble)
    x1, y1 = cx + cup_w // 2, cy + cup_h // 2 + int(wobble)
    rounded(draw, (x0, y0, x1, y1), int(48 * scale), "#d9fbff", BLACK, int(5 * scale))
    rounded(draw, (x0 + int(16 * scale), y0 + int(20 * scale), x1 - int(16 * scale), y0 + int(78 * scale)), int(22 * scale), WHITE, BLACK, int(4 * scale))
    rounded(draw, (x0 + int(62 * scale), y1 - int(70 * scale), x1 - int(62 * scale), y1 - int(28 * scale)), int(22 * scale), BLACK)
    draw.line((cx + int(18 * scale), y0 - int(126 * scale), cx + int(78 * scale), y0 + int(42 * scale)), fill=BLACK, width=int(12 * scale))
    draw.line((cx + int(18 * scale), y0 - int(126 * scale), cx - int(42 * scale), y0 - int(162 * scale)), fill=BLACK, width=int(12 * scale))
    draw.line((x0 + int(30 * scale), y0 + int(142 * scale), x1 - int(30 * scale), y0 + int(142 * scale)), fill=BLUE, width=int(7 * scale))
    draw.line((x0 + int(30 * scale), y0 + int(216 * scale), x1 - int(30 * scale), y0 + int(216 * scale)), fill=RED, width=int(7 * scale))
    for i in range(4):
        angle = sec * 2.3 + i * 1.57
        ix = cx + int(math.cos(angle) * 156 * scale)
        iy = cy - int(152 * scale) + int(math.sin(angle) * 58 * scale)
        s = int((25 + i * 3) * scale)
        rounded(draw, (ix - s, iy - s, ix + s, iy + s), int(8 * scale), WHITE, MINT, int(3 * scale))


def draw_phone_review(draw: ImageDraw.ImageDraw, x: int, y: int, sec: float):
    rounded(draw, (x, y, x + 232, y + 408), 34, BLACK)
    rounded(draw, (x + 12, y + 18, x + 220, y + 390), 24, "#fbfbf7")
    rounded(draw, (x + 44, y + 42, x + 188, y + 58), 8, "#d1d5db")
    draw.text((x + 28, y + 88), "4.8", font=F_54, fill=BLACK)
    draw.text((x + 132, y + 108), "★★★★★", font=F_26, fill="#f6b900")
    draw.text((x + 28, y + 158), "8.9k รีวิว", font=F_30, fill=GRAY)
    rounded(draw, (x + 28, y + 214, x + 204, y + 270), 18, RED)
    draw.text((x + 116, y + 224), "฿199", font=F_34, fill=WHITE, anchor="ma")
    draw.text((x + 28, y + 302), "เช็กร้านก่อนซื้อ", font=F_26, fill=BLACK)
    draw.text((x + 28, y + 334), "ราคาอาจเปลี่ยนได้", font=F_26, fill=GRAY)


def badge(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, color: str):
    rounded(draw, (x, y, x + 240, y + 52), 26, color, BLACK, 3)
    draw.text((x + 120, y + 11), text, font=F_26, fill=BLACK if color != BLACK else WHITE, anchor="ma")


def scene_for(sec: float) -> tuple[int, float]:
    cuts = [0, 2.4, 5.8, 9.6, 13.6, 16.2, 19]
    for i in range(len(cuts) - 1):
        if cuts[i] <= sec < cuts[i + 1]:
            return i, (sec - cuts[i]) / (cuts[i + 1] - cuts[i])
    return 5, 1


def draw_frame(frame: int) -> Image.Image:
    sec = frame / FPS
    scene, local = scene_for(sec)
    img = background(sec).convert("RGBA")
    draw = ImageDraw.Draw(img)

    progress = int((W - 64) * sec / DURATION)
    rounded(draw, (32, 30, W - 32, 42), 6, "#303238")
    rounded(draw, (32, 30, 32 + progress, 42), 6, RED)
    draw.text((36, 62), "@thatslife6969", font=F_26, fill=WHITE)

    if scene == 0:
        shake = int(math.sin(sec * 28) * 8 * (1 - local))
        center_text(draw, "น้ำแข็งละลาย\nก่อนเลิกงาน?", 170 + shake, F_82, WHITE, 8, 3)
        rounded(draw, (82, 500, 638, 594), 28, RED, BLACK, 4)
        draw.text((360, 520), "ปัญหานี้เจอบ่อยมาก", font=F_42, fill=WHITE, anchor="ma")
        draw_product(draw, 360, 870, 0.82 + 0.08 * ease(local), sec)

    elif scene == 1:
        draw.text((44, 150), "ลองเทสต์แบบบ้าน ๆ", font=F_54, fill=BLACK)
        draw.text((44, 214), "ไม่ต้องเชื่อคำโฆษณา", font=F_34, fill=BLACK)
        for i, label in enumerate(["เช้า", "กลางวัน", "เย็น"]):
            x = 62 + i * 204
            y = 372
            rounded(draw, (x, y, x + 154, y + 154), 28, WHITE, BLACK, 4)
            level = [92, 64, 38][i]
            rounded(draw, (x + 42, y + 36 + (90 - level), x + 112, y + 126), 18, "#c8fbff", BLUE, 3)
            draw.text((x + 77, y + 174), label, font=F_30, fill=BLACK, anchor="ma")
        draw_product(draw, 360, 920, 0.76, sec)
        badge(draw, "เทสต์ก่อนซื้อ", 54, 1120, YELLOW)
        badge(draw, "ไม่เคลมเวอร์", 426, 1120, MINT)

    elif scene == 2:
        img = add_shadow_layer(img, (50, 158, 670, 1054), 38, 22, 80)
        draw = ImageDraw.Draw(img)
        rounded(draw, (50, 148, 670, 1044), 38, WHITE, BLACK, 5)
        draw.text((86, 204), "ทำไมชิ้นนี้น่าสนใจ", font=F_54, fill=BLACK)
        bullets = [
            ("พกง่าย", "ถือไปออฟฟิศ/รถ/ยิม"),
            ("ใช้ซ้ำได้", "ลดแก้วทิ้งรายวัน"),
            ("ราคาเข้าถึง", "ประมาณ 199 บาท"),
            ("รีวิวเยอะ", "เช็กคะแนนร้านก่อนกด"),
        ]
        for i, (head, body) in enumerate(bullets):
            y = 318 + i * 152
            rounded(draw, (88, y, 144, y + 56), 18, MINT if i % 2 == 0 else YELLOW, BLACK, 3)
            draw.text((116, y + 8), str(i + 1), font=F_34, fill=BLACK, anchor="ma")
            draw.text((166, y - 2), head, font=F_42, fill=BLACK)
            draw.text((166, y + 50), body, font=F_30, fill=GRAY)
        draw_product(draw, 526, 930, 0.45, sec)

    elif scene == 3:
        draw.text((42, 142), "ก่อนซื้อ ดู 3 จุดนี้", font=F_54, fill=BLACK)
        cards = [
            ("ความจุ", "พอกับวันที่ใช้จริงไหม"),
            ("ฝาปิด", "แน่นพอสำหรับพกไหม"),
            ("รีวิวร้าน", "รูปจริง / ส่งไว / คืนง่าย"),
        ]
        for i, (h, b) in enumerate(cards):
            y = 270 + i * 230
            xoff = int((1 - ease(max(0, min(1, local * 1.8 - i * 0.22)))) * 80)
            rounded(draw, (54 + xoff, y, 666 + xoff, y + 162), 32, BLACK, None)
            draw.text((92 + xoff, y + 28), h, font=F_54, fill=YELLOW)
            draw.text((92 + xoff, y + 88), b, font=F_34, fill=WHITE)
        draw_phone_review(draw, 244, 932, sec)

    elif scene == 4:
        draw_product(draw, 360, 542, 1.0 + 0.04 * math.sin(sec * 4), sec)
        center_text(draw, "ถ้าจะซื้อแก้วใหม่\nดูตัวนี้เป็นตัวเลือก", 850, F_66, BLACK, 8)
        rounded(draw, (86, 1076, 634, 1160), 42, RED, BLACK, 4)
        draw.text((360, 1094), "กดดูสินค้าในตะกร้า", font=F_42, fill=WHITE, anchor="ma")
        draw.text((360, 1180), "เช็กราคา/โปร/รีวิวร้านก่อนจ่าย", font=F_26, fill=BLACK, anchor="ma")

    else:
        center_text(draw, "อย่าเพิ่งกดซื้อ\nถ้ายังไม่ได้เช็กรีวิว", 168, F_66, WHITE, 6, 3)
        draw_phone_review(draw, 78, 430, sec)
        draw_product(draw, 500, 654, 0.68, sec)
        rounded(draw, (72, 1080, 648, 1168), 44, BLACK)
        draw.text((360, 1100), "เปิดตะกร้าแล้วเทียบราคา", font=F_42, fill=WHITE, anchor="ma")
        draw.text((360, 1200), "#แก้วเก็บความเย็น #TikTokShop", font=F_26, fill=BLACK, anchor="ma")

    # Subtle frame to make screenshots pop in TikTok feed.
    draw.rectangle((0, 0, W - 1, H - 1), outline=BLACK, width=8)
    return img.convert("RGB")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = OUT_DIR / "clip01_v2_premium_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(FRAMES):
        draw_frame(frame).save(frames_dir / f"frame_{frame:04d}.png", optimize=True)
    draw_frame(0).save(OUT_DIR / "clip01-v2-premium-thumb.png", optimize=True)
    print(frames_dir)


if __name__ == "__main__":
    main()
