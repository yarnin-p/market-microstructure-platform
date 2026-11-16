# TASK 004.2 — Batch 3

Run `m4-temporal-batch3-20261116-v1`; baseline `89b1a6a`

Selected 240; complete trade windows 240; verified first touches 32; development10แยก; holdout40ไม่วิเคราะห์.

Design-weighted first-touch incidence 13.736%; date clusters 10; security clusters 208.
Original source weightsไม่เปลี่ยน; batch3วิเคราะห์allocation1/4/4/1 และfull30ใช้6/14,9/22,9/21,6/13คูณsecurity n/Nในsidecarแยก ห้ามใช้batch1conditionalweightsหรือbatch2weightsแทนfull30.

## First-passage audit

Batch2 frozen +3/-3 ยังเป็น {'DOWNSIDE_FIRST': 25, 'UPSIDE_FIRST': 5} ไม่แก้ข้อมูล/threshold.

| Barrier | Outcomes |
|---|---|
| +3/-3 | {'UPSIDE_FIRST': 12, 'NEITHER': 3, 'DOWNSIDE_FIRST': 17} |
| +5/-3 | {'UPSIDE_FIRST': 7, 'NEITHER': 3, 'DOWNSIDE_FIRST': 22} |
| +10/-5 | {'UPSIDE_FIRST': 3, 'NEITHER': 9, 'DOWNSIDE_FIRST': 19, 'CENSORED': 1} |

Weighted bucket fractions, denominator/missingness และdate/security cluster sensitivitiesอยู่ใน statistical-results.json ไม่ตัดcensoredทิ้ง ไม่ใช้trade barriersเป็นexecutable fills.

## Confirmation บน initial risk set เดียวกัน

| Policy | Initial | Status counts |
|---|---:|---|
| C0_FROZEN | 32 | {'CONFIRMED': 32} |
| C1_COUNTED_ORIGINAL | 32 | {'CONFIRMED': 31, 'UNCONFIRMED': 1} |
| C1_COUNTED_ORIGINAL_D60 | 32 | {'CONFIRMED': 17, 'UNCONFIRMED': 15} |
| C1_OBSERVED_ACCEPTANCE | 32 | {'CONFIRMED': 27, 'UNCONFIRMED': 5} |
| C1_OBSERVED_ACCEPTANCE_D60 | 32 | {'UNCONFIRMED': 23, 'CONFIRMED': 9} |
| C1_SESSION_BOUND | 32 | {'CONFIRMED': 30, 'UNCONFIRMED': 2} |
| C1_SESSION_BOUND_D60 | 32 | {'CONFIRMED': 17, 'UNCONFIRMED': 15} |
| C2_FROZEN | 32 | {'UNCONFIRMED': 21, 'INSUFFICIENT_DATA': 7, 'CONFIRMED': 4} |

## Common/own clocks และ censoring

| Own horizon C0 | Observed / initial | Median observed return |
|---|---:|---:|
| 5m | 21/32 | -0.0015840253444055106 |
| 15m | 17/32 | -0.00638410214563433 |
| 30m | 14/32 | -0.023930267105531443 |
| 60m | 15/32 | -0.01358421734747756 |
| session_end | 20/32 | -0.040909277958773776 |
| cycle_end | 23/32 | -0.04153354632587859 |

Observed MFE: {'n': 32, 'mean': 0.06144653703098769, 'min': 0.0, 'p25': 0.012360033648004486, 'median': 0.033601853274906196, 'p75': 0.08487116544003097, 'max': 0.29375}
Observed MAE: {'n': 32, 'mean': -0.13405052579323123, 'min': -0.41875, 'p25': -0.18434289127837514, 'median': -0.12454379562043796, 'p75': -0.04237453702394753, 'max': -0.008888888888888889}
Common touch+5/15/30/60-minute paired comparisonsเก็บunmatched/unconfirmed/insufficient/censoredครบ Own-signal horizonsแยกกัน ไม่ตีความsurvivor-onlyreturnmeanเป็นcausal improvement. Pre-confirmation paths, odd-lot, gap300/900s และSECsecondarycontextเก็บแยก ไม่มีhistoricalfloatapproval.

## Uncertainty และข้อจำกัด

