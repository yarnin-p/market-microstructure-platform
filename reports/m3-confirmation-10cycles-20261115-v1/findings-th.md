# TASK 003 — ผล Price Confirmation Research Pilot

Baseline `cb0912f`; run ใหม่ `m3-confirmation-10cycles-20261115-v1`; methodology `task-003-confirmation-v1`.

รันจริงจากหลักฐานเดิมครบ 10 exploration cycles และ **40 primary initial events** ไม่มี API requests เพิ่ม ไม่มี cycle หรือ quote download เพิ่ม และไม่วิเคราะห์ 40-cycle holdout ใช้ risk set เดียวกันในทุก policy; เก็บ unconfirmed และ insufficient-data ไว้ครบ ไม่เติมผลตอบแทนเป็นศูนย์

## Signal และต้นทุนการรอ

| Policy | Initial events | Confirmed | Unconfirmed | Insufficient data | Median delay | Median ราคาที่เปลี่ยนระหว่างรอ |
|---|---:|---:|---:|---:|---:|---:|
| C0 immediate touch | 40 | 40 | 0 | 0 | 0 s | 0% |
| C1 counted trade persistence | 40 | 33 | 7 | 0 | 55.578 s | +0.034% |
| C2 fresh bid support | 40 | 6 | 24 | 10 | 36.201 s | +3.699% |

ราคาที่เปลี่ยนระหว่างรอ = signal market-observation price / original touch price − 1; ค่าบวกคือรอแล้วราคาแพงขึ้น ค่าลบคือราคาดีขึ้น ไม่ใช่กำไรที่พลาดอย่างแน่นอน C1 ราคาแพงขึ้น 17, ดีขึ้น 11, เท่าเดิม 5; C2 แพงขึ้นทั้ง 6 กรณี ตัวเลขเหล่านี้เป็นของ confirmed subset เท่านั้น ไม่ใช่ unconditional policy performance

C1 delay p25/median/p75 = **34.924 / 55.578 / 413.261 วินาที**; min 30.007 s, max **242,293.218 s** (~67.30 ชั่วโมง) Mean 14,699.55 s ถูกดึงด้วย AREN และ SMXT cycle 2026-06-01 ที่ first touch ใน AH ก่อนสุดสัปดาห์และยืนยันใน RTH ถัดไป เกณฑ์ C1 ไม่มี 60-second deadline และไม่ได้ห้ามยืนยัน session ถัดไป แต่ไม่สะสม span ข้าม overnight: ทั้งสองกรณีต้องสะสมหลักฐานชุดใหม่ใน observed session ก่อนยืนยัน ไม่ใช่หลักฐานว่าราคายืนต่อเนื่องตลอดสุดสัปดาห์

C2 delay p25/median/p75 = **17.793 / 36.201 / 46.902 วินาที**, min 10.052 s, max 59.783 s; waiting-price change min/median/max = **+0.419 / +3.699 / +8.127%** ทั้งหมดใช้ราคาเมื่อสัญญาณเกิดจริง ไม่ย้อนกลับไปเข้าที่ C0

## นิยามที่ freeze ก่อนคำนวณ

- C0: trade เดิมที่แตะ threshold = previous RTH close × 1.10; ผลทั้ง 40 events และ outcomes ต้องตรง baseline เดิม
- C1: นับ first touch เป็น observation แรก ต้องมีอย่างน้อยสาม distinct eligible raw records ที่/เหนือ threshold เดิมและ span >=30 วินาที Signal ที่ receipt time ของรายการสุดท้ายที่ทำให้เงื่อนไขครบ ไม่ใช้ timer ย้อนราคา ไม่ reset เพราะ subthreshold trade แทรก จึงเป็น **counted persistence** ไม่ใช่ continuous support; reset การสะสมเมื่อข้าม overnight และหยุด cycle end
- C2: เริ่ม support clock ที่ first touch ใช้ preceding quote ซึ่งสด <=5 s ได้เป็น observation แรก จากนั้นต้องมี NBBO records ต่างกันรองรับ bid >= threshold อย่างน้อย 10 s และไม่มี observed invalid/below-threshold quote หรือ freshness gap >5 s คั่น จำกัดไม่เกิน touch+60 s/cycle end ข้อมูลอนาคตไม่ใช้ qualify หรือ flag สัญญาณ

