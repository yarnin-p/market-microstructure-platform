# Holdout preregistration v1 — NOT AUTHORIZED / NOT EXECUTED

## Origin and scope

This research question was selected after viewing exploratory Full30 findings (26 upside-first, 62 downside-first, 5 neither at +3/-3). It is an exploratory-origin hypothesis, not a retrospectively preregistered exploration result. This document freezes its prospective evaluation before holdout access. No holdout outcomes have been used. Changes require a new explicit version and authorization before any holdout outcome access; no retuning after access.

Primary question: among first eligible +10% touch events in the historically exchange/price-eligible CS population, what are the design-weighted probabilities of downside-first and upside-first at +3%/-3%, within the observable risk window? Primary contrast is Delta = P(DOWNSIDE_FIRST) - P(UPSIDE_FIRST). The full exchange/price population combines both frozen sampling strata; the low-float proxy stratum is a secondary domain, not a claim of verified historical low float.

Exploration target is the fixed remaining70 exploration-date population, excluding Development10. Prospective holdout target is the fixed40 dates designated HOLDOUT in original M1 calendar. Neither inference targets future stationarity, continuous unobserved market paths or profitability.

## Eligibility and sampling (specification only)

Use historical M1 XNAS/XASE/XNYS, CS, 0<P0<=3, identity/currency/corporate-action gates and historical exchange information. P0 is previous RTH unadjusted provider daily close; independent official auction-close certification remains unavailable. Freeze identity mapping and current free_float evidence from original development context, as referenced by TASK004 selection, without refreshing current values. Range100K–15M defines PROXY_FLOAT_IN_RANGE; other otherwise-eligible securities including unresolved float remain OTHER_EXCHANGE_PRICE_ELIGIBLE. SEC remains independent, never forward filled or substituted for missing float.

Date sampling: census all40 designated holdout dates, inclusion probability1, no cherry picking. Security sampling: per date/stratum SRSWOR n=min(12,N), population sorted by security_id, SHA256-derived seed from [202611160050,cycle_id,stratum,"HOLDOUT_V1"], using a versioned deterministic sampler. Freeze complete frame, seed, selected identities and hashes before retrieving any tick outcomes. Preserve N,n,n/N and weightN/n; small strata use census, never replace failures. Planned ceiling960 opportunities. This document does not create the sample or authorize retrieval; acquisition requires a separately frozen resource budget and new user authorization.

## Event and observation window

Reuse OBSERVED_SESSIONS_FIRST / HIGH_LOW_ONLY / NO_MECHANICAL_GAP, +10% relative to fixed P0, SIP-clock ordering with deterministic sequence/exchange/trade-ID/hash ties, original correction reconstruction and vetoes. Primary event is one verified touch per security-cycle. Trigger price is observed print, not executable entry. Preserve raw first candidate, eligible touch, overshoot, conditions, size, source references and NBBO flags.

Barriers are exactly touch_price*1.03 and touch_price*0.97, checked on subsequent eligible trades. Opposite barriers in the same SIP timestamp are ambiguous, never arbitrarily ordered. Risk starts at the selected touch record, ends at cycle close or earlier unobserved overnight/unknown-quality/correction censoring. PRE to RTH is continuous observed-session progression; AH to PRE crosses an unobserved interval. Mechanical300/900-second gaps remain secondary sensitivities only. Preserve original freshness60s and all original censoring semantics. No-hit with adequate terminal evidence is NEITHER; stale terminal evidence is CENSORED. No crossing does not imply loss, zero return or executed stop.

For time-to-event terminology: NEITHER at administrative end is right-censored event time but a known fixed-window NEITHER category; observed upside/downside are competing events. Unknown path/corrections, incomplete coverage, ambiguous ties and stale endpoints remain explicitly distinct. Do not use Kaplan-Meier censoring-independence assumptions without evidence. No extrapolation across unobserved intervals.

## Numerators, denominators and unknown outcomes

For each sampled opportunity j, E_j indicates verified first touch; D_j and U_j indicate verified barrier category. Ratio estimates are sum(w D)/sum(w E), sum(w U)/sum(w E), and Delta=sum(w(D-U))/sum(w E). All initial events, including NEITHER/CENSORED/AMBIGUOUS, remain in E. Non-event opportunities have E=D=U=0 and remain in the sampling-design variance calculation. Category indicators of0 are not imputed returns or guessed outcomes. Always publish all category proportions and unknown fraction.

Full latent resolution is not identified for unknown categories C. Report sensitivity identification bounds Delta_minus=sum(w(D-U-C))/sum(w E) and Delta_plus=sum(w(D-U+C))/sum(w E). These are worst-case bounds, not assignments of individual wins/losses. Unknown event discovery from incomplete prior coverage cannot be repaired by these bounds: it forces INCONCLUSIVE.

