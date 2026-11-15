# TASK 002.1 — ผลตรวจวิธีวิจัยและซ่อม coverage

Run `m2-methodology-qa-20261115-v1`; methodology `task-002-1-observed-sessions-v2`; baseline `8a4903f`.

ซ่อม ASTC/BRTX/SNGX วันที่ 2026-05-27 ถึง terminal cursor แล้ว ใช้ 24 requests/24 หน้าใหม่ รวม 255,244,079 decoded bytes ไม่มี request error; ไม่เพิ่ม securities หรือ cycles

| รายการ | ก่อน | หลัง |
|---|---:|---:|
| Frame opportunities | 48 | 48 |
| Historical-quality exclusions | 3 | 3 |
| Complete provider windows | 42 | 45 |
| Primary touch records | 20 | 20 (เวลาและรายการเดิม) |
| Verified observed-session first touches | 17 | 20 |
| Strict full-cycle opportunity denominator | 0 | 0 |

ผล systematic และ diagnostic แยกจากกัน ไม่ใช้ diagnostic event rate แทน population estimate และไม่รวม cohort ที่ซ้อนกันเป็น independent events

## Forward-return censoring sensitivity

ตารางแสดง **จำนวน censored / event denominator (เปอร์เซ็นต์)**; ไม่ตัดด้วย gap ยังตัดเมื่อข้อมูลไม่ครบ ข้าม overnight มี unknown evidence หรือราคาเก่าเกิน 60 วินาที

| Sample | Gap policy | 5m | 15m | 30m | 60m | Session end | Cycle end |
|---|---|---|---|---|---|---|---|
| SYSTEMATIC | GAP_300_SECONDS | 2/7 (28.6%) | 3/7 (42.9%) | 3/7 (42.9%) | 3/7 (42.9%) | 3/7 (42.9%) | 4/7 (57.1%) |
| SYSTEMATIC | GAP_900_SECONDS | 1/7 (14.3%) | 2/7 (28.6%) | 3/7 (42.9%) | 2/7 (28.6%) | 2/7 (28.6%) | 2/7 (28.6%) |
| SYSTEMATIC | NO_MECHANICAL_GAP | 1/7 (14.3%) | 2/7 (28.6%) | 3/7 (42.9%) | 2/7 (28.6%) | 0/7 (0.0%) | 0/7 (0.0%) |
| DIAGNOSTIC | GAP_300_SECONDS | 3/13 (23.1%) | 1/13 (7.7%) | 3/13 (23.1%) | 3/13 (23.1%) | 3/13 (23.1%) | 7/13 (53.8%) |
| DIAGNOSTIC | GAP_900_SECONDS | 3/13 (23.1%) | 0/13 (0.0%) | 2/13 (15.4%) | 2/13 (15.4%) | 1/13 (7.7%) | 4/13 (30.8%) |
| DIAGNOSTIC | NO_MECHANICAL_GAP | 3/13 (23.1%) | 0/13 (0.0%) | 2/13 (15.4%) | 1/13 (7.7%) | 0/13 (0.0%) | 3/13 (23.1%) |

ค่า mean/min/max ของ uncensored forward returns ทุก cohort อยู่ใน `primary-cohort-results.json` และทุก policy/variant อยู่ใน `summary.json`; denominator เปลี่ยนตาม censoring จึงไม่ควรอ่านความต่างเป็น performance improvement

## First-passage sensitivity

แต่ละช่องคือ **upside first / downside first / censored / neither**; denominator เท่ากับจำนวน event ของแต่ละ sample