รายละเอียดการตีความ cancellation, quote conditions, spans และ clocks อยู่ใน [frozen design](../plans/TASK-003-price-confirmation.md) โดยไม่มีการลอง thresholds แล้วเลือกจากผลตอบแทน

C0/C1 market price คือ actual signal trade; C2 signal เกิดที่ quote receipt time แต่ market-observation return ใช้ latest eligible trade mark ที่/ก่อนเวลานั้นและอายุ <=60 s เก็บ timestamp ของ trade mark แยกไว้ ไม่อ้างว่าเกิด trade ใหม่ตรง quote timestamp และไม่เอา pre-signal extremes มารวม MFE/MAE เก็บ NBBO ask เป็นคนละราคาเพื่อใช้ quote-mark estimates ที่มีหลักฐานพอเท่านั้น

## ผล forward และ censoring บน initial denominator เดิม

แต่ละช่องคือ **observed / censored confirmed / unconfirmed / insufficient data** รวมครบ 40 เสมอ Median เป็น conditional distribution เฉพาะ uncensored marks ไม่ใช่ strategy return

| Policy | Horizon | Population buckets (รวม 40) | Median observed return |
|---|---|---|---:|
| C0 | 5m | 23 / 17 / 0 / 0 | −1.515% |
| C0 | 15m | 20 / 20 / 0 / 0 | −0.967% |
| C0 | 30m | 19 / 21 / 0 / 0 | −0.209% |
| C0 | 60m | 15 / 25 / 0 / 0 | −0.180% |
| C1 | 5m | 22 / 11 / 7 / 0 | −0.587% |
| C1 | 15m | 15 / 18 / 7 / 0 | −0.992% |
| C1 | 30m | 15 / 18 / 7 / 0 | +0.363% |
| C1 | 60m | 17 / 16 / 7 / 0 | −0.159% |
| C2 | 5m | 6 / 0 / 24 / 10 | −1.432% |
| C2 | 15m | 5 / 1 / 24 / 10 | −1.056% |
| C2 | 30m | 5 / 1 / 24 / 10 | −4.481% |
| C2 | 60m | 5 / 1 / 24 / 10 | −3.892% |

Own-signal horizons ของ C0/C1/C2 จบคนละเวลา ดังนั้นห้ามอ่านการเปลี่ยน median เป็น causal improvement คง common initial population และแยก confirmed-by-5/15/30/60-minute initial-touch landmarks; `paired_comparisons.json` เก็บทุกคู่รวม missingness ไม่เลือกเฉพาะผู้ที่รอดยืนยัน ใน primary C1 มี 7 กรณีที่ C0 observed −3% first-passage เกิดก่อนสัญญาณ และ 2 กรณีที่ +3% first-passage เกิดก่อน; C2 มี 1 และ 3 ตามลำดับ ไม่ใช่กำไร/ขาดทุนของการเข้า order แต่แสดง path ที่เกิดระหว่างรอ

## First passage และ excursions

ทุกแถวใช้ initial denominator **40** ช่องเรียงเป็น **upside / downside / neither / censored / unconfirmed / insufficient**

| Policy | Barrier (เทียบ signal price) | Counts |
|---|---|---|
| C0 | +3% / −3% | 14 / 20 / 3 / 3 / 0 / 0 |
| C0 | +5% / −3% | 9 / 24 / 4 / 3 / 0 / 0 |
| C0 | +10% / −5% | 5 / 22 / 9 / 4 / 0 / 0 |
| C1 | +3% / −3% | 12 / 17 / 3 / 1 / 7 / 0 |
| C1 | +5% / −3% | 6 / 22 / 4 / 1 / 7 / 0 |
| C1 | +10% / −5% | 4 / 19 / 9 / 1 / 7 / 0 |
| C2 | +3% / −3% | 1 / 5 / 0 / 0 / 24 / 10 |
| C2 | +5% / −3% | 0 / 6 / 0 / 0 / 24 / 10 |
| C2 | +10% / −5% | 3 / 3 / 0 / 0 / 24 / 10 |

