from copy import deepcopy
from market_lab.calibration_decision import clearance, information_status


def fixture():
    cfg = {'original_scenarios': ['original'], 'independent': [{'name': 'stress'}],
           'primary_candidate': 'FIELLER_SCORE', 'replicates': 1000, 'coverage_floor': .93}
    def row(name, p):
        return {'specification': {'name': name}, 'methods': {
            'FIELLER_SCORE': {'coverage': p, 'replicates': 1000},
            'BONFERRONI_TOTAL_BOX': {'coverage': 1., 'replicates': 1000}}}
    return cfg, {'reports': [row('original', .955)]}, {'reports': [row('stress', .834)]}


def test_failed_stress_cannot_be_waived_or_replaced_by_successful_box():
    cfg, dev, val = fixture()
    r = clearance(cfg, dev, val, {'status': 'PASS'})
    assert r['statistical_clearance'] == 'BLOCKED'
    assert not r['method_substitution_from_secondary'] and not r['protocol_v3_adopted']
    assert not r['holdout_authorized']
    val['reports'] = []
    assert clearance(cfg, dev, val, {'status': 'PASS'})['statistical_clearance'] == 'BLOCKED'


def test_synthetic_success_is_conditional_and_never_holdout_authorization():
    cfg, dev, val = fixture()
    val['reports'][0]['methods']['FIELLER_SCORE']['coverage'] = .95
    r = clearance(cfg, dev, val, {'status': 'PASS'})
    assert r['statistical_clearance'] == 'CONDITIONAL' and not r['holdout_authorized']
    assert clearance(cfg, dev, val, {'status': 'FAIL'})['statistical_clearance'] == 'BLOCKED'


def test_boundary_single_direction_is_inconclusive_even_if_raw_set_bounded():
    result = {'status': 'BOUNDED', 'informative': True, 'components': [[1., 1.]]}
    gate = {'events': 60, 'event_dates': 20, 'securities': 30, 'each_direction': 10, 'unknown_weight_fraction': .05}
    counts = {'events': 100, 'event_dates': 30, 'securities': 90, 'down': 100, 'up': 0}
    r = information_status(result, counts, gate, 0.)
    assert r['status'] == 'INCONCLUSIVE' and 'each_direction' in r['failed_information_gates']
    counts['up'] = 10
    assert information_status(result, counts, gate, .06)['status'] == 'INCONCLUSIVE'
    result['status'] = 'INSUFFICIENT_INFORMATION'
    assert information_status(result, counts, gate, 0.)['status'] == 'INCONCLUSIVE'
