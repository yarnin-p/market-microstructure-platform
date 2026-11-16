# TASK005 — Pre-Holdout Research Audit

Run `m5-preholdout-audit-20261116-v2`; baseline `1c02e67`

Readiness: **CONDITIONAL**. Offline audit ครบ93 events /720 opportunities /30 exploration dates; zero-event627. ไม่เปิด holdout, ไม่รวม Development10, market-data requests0.
Independent raw reconstruction พบ discrepancy 0 events. ตรวจ SIP/ties, condition rules, corrections, trigger/P0, barrier timestamps และ forward censoring ครบทุกevent ไม่จำกัด representative examples.

## First passage และ price quality

| Frozen barrier | Full30 independent outcomes |
|---|---|
| +10/-5 | {'CENSORED': 3, 'DOWNSIDE_FIRST': 61, 'NEITHER': 19, 'UPSIDE_FIRST': 10} |
| +3/-3 | {'DOWNSIDE_FIRST': 62, 'NEITHER': 5, 'UPSIDE_FIRST': 26} |
| +5/-3 | {'DOWNSIDE_FIRST': 71, 'NEITHER': 5, 'UPSIDE_FIRST': 17} |

Trigger shares: {'n': 93, 'mean': 977.3655913978495, 'min': 100.0, 'p25': 100.0, 'median': 202.0, 'p75': 533.0, 'max': 29238.0}; touch quote statuses {'FLAGGED': 34, 'MISSING': 9, 'OK': 50}; trade/NBBO relations {'ABOVE_ASK': 7, 'UNAVAILABLE': 43, 'WITHIN_NBBO': 43}. Odd-lot sensitivity เปลี่ยน first-touch record 58/93 events. Same-SIP multiple prices 1; restored original records 0.
Trade-above-ask flags เก็บไว้ตรวจ ไม่ตัดทิ้งเงียบ ๆ. Barrier support sizes/conditions/corrections/source references อยู่ใน event-audits.json และprice-quality.json. ปริมาณหุ้นที่printไม่ใช่ executable liquidity/queue guarantee.

## Censoring และ missingness

| Horizon | Observed | Censored | Root causes (overlap allowed) |
|---|---:|---:|---|
| 15m | 45 | 48 | {'OBSERVED_SESSION_ENDED': 2, 'PRICE_MARK_FRESHNESS_FAILURE': 48} |
| 30m | 37 | 56 | {'OBSERVED_SESSION_ENDED': 3, 'PRICE_MARK_FRESHNESS_FAILURE': 56} |
| 5m | 50 | 43 | {'OBSERVED_SESSION_ENDED': 1, 'PRICE_MARK_FRESHNESS_FAILURE': 42} |
| 60m | 36 | 57 | {'OBSERVED_SESSION_ENDED': 5, 'PRICE_MARK_FRESHNESS_FAILURE': 57, 'UNOBSERVED_INTERVAL': 1} |
| cycle_end | 62 | 31 | {'PRICE_MARK_FRESHNESS_FAILURE': 12, 'UNOBSERVED_INTERVAL': 22} |
| session_end | 57 | 36 | {'PRICE_MARK_FRESHNESS_FAILURE': 36} |

Complete pagination แยกจาก no recent eligible print: ช่องว่างอาจสอดคล้องกับilliquidity/rejected prints แต่ไม่พิสูจน์feed lossหรือhalt. Quote freshnessไม่ใช่สาเหตุcensoringของtrade-onlyreturn. ไม่แทนcensoredreturnsด้วย0/lastprice/win/loss.
NEITHERที่cycle endเป็น known category แต่เป็น administrative right-censoring สำหรับtime-to-event; upside/downsideเป็นcompeting outcomes. Stale endpoint/overnight/unknown evidenceเก็บcensoring timeและสาเหตุแยก ไม่สมมติnoninformative censoring. ผลgap300/900อยู่ในdata_quality.json.

## Estimator และ calibration

Design-weighted downside-minus-upside contrast = 0.366018; Taylor SE = 0.098720. เป็นexploratory-origin finding ไม่ใช่confirmatory test. Identification bounds = {'lower': 0.3660175855170903, 'upper': 0.3660175855170903}.
Varianceใช้domain residualของทั้ง720opportunities รวม627zero-event rows และfinite population correctionsทั้งdate/security stages. Reconciliationกับincidence estimatorเดิมผ่าน. Repeated securities/serialoutcomesเป็นfixedpopulationstructureในการsampling inference; crossed-date/security และleave-one-security/date sensitivitiesรายงานแยก ไม่อ้างfuture-processindependence.

| Synthetic scenario | Repetitions | Candidate interval coverage | MC SE |
|---|---:|---:|---:|
| regular | 1000 | 94.900% | 0.0070 |
| rare_domain | 1000 | 91.500% | 0.0088 |
| informative_missing | 1000 | 96.600% | 0.0057 |
| holdout_census_dates | 1000 | 95.200% | 0.0068 |

ทั้งหมดเป็นsynthetic known-population calibration ไม่ใช่market observations. Candidate t/Taylor intervals และillustrativebootstrapไม่ใช่formal95%marketCI. Scenarioที่ไม่ผ่านและMCuncertaintyอยู่ในcalibration-readiness.json; informative missingnessไม่recoverlatentoutcomes.
Estimator reference: [Aubry (2024), stratified two-stage SRSWOR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11404174/). สูตรratio linearizationใช้เพื่อfixedfinitepopulation; calibrationในรายงานนี้เป็นsimulationที่รันเอง.

