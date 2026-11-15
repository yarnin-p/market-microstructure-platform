# TASK 003.1 — Historical NBBO top-up proposal (not executed)

Status: **PROPOSED_NOT_AUTHORIZED_NOT_EXECUTED**. TASK 003.1 is offline with zero HTTP requests. This document defines a possible subsequent bounded execution; it does not authorize acquisition.

## Observed need

Using the original 40-event risk set, primary high/low condition policy and eight QA definitions, deduplicating by security/cycle/exact timestamp gives **450 unique entry/exit quote targets**. These include confirmed entries, common touch+5/15/30/60-minute exits reached after entry, and own-signal+5/15/30/60-minute exits, within observed sessions and cycle end.

- **34** targets already have a fresh valid cached preceding NBBO under the frozen regular-quote policy.
- **31** targets have complete cached time coverage but invalid/corrected/stale quote evidence. Repeating the same request does not necessarily fix these values or reconstruct original PIT NBBO.
- **385** targets lack complete cached time coverage. One discrete snapshot query per unmerged missing target requires at least 385 requests before any pagination; overlapping intervals could be coalesced in a separately versioned implementation. The 385 five-second windows total about **1,925 seconds** of requested observation time, counting overlapping windows separately. Record density, valid-quote availability and pagination requirements are unknown before acquisition.

The complete need list, all source-window metadata, each target's policy/entry-or-exit uses, and the full missing-window queue are in `reports/m3-confirmation-qa-20261115-v1/quote-top-up-plan.json`. No missing target is silently discarded. A snapshot covers only an as-of quote mark, not the continuously observed bid/ask path required for execution-path barriers.

## Proposed engineering probe

Use the first **10** missing windows from fixed cycle round-robin scheduling, sorted by historical identity and timestamp within each cycle. This scheduling is independent of realized returns. It is a feasibility subset, not a substitute for the full paired population or its sampling weights.

| Resource | Hard ceiling |
|---|---:|
| Unique query windows | 10 |
| HTTP attempts (including retries/errors) | 40 |
| Successful pages | 40 |
| Pages per window | 4 |
| Records per requested page | 10,000 |
| Decoded responses total | 64 MiB |
| One decoded response | 8 MiB |
| Local run storage | 256 MiB |
| Connect / read timeout | 5 / 20 seconds |
| Total execution wall time | 600 seconds |
| Minimum request spacing | 250 milliseconds |

Endpoint: `GET /v3/quotes/{historical_ticker}` using the existing Massive subscription. Each target T uses `timestamp.gt=T−5 seconds−1 nanosecond`, `timestamp.lte=T`, ascending timestamp order, limit 10,000. The extra nanosecond preserves a quote exactly five seconds old under the exclusive left bound. Historical ticker/security identity is inherited from the original replay, with no ticker brute force. No new credentials, purchase or subscription.

Any later authorized implementation must use a **new immutable run ID**, a persistent shared attempts/pages/bytes/storage ledger, source hashes and bounded cursors. Stop on any exhausted ceiling; retain empty/errored/partial windows explicitly. Completeness requires a terminal cursor, never inferred from a quiet stream. No retry may escape the global request or wall-time budget. Reuse cached successful pages on resume and retain protected prior artifacts. Do not fetch new cycles, extend to 80 exploration cycles or access holdout data.

## Interpretation limits

This budget does not promise to repair all 385 missing targets, corrected quote semantics or continuous NBBO coverage. A response can contain no quote or only stale/non-regular evidence. Ask-entry/bid-exit values, when both fresh valid marks exist, are **quote-mark estimates**, not fills or executable P&L. Queue priority, displayed size available to a hypothetical order, routing/latency, fees and trade execution are unverified. Keep mark estimates separate from observed eligible-trade returns and maintain all original events and missingness in future comparison denominators.
