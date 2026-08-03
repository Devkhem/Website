# Client Video Pipeline

Workflow นี้ทำงานตามสายนี้

```text
Google Form
-> Google Drive
-> ChatGPT/Gemini สร้าง Brand Bible
-> สร้าง Script
-> สร้าง Shot List
-> สร้าง Still Images
-> Google Flow animate
-> ElevenLabs voice-over
-> Premiere Pro
-> ส่ง Review
```

สคริปต์ที่ใช้

```text
scripts/run_client_pipeline.py    ตัวคุม pipeline ทั้งเส้น
scripts/generate_voiceover.py     ยิง ElevenLabs จาก voiceover/lines.csv
data/client_intake_fields.json    map คำถามใน Google Form -> ฟิลด์ใน brief
data/sample_form_responses.csv    ไฟล์ตัวอย่างไว้ลองรัน
```

## หลักการ

ขั้นตอนไหนที่เครื่องทำได้ สคริปต์ทำให้เลย ขั้นตอนไหนต้องใช้คนหรือโปรแกรมข้างนอก
สคริปต์จะเตรียม prompt และโฟลเดอร์ปลายทางไว้ให้ พอไฟล์มาวางครบ สั่ง `sync` แล้วมันจะเดินต่อเอง

สถานะที่เห็นตอนรัน

```text
[x] done      ทำเสร็จแล้ว
[>] ready     ทำต่อได้ทันที มี prompt/ไฟล์รอแล้ว
[.] waiting   รอขั้นก่อนหน้าเสร็จก่อน
[ ] blocked   ยังขาดข้อมูลต้นทาง
```

## 1. รับงานจาก Google Form

โหลดคำตอบจากฟอร์มเป็น CSV (Google Sheet > File > Download > CSV) หรือใช้ลิงก์แบบ Publish to web

```bash
python3 scripts/run_client_pipeline.py new --responses data/sample_form_responses.csv
```

เลือกแถวที่ต้องการ

```bash
python3 scripts/run_client_pipeline.py new --responses ~/Downloads/form.csv --match "mellow@example.com"
```

แก้ค่าใน brief ตอนสร้างงาน

```bash
python3 scripts/run_client_pipeline.py new --responses ~/Downloads/form.csv --field duration_sec=30 --field aspect_ratio=1:1
```

ถ้าคำถามในฟอร์มถูกเปลี่ยน ให้เพิ่มคำค้นใน `data/client_intake_fields.json` ที่ `field_keywords`
สคริปต์จับคู่จากคำที่อยู่ในหัวคอลัมน์ ไม่ต้องตั้งชื่อคอลัมน์ตรงเป๊ะ
คำตอบที่ยัง map ไม่เข้าฟิลด์ไหนจะถูกเก็บไว้ใน `form_extra` ไม่หายไป

## 2. Google Drive

ถ้าอยากให้งานอยู่ในโฟลเดอร์ที่ Drive sync ไว้ ให้ชี้ `--jobs` ไปที่นั่น

```bash
python3 scripts/run_client_pipeline.py --jobs ~/"Google Drive/My Drive/clients" new --responses ~/Downloads/form.csv
```

ค่าเริ่มต้นคือ `outputs/clients/<วันที่>-<ชื่อลูกค้า>/`

## 3-4. Brand Bible และ Script

```bash
python3 scripts/run_client_pipeline.py sync <job-id>
```

แต่ละรอบ sync จะสร้าง prompt ให้ใหม่ตามข้อมูลล่าสุด

```text
01-brand-bible-prompt.md   -> วางใน ChatGPT/Gemini -> บันทึกเป็น brand-bible.md
02-script-prompt.md        -> วางใน ChatGPT/Gemini -> บันทึกเป็น script.json
03-shot-list-prompt.md     -> วางใน ChatGPT/Gemini -> บันทึกเป็น shot-list.json
```

`script.json` และ `shot-list.json` ต้องเป็น JSON ตาม schema ที่อยู่ในตัว prompt เพราะขั้นถัดไปอ่านไฟล์นี้ต่อ
ถ้า JSON เสียหรือคีย์ไม่ครบ `sync` จะเตือนและถือว่าขั้นนั้นยังไม่เสร็จ