Taylor incidence SE None; status INSUFFICIENT_DATE_STRATUM_RESPONSE.
Resampling {'replicates': 500, 'seed': 202611150041, 'p025': 0.06670510963174996, 'median': 0.1333124222052297, 'p975': 0.20265740022310844, 'status': 'ILLUSTRATIVE_CROSSED_CLUSTER_RESAMPLING_RANGE_NOT_CALIBRATED_CI', 'limitations': "10 date clusters, allocation {'2026-06': 1, '2026-07': 4, '2026-08': 4, '2026-09': 1}; crossed-security reweighting, not calibrated two-stage confidence interval; temporal serial dependence unresolved."} เป็นillustrative range ไม่ใช่formalconfidenceinterval. Date/securityclustering, repeatedsecurities, serialdependence และcensoringจำกัดinference. ไม่อ้างstatisticallysignificantcontinuation, executableprofitabilityหรือเปลี่ยนpolicyให้ผลดีขึ้น.
Current floatเป็นretrospectiveproxy; historicalfloatยังunresolved, SECไม่forwardfill. Overnight/feedcontinuityและofficialauctioncloseยังไม่ได้รับรองอิสระ. BoundedNBBOเฉพาะfirst-touchquality/C2 ไม่ใช่entry-exitcoverageครบ.

## ขั้นถัดไปก่อน holdout

ควรทำmethodological checksแบบofflineก่อนformal holdout: ตรวจprice-quality/correctionและchronologicalbarriers, วิเคราะห์censoring/quote freshness และกำหนดprimary estimand, nonresponse rules, clustering/uncertaintyและdecision criteriaล่วงหน้า. หากต้องการเพิ่มexploration ต้องอนุมัติและfreezeแผนแยก ไม่ใช้holdoutมาปรับthreshold. หลักฐาน30cyclesนี้ยังไม่เพียงพอให้เริ่มformalholdoutอัตโนมัติ.

Source hashes/weights/source-run links และraw representative auditอยู่ในbundle ไม่มีrawtickbulkหรือcredentialsเข้าGit. Raw revalidationต้องมีlocalimmutablecache. No385quote-topup, noholdout.

## Analytical-weight publication audit

Source opportunity/event weights unchanged. Canonical stratum/cohort reports use separately derived analytical weights; inherited original-weight projections are explicitly archived for audit only. Full30 uses planned6/14,9/22,9/21,6/13; Batch3 uses1/14,4/22,4/21,1/13.

| Stratum | Selected | Verified first touches | Weighted incidence |
|---|---:|---:|---:|
| OTHER_EXCHANGE_PRICE_ELIGIBLE | 120 | 9 | 8.942% |
| PROXY_FLOAT_IN_RANGE | 120 | 23 | 20.520% |

Primary first-touch session counts: {'AH': 7, 'PRE': 8, 'RTH': 17}

Full test suite: 239 passed; raw/source/weight/replay validation receipts remain separate and unchanged.

## Pattern interpretation

Batch2 5 upside/25 downsideยังคงเดิม. Batch3 12 upside/17 downside/3 neither: downsideยังมากกว่าแต่ไม่ซ้ำความสุดโต่งของBatch2. Full30 26 upside/62 downside/5 neither. นี่เป็นdescriptive observed-trade first-passage pattern ภายใต้กฎเดิม ไม่ใช่statistically significant continuationหรือshort-sellingprofitability.

## Reproduction

Run temporal_final_batch prepare/acquire --offline/analyze/validate, full pytest, scripts.finalize_temporal_final --pytest-output PATH, then scripts.publish_temporal_final. Source caches are required for raw revalidation; compact results/bundles contain all processed outcomes without truncation.

คำแนะนำก่อน formal holdout: prioritize offline methodology/data-quality checks, censoring/quote coverage and a preregistered primary estimand/decision rule. C2 full30มีเพียง9 confirmed casesจึงยังไม่เหมาะสรุปผลการยืนยันทั่วไป หากต้องเพิ่ม precision ให้เสนอ exploration เพิ่มจากวันที่เหลือภายใต้แผนใหม่ที่ freezeก่อน ไม่เปลี่ยนthresholdเพื่อไล่ผลดี และไม่เปิดholdoutอัตโนมัติ.
