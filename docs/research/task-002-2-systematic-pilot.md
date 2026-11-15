# TASK 002.2 — ผล Systematic Tick Replay Expansion

Run: `m2-systematic-10cycles-20261115-v2`

Baseline: `21ed2f8` จาก `feat/task-002-1-replay-methodology-qa`

ดำเนินการจริงครบ **10/10 exploration cycles**, **240/240 trade windows** มี terminal pagination โดยไม่มี API errors ไม่ใช้ holdout, ไม่เพิ่ม subscription, ไม่ปรับ thresholds และไม่ทำ Price Confirmation models

## Sampling และ denominators

ใช้ประชากร historical M1 ของ **แต่ละวัน** ที่ผ่าน exchange/CS/price/identity/currency/corporate-action/change gates เดิม ไม่จำกัดหุ้นจากวันแรก ประชากรรวม 7,211 security-cycle records ในสิบวัน แต่ละวันมี 707–743 securities

สุ่มวันละ 24 opportunities: 12 จาก current-float proxy 100K–15M และ 12 จาก complementary control stratum ด้วย master seed `202611150022` และ independent cycle/stratum seeds ที่ freeze ก่อนอ่าน ticks เก็บ N, n, inclusion probability n/N และ design weight N/n ทุกแถว โอกาสถูกเลือกอยู่ประมาณ 2.70–4.15% ตามวันและ stratum ไม่มี diagnostic sample ที่เลือกจาก future movement ใน run นี้

240 opportunities ประกอบด้วย 212 securities; 26 securities ปรากฏมากกว่าหนึ่ง cycle การคำนวณต่าง policy, overlapping cohorts และ observations ของ issuer เดิมไม่ใช่ independent samples ไม่มีการใช้ unweighted pooled count เป็น probability ของ universe และยังไม่ทำ population inference หรือ iid confidence intervals

| Cycle | Selected / complete windows | Primary events | Zero-event opportunities |
|---|---:|---:|---:|
| 2026-05-27 | 24 / 24 | 5 | 19 |
| 2026-05-28 | 24 / 24 | 4 | 20 |
| 2026-05-29 | 24 / 24 | 5 | 19 |
| 2026-06-01 | 24 / 24 | 6 | 18 |
| 2026-06-02 | 24 / 24 | 3 | 21 |
| 2026-06-03 | 24 / 24 | 3 | 21 |
| 2026-06-04 | 24 / 24 | 4 | 20 |
| 2026-06-05 | 24 / 24 | 2 | 22 |
| 2026-06-08 | 24 / 24 | 4 | 20 |
| 2026-06-09 | 24 / 24 | 4 | 20 |
| รวม | 240 / 240 | 40 | 200 |

Primary เป็น `OBSERVED_SESSIONS_FIRST / HIGH_LOW_ONLY / NO_MECHANICAL_GAP` ทั้ง 40 events verified ภายใน observed sessions เท่านั้น ไม่ใช่ strict full-cycle verification

| First-touch session | Verified risk-set opportunities | Events |
|---|---:|---:|
| AH | 240 | 9 |
| PRE | 231 | 10 |
| RTH | 221 | 21 |

Risk set ของ session ถัดไปตัด opportunities ที่ touch แล้วใน session ก่อนหน้า จึงห้ามบวก denominators ทั้งสามเป็น sample ใหม่ `denominators.json` มี 240 crossed rows แยก cycle/session/cohort/sample/policy พร้อม population eligibility frame N และ selected risk-set N ซึ่งเป็นคนละความหมาย

| Analytical cohort | Selected opportunities | Primary events |
|---|---:|---:|
| EXCHANGE_PRICE_ONLY (ทั้งสอง sampling strata) | 240 | 40 |
| MASSIVE_CURRENT_FLOAT_PROXY (subset) | 120 | 25 |
| Complementary sampling stratum | 120 | 15 |
| SEC evidence overlap (subset) | 8 | 0 |

