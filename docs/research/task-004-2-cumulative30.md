# TASK 004.2 — Full 30-cycle cumulative temporal analysis

Run `m4-temporal-cumulative30-20261116-v1`; baseline `89b1a6a`

Selected 720; complete trade windows 720; verified first touches 93; development10แยก; holdout40ไม่วิเคราะห์.

Design-weighted first-touch incidence 12.257%; date clusters 30; security clusters 486.
Original source weightsไม่เปลี่ยน; batch3วิเคราะห์allocation1/4/4/1 และfull30ใช้6/14,9/22,9/21,6/13คูณsecurity n/Nในsidecarแยก ห้ามใช้batch1conditionalweightsหรือbatch2weightsแทนfull30.

## First-passage audit

Batch2 frozen +3/-3 ยังเป็น {'DOWNSIDE_FIRST': 25, 'UPSIDE_FIRST': 5} ไม่แก้ข้อมูล/threshold.

| Barrier | Outcomes |
|---|---|
| +3/-3 | {'DOWNSIDE_FIRST': 62, 'NEITHER': 5, 'UPSIDE_FIRST': 26} |
| +5/-3 | {'DOWNSIDE_FIRST': 71, 'NEITHER': 5, 'UPSIDE_FIRST': 17} |
| +10/-5 | {'DOWNSIDE_FIRST': 61, 'NEITHER': 19, 'UPSIDE_FIRST': 10, 'CENSORED': 3} |

Weighted bucket fractions, denominator/missingness และdate/security cluster sensitivitiesอยู่ใน statistical-results.json ไม่ตัดcensoredทิ้ง ไม่ใช้trade barriersเป็นexecutable fills.

## Confirmation บน initial risk set เดียวกัน

| Policy | Initial | Status counts |
|---|---:|---|
| C0_FROZEN | 93 | {'CONFIRMED': 93} |
| C1_COUNTED_ORIGINAL | 93 | {'CONFIRMED': 76, 'UNCONFIRMED': 17} |
| C1_COUNTED_ORIGINAL_D60 | 93 | {'UNCONFIRMED': 57, 'CONFIRMED': 36} |
| C1_OBSERVED_ACCEPTANCE | 93 | {'CONFIRMED': 69, 'UNCONFIRMED': 24} |
| C1_OBSERVED_ACCEPTANCE_D60 | 93 | {'UNCONFIRMED': 75, 'CONFIRMED': 18} |
| C1_SESSION_BOUND | 93 | {'CONFIRMED': 72, 'UNCONFIRMED': 21} |
| C1_SESSION_BOUND_D60 | 93 | {'UNCONFIRMED': 57, 'CONFIRMED': 36} |
| C2_FROZEN | 93 | {'INSUFFICIENT_DATA': 20, 'UNCONFIRMED': 64, 'CONFIRMED': 9} |

## Common/own clocks และ censoring

| Own horizon C0 | Observed / initial | Median observed return |
|---|---:|---:|
| 5m | 50/93 | -0.01599375766671047 |
| 15m | 45/93 | -0.021897810218978103 |
| 30m | 37/93 | -0.0387696251201538 |
| 60m | 36/93 | -0.0196639124657026 |
| session_end | 57/93 | -0.0375 |
| cycle_end | 62/93 | -0.04094614536024871 |

Observed MFE: {'n': 93, 'mean': 0.07599031576453018, 'min': 0.0, 'p25': 0.0, 'median': 0.018779342723004695, 'p75': 0.0776061776061776, 'max': 1.368064952638701}
Observed MAE: {'n': 93, 'mean': -0.1233875599691111, 'min': -0.41875, 'p25': -0.16666666666666666, 'median': -0.11498881431767338, 'p75': -0.045454545454545456, 'max': -0.008888888888888889}
Common touch+5/15/30/60-minute paired comparisonsเก็บunmatched/unconfirmed/insufficient/censoredครบ Own-signal horizonsแยกกัน ไม่ตีความsurvivor-onlyreturnmeanเป็นcausal improvement. Pre-confirmation paths, odd-lot, gap300/900s และSECsecondarycontextเก็บแยก ไม่มีhistoricalfloatapproval.

## Uncertainty และข้อจำกัด

