#!/usr/bin/env python3
"""Re-render room-407 episodes with correct Thai text via ffmpeg libass."""

from __future__ import annotations

import math
import random
import struct
import subprocess
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC_IMAGE = ROOT / "outputs" / "2026-05-14" / "room-407-chatgpt-keyvisual.png"
OUT_DIR = ROOT / "outputs" / "2026-05-14" / "videos"
DESKTOP = Path.home() / "Desktop"
FONT_FILE = "/System/Library/Fonts/Supplemental/Thonburi.ttc"

W, H = 720, 1280
FPS = 30
CLIP_DURATION = 22
FRAMES = FPS * CLIP_DURATION
SR = 44100

RED = "#ff315c"
BLACK = "#050507"

EPISODES = [
    {
        "id": "room-407-ep1",
        "beats": [
            (0.0, 2.6,  "อย่าเปิดประตู\\Nหลังตี 3",   "ฟังให้จบก่อนนอน",          True),
            (2.6, 6.4,  "คืนนั้นผมนอน\\Nห้อง 407 คนเดียว", "ทั้งชั้นเงียบผิดปกติ",   False),
            (6.4, 10.8, "ก๊อก... ก๊อก... ก๊อก...",      "เสียงมาจากหน้าประตู",      False),
            (10.8,15.8, "ผมเปิดตาแมว",                  "หน้าห้องไม่มีใคร",          False),
            (15.8,20.8, "แต่โทรศัพท์เด้งขึ้นมา",        '“เปิดหน่อย หนาวมาก”',  True),
            (20.0,22.0, "ถ้าเป็นคุณ",                   "จะเปิดไหม?",                True),
        ],
        "caption": "อย่าเปิดประตูหลังตี 3 ฟังให้จบแล้วบอกทีว่าคุณจะเปิดไหม",
    },
    {
        "id": "room-407-ep2",
        "beats": [
            (0.0, 2.6,  "เบอร์ที่ปิดไปแล้ว\\Nส่งข้อความมา", "03:07",                   True),
            (2.6, 6.8,  "ข้อความแรกเขียนว่า",            '"คุณอยู่คนเดียวใช่ไหม"',  False),
            (6.8, 11.2, "ผมจำเบอร์นั้นได้",              "รูมเมตที่ย้ายออกไปเมื่อปีก่อน", False),
            (11.2,16.4, "ข้อความต่อมา",                  '"อย่ามองตาแมว"',            True),
            (16.4,20.6, "แต่ผมมองไปแล้ว",                "ในเงาประตูมีคนยืนอยู่",    True),
            (20.0,22.0, "แล้วแชตสุดท้ายก็ขึ้น",          '"เขาเห็นคุณแล้ว"',         True),
        ],
        "caption": "เบอร์ที่ปิดไปแล้ว ส่งข้อความมา ถ้าเจอแบบนี้คุณจะทำยังไง",
    },
    {
        "id": "room-407-ep3",
        "beats": [
            (0.0, 2.8,  "ผมไม่เห็นใคร\\Nหน้าห้อง",      "แต่กระจกเห็น",              True),
            (2.8, 7.0,  "ปลายทางเดินมีเงา",              "ยืนนิ่งอยู่ในกรอบกระจก",   False),
            (7.0, 11.4, "ผมหันกลับไปดู",                 "ทางเดินว่างเปล่า",          False),
            (11.4,16.2, "แต่ในจอมือถือ",                 "เงานั้นใกล้กว่าเดิม",       True),
            (16.2,20.8, "ข้อความสุดท้ายส่งมา",           '"ไม่ต้องเปิดแล้ว"',         True),
            (20.0,22.0, '"เราเข้ามาแล้ว"',               "คืนนี้อย่าหันไปมองกระจก",  True),
        ],
        "caption": "ผมไม่เห็นใครหน้าห้อง แต่กระจกเห็น ตอนจบคือไม่โอเคเลย",
    },
]


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def active_beat(episode: dict, sec: float):
    for idx, (*timing, title, sub, danger) in enumerate(episode["beats"]):
        start, end = timing
        if start <= sec < end:
            return idx, title, sub, danger, (sec - start) / (end - start)
    *timing, title, sub, danger = episode["beats"][-1]
    return len(episode["beats"]) - 1, title, sub, danger, 1.0


def background_only(src: Image.Image, sec: float, ep_idx: int, beat_idx: int) -> Image.Image:
    zoom_base = [1.0, 1.035, 1.065][ep_idx]
    zoom = zoom_base + 0.025 * (sec / CLIP_DURATION) + 0.012 * math.sin(sec * 0.45 + ep_idx)
    resized = src.resize((int(W * zoom), int(H * zoom)), Image.Resampling.LANCZOS)
    max_x = resized.width - W
    max_y = resized.height - H
    x = int(max_x * (0.46 + 0.12 * math.sin(sec * 0.18 + beat_idx)))
    y = int(max_y * (0.50 + 0.10 * math.cos(sec * 0.22 + ep_idx)))
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


