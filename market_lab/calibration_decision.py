"""Frozen all-scenario gates; failed stresses cannot be dropped post-validation."""


def clearance(config, development, independent, verification):
    expected_dev = config['original_scenarios']
    expected_ind = [r['name'] for r in config['independent']]
    actual_dev = [r['specification']['name'] for r in development['reports']]
    actual_ind = [r['specification']['name'] for r in independent['reports']]
    complete = actual_dev == expected_dev and actual_ind == expected_ind
    failed = []
    primary = config['primary_candidate']
    for stage, reports in [('development', development['reports']), ('independent', independent['reports'])]:
        for row in reports:
            result = row['methods'][primary]
            if result['replicates'] != config['replicates'] or result['coverage'] < config['coverage_floor']:
                failed.append({'stage': stage, 'scenario': row['specification']['name'],
                               'coverage': result['coverage'], 'method': primary})
    valid = complete and not failed and verification['status'] == 'PASS'
    return {'statistical_clearance': 'CONDITIONAL' if valid else 'BLOCKED',
            'primary_candidate': primary, 'all_scenarios_present_in_frozen_order': complete,
            'failed_scenarios': failed, 'independent_verification': verification['status'],
            'protocol_v3_adopted': False, 'v3_adoption_technically_eligible': valid,
            'protocol_v2_unchanged': True, 'holdout_authorized': False,
            'method_substitution_from_secondary': False,
            'coverage_floor': config['coverage_floor'],
            'interpretation': 'Synthetic coverage alone cannot establish real-market coverage or power.'}


def information_status(result, counts, gate, unknown_weight_fraction):
    missing = []
    for key in ['events', 'event_dates', 'securities']:
        if counts[key] < gate[key]:
            missing.append(key)
    if min(counts['down'], counts['up']) < gate['each_direction']:
        missing.append('each_direction')
    if unknown_weight_fraction > gate['unknown_weight_fraction']:
        missing.append('unknown_weight_fraction')
    if result['status'] != 'BOUNDED' or not result['informative'] or len(result['components']) != 1:
        missing.append('uncertainty_set_insufficient')
    return {'status': 'INCONCLUSIVE' if missing else 'COUNT_AND_SET_GATES_MET_ONLY',
            'failed_information_gates': missing,
            'global_calibration_gate_still_required': True}
