# TASK 004 — ผล Temporal Expansion & Statistical Preparation

Run `m4-temporal-10cycles-20261115-v1`; baseline `e160627`. Freeze 30 exploration dates และ 720 security-cycle opportunities ก่อนอ่าน tick ใหม่; execute เฉพาะ initial batch **10 dates /240 opportunities** กระจาย June–September ไม่เพิ่มอีก 20 วันที่ reserve และไม่วิเคราะห์ 40-cycle holdout

## Frozen sampling

Remaining 70 dates: June14 /July22 /August21 /September13; เลือก 30 เป็น **6/9/9/6**, เลือก batch แรก 10 เป็น **2/3/3/2** ด้วย independent seeded SRS/second-stage permutation และ fixed round-robin order ไม่เลือกจาก returns ทุกวันสุ่ม 12 proxy +12 complementary ด้วย historical M1 gates เดิม เก็บ N,n,n/N,N/n และ date/joint probabilities/weights ทุกแถว

Snapshot current float ใช้ cache เดิมที่ตรวจ hash แล้วจาก development run และ identity FIGI mapping แบบเดิม จึงไม่เปลี่ยน classifier หลังเห็นผล Current float เป็น retrospective proxy ไม่ใช่ historical PIT; SEC evidence แยกและไม่ forward-fill; unresolved proxy อยู่ complementary stratum ไม่ถูกทิ้ง

## Actual coverage และ first touch

| Cycle | Selected | Complete trades | Verified events | Zero-event opportunities | Sessions |
|---|---:|---:|---:|---:|---|
| 2026-06-18 | 24 | 24 | 6 | 18 | {"AH": 1, "PRE": 1, "RTH": 4} |
| 2026-07-16 | 24 | 24 | 2 | 22 | {"AH": 2} |
| 2026-08-06 | 24 | 24 | 4 | 20 | {"AH": 2, "PRE": 2} |
| 2026-09-02 | 24 | 24 | 2 | 22 | {"PRE": 1, "RTH": 1} |
| 2026-06-26 | 24 | 24 | 4 | 20 | {"AH": 1, "PRE": 1, "RTH": 2} |
| 2026-07-17 | 24 | 24 | 2 | 22 | {"PRE": 2} |
| 2026-08-18 | 24 | 24 | 2 | 22 | {"PRE": 1, "RTH": 1} |
| 2026-09-17 | 24 | 24 | 3 | 21 | {"AH": 1, "RTH": 2} |
| 2026-07-15 | 24 | 24 | 2 | 22 | {"RTH": 2} |
| 2026-08-25 | 24 | 24 | 4 | 20 | {"PRE": 2, "RTH": 2} |

รวม complete trade windows **240/240**, verified primary first touches **31**, zero-event opportunities **209**, unknown quality/coverage opportunities **0**. Unverified candidates เก็บใน source tables แต่ไม่เข้าร่วม verified confirmation risk set ไม่ใส่ missing เป็น zero-event

ใช้ **333 requests /333 pages /547,780,770 decoded bytes**; HTTP/network error attempts 0; acquisition stop reason `None`; analysis stop reason `None`. งบ 1,200 attempts/1,150 pages/3GiB decoded/10GiB storage; acquisition1800s, offline analysis5400s

| Historical analytical stratum | Selected | Complete | Event candidates | Joint-weighted observed incidence |
|---|---:|---:|---:|---:|
| PROXY_FLOAT_IN_RANGE | 120 | 120 | 24 | 19.770% |
| OTHER_EXCHANGE_PRICE_ELIGIBLE | 120 | 120 | 7 | 5.958% |

Session-specific verified risk sets (ตัด earlier-session touches ออกจาก session ถัดไป ไม่บวกเป็น independent samples):

| Session | Risk set | Events |
|---|---:|---:|
| AH | 240 | 7 |
| PRE | 233 | 10 |
| RTH | 223 | 14 |

## Frozen confirmation rules บน initial risk set เดียวกัน

Risk set ใหม่ = verified primary events **31**; analyzed initial events **31**. C0, original counted/observed acceptance/session-bound C1 และ D60 sensitivities กับ C2 ใช้ TASK003.1 code เดิมโดยตรง ไม่ retune3 trades/30s, quote freshness5s/support10s/window60s หรือ +10% threshold

| Policy | Initial | Confirmed | Unconfirmed | Insufficient | Median delay(s) | Median waiting price change |
|---|---:|---:|---:|---:|---:|---:|
| C0_FROZEN | 31 | 31 | 0 | 0 | 0.000 | 0.000% |
| C1_COUNTED_ORIGINAL | 31 | 21 | 10 | 0 | 94.893 | -0.061% |
| C1_COUNTED_ORIGINAL_D60 | 31 | 8 | 23 | 0 | 37.216 | -0.189% |
| C1_OBSERVED_ACCEPTANCE | 31 | 20 | 11 | 0 | 167.861 | 0.000% |
| C1_OBSERVED_ACCEPTANCE_D60 | 31 | 4 | 27 | 0 | 41.803 | -0.159% |
| C1_SESSION_BOUND | 31 | 20 | 11 | 0 | 89.398 | -0.030% |
| C1_SESSION_BOUND_D60 | 31 | 8 | 23 | 0 | 37.216 | -0.189% |
| C2_FROZEN | 31 | 2 | 23 | 6 | 38.807 | 1.534% |

