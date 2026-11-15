# TASK 003.1 — Frozen offline QA design

Baseline `423dead`; run `m3-confirmation-qa-20261115-v1`. This policy and config are recorded before executing QA outcomes. The original TASK 003 code, config, events, reports and C0/C1/C2 values remain immutable.

## C1 definitions and deadline factor

All definitions include the original eligible first touch as observation one, retain the original +10% threshold, require three distinct eligible records spanning >=30 seconds, and use the final qualifying trade's actual SIP receipt time and price. No timer-only or retroactive entry.

| Definition | Observed below-threshold print | Session transition | Cutoff |
|---|---|---|---|
| `C1_COUNTED_ORIGINAL` | Does not reset | Original accumulation reset at overnight; may subsequently confirm in a later observed session | Cycle end |
| `C1_OBSERVED_ACCEPTANCE` | Resets accumulated evidence | Same overnight reset/restart as original; PRE→RTH remains contiguous | Cycle end |
| `C1_SESSION_BOUND` | Does not reset | Only the initial-touch AH, PRE or RTH session is allowed; never restart in a later session | Initial session end |

These change one feature at a time; session-bound is a counted rule, not an undocumented combination with observed acceptance. Cross each definition with a separately labeled `_D60` sensitivity, restricting qualifying receipts to <=first touch+60 seconds (inclusive), also respecting the original cycle/session endpoint. Thus six C1 policies plus frozen C0/C2 give eight policies, each evaluated on the same original 40 events, and separately under the inherited odd-lot follow-up sensitivity. No added odd-only discoveries, changed touch anchors or tuned thresholds.

Known correction notices remove counted evidence when received; no future cancellation removes an earlier signal. Unknown evidence before candidate confirmation yields insufficient evidence. Original raw-field reconstruction and trade eligibility are reused. An absence of observed below-threshold trades does **not** independently verify continuous market support, exchange/feed completeness or overnight coverage.

## C2 evidence audit

Recompute frozen C2 unchanged. Audit all 40 cases for context and report the original ten insufficient-data cases individually. Preserve raw quote locators, SIP timestamps, conditions and causal preceding quotes. Distinguish no returned quotes; invalid/corrected quotes; stale preceding quotes; no updates after valid support; explicit fresh below-threshold bids; observed support breaks; and support unproven because of freshness gaps/short duration. Evidence flags can overlap. An explicit below bid or an observed break is negative price evidence; an absent update is neither a maintained bid nor an automatic support failure. No change to regular quote codes, 5-second freshness, 10-second span, threshold or 60-second window.

## Common-clock comparison

Keep original own-signal 5/15/30/60-minute outcomes, excursions, barriers and 300/900-second gap sensitivities. Add exits at **original touch+5/15/30/60 minutes**, shared by all policies for each initial event and condition policy. A policy must already be confirmed at/before the landmark to have a post-entry return. Late confirmation is `NOT_YET_CONFIRMED`, distinct from final unconfirmed or insufficient data. Last eligible trade at/before the common exit must be no older than 60 seconds and at/after entry. Preserve original overnight, unknown evidence, corrections, cycle-end and pagination censoring. All 40 cases stay in each table; no imputed zero returns.

Match C0 and alternative policy by exact initial event ID, condition policy and landmark timestamp. Verify common exit mark identity/timestamp, preserve both sides' statuses and sources, and compute paired differences only when both marks are observable. Conditional differences and weighted means are not unconditional policy returns, causal effects, evidence of survival protection or executable P&L. Store original sampling N/n, n/N, float strata and initial sessions without reweighting confirmed survivors.

For every policy retain observed pre-confirmation favorable/adverse excursions relative to the original touch price, exact sources and pre-confirmation stop/target crossings. Use `[touch,signal)` for confirmed cases and the declared operational cutoff for cases without a signal; C0 has the initial anchor only. Overnight, unknown, correction and stale-tail flags remain explicit. These are retrospective descriptions, not information made available earlier to the trigger.

## Quote top-up plan only

Count unique entry/common-exit/own-exit quote targets, cached valid targets, cached covered-but-invalid targets and missing-time-coverage snapshot windows. Keep the entire deduplicated need queue. No quote is downloaded. Proposed engineering probe: at most 10 missing five-second windows, 40 HTTP attempts/40 pages (four/window), 64 MiB decoded responses, 8 MiB/page, 256 MiB local storage, 5s connect/20s read timeouts, 600s total wall time, >=250ms request spacing. Select windows by fixed cycle round-robin and sorted identity/time, independent of returns. Use existing subscription only. A future authorized fetch must retain incomplete pagination/empty responses, source hashes and a shared ledger; no retries beyond budget, ticker/date brute force or silent completion.

The envelope is **proposed, not execution authorization**. A separate documented execution instruction/run is required before fetching. Re-requesting an already covered corrected quote does not reconstruct original PIT values. Snapshot ask/bid marks do not establish fills, order sizes, queue priority, latency, transaction costs or full bid-path barriers.

## Integrity and export

HTTP requests are trapped at runtime. Freeze code/config and hash all prior local data (including SEC evidence), prior reports and tracked baseline files. Holdout bytes may be hashed for preservation but contents are never parsed/analyzed. A new run ID is mandatory if frozen calculation code/config changes. Validate deterministic recomputation, all 240 frozen baseline signal/condition records and their outcomes, source page hashes/timestamps, session/deadline eligibility and common-pair denominators. Export every event-policy-condition record in compact JSON/Parquet and one consolidated validated research bundle covering the same ten exploration cycles. No 80-cycle expansion, new cycles, float substitution, M1 changes, threshold optimization, significance claim or profitability claim.
