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

ถ้าลูกค้าส่ง brief ใหม่ทับงานเดิม

```bash
python3 scripts/run_client_pipeline.py new --responses ~/Downloads/form.csv --job-id <job-id> --force
```

`--force` จะย้ายของเดิมทั้งหมด (brand bible, script, ภาพ, คลิป, เสียง, ไฟล์ final) เข้า `archive-<เวลา>/`
แล้วเริ่มนับหนึ่งใหม่จาก brief ใหม่ ไม่ให้ review packet ของ brief ใหม่ไปหยิบไฟล์ final ของรอบเก่ามาใช้

ถ้างานไหนไม่เอาตัวหนังสือบนจอเลย ให้ตั้ง `subtitles=none`

```bash
python3 scripts/run_client_pipeline.py new --responses ~/Downloads/form.csv --field subtitles=none
```

prompt ของสคริปต์จะสั่งไม่ให้มี on_screen_text, prompt ภาพจะไม่เว้นที่ว่างสำหรับ subtitle
และ edit notes จะสั่งไม่ให้ใส่ตัวหนังสือใด ๆ ตอนตัดต่อ

ถ้าคำถามในฟอร์มถูกเปลี่ยน ให้เพิ่มคำค้นใน `data/client_intake_fields.json` ที่ `field_keywords`
สคริปต์จับคู่จากคำที่อยู่ในหัวคอลัมน์ ไม่ต้องตั้งชื่อคอลัมน์ตรงเป๊ะ
ลำดับของฟิลด์ในไฟล์นั้นคือลำดับความสำคัญ ฟิลด์ที่มาก่อนจะจับคอลัมน์ไปก่อน
เช่น `contact` อยู่เหนือ `client_name` หัวข้อ `Client email` จึงไปเป็นอีเมล ไม่ใช่ชื่อลูกค้า
คำตอบที่ยัง map ไม่เข้าฟิลด์ไหนจะถูกเก็บไว้ใน `form_extra` ไม่หายไป

## 2. Google Drive

ถ้าอยากให้งานอยู่ในโฟลเดอร์ที่ Drive sync ไว้ ให้ชี้ `--jobs` ไปที่นั่น

```bash
python3 scripts/run_client_pipeline.py --jobs ~/"Google Drive/My Drive/clients" new --responses ~/Downloads/form.csv
```

ค่าเริ่มต้นคือ `outputs/clients/<วันที่>-<ชื่อลูกค้า>/` ซึ่งถูก ignore ไว้ใน `.gitignore` แล้ว
ข้อมูลลูกค้า ไฟล์ที่ลูกค้าส่งมา เสียง และคลิป final จะไม่หลุดขึ้น git ตอน `git add .`

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
ถ้า JSON เสีย คีย์ไม่ครบ หรือรายการใน `scenes`/`shots` ไม่ใช่ object `sync` จะเตือนและถือว่าขั้นนั้นยังไม่เสร็จ

`sync` จะตรวจ `shot-list.json` ให้ก่อนปล่อยผ่าน
ทุกซีนต้องมีช็อตอย่างน้อย 1 ช็อต ช็อตต้องอ้างซีนที่มีอยู่จริง
และเวลาช็อตรวมของแต่ละซีนต้องตรงกับเวลาซีน (คลาดได้ไม่เกิน 1 วินาที)
ถ้าข้อไหนไม่ผ่าน `sync` จะบอกว่าซีนไหนมีปัญหาและยังไม่ปล่อยให้ขั้นตัดต่อเป็น ready

## 5. Still Images

`sync` จะแตก prompt ภาพรายช็อตให้

```text
04-image-prompts/sh-01.txt      ทีละช็อต
04-image-prompts/README.md      รวมทุกช็อตไว้ในไฟล์เดียว พร้อมเช็กลิสต์
```

ถ้า shot list ไม่ได้ใส่ `image_prompt` มา สคริปต์จะประกอบ prompt ให้จาก description + framing + สินค้า
เอาภาพที่ได้มาวางเป็น `stills/sh-01.png` (รับ .png .jpg .jpeg .webp)
ระบบจะเช็กหัวไฟล์ด้วย ไฟล์ที่ดาวน์โหลดไม่ครบหรือเป็นหน้า error จะไม่ถูกนับว่าเสร็จ

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
ถ้าอัดเสียงเองมาวางเป็น `.wav` หรือ `.m4a` ก็นับว่าซีนนั้นเสร็จแล้วเหมือนกัน

