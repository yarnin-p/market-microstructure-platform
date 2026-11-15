# M2 first-touch pilot

{
  "run_id": "m2-first-touch-3cycles-20261115-v1",
  "cycles": [
    "2026-05-27",
    "2026-05-28",
    "2026-05-29"
  ],
  "selected_securities": 16,
  "security_cycle_opportunities": 48,
  "window_status_counts": {
    "PROCESSED": 42,
    "INCOMPLETE": 3,
    "HISTORICAL_QUALITY_EXCLUDED": 3
  },
  "events": 20,
  "verified_first_touches": 2,
  "observed_window_first_verified": 17,
  "session_counts": {
    "RTH": 9,
    "PRE": 8,
    "AH": 3
  },
  "sample_cohort_counts": [
    {
      "sample": "SYSTEMATIC",
      "cohort": "EXCHANGE_PRICE_ONLY",
      "opportunities": 29,
      "events": 7,
      "complete_windows": 29,
      "verified_first_touches": 0,
      "zero_event_observed": 22,
      "session_counts_json": "{\"RTH\": 5, \"PRE\": 2}"
    },
    {
      "sample": "SYSTEMATIC",
      "cohort": "MASSIVE_CURRENT_FLOAT_PROXY",
      "opportunities": 11,
      "events": 3,
      "complete_windows": 11,
      "verified_first_touches": 0,
      "zero_event_observed": 8,
      "session_counts_json": "{\"RTH\": 2, \"PRE\": 1}"
    },
    {
      "sample": "DIAGNOSTIC",
      "cohort": "EXCHANGE_PRICE_ONLY",
      "opportunities": 16,
      "events": 13,
      "complete_windows": 13,
      "verified_first_touches": 2,
      "zero_event_observed": 3,
      "session_counts_json": "{\"PRE\": 6, \"AH\": 3, \"RTH\": 4}"
    },
    {
      "sample": "DIAGNOSTIC",
      "cohort": "MASSIVE_CURRENT_FLOAT_PROXY",
      "opportunities": 4,
      "events": 4,
      "complete_windows": 2,
      "verified_first_touches": 0,
      "zero_event_observed": 0,
      "session_counts_json": "{\"PRE\": 2, \"RTH\": 2}"
    }
  ],
  "float_proxy_status_counts": {
    "INELIGIBLE": 8,
    "ELIGIBLE": 6,
    "UNRESOLVED": 2
  },
  "sec_overlap_events": 4,
  "requests": 150,
  "pages": 148,
  "decoded_bytes": 715846178,
  "api_errors": 2,
  "statistics_scope": "FULL_PILOT_SAMPLE_NOT_FULL_UNIVERSE",
  "statuses": {
    "ENGINEERING_VALIDATED": false,
    "DATA_COVERAGE_VALIDATED": false,
    "PILOT_RESULTS_AVAILABLE": true,
    "RESEARCH_STATISTICALLY_VALIDATED": false
  }
}

## Interpretation limits

Current float is a retrospective proxy, never verified PIT. Survivorship, dilution, splits and float changes can misclassify past eligibility. Diagnostic selection uses first-day high; it cannot estimate population probabilities. Systematic selection is seeded from the first-cycle historical frame, with later-cycle gates reapplied. Zero events mean no eligible crossing in observed sessions, not proof of no overnight trading.

SIP observation clock; all returns are gross observed-price changes, not executable fills. Marks use the last eligible trade at or before the wall-clock horizon, maximum age 60 seconds. Long intertrade gaps (>300 seconds), overnight intervals, missing pages and touch invalidation censor outcomes. MFE/MAE retain observed extrema even when censored. Barrier ties at identical SIP timestamps are ambiguous. Conditions, correction reconstruction and thresholds are versioned in configs.

Quotes cover only ±60 seconds around events. No complete halt feed or overnight coverage is claimed. Historical P0 and quality gates are inherited from M1, including its retrospective reference-data limitations. SEC context is independent and never forward-filled. Confidence intervals and significance tests are not estimated for this tiny clustered pilot.

## Reproduction

Use `python -m market_lab.m2_pilot validate --run-id m2-first-touch-3cycles-20261115-v1` and `query --run-id m2-first-touch-3cycles-20261115-v1 --ticker SYMBOL`. Full data remain in local `data/runs/m2-first-touch-3cycles-20261115-v1`. Selection, policies, source hashes, execution code hashes and request accounting are preserved. Three source-linked examples (or all if fewer) are in audit_examples.json.

## Executed validation

{
  "status": "PASS",
  "events_replayed": 20,
  "raw_pages_hash_checked": 148,
  "m1_unchanged": true,
  "raw_event_price_and_quote_checks": 20,
  "tests": "........................................................................ [ 53%]\n...............................................................          [100%]\n=============================== warnings summary ===============================\ntests/test_bundle.py: 12 warnings\ntests/test_m1_integrity.py: 28 warnings\ntests/test_universe.py: 44 warnings\n  /Users/yarnin/Documents/yarnin-p/market-microstructure-platform/.venv/lib/python3.13/site-packages/pandas/core/series.py:848: Pandas4Warning: Series.values returning an ndarray that drops timezone information for DatetimeTZDtype is deprecated. In a future version, this will return the underlying DatetimeArray instead. Use 'Series.dt.tz_convert(None).to_numpy()' to get a NumPy array of UTC values, or 'Series.array' to get the ExtensionArray.\n  See https://pandas.pydata.org/docs/dev/whatsnew/v3.1.0.html#whatsnew-310-deprecations-values for more details.\n    warnings.warn(\n\n-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html\n135 passed, 84 warnings in 2.35s\n",
  "code_hashes_match": true
}
