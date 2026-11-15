# M2 — ผล historical tick replay pilot

Run: `m2-first-touch-3cycles-20261115-v1`
Baseline: `5a818c3`
Source M1: `m1-universe-120-20261115-v2` (ตรวจ hashes ก่อนและหลัง; ไม่แก้ข้อมูลเดิม)

รันข้อมูล Massive จริงสำหรับ 3 exploration cycles แรก โดย freeze หุ้น 16 ตัวก่อนคำนวณ outcomes: systematic 10 ตัวด้วย seed 20261115 และ diagnostic 6 ตัวเลือกจาก high/P0 ของวันแรก เก็บสมาชิกแยกกัน ไม่วิเคราะห์ holdout และไม่ได้ดาวน์โหลด ticks ทั้ง 120 cycles

## Coverage จริง

| Cycle | Selected opportunities | ผ่าน historical non-float gates | Trade windows ครบ | ไม่ครบ | ถูกตัดด้วย historical gates |
|---|---:|---:|---:|---:|---:|
| 2026-05-27 | 16 | 16 | 13 | 3 | 0 |
| 2026-05-28 | 16 | 15 | 15 | 0 | 1 |
| 2026-05-29 | 16 | 14 | 14 | 0 | 2 |
| รวม | 48 | 45 | 42 | 3 | 3 |

- 3,134,517 trades และ 7,323 quotes; exact duplicate และ invalid timestamp = 0 ในข้อมูลที่ได้รับ
- Trade windows ไม่ครบ: ASTC, BRTX, SNGX วันที่ 2026-05-27 ชนเพดาน 12 pages / 600,000 trades ต่อ window เก็บ partial evidence ไว้ครบ
- Quote windows 20/20 pagination complete เฉพาะ ±60 วินาทีรอบ event; **ไม่ใช่ complete cycle-wide NBBO coverage**
- 150 API requests, 148 successful pages, 715,846,178 decoded bytes (~682.68 MiB)
- API errors 2 รายการ: current ticker overview ของ HCWC และ HOTH ตอบ HTTP 404; historical control ไม่ถูกแทนด้วย current listing
- 1,127,207 rejected above-threshold printed candidates และ 1,248 subsequent crossings เก็บแยกจาก primary events ไม่ใช่จำนวน independent observations
- Offline resume ใช้ API เพิ่ม 0 requests และ hashes ของ events/outcomes/opportunities/request ledger ตรงเดิม

## Cohorts และ first-touch observations

Current Massive free float: ผ่าน 100K–15M จำนวน 6 securities, นอกช่วง 8, unresolved 2 ค่าเหล่านี้เป็น `MASSIVE_CURRENT_FLOAT_PROXY` ไม่ใช่ verified historical float; ไม่มีการแทนด้วย shares outstanding

| Sample / Cohort | Eligible opportunities | Primary observations | Observed zero-event cases |
|---|---:|---:|---:|
| Systematic / EXCHANGE_PRICE_ONLY | 29 | 7 | 22 |
| Systematic / MASSIVE_CURRENT_FLOAT_PROXY | 11 | 3 | 8 |
| Diagnostic / EXCHANGE_PRICE_ONLY | 16 | 13 | 3 |
| Diagnostic / MASSIVE_CURRENT_FLOAT_PROXY | 4 | 4 | 0 |

Cohorts ซ้อนกัน ห้ามบวกจำนวน events ระหว่าง control กับ proxy รวมเป็น sample ใหม่ Events ถูกเก็บครั้งเดียวต่อ security-cycle แล้วแนบ membership ต่างหาก SEC evidence เป็นบริบทอิสระ: 4 events มี overlap กับ SEC pilot เดิม โดยไม่มีการ forward-fill eligibility หรือ ingestion SEC รอบใหม่

20 primary observations: AH 3, PRE 8, RTH 9 แยกเป็น:

- `VERIFIED_FIRST_TOUCH` 2 รายการ อยู่ใน AH และ trade window ครบ
- `FIRST_TOUCH_UNVERIFIED` 18 รายการ: 15 อยู่หลังช่วง overnight ที่ไม่ได้สังเกต และอีก 3 มาจาก incomplete trade windows
- ยืนยัน first touch ภายใน observed sessions ได้ 17 รายการ แต่ไม่อ้างว่าเท่ากับยืนยัน first touch ของ cycle ทั้งหมด

## Continuation ที่สังเกตได้

ราคาที่ touch เป็น observed trade price ไม่ใช่ executable entry ค่า return เทียบราคานั้น ใช้ wall-clock และ mark ล่าสุดไม่เกิน target/อายุไม่เกิน 60 วินาที Outcome ที่ผ่านข้อมูลขาด, overnight, long intertrade gap หรือ invalidated touch ถูก censor

| Sample | +3%/-3% upside first | downside first | censored | Mean 5m return (uncensored only) |
|---|---:|---:|---:|---|
| Systematic | 5 | 2 | 0 | +0.134%, n=5; censored=2 |
| Diagnostic | 4 | 4 | 5 | +0.399%, n=7; censored=6 |

นี่เป็น descriptive observations ของ pilot ที่เลือกไว้ ไม่ใช่ probability ของ universe, significance หรือผลตอบแทนกลยุทธ์ โดยเฉพาะ systematic first touches ยังไม่ verified สำหรับช่วง overnight ส่วน diagnostic ตั้งใจเลือก movers จึงมี selection bias

