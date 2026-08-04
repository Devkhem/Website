# Story Channel Workflow

Workflow หลัก:

```text
ChatGPT สร้างภาพ 1 ภาพ -> Codex ทำคลิป 3 ตอน -> โพสต์ทดสอบ -> ดู retention -> ทำตอนต่อ
```

## 1. ChatGPT สร้างภาพ 1 ภาพ

ใช้ prompt จาก:

```text
outputs/<date>/chatgpt-image-prompt.txt
```

ภาพที่ดีต้องดูเหมือนภาพหลุดหรือภาพมือถือจริง ไม่ใช่โปสเตอร์หนังผี

## 2. Codex ทำคลิป 3 ตอน

ภาพเดียวต้องแตกเป็น 3 ตอน:

- ตอน 1: hook + สถานที่
- ตอน 2: หลักฐานหรือสิ่งผิดปกติ
- ตอน 3: twist + comment bait

ถ้าจะส่งภาพกลับเข้า API ที่ต้องใช้ภาพสี่เหลี่ยมจัตุรัส เช่น legacy image variations ให้เตรียมไฟล์ก่อน:

```bash
python3 scripts/prepare_api_image.py outputs/<date>/room-407-chatgpt-keyvisual.png
```

ใช้ไฟล์ `*-api-square.png` ที่สร้างใหม่แทนภาพ 9:16 เดิม เพื่อเลี่ยง `400 Could not process image`.

## 3. โพสต์ทดสอบ

โพสต์ห่างกันอย่างน้อย 4-6 ชั่วโมง หรือโพสต์วันละ 1-3 คลิปตามกำลังบัญชี

## 4. ดู retention

หลังโพสต์ 2 ชั่วโมงและ 24 ชั่วโมง ให้กรอก:

```text
data/story_metrics.csv
```

เกณฑ์ตัดสิน:

- Retention >= 35%: ทำตอนต่อทันที
- Retention 25-34%: ใช้ภาพเดิม แต่เปลี่ยน hook
- Retention < 20%: เปลี่ยน premise/location

## 5. ทำตอนต่อ

ถ้า premise เวิร์ก ให้ขยายเป็นซีรีส์:

- ห้อง 407 ตอน 4
- แขกคนก่อน
- กล้องวงจรปิดหน้าห้อง
- แม่บ้านกะดึก
- คนที่เช็คเอาท์ไปแล้ว

## Daily Command

```bash
python3 scripts/run_story_channel_plan.py
```
