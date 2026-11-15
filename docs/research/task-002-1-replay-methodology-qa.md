# TASK 002.1 — Replay Methodology QA & Coverage Repair

Run: `m2-methodology-qa-20261115-v1`

Methodology: `task-002-1-observed-sessions-v2`

Immutable reference: commit `8a4903f`, run `m2-first-touch-3cycles-20261115-v1`.

## Observed result

The three truncated trade requests now reach terminal pagination cursors. Complete provider windows increase from 42 to 45; observed-session verified first touches increase from 17 to 20. All 20 primary touch records/timestamps remain unchanged. There are **zero strict full-cycle opportunities**: this experiment does not establish overnight coverage. The unchanged legacy policy reproduces all original 20 events and 20 outcome records exactly.

This is the same fixed 16-security, three-cycle feasibility frame (2026-05-27/28/29), with 10 systematic and six diagnostic securities. Of 48 security-cycle opportunities, three retain their original historical-quality exclusions. The diagnostic securities were chosen for investigation; their event rates are not systematic estimates. No full-universe, holdout, eligibility, historical-float or confirmation-model work was performed. M1 remains `BLOCKED_DATA`; current float is never historical float.

## Population and first-touch definitions

The trigger remains the original eligible trade at or above 110% of the previous RTH close. Ordering, decimal prices, original quality gates and security identities remain fixed. Session boundaries use the original exchange calendar, in ET:

| Definition | Evidence required | Claim supported |
|---|---|---|
| `OBSERVED_SESSIONS_FIRST` | Terminal pagination, no unknown preceding evidence in defined sessions | First eligible touch in AH `(previous RTH close, previous 20:00)`, PRE `[current 04:00,09:30)`, RTH `[09:30,current RTH close]` |
| `PREFIX_FIRST` | Known complete prefix through an AH touch, before the overnight blind interval | No earlier eligible touch in that observed prefix; does not certify the rest of the opportunity |
| `STRICT_FULL_CYCLE_FIRST` | All relevant intervals, including 20:00–04:00, verified | Full chronological cycle first touch; no qualifying opportunity in this pilot |
| `UNVERIFIED_TOUCH` | Missing pages or unknown prior evidence | Candidate observed crossing only, excluded from verified observed-first numerators |

The API requests span `(previous RTH close,current RTH close]`, but requesting those timestamps and exhausting a cursor do not independently certify provider coverage of overnight trading. The policy intentionally excludes 20:00–04:00; no evidence of absence, exchange closure or full 24-hour coverage is inferred. Eighteen returned messages outside the defined sessions are concentrated just after the 20:00 boundary: nine fail price/size checks and nine are outside-session rejects. These boundary messages do not validate overnight coverage. Weekend/calendar gaps also do not become certified coverage.

`PREFIX_FIRST` and observed-session proof are separate booleans and can overlap. The former can apply to an AH touch before a missing tail; the latter requires a complete opportunity. Three repaired diagnostic events have prefix proof. The old `VERIFIED_FIRST_TOUCH` label counted two; this is a definition/completeness distinction, not three full-cycle validations. Strict first-touch rates are undefined with denominator zero, not 0%.

## Condition eligibility audit

The full condition-combination accept/reject distribution, rejection reasons and provider dictionary are in `condition-distributions.json`; `condition-audit-summary.json` includes session totals and overlapping per-code counts. Combination counts are disjoint; per-code counts must not be summed because a print may carry multiple codes.

Three parallel policies were replayed against identical inputs:

1. `LEGACY_BOTH`: original consolidated high/low AND open/close rule.
2. `HIGH_LOW_ONLY`: remove the open/close conjunct where high/low is allowed, retaining all explicit late/reference/correction vetoes. This is the revised primary research policy.
3. `ODD_LOT_OBSERVATION_SENSITIVITY`: additionally admit code 37 as a raw price-observation sensitivity. Other simultaneous rejecting conditions still veto the print. This does not declare odd lots official price-forming trades.

Repaired-stream distribution (`LEGACY_BOTH` and `HIGH_LOW_ONLY` are identical):

| Session | Accepted | Rejected | Odd-lot sensitivity accepted | Odd-lot sensitivity rejected |
|---|---:|---:|---:|---:|
| AH | 184,593 | 114,383 | 298,808 | 168 |
| PRE | 439,410 | 543,002 | 946,669 | 35,743 |
| RTH | 1,586,856 | 1,384,274 | 2,961,899 | 9,231 |
| Outside defined sessions | 0 | 18 | 0 | 18 |

High/low-only adds **zero accepted prints and zero changed touches** in this pilot. Relevant high/low-true, open/close-false codes (5, 10, 22, 32) remain explicitly rejected as reference/out-of-sequence evidence. That result does not prove the conjunct harmless in every population; a regression test demonstrates that an otherwise allowed high/low-only condition is admitted by the revised policy. Form T remains an AH/PRE exception, not an RTH exception; secondary rejecting conditions still apply.