ทุก horizon 5/15/30/60m, session/cycle end, observed MFE/MAE พร้อม timestamps และ barriers +3/-3, +5/-3, +10/-5 อยู่ใน full outcome Parquet และ `cohort_outcomes.json` ซึ่งแยก sample/cohort/session และแสดง censored denominators Confidence intervals ไม่ได้ประมาณสำหรับ pilot ขนาดเล็กที่มี clustering และ diagnostic selection bias; ระบุ `NOT_ESTIMATED` โดยตรง

## ตัวอย่าง audit ที่ทำซ้ำได้

เวลาต่อไปนี้เป็น America/New_York; cycle วันที่ 2026-05-28 เริ่มจาก RTH close วันที่ 2026-05-27

| Security | Event time | P0 | Threshold | Touch | 5m return | +3/-3 outcome |
|---|---|---:|---:|---:|---:|---|
| HOTH | 2026-05-27 16:04:24.363107901 | 1.36 | 1.496 | 1.50 | -0.667% | UPSIDE_FIRST |
| SNGX | 2026-05-27 17:34:36.229025986 | 0.8657 | 0.95227 | 0.9537 | -1.730% | DOWNSIDE_FIRST |

ทั้งสองรายการเป็น verified AH first touches ตาม replay policy ส่วนตัวอย่างที่สามเป็น DBGI 2026-05-27 (systematic, RTH, touch 0.3198, first touch ของทั้ง cycle ยังไม่ verified) ทั้งสามมี source page SHA-256, raw row locator, exact UTC ns, trade conditions, quote reference และ outcomes ใน `verified-audit-examples.json` นอกจากนี้ validator ตรวจทุก event ไม่ได้ตรวจเฉพาะสามตัวอย่าง

## ข้อจำกัด

P0 สืบทอด grouped daily close ของ M1 ซึ่งไม่ได้รับการรับรองอิสระว่าเป็น official auction close Historical exchange/type/identity สืบทอด M1 ไม่มีการใช้ current values แทนประวัติ Current float มี survivorship bias และความเสี่ยงจาก dilution, float changes, reverse splits และ historical misclassification

ไม่มีการรับรอง complete historical halt feed; known-halt interface และ long-gap censoring ผ่าน tests แต่การไม่มี trades ไม่ได้พิสูจน์ว่าเกิด halt Quote conditions ที่บ่งชี้ halt ใน bounded windows ถูกเก็บเป็น flag REST correction reconstruction ที่จับคู่ไม่ได้จะ unresolved; ไม่ใช้ future cancellation flags เพื่อตัด trade ก่อน notice จะมาถึง

โครงสร้างใช้ partitioned ZSTD Parquet และ DuckDB; raw JSON pages เป็น source evidence เพิ่มเติม โหมด pilot มี page/byte budgets และไม่ได้เป็นการ benchmark throughput ระดับ TB ไม่มี Price Confirmation C1/C2/C3 หรือ model optimization

## Reproduction และ artifacts

```sh
.venv/bin/python -m market_lab.m2_pilot run --run-id m2-first-touch-3cycles-20261115-v1 --offline
.venv/bin/python scripts/m2_cohort_report.py m2-first-touch-3cycles-20261115-v1
.venv/bin/python scripts/validate_m2_pilot.py m2-first-touch-3cycles-20261115-v1
.venv/bin/python scripts/m2_query.py --run-id m2-first-touch-3cycles-20261115-v1 --kind events --ticker HOTH --cycle-id 2026-05-28
```

- Full immutable evidence: `data/runs/m2-first-touch-3cycles-20261115-v1/`
- Events/outcomes/opportunities/candidates: แยก Parquet folders ใต้ run directory
- Trade/quote Parquet: `ticks/cycle=DATE/security=FIGI/`
- Compact reports: `reports/m2-first-touch-3cycles-20261115-v1/`
- Local consolidated bundle: `reports/m2-first-touch-3cycles-20261115-v1/research_bundle.zip`
- Validation และ test output: `validation.json`; resume evidence: `resume-validation.json`

ไฟล์ Parquet, ZIP, raw ticks และ credentials ไม่เข้า Git ส่งขึ้นเฉพาะ source, configs, schemas, tests และ compact reports

## Validation ที่รันแล้วและสถานะ

- Full test suite: **135 passed**, 84 existing pandas deprecation warnings
- Replayed events: **20/20**; raw event prices and NBBO references checked: **20/20**
- Source page hashes: **148/148**; execution code hashes match; strict M1 hashes unchanged
- Offline resume: exact event/outcome/opportunity/ledger hashes unchanged; zero additional API requests
- Bundle: **17 files**, SHA-256 manifest verified and ZIP integrity passed; **59,244 bytes**
- Local run evidence: approximately **1.05 GB** (decimal); compact uncompressed report artifacts approximately **185 KB**

| Status | Result |
|---|---|
| ENGINEERING_VALIDATED | true |
| DATA_COVERAGE_VALIDATED | false — 3 incomplete trade windows |
| PILOT_RESULTS_AVAILABLE | true |
| RESEARCH_STATISTICALLY_VALIDATED | false — small exploratory pilot |

ยังไม่ควรใช้ผลนี้สรุปว่าหุ้น +10% จะไปต่อหรือใช้เป็น production strategy ขั้นถัดไปด้านวิจัยคือให้ Research Lead ทบทวน condition/correction policy, censoring และขอบเขต overnight ก่อนอนุมัติรอบข้อมูลเพิ่มเติม ไม่มีการขยาย download budget หรือแตะ holdout ในงานนี้
