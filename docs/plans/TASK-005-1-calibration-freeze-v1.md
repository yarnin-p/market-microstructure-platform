# TASK 005.1 — Offline calibration freeze v1

Baseline `2a1c6a5`, branch `feat/task-005-1-calibration-repair`. No new market requests, no holdout outcomes or market parameter changes. Existing evidence, including the 91.5% rare-domain failure, is read-only.

## Development and independent validation boundary

Original diagnostic suite exactly reproduces TASK005 population RNG and sample RNG: four populations, seed202611160005+scenario_index, 1000 repetitions each. This is development evidence, never independent validation. The implementation calculates design-total covariance, random-denominator RSE, event counts and zero-event dates/strata, boundary estimates, ratio skewness, plug-in variance versus empirical variance and residual variance evaluated at the known truth. It then compares the original Wald/t interval to Fieller score inversion and a Bonferroni projection of marginal total intervals.

Independent suite is frozen in `configs/task-005-1-calibration-v1.json` before its first execution: two new populations per original scenario family plus four rare-event stresses, 1000 repetitions each. Seeds, rates, frames, sample sizes, methods, critical values and decision rules are fixed. No replacement seeds, omitted failures, post-validation method selection or retuning. Runner writes start markers and refuses to repeat a stage under the same ID. `freeze.json` binds config and implementation hashes before either simulation stage.

Primary candidate is **FIELLER_SCORE**, selected on mathematical grounds before independent validation. It keeps the existing t(.975,26) critical2.055529438642871. It inverts the estimated design-total contrast test as a function of candidate theta instead of freezing the ratio residual variance at theta_hat. This is a design-based asymptotic approximation; exact bivariate-normal Fieller coverage is not asserted for a two-stage finite sample.

Secondary candidate is **BONFERRONI_TOTAL_BOX**: marginal total intervals at t(.9875,26), projecting the resulting simultaneous rectangle into Y/Z when denominator lower bound>0; otherwise the entire physical parameter space. This alpha allocation follows the union bound and is not calibrated by choosing larger critical values on successful seeds. It is approximate because the marginal design t intervals themselves are approximate. It cannot be substituted as the primary because independent results look better.

Two-stage covariance uses month/date SRSWOR and independently sampled security strata with both FPCs. All zero-event opportunities enter the covariance. The implemented formula is independently tested against exact enumeration of an unequal-weight finite population. Repeated securities and AR(1) dates are held fixed in each synthetic population; no IID event bootstrap or future-process inference.

## All-repetition reporting and clearance

For each method and scenario report unconditional coverage over all1000 repetitions, binomial Monte Carlo SE and Wilson95% bounds, width mean/median, raw unbounded/disconnected sets, empty domains and invalid sets, bias and variance, and sufficient-information frequency. Physical theta space is[-1,1]. EMPTY_DOMAIN retains point estimate null and a vacuous[-1,1] uncertainty set; it never becomes zero or a usable estimate. Disconnected/unbounded sets remain INSUFFICIENT_INFORMATION for decisions. No excluded repetitions. Conditional-on-informative coverage is diagnostic only and must never replace unconditional coverage.

Primary must reach the frozen >=93% coverage floor in every original and independent case. Failed cases force BLOCKED; no choosing only the successful family. Passing simulations at best gives CONDITIONAL synthetic statistical clearance: real information, coverage-integrity and calibration-transfer limitations remain. Empty/unbounded/disconnected cases and failed sample-size requirements are INCONCLUSIVE. Existing holdout thresholds (>=60 events, >=20 event dates, >=30 securities, >=10 each direction, unknown weighted fraction<=5%, complete prior coverage) are retained; simulation does not turn them into power guarantees.

Unknown latent-outcome identification bounds are separate from intervals for the observable category contrast. Informative missingness may change the observable target even with well-calibrated intervals; no imputation or altered estimand. No assumed market-neutral50/50 model.

Only if the prespecified primary is defensible and meets every calibration gate may a prospective protocol v3 amendment be adopted, preserving v2 unchanged. Otherwise report the failure and retain the blocker. Holdout sampling/acquisition still needs new authorization and a separately frozen budget even if calibration passes.

## Mathematical references

- [von Luxburg and Franz, 2009](https://arxiv.org/abs/0711.0198): confidence sets from inversion of linear contrasts; unbounded sets are meaningful denominator uncertainty.
- [NIST ratio-of-means documentation](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/ratimean.htm): Fieller algebra and denominator precision. Its IID variance formula is **not** used here.
- [Aubry, 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11404174/): two-stage stratified SRSWOR total/ratio variance structure. Our calibration, information gates and approximation limits are separate.