## Estimator and uncertainty

Use domain-ratio Taylor linearization on all sampled opportunities, retaining zero-event rows. For each month h and sampled date i, residual r_ij=y_ij-theta*z_ij; date residual total T_i=sum_strata N_is*mean(r_is); within-date V_i=sum_strata N_is^2*(1-n_is/N_is)*s2(r_is)/n_is. Variance numerator is sum_h [M_h^2*(1-m_h/M_h)*s2(T_i)/m_h + (M_h/m_h)*sum_i V_i], divided by estimated denominator squared. For holdout date census first-stage variance is zero; within-date security sampling remains. Single-member census strata contribute zero sampling variance.

Repeated securities and serial outcomes are held fixed under this finite-population probability-sampling inference; random sampling occurs independently within date/security strata. This does not assume independent price events. Date/security crossed-cluster score sensitivity, month/date/session/float-domain contrasts and leave-one-security-out results must be reported separately. They do not establish process-level or future-period inference. Missingness is not cured by cluster corrections.

Candidate two-sided interval uses frozen t(.975,26)=2.055529438642871 times Taylor SE. It is an approximate design interval, not an exact guarantee. TASK005 known-population simulation evaluates regular, rare-domain, informative-censoring and holdout-census designs with repeated securities, serial date effects and unequal probabilities. Minimum simulated coverage floor0.93 at1000 replicates is a diagnostic, with Monte Carlo error reported; it is not proof of universal95% coverage. Rare-domain undercoverage must remain disclosed. Formal use requires adequate domain-size gates and successful relevant-scenario calibration; otherwise INCONCLUSIVE. Existing illustrative bootstrap percentiles are never relabeled formal95% CIs.

## Decision gates and criteria

Single directional primary claim: downside-first exceeds upside-first in this fixed observable-risk population. Delta=0 is a descriptive equality contrast, not a market-neutral50/50 fair-game model. Arithmetic symmetric barriers, conditioning on a +10% touch, microstructure, jumps and unequal censoring do not justify a fair-market null.

All mandatory gates: all40 selected dates processed; all selected opportunities have complete verified prior trade coverage; zero unresolved source/hash/identity/event-order discrepancies; frozen selection/config verified; at least60 verified initial events on at least20 event-bearing dates and30 securities; at least10 observed events in each barrier direction; weighted CENSORED/AMBIGUOUS fraction<=5%; relevant simulation calibration acceptable; no policy retuning. These are prespecified operational safeguards, not sample-size/power guarantees. Insufficient power/precision remains INCONCLUSIVE; no optional stopping or sample enlargement based on effect size.

SUPPORTED only if every gate passes and the lower candidate95% design limit for Delta_minus is strictly>0. UNSUPPORTED for the directional claim only if every gate passes and the upper candidate95% design limit for Delta_plus is<=0. Otherwise INCONCLUSIVE. All secondary results descriptive; no multiplicity-adjusted or causal claims are implied. A supported category imbalance would not establish executable short profits or a trading recommendation.

## Secondary estimands and fairness

Preserve forward5/15/30/60m/session/cycle returns with valid observed denominators, MFE/MAE, +5/-3 and+10/-5, odd-lot and gap sensitivities, float-stratum association, and all original C0/C1 counted/observed/session-bound/D60/C2 policies. Use the common initial risk set and common exit clocks. Retain unconfirmed, insufficient, not-yet-confirmed, censored and unmatched cases explicitly. C2's nine Full30 confirmations are underpowered exploratory evidence; do not drop missing C2 cases or claim causal improvements.

## API failures, audit and execution authorization

No new requests in TASK005. A later authorized holdout run must freeze budgets and full membership first, use bounded acquisition with complete pagination or explicit incomplete windows, preserve zero-event and missing cases, record hashes and errors, and never substitute another security/date. Retry only predeclared transient failures within the same budget, without viewing outcome favorability. Failure of complete discovery coverage forces INCONCLUSIVE. Raw evidence stays local; version code/config/compact reports. Never overwrite exploration, M1 or SEC evidence.

Readiness of this protocol is CONDITIONAL until TASK005 audit/calibration findings are reviewed and any blockers resolved before access. Separate user authorization remains mandatory even if technical checks pass. No holdout execution is authorized by this document.

Method reference: Aubry (2024), two-stage SRSWOR and Woodruff ratio linearization: https://pmc.ncbi.nlm.nih.gov/articles/PMC11404174/ . This source supports estimator structure; TASK005 simulation is our own synthetic validation, not a coverage guarantee from that paper.
