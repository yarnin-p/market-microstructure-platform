import itertools
import math

import numpy as np
import pytest

from market_lab.audit_statistics import ratio
from market_lab.calibration_repair import population, draw, original_specs
from market_lab.ratio_calibration import (BOX_CRITICAL, CRITICAL, confidence_sets, contains,
                                         quadratic_set, student_t_quantile, totals_covariance)


def test_score_set_matches_candidatewise_quadratic_without_grid_approximation():
    for a, b, c in [(1, 0, -.25), (-1, 0, .25), (0, 1, -.2), (0, 0, 1), (0, 0, 0), (1, 2, 1)]:
        result = quadratic_set(a, b, c)
        for x in np.linspace(-1, 1, 1001):
            assert contains(result, x) == (a*x*x+b*x+c <= 1e-14)
    assert quadratic_set(-1, 0, .25)['components'] == [[-1., -.5], [.5, 1.]]
    assert quadratic_set(1, 2, 1)['components'] == [[-1., -1.]]


def test_fieller_preserves_nonconnected_unbounded_geometry():
    m = {'Y': 2., 'Z': 1., 'cov': [[1., 0.], [0., 4.]]}
    result = confidence_sets(m, 1.)['FIELLER_SCORE']
    assert result['status'] == 'INSUFFICIENT_INFORMATION'
    assert result['raw_geometry'] == 'DISJOINT_UNBOUNDED'
    assert result['raw_unbounded']


def test_empty_domain_and_uncertain_denominator_cannot_produce_zero_estimate():
    m = {'Y': 0., 'Z': 0., 'cov': [[0., 0.], [0., 0.]]}
    for result in confidence_sets(m).values():
        assert result['status'] == 'EMPTY_DOMAIN'
        assert result['point_estimate'] is None
        assert result['components'] == [[-1., 1.]] and not result['informative']
    m = {'Y': .5, 'Z': 1., 'cov': [[1., 0.], [0., 4.]]}
    assert confidence_sets(m)['BONFERRONI_TOTAL_BOX']['status'] == 'INSUFFICIENT_INFORMATION'


def test_bonferroni_critical_comes_from_predeclared_alpha_allocation():
    assert student_t_quantile(.975, 26) == pytest.approx(CRITICAL, abs=1e-10)
    assert student_t_quantile(.975, 1) == pytest.approx(1/math.tan(math.pi*.025), rel=1e-8)
    assert BOX_CRITICAL == student_t_quantile(1-.05/4, 26)


def test_known_census_returns_exact_ratio_and_zero_width():
    groups = [{'month': 'm', 'cycle_id': 'd', 'N': 4, 'y': [1, -1, 0, 0], 'z': [1, 1, 0, 0]}]
    m = totals_covariance(groups, {'m': 1})
    assert np.array_equal(m['cov'], np.zeros((2, 2)))
    for r in confidence_sets(m).values():
        assert r['components'] == [[0., 0.]] and r['width'] == 0


def test_covariance_uses_all_zero_opportunities_and_matches_original_linearization():
    groups = [{'month': 'm', 'cycle_id': str(i), 'N': 10+i,
               'y': [1, -1, 0, 0], 'z': [1, 1, 0, 0]} for i in range(3)]
    m = totals_covariance(groups, {'m': 5})
    old = ratio(groups, {'m': 5})
    wald = confidence_sets(m)['WALD_T']
    assert m['Y']/m['Z'] == old['estimate']
    assert wald['width']/(2*CRITICAL) == pytest.approx(old['se'])
    assert m['events'] == 6
    with pytest.raises(ValueError, match='Missing'): totals_covariance(groups, {'m': 5, 'x': 2})
    with pytest.raises(ValueError, match='date sampling'): totals_covariance(groups[:1], {'m': 5})


def test_exact_enumeration_two_stage_unequal_weights_fpc_covariance_unbiased():
    # Every date SRS and every within-date SRS is enumerated; no Monte Carlo claim.
    yy = [[-1, 0, 1], [1, 1, 0, -1], [0, 1, 0]]
    zz = [[1, 0, 1], [1, 1, 1, 1], [0, 1, 0]]
    estimates, covariances, weights = [], [], []
    for dates in itertools.combinations(range(3), 2):
        choices = [list(itertools.combinations(range(len(yy[d])), 2)) for d in dates]
        for indices in itertools.product(*choices):
            groups = [{'month': 'm', 'cycle_id': str(d), 'N': len(yy[d]),
                       'y': [yy[d][j] for j in ix], 'z': [zz[d][j] for j in ix]}
                      for d, ix in zip(dates, indices)]
            m = totals_covariance(groups, {'m': 3})
            estimates.append([m['Y'], m['Z']]); covariances.append(m['cov'])
            weights.append(1/3/len(choices[0])/len(choices[1]))
    x, w = np.array(estimates), np.array(weights)
    mean = w@x
    assert mean == pytest.approx([sum(map(sum, yy)), sum(map(sum, zz))])
    actual = (x-mean).T@(w[:, None]*(x-mean))
    assert np.tensordot(w, covariances, axes=1) == pytest.approx(actual, abs=1e-12)


def test_frozen_original_population_and_sample_rng_reproducible():
    spec = original_specs({'original_seed': 202611160005})[1]
    a, pa, M, m, ta = population(spec)
    b, pb, _, _, tb = population(spec)
    assert ta == tb
    ga, ca = draw(a, pa, m, 12)
    gb, cb = draw(b, pb, m, 12)
    assert ca == cb
    ma = totals_covariance(ga, {str(i): v for i, v in enumerate(M)})
    mb = totals_covariance(gb, {str(i): v for i, v in enumerate(M)})
    assert ma == mb
