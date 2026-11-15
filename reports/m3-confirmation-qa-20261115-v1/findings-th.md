# TASK 003.1 — ผล Confirmation Methodology QA

Run `m3-confirmation-qa-20261115-v1`; baseline `423dead` ไม่เปลี่ยน ใช้ 40 initial events เดิมและ 10 exploration cycles เท่านั้น ไม่มี HTTP requests เพิ่ม ไม่มีการวิเคราะห์ holdout

## C1 sensitivities และ frozen baselines

ทุกแถวมี initial denominator **40**; deadline 60 วินาทีเป็น sensitivity ที่กำหนดก่อนคำนวณ ไม่ใช่การเลือก threshold จากผลกำไร

| Policy | Confirmed | Unconfirmed | Insufficient | Median delay (s) | Median waiting price change |
|---|---:|---:|---:|---:|---:|
| C0_FROZEN | 40 | 0 | 0 | 0.000 | 0.0000% |
| C1_COUNTED_ORIGINAL | 33 | 7 | 0 | 55.578 | 0.0342% |
| C1_COUNTED_ORIGINAL_D60 | 17 | 23 | 0 | 34.924 | 0.0000% |
| C1_OBSERVED_ACCEPTANCE | 31 | 9 | 0 | 97.421 | 0.3775% |
| C1_OBSERVED_ACCEPTANCE_D60 | 10 | 30 | 0 | 33.391 | 0.2642% |
| C1_SESSION_BOUND | 31 | 9 | 0 | 51.881 | 0.0000% |
| C1_SESSION_BOUND_D60 | 17 | 23 | 0 | 34.924 | 0.0000% |
| C2_FROZEN | 6 | 24 | 10 | 36.201 | 3.6994% |

COUNTED_ORIGINAL คงกฎเดิม; OBSERVED_ACCEPTANCE เริ่มสะสมใหม่เมื่อพบ eligible trade ต่ำกว่า threshold; SESSION_BOUND ใช้ counted rule แต่ยืนยันได้เฉพาะ initial AH/PRE/RTH session ไม่ใช่กฎรวม observed acceptance โดยอัตโนมัติ `_D60` จำกัด receipt time <=touch+60 วินาที ทุกแบบใช้สาม distinct trades/span >=30 วินาที และ threshold เดิม

การไม่พบ observed below-threshold trade **ไม่พิสูจน์ continuous market support** งานนี้ไม่เปลี่ยนนิยามเดิมหรือเขียนผล C1/C2 ทับ ความต่างของ count/delay เป็น sensitivity ไม่ใช่เกณฑ์เลือกวิธีเพื่อ maximize positive returns

## C2: ตรวจ 10 insufficient cases รายตัว

Frozen C2 ยังคง confirmed 6 / unconfirmed 24 / insufficient 10 แต่แยก **ลักษณะหลักฐาน** ออกจาก formal signal status ไม่มี quote update ไม่ถูกแปลว่า bid ยืนหรือ support ล้มเหลวโดยอัตโนมัติ

| Security | Cycle | Evidence assessment | Updates | Stale preceding | Invalid/corrected observations |
|---|---|---|---:|---|---:|
| BIVI | 2026-05-28 | NO_QUOTE_RETURNED | 0 | False | 0 |
| ATNM | 2026-05-29 | INVALID_OR_CORRECTED_QUOTES | 4 | False | 5 |
| AREN | 2026-06-01 | INVALID_OR_CORRECTED_QUOTES | 9 | False | 9 |
| FLNT | 2026-06-01 | NO_QUOTE_RETURNED | 0 | False | 0 |
| SMXT | 2026-06-01 | NO_QUOTE_RETURNED | 0 | False | 0 |
| PMI | 2026-06-02 | INVALID_OR_CORRECTED_QUOTES | 282 | False | 283 |
| BGI | 2026-06-04 | INVALID_OR_CORRECTED_QUOTES | 0 | True | 1 |
| ENHA | 2026-06-08 | INVALID_OR_CORRECTED_QUOTES | 33 | False | 34 |
| GCTS | 2026-06-09 | INVALID_OR_CORRECTED_QUOTES | 141 | False | 142 |
| FEAM | 2026-06-09 | STALE_OR_NO_FRESH_UPDATES | 0 | True | 0 |

