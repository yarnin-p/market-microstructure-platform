# Market Microstructure Platform

Local-first research on first +10% observations in US micro-float stocks. **M1 implements historical universe construction and data auditing. It does not implement tick replay, event detection, confirmation models, or trading.**

The approved policy is [configs/m1-v1.json](configs/m1-v1.json). The user explicitly requires missing historical float to remain `UNRESOLVED`; current float must never substitute. Current-float HTTP requests are disabled in the research client. No event outcomes are computed during M1, including on holdout data.

## Setup and tests

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pytest -q
```

Python 3.13+, PyArrow, DuckDB, exchange_calendars and requests are pinned in the dependency lockfile. The existing environment emits a pandas deprecation warning inside exchange_calendars; calendar checks still pass.

## Reproduce the approved run

The local source objects and connector captures are ignored by Git. These commands require the referenced local datasets; cloning the repository alone does not supply market data.

```sh
# Audit the saved authenticated connector probes, without downloading more ticks.
.venv/bin/python -m market_lab.cli audit-captures \
  --folder data/audit-m1-20261115 \
  --output reports/m1-implementation-20261115/api-audit.json

# Normalize complete saved split/dividend cursor chains.
.venv/bin/python -m market_lab.cli import-actions \
  --folder data/audit-m1-20261115 \
  --start 2026-05-27 --end 2026-11-13 \
  --output data/audit-m1-20261115/corporate-actions.json

# Build or resume the 120-cycle universe from checksum-pinned sources.
.venv/bin/python -m market_lab.cli build \
  --run-id m1-universe-120-20261115-v2 --end 2026-11-13 --cycles 120 \
  --offline \
  --source-index data/runs/universe-120-cs-20261113-v3/evidence-index.json \
  --corporate-actions data/audit-m1-20261115/corporate-actions.json