ซีนที่ตั้งใจไม่ให้มีเสียงพูด (`vo` ว่าง) จะขึ้นสถานะ `no-vo` ใน `lines.csv` และไม่ถือว่าค้าง

ถ้าไฟล์เสียงยาวเกินเวลาซีน (เกิน 20% หรือเกิน 1 วินาที) หรือสั้นกว่า 40% ของซีน ขั้นนี้จะยังไม่ผ่าน
เพราะคนตัดต่อจะต้องตัดเสียงทิ้งหรือทำคลิปที่ยาวเกิน brief ให้แก้บทให้สั้นลงหรือขยาย duration_sec ของซีน

ถ้าแก้ข้อความใน `script.json` หลังอัดเสียงไปแล้ว ซีนนั้นจะขึ้น `stale`
เพราะระบบจำไว้ใน `voiceover/rendered.json` ว่าไฟล์เสียงอัดมาจากข้อความเวอร์ชันไหน
ขั้นตัดต่อจะยังไม่ ready จนกว่าจะอัดใหม่ และตัวอัดเสียงจะไม่ข้ามซีนนั้นแม้ไม่ใส่ `--overwrite`
ส่วนไฟล์เสียงที่อัดเองแล้วเอามาวาง ไม่มีบันทึกใน `rendered.json` จึงไม่ถูกนับว่า stale
ถ้าเปลี่ยน `ELEVENLABS_VOICE_ID` หรือค่าใน `elevenlabs` เสียงที่อัดด้วยค่าเดิมจะขึ้น stale เช่นกัน
งานที่เคยอัดด้วย `--voice-id` จะจำเฉพาะ voice id นั้นไว้ใน `voiceover/settings.json`
และยึดค่านั้นต่อไป ไม่ถูกค่าใน `.env` มาทับ ส่วนค่าอื่นอย่าง model หรือ stability
ยังอ่านจาก config ปัจจุบันเสมอ แก้เมื่อไหร่เสียงเดิมก็ขึ้น stale ทันที

## 8. Premiere Pro

พอมีทั้งคลิปและเสียงครบ `sync` จะสร้าง

```text
06-assembly-sheet.csv   ลำดับตัดต่อ ช็อต ไฟล์ภาพ ไฟล์คลิป ไฟล์เสียง subtitle
06-edit-notes.md        ลำดับงานและข้อควรระวังจาก brief
```

ช่องไหนขึ้น `MISSING` แปลว่ายังขาดไฟล์นั้นอยู่ ส่วน `no-vo` คือซีนที่ตั้งใจไม่มีเสียงพูด
export เสร็จให้วางไฟล์ไว้ในโฟลเดอร์ `final/`
ระบบจะ probe ไฟล์ด้วย ffprobe ว่าเปิดได้จริง มีเสียง ความยาวและสัดส่วนตรงกับ brief
ถ้าเครื่องยังไม่มี ffmpeg ให้ติดตั้งก่อน ไม่งั้นขั้นตัดต่อจะไม่ผ่าน
ถ้ามีหลายไฟล์ในนั้น ระบบจะไม่เดา ให้เหลือไฟล์เดียว หรือระบุ `final_file` ใน `brief.json`
เพราะเวลาไฟล์เชื่อไม่ได้เมื่อก๊อปข้ามเครื่องหรือมาจาก Drive

ถ้าแก้ `brief.json` หรือ `brand-bible.md` หลังเขียนสคริปต์แล้ว สคริปต์จะถูกนับว่าเก่า
และถ้าแก้เนื้อสคริปต์หลังทำ shot list แล้ว shot list ก็จะถูกนับว่าเก่าเช่นกัน
ระบบจำไว้ใน `source-log.json` ว่าแต่ละไฟล์เขียนมาจากต้นทางเวอร์ชันไหน

ถ้าแก้ `script.json`, `shot-list.json` หรือไฟล์คลิป/เสียง หลังจาก export ไปแล้ว
ไฟล์ใน `final/` จะถูกถือว่าเก่ากว่าต้นทาง ขั้นตัดต่อกลับไปเป็น ready และยังส่งรีวิวไม่ได้จนกว่าจะ export ใหม่

เช่นเดียวกัน ถ้าแก้ image_prompt, motion_prompt หรือความยาวของช็อตที่ทำภาพหรือคลิปไปแล้ว
ช็อตนั้นจะถูกนับว่าต้องทำใหม่ ระบบจำไว้ใน `asset-log.json` ว่าไฟล์ที่มีอยู่ทำมาจากนิยามเวอร์ชันไหน

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