Assessment counts ของทั้ง 40: {"EXPLICIT_BELOW_THRESHOLD_BID": 12, "EXPLICIT_OBSERVED_SUPPORT_BREAK": 5, "FROZEN_SUPPORT_CONFIRMED": 6, "INVALID_OR_CORRECTED_QUOTES": 6, "NO_QUOTE_RETURNED": 3, "STALE_OR_NO_FRESH_UPDATES": 1, "SUPPORT_UNPROVEN_FRESHNESS_GAPS_NOT_FAILURE": 7}

Explicit valid below-threshold bid กับ observed support break เป็นหลักฐานราคาเชิงลบที่สังเกตจริง ส่วน freshness gap/ช่วงไม่มี update คือ support ที่ยังพิสูจน์ไม่ได้ ไม่ใช่ genuine observed break; timelines และหลาย flags อาจซ้อนกัน กฎ quote conditions/freshness/10-second support เดิมไม่เปลี่ยน ไม่ใช้ corrected quote fields เป็น original PIT NBBO และไม่อ้างว่า provider มี data outage จากการไม่มี update

## Common wall-clock exits

Exit = **original first touch+5/15/30/60 นาที** ทุก policy ใช้ target และ observed exit mark เดียวกันใน event/condition เดียวกัน Entry ต้องเกิดแล้วก่อนหรือเท่ากับ landmark จึงมี return ได้ `NOT_YET_CONFIRMED` แยกจาก final unconfirmed/insufficient; ไม่มีการใส่ zero return ให้กลุ่มเหล่านี้

แต่ละช่องแสดง **observable / censored / not-yet-confirmed / unconfirmed / insufficient** รวมครบ 40; median return เป็น conditional เฉพาะ observable subset ซึ่งเปลี่ยนตาม policy จึงไม่ใช่ unconditional performance

| Policy | Landmark | Population buckets | Median observed return |
|---|---|---|---:|
| C0_FROZEN | 5m | 23 / 17 / 0 / 0 / 0 | -1.515% |
| C0_FROZEN | 15m | 20 / 20 / 0 / 0 / 0 | -0.967% |
| C0_FROZEN | 30m | 19 / 21 / 0 / 0 / 0 | -0.209% |
| C0_FROZEN | 60m | 15 / 25 / 0 / 0 / 0 | -0.180% |
| C1_COUNTED_ORIGINAL | 5m | 17 / 6 / 10 / 7 / 0 | -1.640% |
| C1_COUNTED_ORIGINAL | 15m | 19 / 11 / 3 / 7 / 0 | -1.056% |
| C1_COUNTED_ORIGINAL | 30m | 18 / 13 / 2 / 7 / 0 | 0.045% |
| C1_COUNTED_ORIGINAL | 60m | 15 / 16 / 2 / 7 / 0 | -0.120% |
| C1_COUNTED_ORIGINAL_D60 | 5m | 15 / 2 / 0 / 23 / 0 | -1.926% |
| C1_COUNTED_ORIGINAL_D60 | 15m | 13 / 4 / 0 / 23 / 0 | -1.111% |
| C1_COUNTED_ORIGINAL_D60 | 30m | 14 / 3 / 0 / 23 / 0 | 0.084% |
| C1_COUNTED_ORIGINAL_D60 | 60m | 12 / 5 / 0 / 23 / 0 | -1.487% |
| C1_OBSERVED_ACCEPTANCE | 5m | 15 / 4 / 12 / 9 / 0 | -1.640% |
| C1_OBSERVED_ACCEPTANCE | 15m | 16 / 10 / 5 / 9 / 0 | -0.818% |
| C1_OBSERVED_ACCEPTANCE | 30m | 17 / 11 / 3 / 9 / 0 | -0.543% |
| C1_OBSERVED_ACCEPTANCE | 60m | 15 / 13 / 3 / 9 / 0 | -1.801% |
| C1_OBSERVED_ACCEPTANCE_D60 | 5m | 9 / 1 / 0 / 30 / 0 | -2.485% |
| C1_OBSERVED_ACCEPTANCE_D60 | 15m | 7 / 3 / 0 / 30 / 0 | -1.111% |
| C1_OBSERVED_ACCEPTANCE_D60 | 30m | 7 / 3 / 0 / 30 / 0 | -0.120% |
| C1_OBSERVED_ACCEPTANCE_D60 | 60m | 7 / 3 / 0 / 30 / 0 | -2.490% |
| C1_SESSION_BOUND | 5m | 17 / 6 / 8 / 9 / 0 | -1.640% |
| C1_SESSION_BOUND | 15m | 19 / 11 / 1 / 9 / 0 | -1.056% |
| C1_SESSION_BOUND | 30m | 18 / 13 / 0 / 9 / 0 | 0.045% |
| C1_SESSION_BOUND | 60m | 15 / 16 / 0 / 9 / 0 | -0.120% |
| C1_SESSION_BOUND_D60 | 5m | 15 / 2 / 0 / 23 / 0 | -1.926% |
| C1_SESSION_BOUND_D60 | 15m | 13 / 4 / 0 / 23 / 0 | -1.111% |
| C1_SESSION_BOUND_D60 | 30m | 14 / 3 / 0 / 23 / 0 | 0.084% |
| C1_SESSION_BOUND_D60 | 60m | 12 / 5 / 0 / 23 / 0 | -1.487% |
| C2_FROZEN | 5m | 6 / 0 / 0 / 24 / 10 | -1.844% |
| C2_FROZEN | 15m | 6 / 0 / 0 / 24 / 10 | -5.893% |
| C2_FROZEN | 30m | 4 / 2 / 0 / 24 / 10 | -3.220% |
| C2_FROZEN | 60m | 5 / 1 / 0 / 24 / 10 | -4.838% |

