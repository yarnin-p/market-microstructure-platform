# TASK 004.1 — Frozen temporal batch 2

Use positions 11–20 of TASK004 selection without resampling; preserve original date/security probabilities and joint weights in all evidence. New immutable run `m4-temporal-batch2-20261115-v1`, baseline `4f3fb66`. Only selected exploration dates, never batch3 or holdout.

Before acquisition freeze `statistical-protocol.json`, selection and execution code hashes. Budget identical to TASK004: 1200 attempts,1150 pages,3GiB decoded,32MiB/page,10GiB storage,96pages/window,160 bounded quote windows,1800s acquisition and5400s analysis. Preserve replay and confirmation definitions without edits.

The original manifest attaches initial-batch month allocation (2/3/3/2) probabilities to all reserved dates. Actual frozen batch2 positions have allocation3/2/2/3. Preserve those source fields exactly; derived analytical views explicitly use batch-specific n_month/N_month and security n/N. Cumulative20 uses5 dates/month. Original-weight summaries remain descriptive and must not be mislabeled design-correct batch2 estimates.

Primary estimands: first-touch incidence overall/by float stratum; conditional forward returns and first-passage buckets; confirmation probability on complete initial risk set; paired common-landmark differences versus C0; censoring/missingness. Preserve unconfirmed/insufficient/censored denominator categories. Taylor finite-population incidence variance requires complete response. Other metrics report crossed date/security cluster sensitivity, not independent-event confidence intervals. Month-stratified date and repeated-security resampling is an illustrative range, not a calibrated CI. Development sample remains separate. No significance or profitability claims.

Validate immutable source manifest, all prior evidence hashes, terminal pagination, raw signal references, deterministic replay and confirmation recomputation. Report both original metadata and derived analysis weights, missing windows and remaining frozen inventory. No new sample or threshold tuning.

Commands: `.venv/bin/python -m market_lab.temporal_batch prepare`, then `acquire --env-file PATH`, then `analyze`, then `validate`. Credentials remain outside Git.
