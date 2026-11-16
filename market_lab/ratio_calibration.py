"""Design-total covariance and bounded-parameter confidence-set inversion.

The Fieller set inverts (Y-theta Z)^2 <= c^2 V(Y-theta Z) rather
than freezing the residual variance at the estimated ratio. This is a design
normal/t approximation, NOT exact Fieller inference for this finite population.
All opportunities, including zero domain indicators, enter design covariance.
"""
import math
from collections import defaultdict
from statistics import NormalDist

import numpy as np

CRITICAL = 2.055529438642871


def student_t_quantile(p, df):
    """Deterministic Simpson integration/bisection; no optional SciPy dependency."""
    if not .5 < p < 1 or df <= 0:
        raise ValueError('Unsupported quantile')
    scale = math.exp(math.lgamma((df+1)/2)-math.lgamma(df/2))/math.sqrt(df*math.pi)
    def cdf(x):
        grid = np.linspace(0., x, 4097)
        f = scale*(1+grid*grid/df)**(-(df+1)/2)
        return .5+x/4096/3*(f[0]+f[-1]+4*f[1:-1:2].sum()+2*f[2:-1:2].sum())
    lo, hi = 0., 1.
    while cdf(hi) < p:
        hi *= 2
        if hi > 1024:
            raise ValueError('Quantile outside numerical budget')
    for _ in range(48):
        mid = (lo+hi)/2
        if cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


BOX_CRITICAL = student_t_quantile(.9875, 26)  # two totals, Bonferroni alpha/2 each


def totals_covariance(groups, date_population):
    """Unbiased SRSWOR total covariance for the frozen two-stage design.

    Within date: independently sampled security strata. Across dates: month
    stratification, date SRSWOR. Both finite-population corrections retained.
    Repeated security/date outcomes are fixed, not assumed IID random events.
    """
    grouped = defaultdict(lambda: defaultdict(list))
    for i, g in enumerate(groups):
        grouped[g['month']][g.get('cycle_id', str(i))].append(g)
    if set(grouped) != set(date_population):
        raise ValueError('Missing or unexpected month stratum')
    total = np.zeros(2)
    first = np.zeros((2, 2))
    second = np.zeros((2, 2))
    nevents = 0
    zero_dates = zero_strata = 0
    for h, dates in grouped.items():
        m, M = len(dates), date_population[h]
        if not 1 <= m <= M or (m == 1 and m < M):
            raise ValueError('INSUFFICIENT_INFORMATION: date sampling variance unavailable')
        ts, vs = [], []
        for strata in dates.values():
            T = np.zeros(2)
            V = np.zeros((2, 2))
            date_count = 0
            for g in strata:
                y, z = np.asarray(g['y'], float), np.asarray(g['z'], float)
                n, N = len(y), g['N']
                if n != len(z) or not 1 <= n <= N or (n == 1 and n < N):
                    raise ValueError('INSUFFICIENT_INFORMATION: invalid security stratum')
                if not np.isfinite(y).all() or not np.isfinite(z).all():
                    raise ValueError('Nonfinite data')
                if np.any((z != 0) & (z != 1)) or np.any(np.abs(y) > z):
                    raise ValueError('Domain contrast requires binary z and |y| <= z')
                x = np.column_stack((y, z))
                T += N*x.mean(axis=0)
                if n < N:
                    centered = x-x.mean(axis=0)
                    V += N*N*(1-n/N)*(centered.T@centered)/(n*(n-1))
                count = int(z.sum())
                nevents += count
                date_count += count
                zero_strata += count == 0
            zero_dates += date_count == 0
            ts.append(T)
            vs.append(V)
        ts = np.array(ts)
        total += M/m*ts.sum(axis=0)
        if m < M:
            centered = ts-ts.mean(axis=0)
            first += M*M*(1-m/M)*(centered.T@centered)/(m*(m-1))
        second += M/m*np.sum(vs, axis=0)
    cov = first+second
    return {'Y': float(total[0]), 'Z': float(total[1]), 'cov': cov.tolist(),
            'first_stage': first.tolist(), 'second_stage': second.tolist(),
            'events': nevents, 'zero_event_dates': zero_dates, 'zero_event_strata': zero_strata}


