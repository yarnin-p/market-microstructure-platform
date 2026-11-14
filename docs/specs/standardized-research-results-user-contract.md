# TASK — Standardized Research Results & Aggregation System

## Objective

Design and implement a standardized research results system for the Market Microstructure Platform.

The platform processes 120 historical trading cycles using Massive tick-level data.

**The final deliverable of each completed research execution must be ONE consolidated `research_bundle.zip` containing results from ALL processed trading cycles.**

Do not require manual consolidation, daily exports, or separate daily result uploads.

## 1. Storage Architecture

Separate internal processing storage from external research outputs.

### Internal Storage

- Preserve raw tick data locally.
- Partition raw data and replay checkpoints by trading cycle where beneficial.
- Use Parquet and DuckDB for efficient processing and analytical queries.
- Support resumable execution and selective cycle reprocessing.
- Avoid duplicating raw tick datasets for each experiment.

### External Research Output

Produce exactly one consolidated research bundle per experiment.

Example:

```text
research/
  runs/
    run_001/
      research_bundle.zip
```

Temporary files and internal caches may exist separately but must not be necessary for reading the consolidated results.

## 2. Research Bundle Contract

```text
research_bundle.zip
│
├── manifest.json
├── summary.json
├── event_results.parquet
├── cycle_metrics.parquet
├── cohort_metrics.parquet
├── distributions.parquet
├── statistical_tests.json
├── data_quality.json
├── anomalies.json
└── report.md
```

### manifest.json

Include:
- Experiment ID
- Git commit and code version
- Research configuration
- Input dataset identifiers
- Requested and processed trading cycles
- Event definitions and outcome definitions
- Timezone and trading-session conventions
- Data schema versions
- File checksums and record counts
- Execution status and completion timestamp

### summary.json

Aggregate results across all processed cycles, including:
- Total universe candidates and qualified securities
- Total detected +10% events
- Price confirmation events
- Pullback events
- Continuation outcomes
- False spike outcomes
- False pullback outcomes
- MFE / MAE distributions
- Time-to-target and time-to-invalidation

Report metrics only where the corresponding research definitions have been implemented. Never fabricate values.

### event_results.parquet

Preserve EVERY detected research event, not just a statistical sample.

Include:
- Event ID
- Trading cycle
- Ticker and stable security identifier where available
- Session (AH/PRE/RTH)
- Event timestamp
- Previous RTH reference close
- Event price and applicable quote information
- Float and relevant point-in-time features
- Confirmation / Pullback classification
- Continuation outcome
- MFE / MAE
- Outcome horizon
- Data validity and censoring flags

Preserve event ordering and identifiers for future tick-level drilldown.

### cycle_metrics.parquet

One row per trading cycle and relevant research configuration, containing:
- Universe size
- Event counts
- Outcome rates
- Session-level results
- Coverage and completeness metrics

### cohort_metrics.parquet

Aggregate results by relevant dimensions:
- Session
- Float bucket
- Price bucket
- Relative volume
- Float turnover
- Time of day
- Confirmation / Pullback category

### distributions.parquet

Preserve distributions and quantiles, not only averages.

### statistical_tests.json

Include confidence intervals, sample sizes, statistical test specifications, and uncertainty estimates.

Account for repeated events from the same security and trading cycle when evaluating uncertainty.

### data_quality.json

Include:
- Missing cycles
- Missing tick intervals
- Invalid timestamps
- Missing quotes
- Unresolved historical float or exchange eligibility
- Duplicate or invalid events
- Replay failures
- Coverage by cycle and session

### anomalies.json

Identify suspicious statistical results, extreme events, and data-quality anomalies for targeted investigation.

### report.md

Provide an AI-readable consolidated research interpretation with metric definitions, findings, limitations, and references to the underlying tables.

## 3. Execution Pipeline

The automated workflow must be:

1. Load the configured historical universe.
2. Process all requested trading cycles.
3. Run tick-level event detection and replay.
4. Generate standardized event records and outcomes.
5. Validate event results and data coverage.
6. Aggregate metrics across all processed cycles.
7. Run statistical analyses.
8. Generate the consolidated research report.
9. Package all output artifacts into `research_bundle.zip`.
10. Validate bundle integrity, row counts, schemas, and checksums.

No manual daily aggregation.

## 4. Large Dataset Requirements

- Do not put raw tick data inside the research bundle.
- Do not silently sample or truncate event-level results.
- Use Parquet compression.
- Stream or batch aggregate datasets rather than loading everything into memory.
- Keep full research results locally if the bundle becomes too large.
- Report bundle size and record counts.
- If the bundle exceeds a configurable size budget, produce a compact analysis bundle and retain the complete event-level data locally, with explicit counts and access instructions. Never silently omit events.

## 5. Execution Reliability

- Each trading cycle must have a recorded processing status.
- Failed cycles must be retriable.
- Aggregation must not double-count retried cycles.
- Each experiment must use immutable configuration and reproducible run identifiers.
- Partial runs must be clearly labeled INCOMPLETE.
- A failed or incomplete run must never be reported as a complete 120-cycle experiment.

## 6. Research Integrity

The analytics layer must:

- Distinguish detected events from independently tradable opportunities.
- Avoid counting overlapping events as independent observations without appropriate treatment.
- Respect chronological ordering.
- Avoid look-ahead bias.
- Preserve unresolved and censored outcomes.
- Separate gross price-movement statistics from execution-adjusted trading performance.
- Avoid claiming statistical significance from insufficient or biased samples.

## 7. CLI

Provide a straightforward interface such as:

```bash
research run --cycles 120
research report --run-id run_001
research export --run-id run_001 --format bundle
```

These are target interface examples; implement them consistently with the existing project CLI architecture.

## 8. Acceptance Criteria

The system passes when:

1. A single command can process the configured cycles and aggregate all available results.
2. It produces ONE consolidated research bundle for the experiment.
3. Event-level records from every successfully processed cycle are included or explicitly retained externally according to the size policy.
4. Bundle metrics reconcile with underlying event records.
5. Missing and failed cycles are visible in the manifest.
6. Interrupted runs can resume without double-counting.
7. The bundle can be analyzed without accessing raw tick data.
8. Drilldown remains possible using event identifiers and locally stored source data.
9. Unit and integration tests validate aggregation and bundle integrity.

## Implementation Priority

The project is currently building TASK 001: Historical Universe Foundation.

Do not interrupt or replace that task.

Establish the results contract now, implement the minimal manifest and reporting foundation alongside TASK 001, and complete event-level aggregation functionality when the Tick Replay Engine and Event Classification modules exist.

Do not generate mock research findings and present them as real results.

The final architecture must support automated 120-cycle research with a single consolidated output bundle.

Respond in Thai.