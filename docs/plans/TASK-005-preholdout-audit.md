# TASK 005 — Offline pre-holdout audit

Baseline 1c02e67; source Full30 m4-temporal-cumulative30-20261116-v1. This is authorization for an offline audit only. No market data request, holdout tick access, parameter retuning, M1/SEC mutation or new confirmation model.

Audit all 93 primary events from cached raw JSON, independently implementing condition eligibility, correction reconstruction, SIP/sequence tie ordering, touch detection, chronological barriers and forward-mark censoring. Preserve source hashes and compare all three barriers and gap policies against frozen outputs. Verify all 720 trade-window pagination chains and stored analytical weights before inspecting paths. Complete pagination is a provider-window claim, not proof of continuous exchange/feed coverage.

Limits: 93 events; 8GiB raw reads (including repeated verification), 1M rows per window, 512MiB additional artifacts, 3600 seconds. Block network calls in the audit process. Existing raw data and every previous run remain unchanged. Exceptions and resource stops produce explicit partial/BLOCKED evidence; never imply a complete audit from representative examples.

Statistical primary question is exploratory-origin: downside-first minus upside-first probability at +3/-3, with all initial eligible events in the denominator. Neither and unknown categories remain separate. Evaluate a domain-ratio Taylor estimator using all 720 sampled opportunities and month/date/security SRSWOR fractions; zero-event domain contributions are retained. Simulation uses four known finite populations, 1000 draws each, fixed seed, repeated security effects, serial date effects, unequal populations, rare-event and informative-missingness scenarios. Candidate t(26) intervals are evaluated for calibration, not declared formal market CIs. No 50/50 market-neutral benchmark.

Secondary estimands and C0/C1/C2 rules remain frozen. Holdout execution is prohibited without new authorization and a separate budget/sample freeze. Holdout protocol must document identification bounds, incomplete coverage, calibration and decision gates before any holdout result is read.
