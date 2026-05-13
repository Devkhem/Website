# Implementation Options

มี 3 ระดับในการทำระบบนี้ให้ใช้งานจริง

## ระดับ 1: ใช้ได้ทันทีในเครื่อง

ใช้ไฟล์ในโปรเจกต์นี้และรัน:

```bash
python3 scripts/run_daily_plan.py
```

เหมาะกับช่วงเริ่มต้น เพราะไม่ต้องต่อ API ใด ๆ และช่วยสร้างแผนคอนเทนต์รายวันได้ทันที

## ระดับ 2: Low-code Workflow

ต่อ workflow เข้ากับเครื่องมืออย่าง n8n, Make หรือ Zapier:

1. Trigger ทุกเช้า
2. อ่าน Google Sheet หรือ CSV ของสินค้า
3. ให้ AI เลือกสินค้าและเขียนสคริปต์
4. ส่งสคริปต์ไปสร้างวิดีโอในเครื่องมือที่รองรับ
5. ส่งไฟล์วิดีโอและ caption เข้า approval step
6. หลังอนุมัติ ค่อยโพสต์หรือจัดคิวในเครื่องมือที่บัญชีรองรับ
7. ดึงผลลัพธ์กลับมาให้ Analytics Agent สรุป

## ระดับ 3: Full AI Agent System

ทำเป็น backend จริง:

- Python หรือ Node.js สำหรับ orchestrator
- LLM สำหรับคิดไอเดียและเขียนสคริปต์
- ฐานข้อมูลสำหรับสินค้า คอนเทนต์ และผลลัพธ์
- Queue สำหรับงานสร้างวิดีโอ
- Storage สำหรับเก็บไฟล์วิดีโอ
- Approval dashboard สำหรับกดอนุมัติก่อนโพสต์
- Integration กับบัญชี TikTok ผ่านช่องทางที่บัญชีมีสิทธิ์ใช้งาน

## Roadmap ที่แนะนำ

1. ใช้สคริปต์รายวันให้ได้ 7 วัน เพื่อหา pattern สินค้าที่ขายได้
2. ย้าย `products.csv` ไปเป็น Google Sheet
3. เพิ่ม AI model เพื่อเขียนสคริปต์แบบ dynamic
4. เพิ่ม video generation หรือ template rendering
5. เพิ่ม approval dashboard
6. ค่อยเชื่อมการโพสต์อัตโนมัติหลัง workflow นิ่งแล้ว

