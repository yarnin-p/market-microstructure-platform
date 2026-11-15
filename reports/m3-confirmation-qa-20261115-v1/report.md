# TASK 003.1 — Confirmation QA

40 initial events per policy; no network requests. Frozen C0/C1/C2 unchanged.

| Policy | Confirmed | Unconfirmed | Insufficient | Median delay seconds | Median waiting price change |
|---|---:|---:|---:|---:|---:|
| C0_FROZEN | 40 | 0 | 0 | 0.0 | 0.0000% |
| C1_COUNTED_ORIGINAL | 33 | 7 | 0 | 55.578372385 | 0.0342% |
| C1_COUNTED_ORIGINAL_D60 | 17 | 23 | 0 | 34.923710371 | 0.0000% |
| C1_OBSERVED_ACCEPTANCE | 31 | 9 | 0 | 97.421303898 | 0.3775% |
| C1_OBSERVED_ACCEPTANCE_D60 | 10 | 30 | 0 | 33.391425316500005 | 0.2642% |
| C1_SESSION_BOUND | 31 | 9 | 0 | 51.881399876 | 0.0000% |
| C1_SESSION_BOUND_D60 | 17 | 23 | 0 | 34.923710371 | 0.0000% |
| C2_FROZEN | 6 | 24 | 10 | 36.201397041999996 | 3.6994% |

Common exits are anchored to original touch+5/15/30/60 minutes. All unconfirmed, not-yet-confirmed, insufficient and censored cases remain in initial denominators. Matched-return distributions are conditional, never unconditional policy P&L. No observed below-threshold print does not independently certify continuous support.

Quote top-up is a plan only; it was not executed or authorized by this run. Full event, own-clock, common-clock, pre-confirmation path and source evidence is included without truncation.