## 5. Still Images

`sync` จะแตก prompt ภาพรายช็อตให้

```text
04-image-prompts/sh-01.txt
04-image-prompts/sh-02.txt
```

ถ้า shot list ไม่ได้ใส่ `image_prompt` มา สคริปต์จะประกอบ prompt ให้จาก description + framing + สินค้า
เอาภาพที่ได้มาวางเป็น `stills/sh-01.png` (รับ .png .jpg .jpeg .webp)

## 6. Google Flow animate

```text
05-flow-prompts/sh-01.txt
```

ในไฟล์มีภาพต้นทาง motion prompt ความยาว และข้อห้าม
เอาคลิปที่ได้มาวางเป็น `clips/sh-01.mp4` (รับ .mp4 .mov .webm)

## 7. ElevenLabs voice-over

`sync` สร้าง `voiceover/lines.csv` จาก `script.json` ให้อัตโนมัติ ทีละซีน

ดูก่อนว่าจะยิงอะไรบ้าง (dry run เป็นค่าเริ่มต้น)

```bash
python3 scripts/generate_voiceover.py <job-id>
```

ยิงจริง

```bash
python3 scripts/generate_voiceover.py <job-id> --execute
```

ต้องตั้งค่าใน `.env` ก่อน

```text
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```

โมเดลและค่าเสียงอยู่ใน `data/client_intake_fields.json` ที่คีย์ `elevenlabs`
ค่าเริ่มต้นคือ `eleven_multilingual_v2` ซึ่งอ่านไทยได้

อัดซ้ำเฉพาะซีนที่แก้

```bash
python3 scripts/generate_voiceover.py <job-id> --scene sc-03 --overwrite --execute
```

ไฟล์ที่มีอยู่แล้วจะถูกข้าม ยกเว้นใส่ `--overwrite` จึงไม่เสีย credit ซ้ำ

## 8. Premiere Pro

พอมีทั้งคลิปและเสียงครบ `sync` จะสร้าง

```text
06-assembly-sheet.csv   ลำดับตัดต่อ ช็อต ไฟล์ภาพ ไฟล์คลิป ไฟล์เสียง subtitle
06-edit-notes.md        ลำดับงานและข้อควรระวังจาก brief
```

ช่องไหนขึ้น `MISSING` แปลว่ายังขาดไฟล์นั้นอยู่
export เสร็จให้วางไฟล์ไว้ในโฟลเดอร์ `final/`

## 9. ส่ง Review

พอมีไฟล์ใน `final/` แล้ว `sync` จะสร้าง `07-review-packet.md`
ในนั้นมีสรุปว่าทำอะไรตาม brief บ้าง และ checklist ให้ลูกค้าเช็กก่อนอนุมัติ

## คำสั่งอื่น

```bash
python3 scripts/run_client_pipeline.py list
python3 scripts/run_client_pipeline.py status <job-id>
```

## โครงสร้างโฟลเดอร์งาน

```text
outputs/clients/2026-08-03-mellow-bean/
  brief.json
  manifest.json
  01-brand-bible-prompt.md
  brand-bible.md
  02-script-prompt.md
  script.json
  03-shot-list-prompt.md
  shot-list.json
  04-image-prompts/
  05-flow-prompts/
  stills/
  clips/
  voiceover/lines.csv
  voiceover/sc-01.mp3
  06-assembly-sheet.csv
  06-edit-notes.md
  final/
  07-review-packet.md
```

## ข้อจำกัดที่ต้องรู้

- สคริปต์ไม่ได้เรียก ChatGPT/Gemini เอง มันสร้าง prompt ให้วางเอง ให้คนคุมคุณภาพก่อนไปขั้นถัดไป
- สคริปต์ไม่ได้เรียก Google Flow และไม่ได้สั่ง Premiere ทั้งสองตัวไม่มี API สาธารณะให้ต่อ
- ขั้นตอนที่ยิง API จริงมีแค่ ElevenLabs และมี dry run เป็นค่าเริ่มต้น
- การส่งงานให้ลูกค้ายังเป็นคนกดส่ง สคริปต์เตรียมของให้ครบเท่านั้น
