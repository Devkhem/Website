# TikTok AI Content Agent Starter Kit

ชุดนี้คือโครงสร้างเริ่มต้นสำหรับสร้าง AI Agent ที่ช่วยทำงานคอนเทนต์ TikTok ตั้งแต่คิดไอเดีย เขียนสคริปต์ วางแผนวิดีโอ เตรียมแคปชัน จัดคิวโพสต์ และวัดผลเพื่อทำตอนต่อ

ตอนนี้มี 3 workflow:

1. `workflow/tiktok-agent-workflow.yaml` สำหรับ TikTok Shop Affiliate / ปักตะกร้า
2. `workflow/story-channel-workflow.yaml` สำหรับช่องเรื่องเล่าแบบ `ChatGPT สร้างภาพ 1 ภาพ -> Codex ทำคลิป 3 ตอน -> โพสต์ทดสอบ -> ดู retention -> ทำตอนต่อ`
3. `docs/client-video-pipeline.md` สำหรับงานลูกค้าแบบ `Google Form -> Brand Bible -> Script -> Shot List -> Still -> Google Flow -> ElevenLabs -> Premiere -> Review`

## Client Video Pipeline

ใช้ workflow นี้เมื่อรับงานทำคลิปให้ลูกค้าผ่าน Google Form

```bash
python3 scripts/run_client_pipeline.py new --responses data/sample_form_responses.csv
python3 scripts/run_client_pipeline.py sync <job-id>
python3 scripts/generate_voiceover.py <job-id> --execute
```

`sync` จะดูว่าไฟล์ไหนมาแล้ว แล้วสร้างขั้นถัดไปให้เอง ทั้ง prompt ของ Brand Bible/Script/Shot List,
prompt ภาพรายช็อต, prompt สำหรับ Google Flow, สคริปต์เสียงสำหรับ ElevenLabs, ใบประกอบสำหรับ Premiere
และ review packet ที่ส่งให้ลูกค้าได้

รายละเอียดทั้งหมดอยู่ใน:

```text
docs/client-video-pipeline.md
```

## Story Channel Workflow

ใช้ workflow นี้เมื่อไม่อยากรอสินค้าและต้องการทำคอนเทนต์ทุกวันจากภาพ AI 1 ภาพ

เอกสารปฏิบัติการรายวัน:

```text
docs/daily-story-ops-workflow.md
```

กติกาสำคัญ:

```text
PLAN_READY = มีแผน แต่ยังโพสต์ไม่ได้
POST_READY = มี MP4 ผ่าน validation และอยู่บน Desktop
TEST_POSTED = โพสต์ตอนแรกแล้ว รอ retention
```

```bash
python3 scripts/run_story_channel_plan.py
```

เลือกซีรีส์เฉพาะ:

```bash
python3 scripts/run_story_channel_plan.py --series-id room-407
```

ผลลัพธ์จะอยู่ใน:

```text
outputs/<วันที่>/chatgpt-image-prompt.txt
outputs/<วันที่>/story-channel-plan.md
outputs/<วันที่>/story_posting_queue.csv
outputs/<วันที่>/episode-01-package.md
outputs/<วันที่>/episode-02-package.md
outputs/<วันที่>/episode-03-package.md
```

หลังโพสต์ ให้กรอกผลใน (คอลัมน์ `measured_after_hours` ใส่ 2 หรือ 24 ตามรอบที่วัด
เกณฑ์ตัดสินใช้แถวที่วัดตอน 2 ชั่วโมง):

```text
data/story_metrics.csv
```

ถ้าเจอ `API Error: 400 Could not process image` ตอนส่งภาพเดิมเข้า image variation/edit API ให้สร้างไฟล์ square/RGB ก่อน:

```bash
python3 scripts/prepare_api_image.py outputs/<วันที่>/room-407-chatgpt-keyvisual.png
```

แล้วใช้ไฟล์ `*-api-square.png` ที่สร้างออกมาแทนภาพแนวตั้ง 9:16 เดิม

เกณฑ์ตัดสิน:

- ยังไม่มี retention: โพสต์ตอนแรกก่อน ตอนที่เหลือรอผล (ดูคอลัมน์ `post_status`)
- Retention >= 35%: ทำตอนต่อจาก premise เดิม
- Retention 25-34%: ใช้ภาพเดิม แต่เปลี่ยน hook
- Retention < 20%: เปลี่ยน premise/location

## การติดตั้ง

`run_daily_plan.py` กับ `run_story_channel_plan.py` ใช้ Python มาตรฐาน รันได้เลย
ส่วน client pipeline ต้องใช้ Pillow (ตรวจไฟล์ภาพ) และ ffmpeg/ffprobe (ตรวจคลิป เสียง ไฟล์ final)
เช่นเดียวกับ `prepare_api_image.py` และ `render_story_triplet_from_image.py`

```bash
python3 -m pip install -r requirements.txt
```

## สิ่งที่ Agent ทำ