No observed below-threshold trade ไม่พิสูจน์ continuous support; C2 ไม่มี quote update ไม่ใช่หลักฐาน support หรือfailureโดยอัตโนมัติ Odd-lot discovery แยกจาก primary; follow-up sensitivity ยังคง initial primary anchor และไม่เพิ่ม odd-only events เข้า confirmation risk set

Odd-lot discovery sensitivity: primary 31, odd 46, added security-cycle events 15, changed primary-pair touch timestamps 20 ไม่รวมเป็น independent observations; confirmation follow-up ยังใช้ primary risk setเดิม. SEC secondary overlap = 4 selected opportunities /1 verified primary events เป็น evidence context เท่านั้น ไม่อนุมัติ historical float eligibility

Common landmarks ใช้ touch+5/15/30/60 นาทีและ exit mark เดียวกันทุก policy เก็บ not-yet-confirmed/unconfirmed/insufficient/censored ครบ พร้อม paired matching โดยไม่เปรียบ survivor-only return means เป็น unconditional improvement

| Policy | Common exit | Observed /initial | Censored | Not yet | Unconfirmed | Insufficient | Median observed return |
|---|---|---:|---:|---:|---:|---:|---:|
| C0_FROZEN | 5m | 14/31 | 17 | 0 | 0 | 0 | -2.754% |
| C0_FROZEN | 15m | 14/31 | 17 | 0 | 0 | 0 | -5.738% |
| C0_FROZEN | 30m | 12/31 | 19 | 0 | 0 | 0 | -5.571% |
| C0_FROZEN | 60m | 8/31 | 23 | 0 | 0 | 0 | -4.338% |
| C1_COUNTED_ORIGINAL | 5m | 11/31 | 5 | 5 | 10 | 0 | -1.831% |
| C1_COUNTED_ORIGINAL | 15m | 10/31 | 8 | 3 | 10 | 0 | -5.735% |
| C1_COUNTED_ORIGINAL | 30m | 10/31 | 9 | 2 | 10 | 0 | -4.515% |
| C1_COUNTED_ORIGINAL | 60m | 6/31 | 14 | 1 | 10 | 0 | -0.332% |
| C1_COUNTED_ORIGINAL_D60 | 5m | 7/31 | 1 | 0 | 23 | 0 | -1.856% |
| C1_COUNTED_ORIGINAL_D60 | 15m | 5/31 | 3 | 0 | 23 | 0 | -3.700% |
| C1_COUNTED_ORIGINAL_D60 | 30m | 5/31 | 3 | 0 | 23 | 0 | -5.929% |
| C1_COUNTED_ORIGINAL_D60 | 60m | 5/31 | 3 | 0 | 23 | 0 | -3.649% |
| C1_OBSERVED_ACCEPTANCE | 5m | 9/31 | 4 | 7 | 11 | 0 | -1.831% |
| C1_OBSERVED_ACCEPTANCE | 15m | 8/31 | 8 | 4 | 11 | 0 | -5.735% |
| C1_OBSERVED_ACCEPTANCE | 30m | 8/31 | 9 | 3 | 11 | 0 | -2.781% |
| C1_OBSERVED_ACCEPTANCE | 60m | 4/31 | 13 | 3 | 11 | 0 | 0.939% |
| C1_OBSERVED_ACCEPTANCE_D60 | 5m | 3/31 | 1 | 0 | 27 | 0 | 0.840% |
| C1_OBSERVED_ACCEPTANCE_D60 | 15m | 1/31 | 3 | 0 | 27 | 0 | 6.112% |
| C1_OBSERVED_ACCEPTANCE_D60 | 30m | 1/31 | 3 | 0 | 27 | 0 | 5.937% |
| C1_OBSERVED_ACCEPTANCE_D60 | 60m | 1/31 | 3 | 0 | 27 | 0 | 4.773% |
| C1_SESSION_BOUND | 5m | 11/31 | 5 | 4 | 11 | 0 | -1.831% |
| C1_SESSION_BOUND | 15m | 10/31 | 8 | 2 | 11 | 0 | -5.735% |
| C1_SESSION_BOUND | 30m | 10/31 | 9 | 1 | 11 | 0 | -4.515% |
| C1_SESSION_BOUND | 60m | 6/31 | 14 | 0 | 11 | 0 | -0.332% |
| C1_SESSION_BOUND_D60 | 5m | 7/31 | 1 | 0 | 23 | 0 | -1.856% |
| C1_SESSION_BOUND_D60 | 15m | 5/31 | 3 | 0 | 23 | 0 | -3.700% |
| C1_SESSION_BOUND_D60 | 30m | 5/31 | 3 | 0 | 23 | 0 | -5.929% |
| C1_SESSION_BOUND_D60 | 60m | 5/31 | 3 | 0 | 23 | 0 | -3.649% |
| C2_FROZEN | 5m | 2/31 | 0 | 0 | 23 | 6 | 10.543% |
| C2_FROZEN | 15m | 2/31 | 0 | 0 | 23 | 6 | 7.932% |
| C2_FROZEN | 30m | 2/31 | 0 | 0 | 23 | 6 | 5.625% |
| C2_FROZEN | 60m | 2/31 | 0 | 0 | 23 | 6 | 6.557% |