def draw_hud_only(draw: ImageDraw.ImageDraw, sec: float, ep_idx: int):
    """Progress bar only — no Thai text."""
    from PIL import ImageFont
    fnt = ImageFont.load_default()
    progress = int((W - 56) * sec / CLIP_DURATION)
    draw.rounded_rectangle((28, 28, W - 28, 40), radius=6, fill=(70, 75, 86, 185))
    draw.rounded_rectangle((28, 28, 28 + progress, 40), radius=6, fill=(255, 49, 92, 255))


def render_bg_frames(src: Image.Image, episode: dict, ep_idx: int, frames_dir: Path):
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(FRAMES):
        sec = frame / FPS
        beat_idx, _title, _sub, _danger, _local = active_beat(episode, sec)
        img = background_only(src, sec, ep_idx, beat_idx)
        draw = ImageDraw.Draw(img)
        draw_hud_only(draw, sec, ep_idx)
        img.convert("RGB").save(frames_dir / f"frame_{frame:04d}.jpg", quality=92)


def ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:06.3f}"


def make_ass(episode: dict, ep_idx: int) -> str:
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Title style — large centered, white, black outline
        "Style: Title,Thonburi,52,&H00F4F7FB,&H000000FF,&H00050507,&HAA000000,-1,0,0,0,100,100,0,0,1,2,0,5,30,30,160,1",
        # Sub style — small, muted/red
        "Style: Sub,Thonburi,30,&H00C2B3AA,&H000000FF,&H00050507,&HAA000000,0,0,0,0,100,100,0,0,1,1,0,2,30,30,140,1",
        # SubRed
        "Style: SubRed,Thonburi,30,&H005C31FF,&H000000FF,&H00050507,&HAA000000,0,0,0,0,100,100,0,0,1,1,0,2,30,30,140,1",
        # Hook style for beat 0 — extra large
        "Style: Hook,Thonburi,64,&H00F4F7FB,&H000000FF,&H00050507,&HCC000000,-1,0,0,0,100,100,0,0,1,3,0,5,30,30,380,1",
        # HookSub — pill button text
        "Style: HookSub,Thonburi,38,&H00F4F7FB,&H000000FF,&H005C31FF,&H00000000,-1,0,0,0,100,100,0,0,3,0,0,2,60,60,530,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for idx, (*timing, title, sub, danger) in enumerate(episode["beats"]):
        start, end = timing
        sub_style = "SubRed" if danger else "Sub"

        if idx == 0:
            # Beat 0: large hook text + pill subtitle
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Hook,,0,0,0,,{title}")
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},HookSub,,0,0,0,,{sub}")
        else:
            # Card box via \bord + alignment
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Title,,0,0,0,,{{\\pos({W//2},{H-310})\\an5\\bord2\\shad0}}{title}")
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},{sub_style},,0,0,0,,{{\\pos({W//2},{H-130})\\an5}}{sub}")

    # Header labels (small, not Thai-heavy)
    ep_num = ep_idx + 1
    lines.append(f"Dialogue: 0,{ts(0)},{ts(CLIP_DURATION)},Sub,,0,0,0,,{{\\pos(32,68)\\an7\\alpha&H44&}}ห้อง 407 ตอน {ep_num}")
    lines.append(f"Dialogue: 0,{ts(0)},{ts(CLIP_DURATION)},Sub,,0,0,0,,{{\\pos({W-32},68)\\an9\\alpha&H44&}}@thatslife6969")

    return "\n".join(lines)


def encode_episode(ep_id: str, frames_dir: Path, audio_path: Path, ass_path: Path, out_path: Path):
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%04d.jpg"),
        "-i", str(audio_path),
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-t", str(CLIP_DURATION),
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def write_audio(path: Path) -> None:
    if path.exists():
        return
    samples = int(CLIP_DURATION * SR)
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


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = Image.open(SRC_IMAGE).convert("RGBA")
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
    src = src.crop((left, top, left + W, top + H))

    audio_path = OUT_DIR / "room-407-triplet-ambient.wav"
    write_audio(audio_path)

    for ep_idx, episode in enumerate(EPISODES):
        ep_id = episode["id"]
        print(f"\n[{ep_idx+1}/3] {ep_id}")

        frames_dir = OUT_DIR / f"{ep_id}_frames_v2"
        print(f"  rendering {FRAMES} bg frames...")
        render_bg_frames(src, episode, ep_idx, frames_dir)

        ass_path = OUT_DIR / f"{ep_id}.ass"
        ass_content = make_ass(episode, ep_idx)
        ass_path.write_text(ass_content, encoding="utf-8")
        print(f"  wrote {ass_path.name}")

        out_mp4 = DESKTOP / f"{ep_id}-tiktok.mp4"
        print(f"  encoding → {out_mp4.name}")
        encode_episode(ep_id, frames_dir, audio_path, ass_path, out_mp4)
        print(f"  done: {out_mp4}")

    print("\nAll 3 episodes rendered with correct Thai font.")


if __name__ == "__main__":
    main()
