# TASK 002 — bounded historical replay

Approved scope: preserve M1 `m1-universe-120-20261115-v2`; new immutable run, three exploration cycles 2026-05-27/28/29, 10 seeded systematic plus six disjoint diagnostic securities. No holdout analysis, confirmation models, large SEC ingestion or full-universe tick download.

## Frozen selection and evidence

Seed 20261115; select without replacement from the first-cycle M1 records passing exchange, CS, price, identity, currency, corporate-action and no-observed-change gates. Recheck those historical gates each later cycle. Diagnostic selection ranks the first day's high/P0 from the second cycle's stored prior-day price records. This outcome-enriched diagnostic sample is separate from systematic results. Freeze selection.json before ticks or continuation calculations. Hashing M1's full artifacts is integrity verification only; no holdout observations are analyzed.

Current Massive `/stocks/vX/float` `free_float` is an explicitly retrospective proxy; match current resolved identity to historical identity before attaching it. Missing evidence stays unresolved. SEC reviewed evidence is independent, never a substitute or forward-filled eligibility. M1 exchange and price provenance are retained. Intra-cycle listing changes and corporate-action uncertainty remain subject to M1 quality gates; no present-day listing eligibility is substituted.

## Ingestion and clocks

Use `/v3/trades/{ticker}` and `/v3/quotes/{ticker}` with ascending SIP timestamp, nanosecond exclusive lower/inclusive upper bounds and complete pagination. Preserve provider JSON pages, page hashes, source row offsets, participant time, corrections, conditions and exchange. Normalized data use ZSTD Parquet, exact full-record deduplication with an audit of duplicate source references. Complete pagination means the provider returned no next page, not independent proof of all exchange messages. Invalid records remain in raw and normalized evidence.

Budget: 300 requests, 280 successful pages, 1 GiB decoded response bytes, 32 MiB per response, 12 pages per window. Stop individual windows with explicit incomplete status; no automatic unbounded retries. Reuse verified pages on resume. Single writer per immutable run. Trades cover each selected eligible cycle; quotes cover only ±60 seconds around detected events, up to 48 windows. Raw pages and all event-level data stay outside Git.

## Replay policy

SIP timestamp, sequence, exchange, trade ID and raw-record hash define deterministic ordering. Threshold is exact Decimal `P0*1.10`. Freeze P0 from M1. First eligible touch is one event per security-cycle, with separate cohort memberships. Later re-crosses and rejected raw candidates are retained.

Conditions come from Massive reference definitions: require consolidated high/low and open/close updates, except Form T during AH/PRE; reject explicit out-of-sequence/reference-price conditions, invalid prices/sizes, participant timestamps outside the cycle or >10 seconds behind SIP. Unknown conditions make earlier evidence unresolved. This conservative 10-second lag rule is a technical pilot choice, not a tuned strategy.

REST corrections require care: original code 1 contains corrected values; matching later code 12 carries original values and can reconstruct the observed original fields. Missing/ambiguous matches are unresolved. Original codes 7/8 remain observable before later 11/10 notices; future cancellation flags must not determine prior eligibility. Later invalidation censors outcomes. Repeated correction chains are not certified. See provider [conditions](https://massive.com/glossary/conditions-indicators) and [cancelled trades](https://massive.com/knowledge-base/article/how-much-does-massives-feeds-handle-canceled-trades).

20:00–04:00 is unobserved; PRE/RTH first touches are `FIRST_TOUCH_UNVERIFIED` for the entire cycle even if first touch across downloaded observed sessions is verified. AH can establish a verified first touch before that gap. No complete historical halt feed is claimed; known halt intervals can be passed to replay, bounded quote indicators are retained, and long intertrade gaps are flagged rather than called halts.

## Outcomes and reporting

Forward wall-clock horizons 5/15/30/60 minutes, session end and cycle end use the latest eligible mark no later than target, age <=60 seconds. Missing pages, overnight intervals, >300-second intertrade gaps and invalidated touch censor the return. Preserve observed marks even when censored. MFE/MAE use observed prices through cycle end and explicitly flag incomplete windows. Barriers +3/-3, +5/-3, +10/-5 are relative to actual touch; simultaneous opposite hits are ambiguous. These are gross price observations, never executable entry assumptions.

Produce full event/outcome/opportunity/candidate Parquet, memberships, coverage/hash reports, compact JSON/Markdown and a research bundle. Descriptive statistics cover the full selected pilot, not the full 120-cycle universe. Diagnostic and systematic samples stay separate; no significance or profitability claim. Confidence intervals are explicitly not estimated for the tiny clustered pilot. Validate deterministic replay against raw source rows and unchanged M1 hashes.

## CLI

```
python -m market_lab.m2_pilot select --run-id NEW_RUN
python -m market_lab.m2_pilot run --run-id NEW_RUN --env-file /path/to/local/.env
python -m market_lab.m2_pilot validate --run-id NEW_RUN
python -m market_lab.m2_pilot query --run-id NEW_RUN --ticker SYMBOL
```

Credentials are read locally and never included in reports. Source code hashes and policies are pinned in execution.json; changing either requires a new run ID.