Primary ไม่มี mechanical gap censoring แต่ยังคง overnight, incomplete pages, unknown evidence, corrections และ mark age <=60 s กฎ 300/900 วินาทีเป็น sensitivity แยก: จำนวน censored ของ +3/−3 สำหรับ C0 = **3/15/8**, C1 = **1/10/4**, C2 = **0/1/0** ตามลำดับ no-gap/300/900 ไม่เลือก policy เพื่อเพิ่ม positive outcomes รายละเอียดทุก forward horizon/stratum/gap อยู่ใน `sensitivity-analysis.json`

Observed path MFE/MAE median: C0 **+2.482% / −9.396%** (40 paths, excursion-censored 10), C1 **+2.894% / −7.458%** (33 paths, censored 5), C2 **+14.309% / −17.151%** (6 paths, censored 3) ยังคง extrema ที่สังเกตได้พร้อม censoring flags ไม่ใช่ complete-market extrema, executable fills หรือหลักฐานว่า C2 ดีกว่าเพราะ MFE สูง

## Float strata, weights และ sessions

สุ่มเดิมวันละ 12 proxy +12 complementary opportunities ด้วยแต่ละวัน/stratum N ของตนเอง รวม 240 opportunities เก็บ inclusion probability n/N และ design weight N/n ทุก signal row ไม่คำนวณ weight ใหม่จาก confirmed survivors Current float เป็น retrospective proxy ไม่ใช่ historical eligibility และ complementary stratum รวม out-of-range กับ unresolved float

| Stratum | Initial events | C1 confirmed / unconfirmed | C2 confirmed / unconfirmed / insufficient | Weighted C1 confirmation fraction | Weighted C2 fraction |
|---|---:|---|---|---:|---:|
| MASSIVE_CURRENT_FLOAT_PROXY | 25 | 19 / 6 | 3 / 17 / 5 | 75.946% | 12.000% |
| Complementary stratum | 15 | 14 / 1 | 3 / 7 / 5 | 93.333% | 19.906% |

Unweighted C1 confirmation fractions คือ 76% กับ 93.333%; C2 คือ 12% กับ 20% แสดงทั้ง weighted/unweighted เพื่อไม่กลบ unequal sampling probabilities Weighted fractions เป็น descriptive weighted ratios ภายใน selected event risk set ไม่ใช่ความน่าจะเป็นของ universe, population estimate หรือ significance test รวมทุก stratum weighted C1 =83.964%, C2 =15.646% ห้ามนับ overlapping EXCHANGE_PRICE_ONLY กับ proxy เป็น independent samples

| Initial session | Initial events | C1 confirmed / unconfirmed | C2 confirmed / unconfirmed / insufficient |
|---|---:|---|---|
| AH | 9 | 6 / 3 | 3 / 1 / 5 |
| PRE | 10 | 7 / 3 | 1 / 7 / 2 |
| RTH | 21 | 20 / 1 | 2 / 16 / 3 |

Signal session เก็บแยกจาก initial session และไม่ใช้ข้าม-session counts เป็น independent observations ไม่มี diagnostic sample เพิ่ม SEC evidence overlap เดิมมี 8 opportunities แต่ไม่มี primary events จึงไม่มี confirmation sample ที่จะอนุมานผล SEC-specific

Odd-lot sensitivity ยังคง **40 original anchors และ thresholds** เพิ่ม eligible follow-up observationsเท่านั้น: C1 ยืนยัน **37/40** เทียบ 33/40, เปลี่ยน signal time 23 กรณี (รวม 4 status changes); C2 ยังคง 6/40 และเวลา signal ไม่เปลี่ยน แต่ as-of trade mark เปลี่ยน 2 กรณี ไม่เพิ่มสาม odd-only opportunities และไม่ย้อน C0 ไปใช้ odd-lot touch ที่เร็วกว่าในงานก่อน

## Quote missingness และ executable estimates

