# TASK 004 — Temporal expansion

{
  "run_id": "m4-temporal-10cycles-20261115-v1",
  "planned_dates": 30,
  "batch_dates": 10,
  "cycles": [
    {
      "cycle_id": "2026-06-18",
      "month": "2026-06",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 6,
      "verified_events": 6,
      "zero_events": 18,
      "sessions": {
        "RTH": 4,
        "PRE": 1,
        "AH": 1
      }
    },
    {
      "cycle_id": "2026-07-16",
      "month": "2026-07",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 2,
      "verified_events": 2,
      "zero_events": 22,
      "sessions": {
        "AH": 2
      }
    },
    {
      "cycle_id": "2026-08-06",
      "month": "2026-08",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 4,
      "verified_events": 4,
      "zero_events": 20,
      "sessions": {
        "PRE": 2,
        "AH": 2
      }
    },
    {
      "cycle_id": "2026-09-02",
      "month": "2026-09",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 2,
      "verified_events": 2,
      "zero_events": 22,
      "sessions": {
        "PRE": 1,
        "RTH": 1
      }
    },
    {
      "cycle_id": "2026-06-26",
      "month": "2026-06",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 4,
      "verified_events": 4,
      "zero_events": 20,
      "sessions": {
        "RTH": 2,
        "AH": 1,
        "PRE": 1
      }
    },
    {
      "cycle_id": "2026-07-17",
      "month": "2026-07",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 2,
      "verified_events": 2,
      "zero_events": 22,
      "sessions": {
        "PRE": 2
      }
    },
    {
      "cycle_id": "2026-08-18",
      "month": "2026-08",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 2,
      "verified_events": 2,
      "zero_events": 22,
      "sessions": {
        "RTH": 1,
        "PRE": 1
      }
    },
    {
      "cycle_id": "2026-09-17",
      "month": "2026-09",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 3,
      "verified_events": 3,
      "zero_events": 21,
      "sessions": {
        "AH": 1,
        "RTH": 2
      }
    },
    {
      "cycle_id": "2026-07-15",
      "month": "2026-07",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 2,
      "verified_events": 2,
      "zero_events": 22,
      "sessions": {
        "RTH": 2
      }
    },
    {
      "cycle_id": "2026-08-25",
      "month": "2026-08",
      "selected": 24,
      "complete": 24,
      "verified_risk_set": 24,
      "events": 4,
      "verified_events": 4,
      "zero_events": 20,
      "sessions": {
        "RTH": 2,
        "PRE": 2
      }
    }
  ],
  "selected_opportunities": 240,
  "complete_trade_windows": 240,
  "primary_events": 31,
  "verified_primary_events": 31,
  "zero_event_opportunities": 209,
  "unknown_opportunities": 0,
  "session_events": {
    "AH": 7,
    "RTH": 14,
    "PRE": 10
  },
  "unverified_opportunities_including_unknown_prior_evidence": 0,
  "confirmation_initial_risk_set": 31,
  "analyzed_confirmation_initial_events": 31,
  "acquisition": {
    "completed_checkpoints": 240,
    "deadline_epoch": 1794751687.06235,
    "http_requests": 333,
    "network_phase_closed": true,
    "quote_windows": 66,
    "stop_reason": null
  },
  "analysis": {
    "confirmation_rows": 496,
    "elapsed_seconds": 84.46940204198472,
    "stop_reason": null
  },
  "ledger": {
    "deadline_epoch": 1794751687.06235,
    "decoded_bytes": 547780770,
    "pages": 333,
    "started_epoch": 1794749887.06235
  },
  "http_requests": 333,
  "http_errors": 0,
  "development_separate": {
    "run_id": "m2-systematic-10cycles-20261115-v2",
    "opportunities": 240,
    "events": 40,
    "sessions": {
      "AH": 9,
      "PRE": 10,
      "RTH": 21
    },
    "date_sampling": "Original consecutive ten development dates; not pooled as validation"
  },
  "holdout_analyzed": false,
  "executable_profitability": "NOT_ASSESSED",
  "strict_full_cycle_first": "UNVERIFIED_OVERNIGHT"
}

No profitability, significance or full-cycle coverage claim. Development dates remain separate. All frozen date/security weights, missing opportunities and censored policy outcomes are retained.