.venv/bin/python -m market_lab.cli validate --run-id m1-universe-120-20261115-v2
.venv/bin/python -m market_lab.cli query --run-id m1-universe-120-20261115-v2 --count
```

`build` exit **2** means the data remain unresolved, even when processing and technical validation succeed. Exit **1** signals a failure. `acceptance.json` separates `technical_validation` from `research_ready`. No transition to M2 is authorized while core data blockers remain. A zero eligible count caused by unavailable float is not evidence that no micro-float stocks or +10% events existed.

A different source dataset, policy, code version or schema requires a **new run ID**. Resume preserves committed partitions and verifies their checksums. Raw successful API pages are immutable within a cache root. To refresh provider revisions, use a separate data root/dataset version. Legacy cache objects require `--source-index`; new API pages receive checksum sidecars. This prevents trusting old unverified cache files implicitly.

For direct REST downloads, supply `MASSIVE_API_KEY` / `POLYGON_API_KEY` or `--env-file /path/to/credentials.env`. Credentials stay out of artifacts. `--max-requests N` counts HTTP attempts including retries; budgeted/offline builds require one worker. Current authenticated feasibility evidence came through the connected Massive tool, not a local REST API key.

## Universe semantics

- Primary listing MIC allowlist: `XNAS`, `XASE`, `XNYS`. Trade execution venues and TRFs do not determine listing eligibility.
- Historical discovery explicitly uses date-qualified reference data, including securities that later delisted. All returned types remain in audit records; eligible type is `CS` only.
- The cycle is `(previous RTH close, current RTH close]`. A materialized XNYS calendar supplies DST, holidays and early regular closes. AH/PRE labels describe provider observation windows; they do not certify venue-specific session availability. Unobserved overnight intervals are not labeled proof of a market closure or absence of trades.
- Proposed dates are now frozen by approval: 120 cycles from **2026-05-27 to 2026-11-13**, with anchor **2026-05-26**. Exploration ends **2026-09-18** (80 cycles); holdout starts **2026-09-21** (40 cycles). Shorter runs are labeled `PILOT`.
- P0 is unadjusted provider daily close, `0 < P0 <= 3`. It is a retrospective reference, not a guaranteed official auction print or a price known at the exact anchor instant. Missing closes are never forward-filled. Threshold arithmetic uses Decimal, `P0 × 1.10`.
- Historical float range is inclusive `100000..15000000`. Missing float is null and `UNRESOLVED`. Shares outstanding and market-cap/price are never substitutes.
- Repeated/missing security identifiers cannot pass the identity gate; observations remain available for audit. CIK alone is never a security identity. Missing/non-USD currency cannot silently pass the USD price rule.
- Split cycles remain `UNRESOLVED` for price-basis treatment. Dividend records remain in provenance without total-return adjustment. Actions are checked against both anchor and cycle-end symbols linked by the observed security ID. Missing/ambiguous identity continuity stays unresolved. Metadata is retrospective and does not prove permanent identity continuity through every corporate event.
- Overall status is `INELIGIBLE` if any gate fails, `UNRESOLVED` if no gate fails but one is unknown, otherwise `ELIGIBLE`. Independent missingness counts still include records excluded by another gate.

## Historical float evidence contract

Massive's float endpoint is latest-only. The primary gate accepts only explicitly labeled `VERIFIED_PIT` evidence with historical source provenance, valid intervals, measurement time, availability time, and a declared validity policy. Historical/current proxies never pass this gate. Labeling today's endpoint as PIT is rejected.

An external evidence JSON record has the following shape. This illustration is **not market evidence**:

```json
{
  "kind": "float",
  "security_id": "ACTUAL_SHARE_CLASS_FIGI",
  "shares_float": 1000000,
  "cohort": "VERIFIED_PIT",
  "source_kind": "AUDITED_HISTORICAL_RECORD",
  "measurement_at": "2026-06-01T00:00:00Z",
  "available_at": "2026-06-01T12:00:00Z",
  "effective_from": "2026-06-01T00:00:00Z",
  "effective_to": "2026-06-02T00:00:00Z",
  "validity_policy": "APPROVED_SOURCE_SPECIFIC_POLICY_VERSION",
  "source": "ARCHIVED_SOURCE_REFERENCE",
  "source_sha256": "SHA256_OF_AUTHENTICATED_SOURCE"
}
```

`--evidence` accepts an array of records and must use a new run ID. Effective intervals must be supported by the source; do not invent indefinite carry-forward validity. The provider/source claim still needs an external authenticity review: validating the input structure and timestamps cannot authenticate a filing or certify its economic meaning. Overlapping conflicting values remain unresolved.

## Evidence and queries

The v2 universe schema retains exact source row locators, original reference/price records, all gates, float cohort, action evidence, Decimal prices, split group and version identifiers. The validator recomputes float, identity, exchange, currency, price and action decisions; it verifies raw source hashes and row locations as well as summary counts.

```text
data/cache/raw/endpoint=*/REQUEST_HASH.parquet
data/audit-m1-20261115/*-connector.json
data/runs/RUN/calendar.json
data/runs/RUN/corporate_actions.json
data/runs/RUN/universe/cycle=YYYY-MM-DD/snapshot.parquet
data/runs/RUN/exchange_changes/cycle=YYYY-MM-DD/changes.parquet
data/runs/RUN/evidence-index.json
reports/RUN/{manifest,summary,coverage,data_quality,acceptance}.json
reports/RUN/{statistical_results,anomalies}.json
reports/RUN/report.md
```

Full population counts span every stored partition. Query `--limit` bounds only the extract; `matching_rows` always counts the full matching population. `--count` never samples. Future event/tick storage interfaces preserve complete records, but no event/tick producer is implemented in M1. Read-only Research MCP is deferred to M6.

```sh
.venv/bin/python -m market_lab.cli query \
  --run-id m1-universe-120-20261115-v2 \
  --cycle 2026-11-13 --status UNRESOLVED --limit 10
```

Consolidated ZIP export is **optional** under the approved master plan. Use `build --export-bundle` or `export --run-id RUN` when required. Existing export format remains available; empty event tables explicitly mean `NOT_IMPLEMENTED`, not zero market events. Earlier v1 outputs are preserved; the current validator targets v2 runs.

See [M1 implementation evidence](docs/M1_IMPLEMENTATION.md), [approved decision](docs/decisions/2026-11-15-m1-authorization.md), [implementation plan](docs/plans/task-001-m1-v0.1/README.md), and [original master specification](docs/specs/master-research-engineering-plan-v0.1.md).

## M2 bounded historical tick pilot

M2 adds a separate exploratory current-float cohort, full selected-window trade ingestion,
bounded event NBBO windows, SIP replay, first-touch observations and censored continuation
outcomes. Strict M1 data and eligibility remain unchanged. See
[TASK 002 policy and limits](docs/plans/TASK-002-tick-replay.md).

```sh
.venv/bin/python -m market_lab.m2_pilot select --run-id NEW_M2_RUN
.venv/bin/python -m market_lab.m2_pilot run --run-id NEW_M2_RUN --env-file /path/to/local/.env
.venv/bin/python scripts/validate_m2_pilot.py NEW_M2_RUN
.venv/bin/python scripts/m2_query.py --run-id NEW_M2_RUN --kind events --session AH
.venv/bin/python scripts/m2_query.py --run-id NEW_M2_RUN --kind trades --ticker SYMBOL --cycle-id 2026-05-27 --limit 100 --output data/extracts/new-extract.json
```

New immutable run IDs are mandatory when research code or frozen policies change.
Resume an unchanged run using the same `run` command; `--offline` reuses verified cached
pages without network. Evidence is in `data/runs/RUN`; compact reports and a local
`research_bundle.zip` are in `reports/RUN`. Parquet/ZIP/raw ticks are excluded from Git.
Queries support run, cycle, security, ticker, event and session filters. Focused extracts
report total matching counts and explicit truncation; underlying evidence is never truncated.
DuckDB queries cap memory at 256 MB; pilot ingestion is page-budgeted, not a TB-scale
throughput benchmark. Research MCP integration remains deferred.