## Confirmation fairness และ protocol

Common initial risk set93ครบทุกpolicy; common-clock marksตรวจ 5952 รายการ; errors 0. C2confirmed9/93ยังunderpowered. Unconfirmed/insufficient/not-yet-confirmed/censoredเก็บครบ ไม่อ้างcausal improvement.
Freeze primary +3/-3 contrast โดยเปิดเผยว่าเลือกหลังเห็นexploration; ไม่สมมติ50/50เป็นmarket-neutral benchmark. Secondary continuation/C1/C2/float/otherbarriersคงเดิม. Holdoutplanกำหนดdatecensus40และSRS12/stratum/date, snapshotเดิม, estimator/unknownbounds/gatesและSUPPORTED/UNSUPPORTED/INCONCLUSIVEล่วงหน้า. ยังไม่สร้างsampleหรือเรียกholdoutticks.

## ข้อจำกัดและเงื่อนไขที่ยังต้องผ่าน

- New explicit user authorization and frozen acquisition budget/sample are required before any holdout tick access.
- Formal statistical clearance BLOCKED: rare_domain coverage 0.915 is below frozen global floor 0.93. All four scenarios are required. A pre-access statistical amendment and independent calibration validation are necessary; count gates or review alone cannot waive this failure.
- Holdout must pass complete discovery-coverage, domain-size, unknown-fraction and source-integrity gates; failures are INCONCLUSIVE, not replacement samples.
- Current-float classification, unverified overnight intervals and provider-close basis limit the claim to the frozen retrospective-proxy observed-print population.
- Bounded NBBO and only nine C2 confirmations do not support executable or causal confirmation claims.
- Simulation diagnostics below floor: rare_domain

Tests **255 passed**, 84 existing warnings. Protected artifacts 13818 files unchanged. Raw reads 1,520,323,131 bytes (รวมตรวจซ้ำ), elapsed 37.6s ภายในงบ. Raw marketdata0bytesใหม่; outputข้อมูลauditแยกจากrunsเดิม.
Local event/censoring Parquet: `data/runs/m5-preholdout-audit-20261116-v2`; compact package `reports/m5-preholdout-audit-20261116-v2`. Raw source paths+SHA256อยู่ครบในevent-audits.json.
Reproduction: new versioned run ID in config, `.venv/bin/python -m market_lab.preholdout_audit --config PATH`, full pytest, `.venv/bin/python -m scripts.finalize_preholdout_audit_v2 --pytest-output PATH`. Default run refuses overwrite; holdout authorization remains separate.

## Additional independent rerun / readiness freeze v2

Technical audit PASS; overall readiness CONDITIONAL; formal statistical clearance **BLOCKED**; holdout NOT AUTHORIZED.
Independent rerun agrees exactly with preserved v1 for 7 evidence files. Strict manifest verification requires every listed file to exist, not just hash-checking existing files.
271 censored primary forward marks across six horizons (not 271 unique events): {'NO_RETURNED_MESSAGES_IN_RECENT_WINDOW': 155, 'RECENT_ELIGIBLE_PRINT': 19, 'RECENT_RETURNED_MESSAGES_ALL_REJECTED': 86, 'TARGET_AFTER_OBSERVED_CYCLE': 11}. Eligible recent prints can coexist with overnight/gap censoring; they do not repair the missing interval.
PRICE_MARK_FRESHNESS_FAILURE witnesses: {'NO_RETURNED_MESSAGES_IN_RECENT_WINDOW': 155, 'RECENT_RETURNED_MESSAGES_ALL_REJECTED': 86, 'TARGET_AFTER_OBSERVED_CYCLE': 10}. Return values remain null, never zero or assumed last-price returns.
All returned-message condition distributions by AH/PRE/RTH and rejected reason are in root-cause-summary.json; per-mark raw witnesses and source hashes are in root-cause-witnesses.json. Scope is 93 event windows, not all 720 windows.
Primary technical conclusion is about observed eligible prints and provider-complete pagination. No tick-level source independently establishes continuous exchange coverage, official closing auction certification or verified historical float.
Total raw-cache bytes read including supplemental witnesses: 1,951,463,480, below 8GiB. No new market data acquired.
Rare-domain simulation coverage 91.5% is below the frozen 93% floor. The four-scenario gate cannot be narrowed after viewing outcomes. Other simulated observable-target coverage is 94.9%,96.6%,95.2%; informative-missingness latent-target coverage is only38.7%, demonstrating that an observable classification contrast does not recover latent full-path probabilities.
Primary point estimate 36.60 percentage points is exploratory and design-weighted across both strata; no formal exploration CI or significance claim. Equality of observed downside/upside probabilities is not a market-neutral null.
The holdout sampler is specified but not implemented/executed in this task. Separate authorization, a frozen bounded acquisition plan and a pre-access validated statistical amendment remain outstanding. No actual holdout outcomes or membership sample have been opened.
Reproduce witnesses: `.venv/bin/python -m market_lab.audit_supplement --config configs/task-005-audit-v2.json`; publisher: `.venv/bin/python -m scripts.finalize_preholdout_audit_v2 --pytest-output PATH`. For reruns choose a new run ID and matching publication config; all stages refuse overwrites.
The v1 draft source and unfinalized v1 local audit are retained. This v2 is the completed publication. Audit bundle uses its own audit-evidence-v1 contract; it is not the narrower original research-bundle-v1 schema.