Odd-lot sensitivity moves eight existing touches earlier and adds two diagnostic events (AIM and RKTO on May 29), giving seven systematic and 15 diagnostic events. These are policy-sensitive observations, not an improvement score or a reason to select the policy by returns. Dictionary flags describe aggregate eligibility and the downloaded dictionary is not a historically versioned SIP rulebook. See the provider's [conditions glossary](https://massive.com/glossary/conditions-indicators) and [Form T extended-hours explanation](https://massive.com/knowledge-base/article/does-a-form-t-trade-update-a-pre-market-minute-bars-high-low-open-and-close).

## Bounded coverage repair

Frozen budget: at most 96 requests, 80 new pages, 64 trade pages, 16 quote pages, 1 GiB decoded responses, 32 MiB/page, plus existing bounded client timeouts. Only the three named trade requests were continued from their original terminal `next_url`. Original prefix pages are read-only. Each cursor, page checksum, ascending timestamp and request bound was independently checked; completeness requires a terminal response without `next_url`. Exhausted budgets/errors retain partial status. The provider's [trade endpoint documentation](https://massive.com/docs/rest/stocks/trades-quotes/trades) describes pagination; cursor exhaustion is not independent exchange-feed certification.

| Security / cycle | Original pages / rows | Added pages / rows | Final pages / rows | Result |
|---|---:|---:|---:|---|
| ASTC / 2026-05-27 | 12 / 600,000 | 20 / 963,713 | 32 / 1,563,713 | Terminal cursor |
| BRTX / 2026-05-27 | 12 / 600,000 | 2 / 84,742 | 14 / 684,742 | Terminal cursor |
| SNGX / 2026-05-27 | 12 / 600,000 | 2 / 69,564 | 14 / 669,564 | Terminal cursor |

Actual: **24 requests, 24 new pages, 255,244,079 decoded bytes, no request errors**. No additional quotes were needed: the original quote samples cover the three original audit timestamps. Repair confirms the existing three candidate touches as observed-session firsts; it does not change their timestamps. Unrepaired comparisons retain their incomplete status.

## Gaps, censoring and sensitivity

There are 858 eligible-print gaps longer than 300 seconds; 734 contain returned messages rejected by the eligibility policy. There are also 868 raw-message gaps longer than 300 seconds, measured separately across within-session raw messages. These counts describe different intervals. Missing pagination is explicit API truncation. A quiet returned stream in a terminal-cursor window is not by itself proof of ordinary illiquidity, an exchange halt, or feed loss; no independent halt/feed-loss source was obtained.

The primary sensitivity removes automatic elapsed-gap censoring within complete observed sessions. Missing pages, overnight gaps, unknown price evidence, later invalidation and the fixed 60-second forward-mark freshness limit still censor. It measures the reported eligible-trade path, not a continuously observable/executable price path. A barrier can occur on the next eligible print after a quiet period; no crossing time between prints is invented. The retained 300- and 900-second policies expose dependence on a conservative continuity assumption. Observed MFE/MAE are descriptive trade-path excursions, not fills or complete continuous-market extrema.

The accompanying run report tabulates all forward horizons and first-passage outcomes under all three gap policies, separately by sample. Per-cohort figures and uncensored return means/min/max are in `primary-cohort-results.json`; return means are conditional on the policy-specific uncensored sample, not directly comparable performance estimates. Censoring and neither-barrier outcomes are kept separate.

## Cohorts and denominators

The primary repaired high/low policy gives:

| Sample | Cohort | Complete observed opportunities | Verified events | Zero-event opportunities | Prefix events | Strict opportunities |
|---|---|---:|---:|---:|---:|---:|
| Systematic | EXCHANGE_PRICE_ONLY | 29 | 7 | 22 | 0 | 0 |
| Systematic | MASSIVE_CURRENT_FLOAT_PROXY | 11 | 3 | 8 | 0 | 0 |
| Systematic | SEC historical evidence overlap | 3 | 2 | 1 | 0 | 0 |
| Diagnostic | EXCHANGE_PRICE_ONLY | 16 | 13 | 3 | 3 | 0 |
| Diagnostic | MASSIVE_CURRENT_FLOAT_PROXY | 4 | 4 | 0 | 0 | 0 |
| Diagnostic | SEC historical evidence overlap | 3 | 2 | 1 | 0 | 0 |

