# TikTok Affiliate AI Agent Starter Kit

ชุดนี้คือโครงสร้างเริ่มต้นสำหรับสร้าง AI Agent ที่ช่วยทำงานคอนเทนต์ TikTok Shop Affiliate ตั้งแต่คิดไอเดีย เลือกสินค้า เขียนสคริปต์ วางแผนวิดีโอ เตรียมแคปชัน และจัดคิวโพสต์

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
docs/
  tiktok-account-connection.md วิธีเชื่อมบัญชี TikTok และข้อจำกัดการโพสต์จริง
  tiktok-developer-setup.md ขั้นตอนตั้งค่า TikTok Developer app
  netlify-verification-deploy.md วิธี deploy verification file ด้วย Netlify
  agent-contract.md        สัญญาการทำงานของ Agent
  implementation-options.md วิธีต่อยอดเป็นระบบจริง
  weekly-30000-target-plan.md แผนไปให้ถึงคอมมิชชัน 30,000 บาทต่อสัปดาห์
prompts/
  content_idea_agent.md    Prompt สำหรับคิดไอเดีย
  script_agent.md          Prompt สำหรับเขียนสคริปต์
  video_agent.md           Prompt สำหรับวางแผนวิดีโอ
  publisher_agent.md       Prompt สำหรับเตรียมโพสต์
  analytics_agent.md       Prompt สำหรับวิเคราะห์ผล
scripts/
  run_daily_plan.py        สคริปต์สร้างแผนคอนเทนต์รายวัน
  check_tiktok_connection.py เช็ก env สำหรับ TikTok Developer
workflow/
  tiktok-agent-workflow.yaml โครงสร้าง workflow ทั้งระบบ
```

## ข้อควรรู้เรื่องการโพสต์

ระบบนี้เตรียมทุกอย่างให้พร้อมโพสต์ แต่การโพสต์อัตโนมัติเต็มรูปแบบต้องเชื่อมบัญชี TikTok ผ่านช่องทางที่บัญชีอนุญาต และควรมีการอนุมัติจากคนก่อนเผยแพร่จริง โดยเฉพาะคลิปที่มีราคา ส่วนลด ผลลัพธ์จากสินค้า หรือคำเคลมด้านสุขภาพ/ความงาม