`common-landmark-pairs.json` เก็บคู่ครบ **2,240 rows** รวม missing/censored พร้อม matching keys, timestamps และ source locators; `paired_summary.json` เก็บจำนวน matched pairs และ conditional differences ไม่ตีความ survivor-only paired means ว่าเป็นผลของกลยุทธ์บนทั้งประชากร Own-signal horizon distributions/barriers เดิมยังอยู่ในทุก event และ cohort summary แยกจาก common-clock

Common 5-minute matched pairs เทียบ C0 (initial denominator 40 ทุกแถว):

| Policy | Matched observable pairs | Median return difference (percentage points) |
|---|---:|---:|
| C1_COUNTED_ORIGINAL | 17/40 | +0.000 |
| C1_COUNTED_ORIGINAL_D60 | 15/40 | +0.000 |
| C1_OBSERVED_ACCEPTANCE | 15/40 | -0.890 |
| C1_OBSERVED_ACCEPTANCE_D60 | 9/40 | -0.320 |
| C1_SESSION_BOUND | 17/40 | +0.000 |
| C1_SESSION_BOUND_D60 | 15/40 | +0.000 |
| C2_FROZEN | 6/40 | -3.296 |

นี่เป็น conditional difference ในคู่ที่ทั้งสองฝั่งมี mark เท่านั้น ช่วง exit เดียวกันทำให้เห็นผลของ entry-price difference ชัดขึ้น แต่ไม่แก้ missingness ให้กลายเป็น unconditional performance และไม่ใช่ executable returns

## Pre-confirmation path, weights และ cohorts

ทุก event-policy เก็บ MFE/MAE ก่อนสัญญาณ อ้างอิงราคา original touch พร้อม exact sources และ +3/−3, +5/−3, +10/−5 first-passage ก่อน signal ไม่รวม signal trade ในช่วงรอ สำหรับ no-signal cases ใช้ operational deadline/session/cycle end ที่ประกาศไว้แทนและติด flags จึงไม่เงียบตัดเหตุการณ์เหล่านี้ออก Overnight/unknown/corrections/stale-tail flags ยังคงอยู่ ไม่มีการย้ายข้อมูล extrema ย้อนเข้า trigger

| Policy | Pre-confirmation MFE median | MAE median | Censored waiting paths /40 |
|---|---:|---:|---:|
| C0_FROZEN | 0.000% | 0.000% | 0/40 |
| C1_COUNTED_ORIGINAL | 0.165% | -1.117% | 14/40 |
| C1_COUNTED_ORIGINAL_D60 | 0.000% | -0.299% | 0/40 |
| C1_OBSERVED_ACCEPTANCE | 0.434% | -1.448% | 13/40 |
| C1_OBSERVED_ACCEPTANCE_D60 | 0.000% | -0.299% | 0/40 |
| C1_SESSION_BOUND | 0.132% | -0.831% | 16/40 |
| C1_SESSION_BOUND_D60 | 0.000% | -0.299% | 0/40 |
| C2_FROZEN | 0.000% | -0.299% | 0/40 |