Taylor incidence SE 0.01175400166205742; status EXPLORATORY_TWO_STAGE_DESIGN_LINEARIZATION_NOT_SIGNIFICANCE.
Resampling {'replicates': 500, 'seed': 202611150041, 'p025': 0.08717128125153131, 'median': 0.12176764130916116, 'p975': 0.1621907115162129, 'status': 'ILLUSTRATIVE_CROSSED_CLUSTER_RESAMPLING_RANGE_NOT_CALIBRATED_CI', 'limitations': "30 date clusters, allocation {'2026-06': 6, '2026-07': 9, '2026-08': 9, '2026-09': 6}; crossed-security reweighting, not calibrated two-stage confidence interval; temporal serial dependence unresolved."} เป็นillustrative range ไม่ใช่formalconfidenceinterval. Date/securityclustering, repeatedsecurities, serialdependence และcensoringจำกัดinference. ไม่อ้างstatisticallysignificantcontinuation, executableprofitabilityหรือเปลี่ยนpolicyให้ผลดีขึ้น.
Current floatเป็นretrospectiveproxy; historicalfloatยังunresolved, SECไม่forwardfill. Overnight/feedcontinuityและofficialauctioncloseยังไม่ได้รับรองอิสระ. BoundedNBBOเฉพาะfirst-touchquality/C2 ไม่ใช่entry-exitcoverageครบ.

## ขั้นถัดไปก่อน holdout

ควรทำmethodological checksแบบofflineก่อนformal holdout: ตรวจprice-quality/correctionและchronologicalbarriers, วิเคราะห์censoring/quote freshness และกำหนดprimary estimand, nonresponse rules, clustering/uncertaintyและdecision criteriaล่วงหน้า. หากต้องการเพิ่มexploration ต้องอนุมัติและfreezeแผนแยก ไม่ใช้holdoutมาปรับthreshold. หลักฐาน30cyclesนี้ยังไม่เพียงพอให้เริ่มformalholdoutอัตโนมัติ.

Source hashes/weights/source-run links และraw representative auditอยู่ในbundle ไม่มีrawtickbulkหรือcredentialsเข้าGit. Raw revalidationต้องมีlocalimmutablecache. No385quote-topup, noholdout.

## Analytical-weight publication audit

Source opportunity/event weights unchanged. Canonical stratum/cohort reports use separately derived analytical weights; inherited original-weight projections are explicitly archived for audit only. Full30 uses planned6/14,9/22,9/21,6/13; Batch3 uses1/14,4/22,4/21,1/13.

| Stratum | Selected | Verified first touches | Weighted incidence |
|---|---:|---:|---:|
| OTHER_EXCHANGE_PRICE_ELIGIBLE | 360 | 31 | 8.727% |
| PROXY_FLOAT_IN_RANGE | 360 | 62 | 17.248% |

Primary first-touch session counts: {'AH': 22, 'PRE': 27, 'RTH': 44}

Full test suite: 239 passed; raw/source/weight/replay validation receipts remain separate and unchanged.

## Pattern interpretation

Batch2 5 upside/25 downsideยังคงเดิม. Batch3 12 upside/17 downside/3 neither: downsideยังมากกว่าแต่ไม่ซ้ำความสุดโต่งของBatch2. Full30 26 upside/62 downside/5 neither. นี่เป็นdescriptive observed-trade first-passage pattern ภายใต้กฎเดิม ไม่ใช่statistically significant continuationหรือshort-sellingprofitability.

## Reproduction

Run temporal_final_batch prepare/acquire --offline/analyze/validate, full pytest, scripts.finalize_temporal_final --pytest-output PATH, then scripts.publish_temporal_final. Source caches are required for raw revalidation; compact results/bundles contain all processed outcomes without truncation.

คำแนะนำก่อน formal holdout: prioritize offline methodology/data-quality checks, censoring/quote coverage and a preregistered primary estimand/decision rule. C2 full30มีเพียง9 confirmed casesจึงยังไม่เหมาะสรุปผลการยืนยันทั่วไป หากต้องเพิ่ม precision ให้เสนอ exploration เพิ่มจากวันที่เหลือภายใต้แผนใหม่ที่ freezeก่อน ไม่เปลี่ยนthresholdเพื่อไล่ผลดี และไม่เปิดholdoutอัตโนมัติ.