Current float ของ selected opportunities: eligible 120, out of range 102, unresolved 18 เป็น **security-cycle counts** ไม่ใช่จำนวน unique securities SEC context ยังคงแยกจาก eligibility และไม่มีการ forward-fill estimates

## Observed continuation

Barriers เทียบ **actual first-touch trade price** ไม่ใช่ P0 และไม่สมมติว่า execute order ได้ที่ราคานั้น ผลต่อไปนี้เป็น full selected primary sample แบบไม่ถ่วงน้ำหนัก:

| Upside / downside | Upside first | Downside first | Neither | Censored |
|---|---:|---:|---:|---:|
| +3% / -3% | 14 | 20 | 3 | 3 |
| +5% / -3% | 9 | 24 | 4 | 3 |
| +10% / -5% | 5 | 22 | 9 | 4 |

Forward marks ใช้ wall-clock, latest eligible trade ไม่เกิน target และอายุไม่เกิน 60 วินาที แม้ pagination ครบก็ยัง censor จาก freshness, overnight, missing/unknown price evidence และ corrections ตาม policy

| Horizon | Uncensored / 40 | Mean return | Median return | Censored |
|---|---:|---:|---:|---:|
| 5m | 23 | -0.794% | -1.515% | 17 |
| 15m | 20 | -1.302% | -0.967% | 20 |
| 30m | 19 | -0.655% | -0.209% | 21 |
| 60m | 15 | +0.194% | -0.180% | 25 |
| Session end | 28 | +1.718% | -3.617% | 12 |
| Cycle end | 30 | -0.385% | -3.874% | 10 |

ค่า mean/median เป็นของ **uncensored subset ที่ต่างกันในแต่ละ horizon** จึงไม่ใช่เส้นผลตอบแทนของ cohort เดียวกันทุกช่วง และไม่ใช่ผลกำไรกลยุทธ์ Complete pagination ไม่ได้ทำให้ราคาที่เงียบ/เก่าเป็น executable mark

Observed MFE/MAE พร้อม timestamps และ windows อยู่ใน full outcomes; 10 จาก 40 primary excursion windows มี censoring flags ผลแยกตาม cycle และ security รวม forward distributions และ barrier counts อยู่ใน `cycle_metrics.json` / `security_variation.json` ไม่ได้สรุปเพียงค่าเฉลี่ยรวม

## Sensitivities และ anomalies

- Odd-lot sensitivity ให้ 43 events: เพิ่ม 3 opportunities และเปลี่ยน first-touch timestamp ของ 19 events เดิม ไม่รวมกับ primary เป็น 83 independent events
- สำหรับ +3/-3 ใน primary: ไม่มี mechanical gap censoring ให้ censored 3; กฎ 900 วินาทีให้ 8; กฎ 300 วินาทีให้ 15 ความต่างนี้แสดงผลของ continuity assumption ไม่ใช่การเลือก policy จากผลตอบแทน
- ยังรักษา overnight/freshness/correction/unknown-evidence checks ทุก sensitivity ไม่มีการนับช่วงเงียบเป็น halt หรือ missing page โดยอัตโนมัติ
- Primary preceding NBBO relations: within 32, unavailable/invalid 7, above ask 1 โดย quality/freshness flags ของแต่ละ quote อยู่ใน event payload
- **DEVS, cycle 2026-06-05, AH:** touch 0.518 เทียบ preceding bid/ask 0.4925 / 0.5000 อายุ quote 719.027253 ms; trade condition `[12]` เก็บ `ABOVE_PRECEDING_ASK` พร้อม raw trade/quote locators ไม่ลบ event และไม่อ้างสาเหตุหรือ executable fill

## ข้อมูลและงบที่ใช้จริง

- Trades: **2,722,278** raw/normalized records
- NBBO: **7,316** records ใน **62/62** bounded windows ที่ pagination ครบ เฉพาะ ±60 วินาทีรอบ detected primary/sensitivity events ไม่ใช่ quote coverage ทั้ง cycle
- Requests/pages: **351 / 351** รวม reference preparation; errors **0**
- Decoded response bytes: **643,037,535** (~613.25 MiB) ภายใน 2 GiB
- Frozen ceilings: 900 requests, 850 pages, 64 pages/window, 160 quote windows, 6 GiB run storage
- Local run artifacts ประมาณ **913 MB**; local research bundle ประมาณ **0.4 MB**; ไม่มี raw ticks, Parquet หรือ credentials เข้า Git