| Sample | Gap policy | +3% / −3% | +5% / −3% | +10% / −5% |
|---|---|---|---|---|
| SYSTEMATIC | GAP_300_SECONDS | 5 / 2 / 0 / 0 | 3 / 3 / 1 / 0 | 3 / 1 / 3 / 0 |
| SYSTEMATIC | GAP_900_SECONDS | 5 / 2 / 0 / 0 | 4 / 3 / 0 / 0 | 4 / 2 / 1 / 0 |
| SYSTEMATIC | NO_MECHANICAL_GAP | 5 / 2 / 0 / 0 | 4 / 3 / 0 / 0 | 4 / 2 / 0 / 1 |
| DIAGNOSTIC | GAP_300_SECONDS | 6 / 5 / 2 / 0 | 5 / 6 / 2 / 0 | 4 / 7 / 2 / 0 |
| DIAGNOSTIC | GAP_900_SECONDS | 7 / 6 / 0 / 0 | 6 / 7 / 0 / 0 | 6 / 7 / 0 / 0 |
| DIAGNOSTIC | NO_MECHANICAL_GAP | 7 / 6 / 0 / 0 | 6 / 7 / 0 / 0 | 6 / 7 / 0 / 0 |

## ข้อค้นพบและข้อจำกัด

- High/low-only เทียบกับ high/low AND open/close ไม่เปลี่ยน accepted count หรือ touch ใน sample นี้ เพราะ explicit veto ยังปฏิเสธ codes 5/10/22/32; ไม่ได้พิสูจน์ว่ากฎเดิมไม่มี false exclusions ใน population อื่น
- Odd-lot sensitivity ทำให้ 8 touches เร็วขึ้นและเพิ่ม 2 diagnostic events; แยกจาก primary โดยชัดเจน ไม่เลือกวิธีเพื่อเพิ่ม positive outcomes
- 734 จาก 858 eligible-trade gaps >300 วินาทีมี returned rejected messages อยู่ภายใน จึงไม่ใช่หลักฐาน missing pagination; ไม่มี independent halt/feed-loss proof
- AH/PRE/RTH ที่ใช้ไม่รวม 20:00–04:00 ET จึงไม่อ้าง first touch ครบ 24 ชั่วโมง; strict denominator เป็นศูนย์และไม่รายงาน rate เป็น 0%
- Systematic: 7 events /29 complete opportunities และ 22 zero-event opportunities; diagnostic: 13/16 และ 3 zero-event opportunities
- Current-float proxy: systematic 3/11, diagnostic 4/4; SEC evidence overlap: systematic 2/3, diagnostic 2/3. SEC overlap ไม่ได้แปลว่า historical float ผ่าน PIT gate
- ตรวจ original published examples จาก raw/hash: SNGX 2026-05-28 ที่ 0.9537 และ DBGI 2026-05-27 ที่ 0.3198 อยู่ที่ preceding ask; HOTH 2026-05-28 ที่ 1.50 สูงกว่า preceding ask 1.49 และไม่พบ NBBO รองรับใน 5 วินาทีถัดมา ไม่ได้ยืนยันว่าราคาใด executable
- ผลเดิม 20 events/20 outcomes ตรงทุก record; original artifacts และ M1 ไม่เปลี่ยน; M1 ยัง `BLOCKED_DATA`
- Regression tests: 150 passed, 84 existing pandas warnings; independent validation PASS ทั้ง source hashes, cursor chains, exports และ audit examples

รายละเอียดวิธี ขอบเขตเวลา condition distributions, repair records, cohort denominators, reproduction และข้อจำกัด raw-cache อยู่ใน [methodology report](../../docs/research/task-002-1-replay-methodology-qa.md). หลักฐานของตัวอย่างเดิมอยู่ใน `requested-raw-nbbo-audit.json`; generic `raw-nbbo-audit.json` เป็นข้อมูลเสริมซึ่งอาจเป็นคนละวัน

Raw/Parquet อยู่ใน local ignored data cache; Git มีผล event-level ครบและ source hashes แต่ fresh checkout ที่ไม่มี cache จะตรวจ raw ซ้ำไม่ได้ทันที ไม่มี credential ถูก commit ไม่มีการขยาย 120-cycle universe หรือสร้าง confirmation model และผลนี้ไม่ใช่การทดสอบ executable profitability

Consolidated output: `research_bundle.zip` (local, ไม่เข้า Git ตาม convention เดิม); สร้างซ้ำด้วย `python -m scripts.bundle_replay_qa`. รวมผลทั้งสาม cycle, event payload ครบพร้อมสาม gap policies, cycle/cohort metrics และ distributions; ตรวจ ZIP/checksums/row counts แล้ว ดู `bundle-validation.json`
