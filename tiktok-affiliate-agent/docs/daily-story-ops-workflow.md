# Daily Story Ops Workflow

เป้าหมาย: ทำคอนเทนต์ TikTok Story ให้โพสต์ได้จริงทุกวัน โดยไม่สับสนระหว่าง "มีแผน" กับ "มีคลิปพร้อมโพสต์"

Workflow หลัก:

```text
เลือก premise -> สร้าง prompt ภาพ -> สร้าง/วางภาพแม่ -> เรนเดอร์ 3 คลิป -> ตรวจไฟล์ -> โพสต์ตอนแรก -> กรอก retention -> ตัดสินใจตอนต่อ
```

## Stage 0: Input Check

เช็คว่ามีผลลัพธ์วันก่อนหรือยัง:

```bash
cat data/story_metrics.csv
```

การตัดสินใจ:

- ถ้ามี retention >= 35%: ทำต่อ premise เดิม
- ถ้ามี retention 25-34%: ใช้ premise เดิม แต่เปลี่ยน hook
- ถ้า retention < 20%: เปลี่ยน premise
- ถ้ายังไม่มี retention: ทดสอบ premise ใหม่หรือโพสต์ตอนแรกที่มีอยู่ก่อน

## Stage 1: Create Daily Plan

สร้างแผนรายวัน:

```bash
python3 scripts/run_story_channel_plan.py --date YYYY-MM-DD --series-id SERIES_ID
```

ตัวอย่าง:

```bash
python3 scripts/run_story_channel_plan.py --date 2026-05-20 --series-id laundry-24
```

ไฟล์ที่ต้องได้:

```text
outputs/YYYY-MM-DD/chatgpt-image-prompt.txt
outputs/YYYY-MM-DD/story-channel-plan.md
outputs/YYYY-MM-DD/story_posting_queue.csv
outputs/YYYY-MM-DD/episode-01-package.md
outputs/YYYY-MM-DD/episode-02-package.md
outputs/YYYY-MM-DD/episode-03-package.md
```

สถานะหลัง stage นี้:

```text
มีแผน แต่ยังโพสต์ไม่ได้
```

## Stage 2: Create Key Visual

เอา prompt จาก:

```text
outputs/YYYY-MM-DD/chatgpt-image-prompt.txt
```

ไปสร้างภาพด้วย ChatGPT image generation

ชื่อไฟล์ภาพแม่ที่ควรใช้:

```text
outputs/YYYY-MM-DD/<series-id>-keyvisual.png
```

กติกาภาพ:

- ต้องเป็น 9:16 หรือ crop เป็น 9:16 ได้
- ต้องดูเหมือนภาพมือถือจริง / CCTV / found footage
- ห้ามเป็นโปสเตอร์ผี
- ห้ามมีตัวหนังสือในภาพ
- ห้ามมีผีชัดจนตลก

สถานะหลัง stage นี้:

```text
มีภาพแม่ แต่ยังโพสต์ไม่ได้
```

## Stage 3: Render 3 Clips

ถ้าเป็น template `room-407` ให้ใช้:

```bash
python3 -m pip install -r requirements.txt   # ครั้งแรกครั้งเดียว renderer ต้องใช้ Pillow และเครื่องต้องมี ffmpeg
python3 scripts/render_story_triplet_from_image.py \
  --image outputs/YYYY-MM-DD/<series-id>-keyvisual.png \
  --out outputs/YYYY-MM-DD
```

ผลลัพธ์ที่ต้องได้:

```text
outputs/YYYY-MM-DD/videos/<series-id>-ep1-tiktok.mp4
outputs/YYYY-MM-DD/videos/<series-id>-ep2-tiktok.mp4
outputs/YYYY-MM-DD/videos/<series-id>-ep3-tiktok.mp4
```

หมายเหตุ: ตอนนี้ renderer ยัง hard-code copy ของ `room-407` อยู่ ถ้าจะใช้ premise ใหม่จริง เช่น `laundry-24` ต้องปรับ script text/episodes ให้ตรง premise ก่อน render

สถานะหลัง stage นี้:

```text
มี MP4 แต่ยังต้องตรวจไฟล์ก่อนโพสต์
```

## Stage 4: Validate Post-Ready Files

เช็คไฟล์ด้วย ffmpeg:

```bash
ffmpeg -v error -i outputs/YYYY-MM-DD/videos/<clip>.mp4 -f null -
```

เช็คสเปก:

```bash
ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=codec_type,codec_name,width,height,r_frame_rate \
  -of json outputs/YYYY-MM-DD/videos/<clip>.mp4
```

ต้องผ่าน:

- 720x1280 หรือ 1080x1920
- 30fps
- H.264 video
- AAC audio
- 20-35 วินาที
- ffmpeg decode ไม่มี error

คัดลอกไป Desktop:

```bash
cp outputs/YYYY-MM-DD/videos/<clip>.mp4 ~/Desktop/
```

สถานะหลัง stage นี้:

```text
โพสต์ได้จริง
```

## Stage 5: Post Test

โพสต์ทีละตอนเท่านั้น:

1. โพสต์ Episode 1
2. รอ 2 ชั่วโมง
3. กรอก metrics
4. ค่อยตัดสินใจโพสต์ Episode 2

ห้ามโพสต์ 3 ตอนรวดถ้ายังไม่มี retention

## Stage 6: Record Metrics

กรอกที่:

```text
data/story_metrics.csv
```

ช่องที่ต้องกรอก:

```text
date,series_id,episode,clip_id,posting_time,views,avg_watch_time_seconds,retention_percent,likes,comments,shares,saves,profile_visits,notes,next_action
```

ตัวอย่าง:

```csv
2026-05-21,room-407,1,room-407-ep1,12:00,1200,7.8,36,88,12,3,9,4,hook ดี ทำต่อ,keep
```

## Stage 7: Decide Next Action

Decision rule:

```text
retention >= 35%  -> keep: ทำตอนต่อ / ลง episode 2
retention 25-34% -> rewrite_hook: ใช้ภาพเดิม แต่เปลี่ยน 2 วินาทีแรก
retention < 20%  -> kill: เปลี่ยน premise/location
```

## Current Post-Ready Inventory

ตอนนี้ไฟล์ที่โพสต์ได้จริง:

```text
/Users/cjproduction/Desktop/room-407-ep1-tiktok.mp4
/Users/cjproduction/Desktop/room-407-ep2-tiktok.mp4
/Users/cjproduction/Desktop/room-407-ep3-tiktok.mp4
```

ให้โพสต์แค่:

```text
room-407-ep1-tiktok.mp4
```

ก่อน แล้วค่อยดู retention

## Definition Of Done

งานแต่ละวันจะถือว่าเสร็จได้แค่ 1 ใน 3 สถานะนี้:

### PLAN_READY

มี prompt, plan, queue แต่ยังไม่มี MP4

### POST_READY

มี MP4 ผ่าน validation และอยู่บน Desktop

### TEST_POSTED

โพสต์ Episode 1 แล้ว และรอ retention

ห้ามเรียก PLAN_READY ว่า "โพสต์ได้"