Cohorts overlap and cannot be added as independent samples. `EXCHANGE_PRICE_ONLY` is the inherited shorthand for unchanged non-float M1 gates, not permission to remove other quality gates. Current float is the frozen original retrospective proxy. SEC overlap means HCWC/systematic and AIM/diagnostic occur in the original SEC evidence context, irrespective of whether the disclosure supports a usable share-class estimate. It neither supplies verified historical float nor permits carrying an SEC estimate forward. The three historical-quality exclusions remain excluded. All 48 frame opportunities, including exclusions, are represented in the export; 45 eligible opportunities expand into policy/variant records.

## Raw trade and NBBO audit

`requested-raw-nbbo-audit.json` matches the **exact original published security-cycle and trade record**, rather than selecting the first event for each ticker. Both raw trade and quote page hashes are verified. The generic `raw-nbbo-audit.json` is supplemental and can contain another date for the same ticker.

| Original example | Touch | Preceding bid / ask | Quote age | Observed consistency |
|---|---:|---|---:|---|
| SNGX / 2026-05-28 | 0.9537 | 0.9519 / 0.9537 | 3.356917 ms | At preceding ask; subsequent supporting NBBO after 217 ns |
| HOTH / 2026-05-28 | 1.50 | 1.48 / 1.49 | 5.239561 ms | Above preceding ask; no supporting NBBO within following 5 s |
| DBGI / 2026-05-27 | 0.3198 | 0.3166 / 0.3198 | 0.001969 ms | At preceding ask; subsequent support after 13.692528 ms |

HOTH is an extended-hours Form T print, size 14,400, exchange 4, TRF 202; its participant-to-SIP lag is approximately 4.108 ms. The discrepancy is retained as an audit finding, without asserting a cause or silently deleting the print. Following quotes are retrospective context only and never trigger inputs. Even a print at the ask does not establish that an order of any size could execute there.

## Reproduction, artifacts and validation

From an environment installed with the pinned project dependencies and pytest:

```sh
python -m market_lab.replay_qa freeze
python -m market_lab.replay_qa repair --env-file /absolute/path/to/local/credential.env
python -m market_lab.replay_qa analyze
python -m scripts.report_replay_qa
python -m scripts.validate_replay_qa
python -m pytest -q
python -m scripts.bundle_replay_qa
```

Use `repair --offline` for cached replay. Freeze refuses code/config drift under the same run ID; new methodology/input changes require a new run ID. Run from the repository root. The original pilot raw/normalized cache is a prerequisite; it is not fabricated or downloaded by the QA command. Resuming reuses cached pages within the shared request ledger. Credentials stay in the local environment file; API URLs are sanitized before persistence. No credential file is committed.

Versioned inputs/code/schema and compact evidence/results are committed. Full raw response pages and Parquet remain under ignored `data/runs/`, following the original repository convention; a fresh checkout alone cannot independently replay raw evidence without that cache or explicitly authorized reacquisition. Reports link hashes, page rows and exact nanosecond timestamps to the local evidence. `manifest.json` hashes the report artifacts; `execution.json` in the local run freezes all replay-module hashes, original artifact hashes and M1 fingerprint. Publisher and independent validator hashes are separately recorded.

`event-level-results.json` exports all 124 event-policy-variant records, 372 gap-policy outcomes and 273 opportunity records including exclusions. These are repeated analyses of a small fixed pilot, not 124 independent market events. `summary.json` retains the full before/after grid; `first-touch-comparison.json` contains pair-level differences. The event contract is `schemas/replay-methodology-qa-v2.json`.

Validation passes: all original artifacts/M1 unchanged; original 20 legacy events and outcomes exactly reproduced; 60 original-plus-tail cursor pages checked; all 124 event sources verified; 372 outcome references checked; exact original three audit examples verified; full JSON export equals Parquet. **150 tests pass** (84 pre-existing pandas warnings). Regression coverage includes condition combinations/session exceptions, unknown prior evidence, observed/prefix/strict proof, stale marks vs gaps, overnight/missing pages, unknown paths, bounded resumable pagination and exact published-audit selection.

Next research decision: use explicitly named observed-session first touches for this population; keep strict full-cycle claims unavailable until separately validated overnight evidence exists. Retain condition and gap sensitivities with denominators. Investigate the HOTH quote discrepancy and external halt/feed quality only within a separately bounded scope before expanding the sample. This pilot establishes neither executable profitability nor verified historical low-float eligibility.

The consolidated local deliverable is `reports/m2-methodology-qa-20261115-v1/research_bundle.zip` (ignored by Git, matching the original pilot). It contains all three processed cycles, all 124 event-policy-variant payloads with their three gap outcomes, 39 cycle/config/sample metric rows, 36 cohort groups, 2,976 distribution observations and the complete reports. Bundle validation checks ZIP integrity, every artifact checksum and Parquet row counts. Results can be read without raw ticks; raw-source revalidation still requires the local evidence cache. `bundle-validation.json` is committed as the compact packaging receipt.