ทั้ง 40 primary events มี provider-pagination-complete original quote windows ครอบคลุมช่วงประเมิน C2 แต่ **complete pagination ไม่ได้แปลว่ามี fresh valid NBBO** ใน 10 insufficient cases: สามกรณีไม่มี returned quotes, หกกรณีเจอ corrected-price quote conditions โดยไม่มี fresh quote ที่ผ่านกฎ regular 0/1 และอีกหนึ่งกรณีมีแต่ stale preceding quote/ไม่มี update ใหม่ ข้อมูลไม่พอเหล่านี้ไม่ถูกนับเป็น trade failure หรือ zero return

ผู้ให้ข้อมูลระบุ quote condition 81 ว่า `Corrected_Price`; งานนี้รักษากฎ conservative เดิมที่ไม่ใช้ corrected quote fields เป็น original PIT NBBO และไม่สร้าง quote reconstruction ขึ้นเอง ดู [official conditions glossary](https://massive.com/glossary/conditions-indicators) (ตรวจ 2026-11-15) และ `c2_insufficient_observation_audit` ใน sensitivity report นี่เป็นข้อจำกัดของหลักฐาน/validity policy ที่ใช้ ไม่ใช่ข้อสรุปว่า paid product หรือ provider feed ใช้งานไม่ได้

ไม่มี primary entry/exit quote-mark pair ที่ครบสำหรับ post-signal 5/15/30/60 นาที: **0/316 requested confirmed-signal marks** มีหลักฐานพอ จึงไม่มี ask-entry/bid-exit return ที่รายงานได้ และไม่มี executable P&L ตำแหน่ง bid/ask ยังเป็น market context ไม่พิสูจน์ fill/size/queue/costs การไม่มี quotes สำหรับ exits ไม่ทำให้ trade-observation returns ถูกแทนด้วยราคาแต่งขึ้น

## Validation, outputs และข้อจำกัด

- **182 tests passed**, 84 existing pandas deprecation warnings; ครอบคลุม distinct records, spans, overnight, correction timing, bid freshness/resets/deadline, no future quote flags, synthetic signal-mark clocks, missing exits, original denominator และ weights
- Deterministic recomputation ครบทุก 40 initial events ให้ **240 policy/condition rows** ตรงเดิมทั้งหมด; C0 original 40 outcomes ตรง baseline
- ตรวจ source pages 46 และ signal-evidence references 314; previous artifacts **3,865 files** ไม่เปลี่ยน รวม M1/previous pilots/holdout byte-preservation checks โดยไม่ parse holdout outcomes
- Offline resume เปิด HTTP request trap แล้วยืนยัน zero requests และ immutable run hashes เดิม; ไม่มี credentials ใน Git
- Local bundle รวมทุก 10 cycles, 240 event rows, 486 gap-outcome rows, 72 cohort/session/policy groups และ 30 primary cycle-policy summaries ไม่มี raw ticks ไม่มี sampling/truncation

Reproduction จาก repository root และ existing immutable cache:

```sh
python -m market_lab.confirmation_pilot run
python -m market_lab.confirmation_pilot validate
python -m scripts.analyze_confirmation
python -m pytest -q
python -m scripts.finalize_confirmation
```

Compact reports: `reports/m3-confirmation-10cycles-20261115-v1/`; local run/cache references: `data/runs/m3-confirmation-10cycles-20261115-v1/`; consolidated local deliverable: `reports/m3-confirmation-10cycles-20261115-v1/research_bundle.zip` (ZIP/Parquet/raw data ไม่เข้า Git ตาม convention เดิม) Fresh checkout อ่าน compact JSON ได้ แต่ raw revalidation ต้องมี source cache ไม่อ้างว่า checkout อย่างเดียวทำได้

นิยาม C1/C2 เป็น fixed exploratory operational definitions ไม่ใช่ optimized trading rules ผลยังมี dependence ของ securities/cycles, selection conditioning ที่ +10% touch, retrospective float misclassification, unverified overnight, retrospective REST corrections, quote coverage/freshness และ M1 grouped-close reference ที่ไม่ได้รับรอง official auction close แยกต่างหาก ไม่อ้าง significance/profitability ไม่เลือก threshold ใหม่ และไม่แก้ M1 `BLOCKED_DATA` หรือ historical float gate
