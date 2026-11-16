# TASK 004.2 — Frozen final temporal batch and cumulative30 protocol

Baseline `89b1a6a`, verified remote `feat/task-004-1-temporal-batch2`. Batch run `m4-temporal-batch3-20261116-v1`; separately versioned cumulative analysis `m4-temporal-cumulative30-20261116-v1`.

## Exact frozen membership

Read the remaining inventory from TASK004.1, verify its hash, and compare the entire calendar and all 240 opportunity records against original TASK004 positions 21–30. Reject differences in identity, provenance, strata, probabilities or weights. Dates, in frozen execution order: 2026-06-23, 2026-07-07, 2026-08-21, 2026-09-10, 2026-07-14, 2026-08-04, 2026-07-13, 2026-08-19, 2026-07-31, 2026-08-26. Only execution flags and the calendar view are derived; original selected records and source files are untouched. No new random draw.

## Fixed acquisition and research

Reuse TASK004 budgets: 1,200 HTTP attempts, 1,150 successful pages, 3GiB decoded total, 32MiB/page, 10GiB local storage; 96 pages/window; trades 50,000/page; quotes 10,000/page; at most 160 unique event-centered +/-60-second windows. Persist acquisition deadline 1,800s and shared request/page/byte ledger. Offline analysis has a 5,400s hard alarm/checkpoints. Stop on limits; retain partial/missing opportunities, including cached-only recovery without new requests. No 385-target execution quote top-up, new subscription, other dates or holdout.

Reuse unchanged eligibility, retrospective current float snapshot/FIGI mapping, separate SEC context, observed-session first touch, high/low rule, no mechanical gap policy, corrections, unknown/overnight/freshness censoring, odd-lot and 300/900s gap sensitivities. Apply all eight existing C0/C1/C2/deadline definitions to the same verified initial primary risk set. Own-signal and original-touch common exits, pre-confirmation evidence and missing/unmatched populations stay separate. No threshold, stop or target optimization.

## Batch and full30 estimands

Batch3 has month allocation 1/4/4/1. Derive batch-specific analytical date weights separately; one June and one September date do not support a within-month Taylor variance estimate, so suppress that SE rather than use iid intervals.

For the completed30 sample use **original planned** month probabilities June6/14, July9/22, August9/21, September6/13. Multiply these by the original per-date/float-stratum security probability n/N. Analytical joint weight = inverse joint probability. Preserve every original source weight, including original batch1 marginal metadata; write a separate 720-row analytical-weight sidecar and derived views. Do not reuse batch2's 3/2/2/3 or cumulative20's 5/5/5/5 probabilities. Full30 is the original month-stratified SRS date plan, not an iid concatenation of three batches. Keep development10 separate.

Before estimates reconcile exactly30 unique exploration dates, 720 unique security-cycle opportunities (360/360 strata), no overlaps between batches, all source fingerprints, original80 exploration/40 holdout partition metadata, completeness and quality response. No holdout outcome table is parsed. Estimate weighted incidence, stratum differences, confirmation frequencies and first-passage bucket fractions with explicit effective/observed/missing denominators. Use existing finite-population design linearization, date/security cluster-score and month/date-crossed-security resampling infrastructure; report finite-sample/serial-dependence limitations. Bootstrap percentile ranges remain exploratory, never calibrated confidence intervals or significance evidence.

## Raw first-passage audit

Verify the unchanged Batch2 primary no-gap +3/-3 result (5 upside first,25 downside first) against its frozen table/hash. Report corresponding Batch3/full30 counts without changing rules. Select representative upside/downside/censored examples deterministically by chronological cycle/security identity within outcome category, not return magnitude. Reconstruct chronological eligible trades with the original correction policy, check first eligible barrier timestamp and direction, raw price/source hashes, preceding observations and cancellation/correction notices. Same-SIP ambiguity and censoring remain explicit. Observed trade barriers are not executable fills.

## Outputs and validation

Deterministically recompute all240 Batch3 first-touch opportunities plus full confirmation/outcome tables. Verify source hashes, pagination/timestamps, source weight identity, old artifacts/SEC/M1 preservation, full JSON/Parquet equivalence, test suite and consolidated bundle integrity. Publish separate Batch3 and cumulative30 bundles/results with linked source-run hashes. Conclude whether additional exploration or methodological work is needed before a **separately authorized** formal holdout design; never start holdout automatically.
