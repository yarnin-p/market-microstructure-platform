# TASK 003-S3 — bounded daily-source lineage v1

Baseline `eb95502`, branch `feat/task-003-s3-flatfiles`. TASK005.1 has completed and is preserved. No modification of market methods, historical eligibility, 40 original events, M1–M5 artifacts or holdout. No new REST calls. S3 is the preferred bulk source going forward, subject to this feasibility pilot and reconciliation.

## Frozen acquisition

Metadata HEAD requests inspect five frozen TASK003.2 audit dates (BIVI, ATNM, EVTV, FFAI, QRHC) and two trade objects. Pilot selection is the first two audit dates among those named cases: 2026-05-28 and2026-05-29, covering REST-empty BIVI and corrected ATNM. Download2 daily quote objects and1 trade object (May28 only), total16,890,044,044 compressed bytes. Other named cases remain explicitly SOURCE_COVERAGE_UNKNOWN, not negative observations. Selection is not based on new quote or return outcomes.

Budgets:20GiB received bytes including probes/retries;40GiB local raw+selected storage;80GiB minimum free disk;2GiB memory ceiling (report conservative sum of observed concurrent-process peaks);3600s active acquisition/extraction execution;32 request attempts including7 metadata HEADs;256GiB decoded CSV;10M selected rows. Read/connect timeouts30/5s; no automatic SDK retries. Four fixed contiguous ranges per object share one thread-safe request/byte/time ledger. The one-hour clock remains shared with streaming extraction. Data preparation/tests are offline and outside the acquisition clock.

A range probe of8MiB measures throughput before the full transfer and is reused as the first partial prefix. Checkpoints bind prefix SHA256 and byte counts. Each source identity binds key,size,ETag,LastModified; post-download HEAD must match. Final SHA256 is calculated over the ordered reassembled compressed object. ETag is not assumed to be MD5. Changed source objects create a new content-addressed snapshot; old snapshots remain intact. No credentials in metadata/errors/Git. Keys are runtime-only, from private local file or dedicated environment variables.

## Streaming extraction and coverage

Gzip CSV is scanned once per completed source/ticker-selection version, in8MiB blocks; filter all tickers from the original40-event historical identity mapping. Preserve every original column as string; add exact int64 SIP timestamp, sequence, original source-row ordinal and frozen security mapping. Partition Parquet by source date/ticker and bind raw source SHA in metadata. Explicit zero-row partitions are evidence of no selected records in the parsed source, not zero economic outcomes. DuckDB orders by SIP,sequence,source ordinal; exact full-record duplicates are audited and deduplicated only for event replay.

A completed extraction is immutable and reused. An incomplete gzip parse retains its attempt and is not coverage-complete; resume scans that incomplete file under a new attempt. Ordinary gzip has no direct arbitrary-offset decompression checkpoint, so this may replay a prefix on recovery. Completed daily sources are never reprocessed per event. Gzip EOF/CRC and full source hash prove object integrity, not completeness of an independent exchange feed.

Daily filename/time alignment is audited using global min/max SIP and counts outside the object's UTC date. Provider-day coverage is admitted only after full parse/CRC with no out-of-date rows; no inference of continuous24-hour trading or absence of provider gaps. Missing dates remain unknown. AH/PRE/RTH risk windows remain those of the original cycle; no carry across the blind overnight interval or session boundaries in state replay.

## Predeclared confirmation comparison

Keep all40 initial events and both trade-condition policies. Independently rerun original TASK003/TASK003.1 trade-based definitions and require exact equality of C0/C1/C2 baseline signals/outcomes and all QA rows. This does not replace original data.

`C2_S3_FROZEN_RULE` invokes the original C2 function unchanged on normalized S3 quotes: bid at original +10% threshold, observations spanning>=10s, original5s freshness/gap rules, <=60s confirmation deadline. No changed confirmation parameters. Full source coverage is mandatory; otherwise INSUFFICIENT_DATA rather than a negative result.

`C2_S3_STATE_BASED_V1` is a separate sensitivity, fixed before outcomes: causal current-state bid>=original threshold for10s measured by a timer, <=60s deadline. Current state must be valid (positive uncrossed bid/ask, positive sizes, regular/non-corrected conditions) and age<=60s at evaluation; fresh age<=5s is reported separately. No5s mechanical quote-update-gap reset. Continuous in the observed state stream does not establish continuous market support or executable liquidity. Locked quotes remain allowed under the frozen validity rule and flagged explicitly.

At the same SIP clock process all observed events before a timer. Any invalid/below-threshold observation breaks accumulated support even if a later sequence at that same SIP restores a valid state. Contradictory states at identical SIP+sequence are ambiguous and invalidate state. Any session transition resets support; PRE→RTH differs deliberately from the frozen event rule and is labeled a state-policy sensitivity. No earlier valid state can be resurrected past a latest invalid/corrected event. No future event can invalidate or support a past decision.

Recompute trade-path outcomes only for changes in signal status/time/price; otherwise reuse the frozen trade outcomes with explicit provenance. Keep own-signal and touch-anchored common-clock returns, MFE/MAE, all original barriers and gap sensitivities. Missing/unconfirmed/censored cases stay in the risk set. Report ask-entry/bid-exit only when both causal quote marks are fresh and valid; never fills or realized P&L.

## Reconciliation and expansion gates

Retain all five named TASK003.2 cases. Compare overlap-only records, nanosecond clocks, prices/sizes/exchanges/conditions/indicators/tape/TRF fields, sequence ordering and duplicates; show raw source witnesses before/inside/after the frozen windows. Subsequent quotes are context only. Empty REST does not prove data loss. REST and S3 share a provider and are not independent data sources. One bounded BIVI trade-file shared-field reconciliation is secondary and does not replace existing trade/correction evidence.

Before expansion require validated object integrity, date/session alignment, explicit REST/S3 findings, deterministic causal state replay, unchanged C0/C1, auditable C2 differences, old-artifact hashes intact and no holdout access. If any gate is unresolved, report CONDITIONAL/BLOCKED with exact evidence. A successful two-day pilot only permits preparing a separate bounded plan for the original10 development dates, not automatic download. No120-cycle acquisition and no holdout execution.