1. อ่านโปรไฟล์แบรนด์และสินค้าที่มีอยู่
2. คำนวณ gap จากเป้าคอมมิชชัน 30,000 บาทต่อสัปดาห์
3. ให้คะแนนสินค้าเพื่อเลือกตัวที่น่าทำคอนเทนต์วันนี้
4. สร้างไอเดียวิดีโอแบบขายของแต่ไม่แข็ง
5. เขียน hook, สคริปต์พูด, shot list และ caption
6. สร้าง posting queue ที่พร้อมนำไปโพสต์
7. เว้นจุดอนุมัติก่อนโพสต์จริง เพื่อกันความผิดพลาดเรื่องราคา เคลมสินค้า และบัญชี TikTok

## ใช้งานทันที

แก้สินค้าในไฟล์:

```text
data/products.csv
```

ตั้งค่าบัญชี TikTok เป้าหมายในไฟล์:

```text
data/tiktok_account.json
```

แล้วรัน:

```bash
python3 scripts/run_daily_plan.py
```

เช็กความพร้อมในการเชื่อม TikTok Developer API:

```bash
python3 scripts/check_tiktok_connection.py
```

ผลลัพธ์จะอยู่ใน:

```text
outputs/<วันที่>/daily-content-plan.md
outputs/<วันที่>/posting_queue.csv
```

ตัวอย่างใส่เป้าหมายของวัน:

```bash
python3 scripts/run_daily_plan.py --goal "เพิ่มยอดกดตะกร้าสินค้าสุขภาพสำหรับคนทำงานออฟฟิศ"
```

คำนวณจำนวนออเดอร์ที่ต้องได้เพื่อไปถึง 30,000 บาทต่อสัปดาห์:

```bash
python3 scripts/calculate_revenue_target.py
```

## โครงสร้างไฟล์

```text
data/
  tiktok_account.json      บัญชี TikTok เป้าหมายสำหรับ workflow
  brand_profile.json       โปรไฟล์แบรนด์ กลุ่มเป้าหมาย โทนเสียง
  products.csv             รายการสินค้าสำหรับปักตะกร้า
  revenue_targets.json     เป้ารายได้และ scenario คอมมิชชัน
  client_intake_fields.json map คำถาม Google Form และค่า ElevenLabs
  sample_form_responses.csv ตัวอย่างคำตอบฟอร์มไว้ลองรัน
  story_series.json        premise และ episode ของช่องเรื่องเล่า
  story_metrics.csv        ผล retention ของแต่ละตอน
docs/
  daily-story-ops-workflow.md ขั้นตอนรายวันของช่องเรื่องเล่า
  client-video-pipeline.md งานลูกค้าตั้งแต่ Google Form ถึงส่ง Review
  tiktok-account-connection.md วิธีเชื่อมบัญชี TikTok และข้อจำกัดการโพสต์จริง
  tiktok-developer-setup.md ขั้นตอนตั้งค่า TikTok Developer app
  netlify-verification-deploy.md วิธี deploy verification file ด้วย Netlify
  agent-contract.md        สัญญาการทำงานของ Agent
  implementation-options.md วิธีต่อยอดเป็นระบบจริง
  weekly-30000-target-plan.md แผนไปให้ถึงคอมมิชชัน 30,000 บาทต่อสัปดาห์
requirements.txt           Pillow สำหรับสคริปต์ที่ทำงานกับรูป/วิดีโอ
prompts/
  content_idea_agent.md    Prompt สำหรับคิดไอเดีย
  script_agent.md          Prompt สำหรับเขียนสคริปต์
  video_agent.md           Prompt สำหรับวางแผนวิดีโอ
  publisher_agent.md       Prompt สำหรับเตรียมโพสต์
  analytics_agent.md       Prompt สำหรับวิเคราะห์ผล
scripts/
  run_daily_plan.py        สคริปต์สร้างแผนคอนเทนต์รายวัน
  run_story_channel_plan.py แผนช่องเรื่องเล่า 1 ภาพ 3 ตอน
  run_client_pipeline.py   คุม pipeline งานลูกค้าทั้งเส้น
  generate_voiceover.py    สร้าง voice-over ด้วย ElevenLabs
  render_story_triplet_from_image.py เรนเดอร์ 3 คลิปจากภาพแม่ภาพเดียว
  prepare_api_image.py     แปลงภาพให้ API รับได้
  check_tiktok_connection.py เช็ก env สำหรับ TikTok Developer
workflow/
  tiktok-agent-workflow.yaml โครงสร้าง workflow ทั้งระบบ
  story-channel-workflow.yaml โครงสร้าง workflow ช่องเรื่องเล่า
```

## ข้อควรรู้เรื่องการโพสต์

ระบบนี้เตรียมทุกอย่างให้พร้อมโพสต์ แต่การโพสต์อัตโนมัติเต็มรูปแบบต้องเชื่อมบัญชี TikTok ผ่านช่องทางที่บัญชีอนุญาต และควรมีการอนุมัติจากคนก่อนเผยแพร่จริง โดยเฉพาะคลิปที่มีราคา ส่วนลด ผลลัพธ์จากสินค้า หรือคำเคลมด้านสุขภาพ/ความงาม