def quadratic_set(a, b, c, domain=(-1., 1.)):
    """Solve a*x^2+b*x+c <= 0, retaining disconnected and unbounded geometry.

    Returns exact component endpoints inside the physical parameter space;
    never substitutes a hull for disconnected sets in a decision rule.
    """
    scale = max(abs(a), abs(b), abs(c))
    if not math.isfinite(scale):
        raise ValueError('Nonfinite quadratic')
    if scale:
        a, b, c = a/scale, b/scale, c/scale
    tol = 1e-12
    if abs(a) <= tol:
        if abs(b) <= tol:
            raw, shape = ([(-math.inf, math.inf)], 'ALL_REAL') if c <= tol else ([], 'EMPTY')
        else:
            root = -c/b
            raw = [(-math.inf, root)] if b > 0 else [(root, math.inf)]
            shape = 'HALF_LINE'
    else:
        disc = b*b-4*a*c
        if disc < -tol:
            raw, shape = ([(-math.inf, math.inf)], 'ALL_REAL') if a < 0 else ([], 'EMPTY')
        else:
            disc = max(0., disc)
            q = -.5*(b+math.copysign(math.sqrt(disc), b))
            roots = sorted((q/a, c/q)) if q else [0., 0.]
            lo, hi = roots
            raw, shape = ([(lo, hi)], 'BOUNDED') if a > 0 else ([(-math.inf, lo), (hi, math.inf)], 'DISJOINT_UNBOUNDED')
            if a < 0 and disc == 0:
                raw, shape = [(-math.inf, math.inf)], 'ALL_REAL'
    components = [[max(l, domain[0]), min(u, domain[1])] for l, u in raw
                  if max(l, domain[0]) <= min(u, domain[1])]
    return {'components': components, 'raw_geometry': shape,
            'raw_unbounded': any(not math.isfinite(l) or not math.isfinite(u) for l, u in raw),
            'width': sum(u-l for l, u in components)}


def confidence_sets(m, critical=CRITICAL):
    Y, Z = m['Y'], m['Z']
    vyy, vyz = m['cov'][0]
    vzz = m['cov'][1][1]
    if min(vyy, vzz) < -1e-8 or vyz*vyz > vyy*vzz+1e-8*max(1., vyy*vzz):
        raise ValueError('Invalid covariance')
    if Z <= 0:
        empty = dict(status='EMPTY_DOMAIN', components=[[-1., 1.]], width=2., raw_unbounded=True,
                     raw_geometry='ALL_REAL', point_estimate=None, informative=False)
        return {name: dict(empty) for name in ['WALD_T', 'FIELLER_SCORE', 'BONFERRONI_TOTAL_BOX']}
    estimate = Y/Z
    variance = max(0., vyy-2*estimate*vyz+estimate*estimate*vzz)/(Z*Z)
    half = critical*math.sqrt(variance)
    # Baseline raw Wald coverage/width deliberately remains untruncated.
    wald = dict(status='BOUNDED', components=[[estimate-half, estimate+half]], width=2*half,
                raw_unbounded=False, raw_geometry='BOUNDED', point_estimate=estimate, informative=True)
    c2 = critical*critical
    fieller = quadratic_set(Z*Z-c2*vzz, -2*(Y*Z-c2*vyz), Y*Y-c2*vyy)
    fieller['status'] = ('INSUFFICIENT_INFORMATION' if fieller['raw_unbounded'] else
                         'EMPTY_CONFIDENCE_SET' if not fieller['components'] else 'BOUNDED')
    # Simultaneous marginal total intervals, not an IID event bootstrap.
    zy = BOX_CRITICAL*math.sqrt(max(0., vyy))
    zz = BOX_CRITICAL*math.sqrt(max(0., vzz))
    if Z-zz <= 0:
        box = dict(components=[[-1., 1.]], width=2., raw_unbounded=True,
                   raw_geometry='DENOMINATOR_INTERVAL_INCLUDES_ZERO', status='INSUFFICIENT_INFORMATION')
    else:
        corners = [(Y+s*zy)/(Z+t*zz) for s in [-1, 1] for t in [-1, 1]]
        low, high = max(-1., min(corners)), min(1., max(corners))
        box = dict(components=[[low, high]] if low <= high else [], width=max(0., high-low),
                   raw_unbounded=False, raw_geometry='BOUNDED', status='BOUNDED' if low <= high else 'EMPTY_CONFIDENCE_SET')
    for result in [fieller, box]:
        result['point_estimate'] = estimate
        result['informative'] = result['status'] == 'BOUNDED' and result['width'] < 2
    return {'WALD_T': wald, 'FIELLER_SCORE': fieller, 'BONFERRONI_TOTAL_BOX': box}


def contains(result, truth):
    return any(lo <= truth <= hi for lo, hi in result['components'])


def wilson(hits, n):
    z = NormalDist().inv_cdf(.975)
    p = hits/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [center-half, center+half]
