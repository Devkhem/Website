#!/usr/bin/env python3
"""Render a simple TikTok app-review demo as an animated GIF source."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "demo"
WIDTH = 1280
HEIGHT = 720
FPS = 10
SECONDS_PER_SCENE = 4
BG = "#f7f8fb"
INK = "#111827"
MUTED = "#5b6472"
PINK = "#fe2c55"
CYAN = "#25f4ee"
DARK = "#12131a"


SCENES = [
    (
        "TikTok Content Posting API Demo",
        "Devkhem TikTok Affiliate Agent",
        [
            "Goal: prepare TikTok Shop affiliate videos for @thatslife6969",
            "Posting mode: video.upload to TikTok draft/inbox",
            "Human approval is required before publishing",
        ],
    ),
    (
        "1. Creator Connects TikTok",
        "OAuth authorization",
        [
            "The creator signs in with TikTok",
            "The app requests user.info.basic and video.upload",
            "The account identity is confirmed before any upload",
        ],
    ),
    (
        "2. Agent Builds Content Plan",
        "Affiliate workflow",
        [
            "Select products from the catalog",
            "Generate hooks, captions, scripts, and shot lists",
            "Prepare posting metadata for TikTok review",
        ],
    ),
    (
        "3. Creator Reviews Content",
        "Approval gate",
        [
            "Review the video, caption, product basket, and claims",
            "Confirm the content is ready for TikTok",
            "No upload starts until the creator approves",
        ],
    ),
    (
        "4. Upload Video File",
        "Content Posting API: video.upload",
        [
            "The approved video file is uploaded to TikTok",
            "The upload is associated with the authorized creator",
            "The app stores the upload status for follow-up",
        ],
    ),
    (
        "5. TikTok Draft / Inbox",
        "Manual publishing",
        [
            "The creator opens TikTok to review the draft",
            "The creator can edit, add basket products, and publish",
            "The app never claims content was posted before confirmation",
        ],
    ),
    (
        "6. Track Results",
        "Daily optimization",
        [
            "The creator records views, cart clicks, orders, and commission",
            "The agent uses performance data to plan the next content batch",
            "Revenue target: 30,000 THB commission per week",
        ],
    ),
    (
        "End-to-End Flow Complete",
        "Safe draft upload workflow",
        [
            "Authorize -> Plan -> Approve -> Upload -> TikTok draft -> Publish manually",
            "No password collection. No scraping. No automatic publishing without approval.",
            "Domain: comdevkhem.com",
        ],
    ),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


TITLE = font(54, True)
SUBTITLE = font(34, True)
BODY = font(28)
SMALL = font(22)


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], max_width: int, font_obj, fill: str, line_gap: int = 8) -> int:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=font_obj)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += draw.textbbox((0, 0), line, font=font_obj)[3] + line_gap
    return y


def rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str | None = None, radius: int = 26, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def render_scene(index: int, title: str, subtitle: str, bullets: list[str], frame_no: int, total_frames: int) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    progress = frame_no / max(total_frames - 1, 1)

    # Decorative but restrained brand rail.
    draw.rectangle((0, 0, WIDTH, 16), fill=DARK)
    draw.rectangle((0, 16, int(WIDTH * progress), 24), fill=PINK)
    draw.rectangle((int(WIDTH * progress), 16, WIDTH, 24), fill=CYAN)

    rounded_rect(draw, (64, 76, 1216, 644), "#ffffff", "#d8dee8", 30, 2)

    draw.text((104, 112), "Devkhem TikTok Affiliate Agent", font=SMALL, fill=MUTED)
    draw.text((104, 154), title, font=TITLE, fill=INK)
    draw.text((104, 224), subtitle, font=SUBTITLE, fill=PINK)

    y = 300
    for bullet in bullets:
        rounded_rect(draw, (104, y - 8, 1176, y + 58), "#f4f7fb", None, 16, 0)
        draw.ellipse((128, y + 12, 148, y + 32), fill=CYAN)
        draw_wrapped(draw, bullet, (166, y + 4), 940, BODY, INK)
        y += 86

    # Flow footer.
    footer = "Authorize  ->  Plan  ->  Approve  ->  Upload  ->  TikTok Draft  ->  Manual Publish"
    draw.text((104, 604), footer, font=SMALL, fill=MUTED)
    draw.text((1096, 604), f"{index + 1}/{len(SCENES)}", font=SMALL, fill=MUTED)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    frames_per_scene = FPS * SECONDS_PER_SCENE
    for index, (title, subtitle, bullets) in enumerate(SCENES):
        for frame_no in range(frames_per_scene):
            frames.append(render_scene(index, title, subtitle, bullets, frame_no, frames_per_scene))

    gif_path = OUT_DIR / "tiktok-content-posting-api-demo.gif"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=False,
    )
    print(gif_path)


if __name__ == "__main__":
    main()