Own-signal 5/15/30/60m returns, MFE/MAE, first passage +3/−3/+5/−3/+10/−5 และ 300/900-second censoring sensitivities อยู่ครบใน event-level tables, รวม pre-confirmation excursions/crossings และ exact source timestamps. `design-weighted-policy-metrics.json` เก็บ joint-weighted buckets/conditional means และ effective observable denominators; ไม่ใช้คำว่า profitability

## Temporal comparison และ uncertainty feasibility

Development เดิม: **40/240** primary events จากสิบวัน May–June ที่เลือกติดกัน ใช้เป็น development evidence เท่านั้น New distributed exploration: **31/240** verified events (unknown 0); joint-design-weighted observed incidence **11.694%** เป้าหมายคือ remaining70 exploration dates ไม่ใช่ development+new pooled validation หรือ holdout

Original C1 counted33/40, observed acceptance31/40, session-bound31/40; D60 17/10/17; C2 6 confirmed/24 unconfirmed/10 insufficient ใช้เป็น frozen descriptive reference ไม่ใช่ independence assumption หรือ causal comparator ค่า incidence/confirmation ต่างเวลาอาจเกี่ยวข้องกับ calendar composition, unequal weights, retrospective float classification และ missingness จึงไม่เลือก policy จากผลที่ดีขึ้น

Effective denominators: selected 240, quality-complete 240, Kish n_eff 232.91683268314478, date clusters 10, security clusters 210. Two-stage Taylor SE `0.012354783703241782`; status `EXPLORATORY_TWO_STAGE_DESIGN_LINEARIZATION_NOT_SIGNIFICANCE`. Date+security−intersection cluster-score SE `0.016998842354849872` เป็น sensitivity ไม่ใช่ iid event interval

Month-stratified date × crossed-security resampling 500 replicates: p2.5/median/p97.5 = 0.0659421216245301/0.11669245720657903/0.1683104915281683. นี่เป็น **illustrative resampling range ไม่ใช่ calibrated confidence interval**. มีเพียง10 date clusters/2–3ต่อเดือน; repeated securities และ subset censoring จำกัด inference. ไม่มี significance test และ suppress finite-population design SE เมื่อมี nonresponse/unknown prior evidence

Design-based SE อ้างอิง fixed remaining70-date finite population ภายใต้การสุ่มที่ประกาศไว้ ไม่ใช่ stationarity test หรือ superpopulation forecast; date/security sensitivities ยังไม่ calibrate serial dependence ระหว่างวัน จึงไม่อ้างว่า10วันที่กระจายใหม่พิสูจน์ความเสถียรทั่วไปของ strategy

## Integrity และ reproduction

Tests **223 passed** (84 existing pandas warnings); protected files **8035** ไม่เปลี่ยน; ตรวจ coverage pages **333**, raw signal references **705**. Reproduced30date/720security selections; selection fingerprint precedes first HTTP request; deterministic first-touch replays **240**. Reserved20datesไม่ถูกเรียกtick endpoint; M1/SEC/priorM2/M3/holdoutเก็บเดิมครบ

```sh
python -m market_lab.temporal_pilot prepare
python -m market_lab.temporal_pilot acquire --offline
python -m market_lab.temporal_pilot analyze
python -m market_lab.temporal_pilot validate
python -m pytest -q > /tmp/temporal-tests.txt
python -m scripts.finalize_temporal --pytest-output /tmp/temporal-tests.txt --replay-ticks
```

Online acquisition ดำเนินการแล้วภายในrunนี้ ไม่ควรใช้คำสั่งonlineเพื่อขยาย20reserveddates Full raw/normalized evidence local under `data/runs/m4-temporal-10cycles-20261115-v1/`; compact reports และ consolidated `research_bundle.zip` under `reports/m4-temporal-10cycles-20261115-v1/`. Fresh checkout อ่าน compact results ได้; raw revalidationต้องมีimmutablecache ไม่มีraw ticks, Parquet หรือcredentialsเข้าGit

ข้อจำกัดคงเดิม: historical float unresolved, current snapshotอาจมีsurvivorship/dilution/split misclassification, unverifiedovernight/feedcontinuity, retrospectiveRESTcorrectionsและ groupedcloseที่ไม่ได้รับรองofficialauctioncloseอิสระ BoundedNBBOไม่ครอบคลุมentry/exitทั้งหมด ไม่มีorder/fill/queue/fees evidence จึงไม่อ้างexecutableprofitability งานนี้ไม่ขยาย80explorationcyclesและไม่ปรับtradingstrategy
