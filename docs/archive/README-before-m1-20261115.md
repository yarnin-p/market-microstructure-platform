# Market Microstructure Platform

Executable historical universe builder and initial Research Results Contract. Python 3.13+, Massive reference/daily-price APIs, exchange_calendars, Parquet/ZSTD, DuckDB. No bulk tick ingestion or continuation detector is implemented in TASK 001.

## Setup and execution

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pytest -q

# Credential: MASSIVE_API_KEY / POLYGON_API_KEY environment variable,
# or --env-file pointing at an existing credential file. Never commit credentials.
.venv/bin/python -m market_lab.cli --env-file /path/to/credentials.env smoke --date 2026-11-12
.venv/bin/python -m market_lab.cli --env-file /path/to/credentials.env build \
  --run-id universe-120-20261113-v1 --end 2026-11-13 --cycles 120
.venv/bin/python -m market_lab.cli validate --run-id universe-120-20261113-v1
```

`build` exit code 0 means fully verified coverage; 2 means processed with unresolved/missing coverage. `validate` exit code 0 means structural/count/hash checks pass; read `research_ready` separately. Never interpret validation success as historical data completeness.

Repeat the same command to resume. Successful API pages are cached; unsuccessful requests are not. Cycle checkpoints and snapshot hashes prevent silent overwrite. Change the run ID when configuration, evidence or implementation changes. A process lock enforces one writer per run ID, and per-request cache locks allow shared raw inputs across experiments. An interrupted cycle is rebuilt from cached pages; committed cycle snapshots are reused. Exact float evidence received later requires a new run, preserving original outputs. `--workers 16` enables bounded parallel reference/price prefetch (maximum 16).

## Eligibility and point-in-time semantics

- Each cycle is `(previous RTH close, current RTH close]`; the previous close is an anchor, not a new-cycle tick. Freeze eligibility at this anchor.
- XNYS calendar supplies holidays, DST and early regular closes. Extended-hours segments use the provider's conventional 04:00–20:00 ET coverage; venue-specific early extended-session closes are not asserted by this calendar.
- Explicit MIC allowlist: `XNAS → NASDAQ`, `XASE → NYSE American (AMEX)`, `XNYS → NYSE`. Each code must exist in the recorded Massive exchange directory. Other codes under the same operating MIC are not admitted.
- Historical discovery uses explicit `date`, `active=true` as of that date, no exchange/type prefilter. Current survivor lists are never substituted. Asset scope is Massive `market=stocks`; full OTC enumeration is outside discovery. Missing exchange fields survive into audit output.
- Candidate discovery preserves all returned security types in audit output. Eligible membership requires historical `type=CS` (Common Stock), per the user's decision. ADR/ADRC, ETF, warrants, rights, units, funds and all other types are excluded; missing historical type is unresolved. No country-of-incorporation rule is inferred from US listing.
- Previous RTH close uses **unadjusted** grouped daily `c` for the anchor date, with `0 < c <= 3`. This is the provider's regular-session daily close, not guaranteed identical to the official auction print. No forward-fill, current snapshot, or split-adjusted current-dollar substitute.
- Required float is `100,000 <= shares_float <= 15,000,000`. Shares outstanding and market-cap/price are never float substitutes.
- Daily historical reference is an effective-date reconstruction maintained by the provider, not proof of contemporaneous publication. Save request dates, retrieval time, raw provider fields, source hashes and precision labels. Date-only observations do not establish exact intraday transfer timestamps.
- Compare anchor reference with cycle-end reference using security FIGI, never ticker/CIK alone. Identified changes or missing identity/observation make event-time checks unresolved until precise evidence covers the event. Initial snapshot membership is never changed by this comparison.
- `INELIGIBLE` means at least one known exclusion; `UNRESOLVED` means no known exclusion but at least one unknown gate. Independent `unresolved_*` counts also include unknown fields on already excluded records. Independent exclusion counts can overlap.

## Historical float limitation and reproducible resolution

Massive documents `/stocks/vX/float` as **latest-only**, with no historical lookup; unsupported date filters can be ignored silently. The builder intentionally does not query this endpoint for historical eligibility. Live smoke tests may probe availability, but cannot turn its response into historical float.

Supply `--evidence evidence.json` to a **new run ID** when audited historical evidence becomes available. JSON is an array of records:

```json
[
  {
    "kind": "float",
    "security_id": "ACTUAL_SHARE_CLASS_FIGI",
    "effective_from": "2026-06-01T00:00:00Z",
    "effective_to": "2026-07-01T00:00:00Z",
    "available_at": "2026-06-01T00:00:00Z",
    "shares_float": 1000000,
    "source": "/absolute/path/to/audited/source",
    "source_sha256": "replace_with_64_character_sha256_of_actual_source"
  }
]
```

This is a schema illustration, not usable market evidence. Effective intervals must be established by the source, not guessed. `available_at` must be no later than the evaluation timestamp. Conflicting overlapping values remain unresolved. The caller is responsible for authenticating external source claims; the pipeline checks fields, timestamps and intervals and retains source identity/hash, but does not certify the source's truth.

Exchange evidence uses `kind: exchange` with `primary_exchange` instead of `shares_float`, and the same provenance fields. Event checks may receive additional exchange evidence without mutating the original snapshot:

```sh
.venv/bin/python -m market_lab.cli event-check --run-id RUN \
  --cycle 2026-11-13 --ticker TICKER --at 2026-11-13T15:00:00Z \
  --evidence exchange-evidence.json
