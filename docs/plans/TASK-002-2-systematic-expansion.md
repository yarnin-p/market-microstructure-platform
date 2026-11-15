# TASK 002.2 — frozen 10-cycle systematic expansion

Baseline: `21ed2f8`, branch `feat/task-002-1-replay-methodology-qa`.

Use the first ten chronological EXPLORATION cycles in M1. No holdout values are parsed or analyzed; SHA-256 preservation checks read existing artifact bytes only. Preserve every existing run and report. No diagnostic additions, model optimization, confirmation models or alternative paid source.

## Selection before outcomes

Each day's own M1 population must pass the existing historical non-float gates (listing exchange, CS, previous close >0 and <=3, identity, currency, corporate-action and exchange-change quality). Duplicate/ambiguous security identities are excluded explicitly. No restriction to day-one securities. The full daily frame, source hashes and exclusion/frame counts are retained.

Retrieve current Massive ticker reference (active stocks) and latest `/stocks/vX/float` before sampling. Resolve historical security FIGI to exactly one current identity, including ticker renames. These current values never replace historical listing/type gates. Inactive or unresolvable identities remain unresolved, not excluded from the historical control. Current free float is a retrospective exploratory proxy, never verified PIT or outstanding shares. The approved range is inclusive 100K–15M.

Two disjoint selection strata per cycle: PROXY_FLOAT_IN_RANGE and OTHER_EXCHANGE_PRICE_ELIGIBLE (out-of-range and unresolved proxy). Sample 12 per stratum without replacement, or census if smaller; do not silently top up or reallocate. Stable sort by security identity; independent per-cycle/per-stratum seed = first 16 hex digits of SHA-256 canonical JSON [202611150022, cycle, stratum]. Store N, n, exact integer counts, probability n/N and weight N/n. Both strata belong to the overlapping EXCHANGE_PRICE_ONLY analytical cohort; proxy members additionally belong to MASSIVE_CURRENT_FLOAT_PROXY. SEC context is separate and is not forward-filled.

Freeze selection.json and its SHA-256 before any tick outcomes. Process in deterministic round-robin cycle order, alternating proxy/complementary stratum for each within-stratum draw index. Budget exhaustion is explicit nonresponse, not a negative event. This balances early resource use without selecting on price moves. No population inference is attempted; unweighted descriptive results cover the entire selected sample, and design weights remain available for later design-aware analysis. Repeated securities, overlapping cohorts and policy analyses are not independent samples.

## Frozen resource envelope

900 HTTP attempts; 850 successful pages; 2 GiB decoded response bytes; 32 MiB per response; 64 pages/window; 6 GiB local run storage with conservative pre-request headroom. Metadata pages count toward the same request/page/byte budget. Up to 40 pages per reference endpoint; up to 160 unique ±60-second event quote windows. Same-timestamp events across policies reuse the quote window. No new subscription. Credentials remain local.

Complete pagination is required for observed-session proof. Exhausted/error windows retain partial records and unresolved completeness. Preserve raw JSON source pages plus per-page normalized ZSTD Parquet containing lossless raw JSON and source references. Exact-record duplicates are removed from replay, never from source evidence. UTC ns and deterministic SIP tie-breaking are inherited. Checkpoint and page hashes allow bounded offline resume; incomplete checkpoints are sealed for this run, and further data requires a new run/policy.

## Approved replay

Reuse TASK 002.1 ReplayState and outcome_sensitivity. Primary: OBSERVED_SESSIONS_FIRST / HIGH_LOW_ONLY / NO_MECHANICAL_GAP. Compare odd-lot observation sensitivity separately; retain 300- and 900-second censoring sensitivities. Explicit delayed/reference-price/correction vetoes remain unchanged. Freshness, unknown evidence, missing pages, overnight and later-invalidated touch checks remain active. STRICT_FULL_CYCLE_FIRST stays unavailable without independent overnight verification.

Returns at 5/15/30/60 minutes and session/cycle end, observed MFE/MAE, first passage +3/-3, +5/-3 and +10/-5 are gross observed-trade outcomes. Preserve NBBO freshness/validity and trade-above-ask/below-bid anomalies without deleting trade signals. Quotes never enter the trigger decision. No executable-fill or profitability claim.

## Results and verification

Full event, outcome, population, opportunity and tick partitions remain local. Compact JSON/Markdown, queryable event Parquet and a research bundle expose cycle, session risk-set, cohort, security and sample denominators, censored counts and sensitivity differences. Session risk sets exclude an earlier-session first touch within the same policy; session counts must not be summed as independent opportunities. No iid confidence intervals or significance claims from repeated clustered pilot observations.

Validate terminal cursors and page chains, exact timestamp bounds, source hashes, every event's raw record and quote context, deterministic policy replay/outcomes, frozen selection and unchanged previous runs. Unit tests cover daily population refresh, probabilities/weights, outcome-independent sampling, aliases/missing float, budgets and retained quote anomalies, in addition to inherited replay tests.

```
python -m market_lab.systematic_pilot prepare --env-file /path/to/local/.env
python -m market_lab.systematic_pilot run --env-file /path/to/local/.env
python -m market_lab.systematic_pilot run --offline
python -m market_lab.systematic_pilot validate --offline
python scripts/query_systematic_pilot.py --kind events --cycle-id 2026-06-01
```
