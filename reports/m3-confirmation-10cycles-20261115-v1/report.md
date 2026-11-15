# TASK 003 — Price Confirmation Research Pilot

Existing 40 primary initial events; no downloads, no holdout, no optimized thresholds.

| Policy | Initial | Confirmed | Unconfirmed | Insufficient data | Median delay (s) | Median waiting price change |
|---|---:|---:|---:|---:|---:|---:|
| C0 | 40 | 40 | 0 | 0 | 0.0 | 0.000% |
| C1 | 40 | 33 | 7 | 0 | 55.578372385 | 0.034% |
| C2 | 40 | 6 | 24 | 10 | 36.201397041999996 | 3.699% |

## Full-risk-set outcomes

Every denominator includes unconfirmed and insufficient-data events. Observed post-signal return distributions condition on a signal and an uncensored mark; they are not unconditional success probabilities or strategy returns.

| Policy | Horizon | Observed / initial | Censored confirmed | No confirmation | Insufficient confirmation/mark | Median observed return |
|---|---|---:|---:|---:|---:|---:|
| C0 | 5m | 23/40 | 17 | 0 | 0 | -1.515% |
| C0 | 15m | 20/40 | 20 | 0 | 0 | -0.967% |
| C0 | 30m | 19/40 | 21 | 0 | 0 | -0.209% |
| C0 | 60m | 15/40 | 25 | 0 | 0 | -0.180% |
| C1 | 5m | 22/40 | 11 | 7 | 0 | -0.587% |
| C1 | 15m | 15/40 | 18 | 7 | 0 | -0.992% |
| C1 | 30m | 15/40 | 18 | 7 | 0 | 0.363% |
| C1 | 60m | 17/40 | 16 | 7 | 0 | -0.159% |
| C2 | 5m | 6/40 | 0 | 24 | 10 | -1.432% |
| C2 | 15m | 5/40 | 1 | 24 | 10 | -1.056% |
| C2 | 30m | 5/40 | 1 | 24 | 10 | -4.481% |
| C2 | 60m | 5/40 | 1 | 24 | 10 | -3.892% |

## Limitations

C1 includes the touch and requires three distinct eligible records spanning >=30 seconds, without resetting for intervening below-threshold prints; this is counted persistence, not continuous price support. C1 can signal later in the cycle; only the overnight blind interval resets its accumulated span. C2 needs two distinct fresh bid observations spanning >=10 seconds, resets on invalid/below bids or >5-second freshness gaps, and stops by touch+60 seconds or cycle end. Both retain the exact original +10% threshold.

C2 signal time is a quote receipt time; its market-observation entry basis is the latest eligible trade at/before that timestamp, no older than 60 seconds. That is an as-of mark, not a new trade or a fill. Ask-to-bid quote marks are a separate dataset; unavailable entry/exit quotes remain missing. No executable P&L is claimed.

All 40 initial events remain in every policy, including failures/missingness. Delayed signals do not enter retrospectively at C0 prices. Own-signal horizons differ in exit times; paired results are conditional descriptions, not causal strategy comparisons. Confirmation-by-common-landmark indicators and pre-signal C0 barrier outcomes expose waiting risk. Nonconfirmation is not assigned a zero return.

Odd-lot sensitivity keeps the same 40 original anchors and expands subsequent eligible observations only; three odd-only opportunities from TASK 002.2 are excluded from this fixed-risk-set experiment. AH/PRE/RTH grouping uses the initial session, while signal session is also retained. Original sampling weights N/n are preserved on every row; cohort/weighted summaries are descriptive and account for the two disjoint strata without treating policy copies as independent events. Current float is retrospective, not historical PIT. No independent overnight, halt/feed-loss or official-auction-close certification.

Reproduce offline: `python -m market_lab.confirmation_pilot run`, then `python -m market_lab.confirmation_pilot validate`. Original local cache is required to revalidate raw source evidence; compact JSON and the single research_bundle.zip can be read independently.