```

## Consolidated Research Bundle v1 — final external contract

The latest user-supplied contract supersedes the six-file external package. The six files below remain internal reporting foundation. Each `build` / `run` command automatically exports **one** `research/runs/RUN/research_bundle.zip` after validation. No manual daily consolidation is needed. This ZIP contains exactly:

```text
manifest.json
summary.json
event_results.parquet
cycle_metrics.parquet
cohort_metrics.parquet
distributions.parquet
statistical_tests.json
data_quality.json
anomalies.json
report.md
```

`cycle_metrics.parquet` includes **every requested cycle**, even missing or failed cycles, and reconciles candidate/exclusion counts against snapshots. Metadata identifies processed versus fully verified universe cycles. The experiment status stays `INCOMPLETE` because replay/classification are not implemented. Event, cohort and distribution tables have explicit schemas and zero stored rows, with `NOT_IMPLEMENTED` stage labels and null research metrics. Zero stored event rows is not a claim that no +10% events occurred.

```sh
.venv/bin/python -m market_lab.cli --env-file /path/to/credentials.env run \
  --run-id RUN --end 2026-11-13 --cycles 120 --workers 16
.venv/bin/python -m market_lab.cli report --run-id RUN
.venv/bin/python -m market_lab.cli export --run-id RUN --format bundle --bundle-budget-mb 50
.venv/bin/python -m market_lab.cli validate-bundle research/runs/RUN/research_bundle.zip
```

ZIP validation checks exact membership, checksums, schemas, row counts, cycle coverage, reconciled counts and false completion claims. Tables are streamed to temporary local files for validation. Raw ticks never enter the bundle. If even minimal metadata exceeds a configured budget, the bundle explicitly reports the overage and omits nothing. Full event aggregation, statistical dependence handling and event externalization for oversized bundles are deferred to the replay/classification phase. The exporter **refuses** to silently discard existing event Parquet until those contracts are implemented.

## Internal reporting foundation

Every finished universe invocation writes these compact files under `reports/RUN/`:

| File | Content |
| --- | --- |
| `manifest.json` | Run/config identity, code/dependency versions, calendar, cycle coverage, artifact hashes and provenance |
| `summary.json` | Full discovered-population counts, unique ticker/security counts, metric definitions, classification distribution |
| `data_quality.json` | API errors, missing/unresolved coverage, exact data limitations |
| `statistical_results.json` | Current study stage, sample sizes, outcomes/CI fields; explicitly NOT_ESTIMATED until event research runs |
| `anomalies.json` | Blocking data issues and drilldown instructions |
| `report.md` | Human/AI-readable interpretation, scope and limitations |

Universe classification counts are full-population descriptive statistics. There are no continuation probabilities or confidence intervals yet: no events or outcomes have been computed. The contract reserves these fields rather than inventing numbers.

Large artifacts live under ignored `data/`, or an external `--data-root` volume:

```text
data/cache/raw/endpoint=reference|prices|float/*.parquet
data/runs/RUN/universe/cycle=YYYY-MM-DD/snapshot.parquet
data/runs/RUN/exchange_changes/cycle=YYYY-MM-DD/changes.parquet
data/runs/RUN/events/cycle=YYYY-MM-DD/session=RTH/*.parquet
data/runs/RUN/ticks/dataset-reference.json
data/datasets/ticks/DATASET_ID/cycle=YYYY-MM-DD/session=RTH/*.parquet
```

All Parquet uses ZSTD. API pages are retained as full JSON payloads in compressed Parquet envelopes; normalized snapshots are columnar. Event/tick producers can use `market_lab.datasets.append_evidence` for bounded batches, preserved in full and partitioned locally. Tick writers must supply a stable `dataset_id`; experiments reference the same shared raw tick dataset without making copies. This is a storage interface, not a tick downloader. TB-scale throughput has **not** been benchmarked.

DuckDB queries local Parquet without uploading datasets:

```sh
# Count all matching rows, no sampling or extract limit applied to statistics.
.venv/bin/python -m market_lab.cli query --run-id RUN --count

# Small focused extract; matching population size and truncation label are included.
.venv/bin/python -m market_lab.cli query --run-id RUN --cycle 2026-11-13 \
  --ticker TICKER --status UNRESOLVED --limit 20 --output /tmp/extract.json

# Future event/tick producer output supports the same query contract.
.venv/bin/python -m market_lab.cli query --run-id RUN --dataset events \
  --event-id EVENT_ID --session RTH --limit 20
```

The query implementation bounds returned extracts to at most 10,000 rows; raw evidence is never shortened. `--count` always counts the full matching dataset. Extract rows are not presented as statistical samples. Additional research-specific statistics can be added incrementally using full-population DuckDB aggregates.

Version code, schema contracts, configuration and compact reports. `.gitignore` excludes environments, credentials, Parquet, DuckDB and the large data tree. No auto-commit, push, tick download or trading action is performed.

## Provider references

- [Historical float limitation](https://massive.com/knowledge-base/article/does-massive-have-historical-float-data)
- [Historical security master and reconstruction limitations](https://massive.com/knowledge-base/article/does-massive-have-a-downloadable-security-master)
- [Exchange identifiers](https://massive.com/docs/rest/stocks/market-operations/exchanges)
- [Daily price trade-condition semantics](https://massive.com/knowledge-base/article/does-a-form-t-trade-update-a-pre-market-minute-bars-high-low-open-and-close)
- [Historical exchange calendar](https://github.com/gerrymanoim/exchange_calendars)