Preparation ครั้งแรก (`...-v1`) หยุดก่อน selection/tick outcomes เพราะ bulk float response มีหนึ่งแถวไม่มี ticker เก็บหลักฐานเดิมไว้ครบ แก้ parser ให้บันทึกเป็น unmapped evidence แล้วเริ่ม `...-v2` ด้วย reference cache เดิม 17 requests ไม่มีการเรียก reference ซ้ำ และ budget ledger ยังคงนับ 17 requests นั้น ค่า float ที่ไม่มี identity ไม่ถูกผูกกับหุ้นอื่นหรือเติมขึ้นเอง ดู `preparation-data-quality.json`

## Validation และสถานะ

- **162 tests passed**, 84 existing pandas deprecation warnings
- Deterministic replay: **240 opportunities**, **83 event-policy records**, **249 outcomes** ตรงเดิมทั้งหมด
- ตรวจ **334 raw tick pages**, terminal cursor chains, timestamp bounds, source hashes, event raw prices และ NBBO context
- ตรวจ historical eligibility และ sampling probabilities/weights ครบ 240 opportunities; ไม่ทำ zero-event denominator หาย
- Full JSON export เท่ากับ full Parquet: 83 event-policy records, 249 outcomes, 480 policy-opportunity records
- Offline resume เรียก HTTP เพิ่ม **0**, hashes ของ selection/execution/events/outcomes/opportunities/ledger ตรงเดิม
- Existing artifacts **1,917 files** ไม่เปลี่ยน รวม M1 และ prior pilots; holdout ไม่ถูกวิเคราะห์
- Bundle ZIP integrity และ manifest SHA-256 ผ่านการตรวจ

| Status | Result |
|---|---|
| ENGINEERING_VALIDATED | true |
| DATA_COVERAGE_VALIDATED | true — provider pagination ของ observed sessions/ bounded quote windows |
| PILOT_RESULTS_AVAILABLE | true |
| RESEARCH_STATISTICALLY_VALIDATED | false |
| STRICT_FULL_CYCLE_FIRST | unavailable; independent overnight verification ไม่มี |

ข้อจำกัดหลักยังเป็น retrospective current-float proxy, historical float misclassification/survivorship/dilution/splits, M1 grouped-close reference ที่ไม่ได้รับรองอิสระว่าเป็น official auction close, provider condition dictionary ที่ไม่ใช่ historical SIP rulebook, absence of independent halt/feed-loss certification, freshness censoring และ dependent/stratified sample ผลนี้ไม่ใช่คำยืนยัน profitability หรือข้อสรุปว่าประชากรหุ้น +10% จะไปต่อ/ไม่ไปต่อ

## Reproduction และ query

```sh
.venv/bin/python -m market_lab.systematic_pilot run --offline
.venv/bin/python -m market_lab.systematic_pilot validate --offline
.venv/bin/python scripts/systematic_denominators.py
.venv/bin/python scripts/compact_systematic_reports.py
.venv/bin/python scripts/validate_systematic_export.py
.venv/bin/python scripts/query_systematic_pilot.py --kind events --ticker DEVS --cycle-id 2026-06-05
.venv/bin/python scripts/query_systematic_pilot.py --kind population --cycle-id 2026-06-01 --limit 10
```

Full local evidence: `data/runs/m2-systematic-10cycles-20261115-v2/`

Compact results และ consolidated bundle: `reports/m2-systematic-10cycles-20261115-v2/`

Fresh checkout อ่านผลได้จาก compact JSON แต่การ audit raw ticks ต้องมี local immutable evidence cache ตาม source paths และ hashes ห้ามอ้างว่าเพียง checkout แล้วจะได้ raw data ครบ
