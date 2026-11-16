# Development diagnosis — frozen before independent validation

Original TASK005 Wald failure reproduced exactly: regular94.9%, rare_domain91.5%, informative_missing96.6%, synthetic holdout-census95.2%. The original files remain unchanged.

Rare-domain evidence: mean17.826 observed events per720 sampled opportunities (range7–32); mean17.112/30 dates and44.928/60 date/security strata have zero domain events. Estimated domain-denominator RSE mean24.866%, versus12.077% in regular. This is an estimated random domain total, not a known count.

Observed ratio variance0.0563817 versus mean plug-in variance0.0481273 (ratio0.85360). Bias−0.00809; skewness−0.09263. Only1/1000 estimates is at a physical boundary. Thus strong skew or boundary saturation is not established as the principal original failure. Residual-total variance evaluated at the known true ratio averages2187.20 versus empirical2326.41; covariance is exactly unbiased on controlled enumeration but finite Monte Carlo variability and the nonlinear ratio plug-in need not agree with empirical variance. These comparisons do not uniquely identify a causal decomposition.

The unchanged critical2.055529438642871 yields Fieller score-inversion coverage95.5% (955/1000), versus Wald91.5% (915/1000). Mean physical-set width increases from0.88619 to1.03895; median from0.87387 to1.01111. Fieller has1 raw unbounded set; it is retained as insufficient information, never forced finite. This development comparison supports testing score inversion, not a claim of independent success.

The two-stage estimator retains unequal inclusion weights, both FPCs and date/security stratification. Exact enumeration verifies design-total covariance. Shared security effects and serial date effects are fixed population attributes, not IID events. A frozen t26 is an approximation, not a justified exact sparse-domain pivot; normal-critical and known-truth residual sensitivity will be reported as diagnostics. Increasing the critical is not the proposed repair.

Prespecified primary remains FIELLER_SCORE. BONFERRONI_TOTAL_BOX is wider and secondary. No method, seed, frame, event rate or criterion is changed after these development results. The twelve separately frozen independent populations are now eligible for one-shot synthetic validation; no market holdout is involved.
