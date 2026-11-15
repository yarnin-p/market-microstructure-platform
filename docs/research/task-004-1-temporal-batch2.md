# TASK 004.1 — ผล frozen temporal batch 2

Run `m4-temporal-batch2-20261115-v1`; baseline `4f3fb66`

รัน 10 dates / 240 opportunities ตาม frozen positions 11–20 โดยไม่สุ่มใหม่; complete trade windows 240/240; verified first touches 30; zero-event 210; sessions {'AH': 8, 'PRE': 9, 'RTH': 13}.
ใช้ 298 HTTP attempts / 298 pages / 286,527,716 decoded bytes; errors 0; acquisition stop=None.

## ผลราย cycle

| Cycle | Complete | First touches | Sessions |
|---|---:|---:|---|
| 2026-06-12 | 24 | 6 | {'AH': 4, 'PRE': 1, 'RTH': 1} |
| 2026-09-08 | 24 | 1 | {'AH': 1} |
| 2026-06-16 | 24 | 2 | {'RTH': 2} |
| 2026-07-09 | 24 | 3 | {'PRE': 2, 'RTH': 1} |
| 2026-08-27 | 24 | 0 | {} |
| 2026-09-15 | 24 | 1 | {'PRE': 1} |
| 2026-06-15 | 24 | 6 | {'AH': 2, 'RTH': 4} |
| 2026-07-01 | 24 | 6 | {'PRE': 3, 'RTH': 3} |
| 2026-08-31 | 24 | 3 | {'PRE': 1, 'RTH': 2} |
| 2026-09-03 | 24 | 2 | {'AH': 1, 'PRE': 1} |

## Incidence และ comparison

Development 40/240, temporal batch1 31/240, batch2 30/240 แยกกลุ่ม ไม่ถือ observations เป็นอิสระ.
Batch2 design-weighted incidence 12.667%; cumulative temporal20 11.938%. คง original weights ทุกแถว แต่ derived analysis weights ใช้ actual month allocation 3/2/2/3 และ cumulative5/5/5/5; ห้ามใช้ initial-batch probabilities เพื่ออ้าง batch2 design inference.
OTHER_EXCHANGE_PRICE_ELIGIBLE: events 15 / selected 120; weighted incidence 12.645%.
PROXY_FLOAT_IN_RANGE: events 15 / selected 120; weighted incidence 12.699%.

## Confirmation บน initial risk set เดิม

| Policy | Status counts |
|---|---|
| C0_FROZEN | {'CONFIRMED': 30} |
| C1_COUNTED_ORIGINAL | {'CONFIRMED': 24, 'UNCONFIRMED': 6} |
| C1_COUNTED_ORIGINAL_D60 | {'CONFIRMED': 11, 'UNCONFIRMED': 19} |
| C1_OBSERVED_ACCEPTANCE | {'CONFIRMED': 22, 'UNCONFIRMED': 8} |
| C1_OBSERVED_ACCEPTANCE_D60 | {'CONFIRMED': 5, 'UNCONFIRMED': 25} |
| C1_SESSION_BOUND | {'CONFIRMED': 22, 'UNCONFIRMED': 8} |
| C1_SESSION_BOUND_D60 | {'CONFIRMED': 11, 'UNCONFIRMED': 19} |
| C2_FROZEN | {'UNCONFIRMED': 20, 'INSUFFICIENT_DATA': 7, 'CONFIRMED': 3} |

## Forward returns และ barriers

| Horizon | Observed / initial | Median return |
|---|---:|---:|
| 5m | 15/30 | -0.03238052702099151 |
| 15m | 14/30 | -0.0428765630166681 |
| 30m | 11/30 | -0.011609498680738786 |
| 60m | 13/30 | -0.013513513513513514 |
| session_end | 17/30 | -0.024450307827616535 |
| cycle_end | 18/30 | -0.0329294267998296 |

+3/-3: {'DOWNSIDE_FIRST': 25, 'UPSIDE_FIRST': 5}

+5/-3: {'DOWNSIDE_FIRST': 25, 'UPSIDE_FIRST': 5}

+10/-5: {'DOWNSIDE_FIRST': 20, 'UPSIDE_FIRST': 3, 'CENSORED': 2, 'NEITHER': 5}

Observed MFE distribution: {'n': 30, 'mean': 0.08559031226437448, 'min': 0.0, 'p25': 0.0, 'median': 0.013629723408702785, 'p75': 0.08047324148463936, 'max': 1.1608391608391608}
Observed MAE distribution: {'n': 30, 'mean': -0.1125507086703546, 'min': -0.32222222222222224, 'p25': -0.14479237531774322, 'median': -0.10257976108493308, 'p75': -0.046006024763199926, 'max': -0.017341040462427744}

## Validation และข้อจำกัด

Tests 228 passed; source hashes/pagination/event references ตรวจครบ; deterministic replay และ confirmation/outcomes recomputed. ผลเดิมและ SEC/M1 ไม่เปลี่ยน. Batch3 10 dates/240 opportunities ยังไม่รัน; holdout40ไม่วิเคราะห์.
รายงาน conditional returns เฉพาะ marks ที่มี evidence พร้อม missing denominators; excursion extremes เป็น observed path ไม่ใช่ guaranteed full path. Date/security clustering และ month-stratified resampling เป็น uncertainty sensitivity ไม่ใช่ calibrated confidence intervals หรือ significance. วันซ้ำและ security ซ้ำไม่ใช่ independent events; serial dependence ยังจำกัด inference.
Current float เป็น retrospective proxy ไม่ใช่ PIT; SEC แยกอิสระ. NBBO จำกัดเฉพาะ event windows ไม่ใช่ complete quote coverage. Overnight ยัง unverified. ไม่อ้าง executable fills, P&L หรือปรับ thresholds ตามผล.

Full local evidence: `data/runs/m4-temporal-batch2-20261115-v1`; compact results: `reports/m4-temporal-batch2-20261115-v1`; remaining inventory `remaining-frozen-batch.json`. Reproduce: temporal_batch prepare/acquire --offline/analyze/validate; scripts.finalize_temporal_batch --pytest-output PATH.
