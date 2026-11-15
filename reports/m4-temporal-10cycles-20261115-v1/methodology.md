# TASK 004 — Frozen temporal expansion design

Baseline `e160627`. New immutable run `m4-temporal-10cycles-20261115-v1`. The original ten consecutive May–June development cycles remain separate. No holdout outcome rows are read.

## Selection before new ticks

Remaining exploration dates: June 14, July 22, August 21, September 13 (70 total). Hamilton proportional allocation gives a 30-date plan of 6/9/9/6. Independently seeded SRS within each month selects the dates. A second seeded permutation selects an initial ten-date batch of 2/3/3/2; round-robin month order makes the first ten temporally distributed, not the earliest ten chronological dates. The remaining twenty dates are reserved and never sent to a tick endpoint in this task.

Master seed `202611150004`; per-month plan and batch seeds derive from canonical SHA-256 `[master_seed, DATE_PLAN or DATE_BATCH, month]`. Per-cycle/security-stratum seeds reuse the existing canonical `[master_seed, cycle_id, stratum]` procedure. Freeze all 30 dates and 720 selected opportunities, full historical eligibility frame, source fingerprints, seeds, integer N/n counts, probabilities and weights before any new tick outcome is accessed. Selection file hashes are immutable; no replacement for an illiquid, failed or missing response.

Historical eligibility uses unchanged M1 non-float quality gates: primary XNAS/XASE/XNYS, CS, close >0 and <=3, identity/currency/action/change checks. Reuse the already cached development current-reference/free-float snapshot, matched by historical FIGI to one current identity. Current identity is only proxy mapping, never a historical listing gate. Inclusive 100K–15M current free float defines the proxy stratum; out-of-range and unresolved mappings remain in its complementary historical-eligible stratum. This retrospective snapshot is neither historical PIT nor refreshed after inspecting outcomes. SEC context is independent, never forward-filled or used to approve float eligibility.

Select 12 per stratum without replacement for every planned cycle (24 each). Store within-cycle probability n/N and weight N/n. Store date-plan probability n30/Nmonth, conditional initial-batch probability n10/n30 and marginal batch-date probability n10/Nmonth. Joint inclusion = date × security probability; joint design weight is its inverse. Reserve-date rows carry the declared probability of entering the initial ten-date batch, but are not analyzed. Freeze `selection.json`, population Parquet and hashes before network acquisition. Preparation uses no new API calls.

## Explicit execution envelope

Execute only the ten frozen batch dates / 240 opportunities. One shared ledger caps 1,200 HTTP attempts, 1,150 successful pages, 3 GiB decoded bytes, 32 MiB/response and 10 GiB local storage with conservative headroom. Trades: 50,000/page, at most 96 pages/window. NBBO: 10,000/page, at most 160 unique +/-60-second first-touch windows shared across primary/odd policies. Request spacing >=100ms, connect/read timeouts 5/30s. Acquisition wall clock is at most 1,800s from the first client creation, persisted across resume; offline analysis has a separate 5,400s hard alarm and checkpoint boundaries. No new subscription or credential files in Git.

Stop on a hard resource cap or authorization denial; keep complete/partial/empty/unattempted statuses. Cached-only salvage may seal already obtained evidence and missing rows after a stop, issuing zero new requests. No partial cursor is silently completed. Preserve raw page hashes, original window bounds, terminal cursors and normalized page provenance. No network retry beyond the ledger or automatic extra batches. The original 20 reserved dates and 40-cycle holdout remain untouched.

## Frozen research

Reuse OBSERVED_SESSIONS_FIRST / HIGH_LOW_ONLY / NO_MECHANICAL_GAP. Original explicit trade-condition vetoes, corrections, 60-second mark freshness, overnight/unknown evidence censoring and 300/900-second sensitivities are unchanged. Odd-lot discovery is separate. Confirmation risk set consists of verified primary observed-session touches; partial/unverified candidates remain in first-touch evidence with explicit exclusions, not negative events.

Apply frozen TASK 003.1 C0, C2, counted C1, observed-acceptance C1 and initial-session-bound C1, with each C1's independent 60-second deadline sensitivity. No threshold change. Within each initial-event risk set use the same original anchor for primary/odd follow-up analyses. Compute own-signal and common touch+5/15/30/60-minute marks, observed MFE/MAE, first passage and pre-confirmation path evidence. Preserve all unmatched, unconfirmed, insufficient and censored cases. Conditional paired means are not unconditional causal improvements. NBBO windows support quality/C2 observation, not exhaustive executable entry/exit coverage. No P&L/fill claim.

## Statistical preparation

Report response/quality denominators before estimates. Give descriptive design-weighted incidence using joint date/security weights, per-stratum and session risk sets, and conditional confirmation/mark summaries. Store both weights and date/security clustering keys on every event.

With full response, implement a two-stage SRSWOR Taylor-linearized ratio SE: within-date float-stratum finite-population variance and between-date month-stratum variance, with the appropriate finite-population corrections. It is an exploratory finite-population design approximation based on only 2–3 observed dates/month; no normal/iid event confidence interval or significance claim. Suppress this SE under missing dates/windows/unknown prior evidence. Also provide date+security−intersection cluster-score variance and month-stratified date/crossed-security bootstrap sensitivity (500 replicates, seed `202611150041`). The latter is not an exact two-stage SRSWOR bootstrap or a calibrated confidence interval; negative sandwich variance remains undefined, never silently clamped into a positive certainty claim.

Original development dates have no randomized temporal probability for the remaining seventy-date population. Keep their 240 opportunities/40 primary events and frozen confirmation findings as development descriptions, never pool them as independent validation or claim the new exploratory batch is the holdout. Preserve M1, SEC evidence, every prior run and all baseline tracked files by hashes.