ตาราง pre-path รวม no-signal cases ด้วย cutoff ที่ต่างกันตามนิยาม และเก็บ observed extrema แม้ path ถูก censor จึงไม่ใช่การเปรียบเทียบ opportunity/fill ที่เท่ากันโดยอัตโนมัติ

ทุก policy คง risk set proxy 25 events กับ complementary 15 events และ original cycle/stratum N/n, n/N ไม่ reweight เฉพาะ confirmed survivors ค่า weighted buckets/conditional means เป็น descriptive ratios เท่านั้น ไม่มี population/significance/profitability inference ตารางตาม AH/PRE/RTH, float strata และ odd-lot follow-up sensitivity อยู่ใน `cohort_metrics.json` ทั้ง 192 กลุ่ม Current float ไม่ใช่ historical PIT; SEC/M1 ไม่เปลี่ยน

## Execution-data coverage และ proposed quote budget

นับ unique primary-policy entry/exit targets ได้ **450**: cached fresh-valid **34**, มี complete time coverage แต่ invalid/stale **31**, ขาด time coverage **385** snapshot windows แต่ละ missing window ขอช่วงย้อนหลัง 5 วินาที+1ns ถึง target เพื่อรับ preceding mark การขอหนึ่งหน้าต่อทุก unmerged missing window ต้องอย่างน้อย 385 calls โดยยังไม่รู้จำนวน pages จริงหรือว่าจะมี valid quotes หรือไม่

แผน probe ที่เสนอ: **10 windows / 40 requests / 40 pages / 4 pages ต่อ window / 64 MiB decoded / 8 MiB ต่อ page / 256 MiB storage**, connect/read timeout 5/20s, รวมไม่เกิน 600s และ spacing >=250ms เลือก queue แบบ cycle round-robin ตาม identity/time ไม่ดู returns ใช้ subscription เดิมเท่านั้น แผนนี้ **ยังไม่อนุมัติให้ fetch และไม่ได้ execute**; full queue กับ pilot queue อยู่ใน `quote-top-up-plan.json`

Snapshot ask-entry/bid-exit marks ไม่พิสูจน์ fills, queue, size, latency/costs หรือ bid-path barriers การ top-up อาจได้ empty/partial response และไม่แก้ historical corrected quote fields โดยอัตโนมัติ ไม่อ้าง executable P&L และไม่ขยาย 80 exploration cycles

## Validation และ reproduction

Tests **197 passed** (84 existing pandas warnings); baseline **240 signal/condition records พร้อม outcomes** ตรงเดิม, protected artifacts **7883 files** ไม่เปลี่ยน, ตรวจ raw source **79 pages / 8741 references**; independent checker ตรวจ qualifying C1 proof 912 records และ C0 common marks 320 จุดตรง own-clock C0 เดิม ไม่มี HTTP request และไม่ parse holdout outcomes

```sh
python -m market_lab.confirmation_qa_run run
python -m market_lab.confirmation_qa_run validate
python -m pytest -q > /tmp/confirmation-qa-tests.txt
python -m scripts.finalize_confirmation_qa --pytest-output /tmp/confirmation-qa-tests.txt
```

Full new local run/checkpoints อยู่ใน `data/runs/m3-confirmation-qa-20261115-v1/`; compact reports และ single `research_bundle.zip` อยู่ใน `reports/m3-confirmation-qa-20261115-v1/` ZIP/Parquet/raw data ไม่เข้า Git ตาม convention เดิม ทุก 640 event-policy-condition rows และ own/common outcomes รวมครบสิบ cycles ไม่มี truncation Fresh checkout อ่าน compact results ได้ แต่ raw source revalidation ต้องมี immutable existing cache

ข้อจำกัดยังเป็น small dependent stratified sample, conditioning ที่ +10% first touch, retrospective float/REST evidence, unverified overnight/feed continuity และ M1 grouped close ที่ไม่ได้รับรอง official auction close อิสระ งานนี้ประเมินความหมายและความเป็นธรรมของ comparison ไม่เลือก thresholds หรืออ้างผลกำไร
