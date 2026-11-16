"""Offline root-cause witnesses and conservative pre-access clearance gates.

This module supplements the independent replay without changing any outcome.
A complete provider pagination chain is not independent proof of market coverage.
"""
from collections import Counter
from pathlib import Path

from .audit_paths import S, cycle_bounds, eligible, pages, reconstruct, session
from .preholdout_audit import Budget, denied
from .storage import file_hash, write_json
from .temporal_design import read
from .temporal_pilot import runtime_config

SCENARIOS = {'regular', 'rare_domain', 'informative_missing', 'holdout_census_dates'}


def calibration_clearance(calibration, floor=0.93):
    names = [r['scenario'] for r in calibration]
    complete = len(names) == len(SCENARIOS) and set(names) == SCENARIOS
    failed = [r['scenario'] for r in calibration
              if r['coverage_all_replicates'] < floor or r['replicates'] != 1000
              or not r['synthetic_only'] or r['valid_intervals'] != r['replicates']]
    return {'status': 'PASS' if complete and not failed else 'BLOCKED',
            'all_scenarios_required': sorted(SCENARIOS), 'coverage_floor': floor,
            'failed_scenarios': failed, 'scenario_set_complete': complete,
            'nominal_95_percent_coverage_proven': False,
            'holdout_authorized': False}


def freshness_witness(rows, mark, bounds, conditions, lag):
    """Count returned messages in the exact permitted 60s endpoint window.

    Session-end marks exclude the next session, even at its boundary. Targets
    beyond cycle end have no observed window and must not be called illiquidity.
    """
    target = mark['target_ns']
    if target > bounds[4]:
        return {'classification': 'TARGET_AFTER_OBSERVED_CYCLE', 'raw_recent': None,
                'eligible_recent': None, 'rejections': {}}
    candidates = [r for r in rows if target - 60*S <= r['sip_timestamp'] <= target]
    if mark['horizon'] == 'session_end' and mark['mark']:
        origin = session(mark['mark']['sip_timestamp'], bounds)
        candidates = [r for r in candidates if session(r['sip_timestamp'], bounds) == origin]
    reasons = Counter()
    accepted = 0
    for r in candidates:
        ok, reason = eligible(r, bounds, conditions, lag)
        accepted += ok
        if not ok:
            reasons[reason] += 1
    label = ('RECENT_ELIGIBLE_PRINT' if accepted else 'RECENT_RETURNED_MESSAGES_ALL_REJECTED'
             if candidates else 'NO_RETURNED_MESSAGES_IN_RECENT_WINDOW')
    return {'classification': label, 'raw_recent': len(candidates),
            'eligible_recent': accepted, 'rejections': dict(reasons),
            'last_recent_raw_source': candidates[-1]['_source'] if candidates else None,
            'independent_feed_completeness_verified': False}


def verify_manifest(path):
    manifest = read(path / 'manifest.json')
    for name, meta in manifest['files'].items():
        source = path / name
        if not source.is_file() or file_hash(source) != meta['sha256']:
            raise ValueError('Missing or changed manifested source: ' + str(source))
    return len(manifest['files'])


def supplement(config_path):
    config = read(config_path)
    dest = Path('reports', config['run_id'])
    output = dest / 'root-cause-witnesses.json'
    if output.exists():
        raise ValueError('Immutable supplement already exists')
    audits = read(dest / 'event-audits.json')
    tables = read(Path('reports', config['source_run'], 'source-event-level-results.json'))
    strict = {run: verify_manifest(Path('reports', run))
              for run in {config['source_run']} | {r['source_run_id'] for r in audits}}
    budget = Budget(config)
    evidence = []
    accepted_by_session = Counter()
    rejected_by_session = Counter()
    for event in audits:
        root = Path('data/runs', event['source_run_id'])
        plan = read(root / 'selection.json')
        cycle = next(c for c in plan['calendar'] if c['cycle_id'] == event['cycle_id'])
        bounds = cycle_bounds(cycle)
        context = read(root / 'context.json')
        conditions = {r['id']: r for r in context['conditions']}
        cfg = runtime_config(plan['config'])
        cov_path = root / 'ticks' / ('cycle=' + event['cycle_id']) / ('security=' + event['security_id']) / 'trades/coverage.json'
        coverage = read(cov_path)
        raw, _ = pages(coverage, budget)
        rows = reconstruct(raw)
        for r in rows:
            ok, reason = eligible(r, bounds, conditions, cfg['max_participant_lag_seconds'])
            key = (session(r['sip_timestamp'], bounds), reason)
            (accepted_by_session if ok else rejected_by_session)[key] += 1
        for policy in event['outcomes']:
            for mark in policy['forward']:
                if not mark['censored']:
                    continue
                witness = freshness_witness(rows, mark, bounds, conditions, cfg['max_participant_lag_seconds'])
                # An eligible recent print can coexist with overnight/gap censoring,
                # but may never contradict a primary freshness-only failure.
                if (policy['gap_seconds'] is None and
                    mark['root_causes'] == ['PRICE_MARK_FRESHNESS_FAILURE'] and
                    witness['eligible_recent']):
                    raise AssertionError('Freshness classification contradicted by raw evidence')
                evidence.append({'event_id': event['event_id'], 'horizon': mark['horizon'],
                    'gap_seconds': policy['gap_seconds'], 'target_ns': mark['target_ns'],
                    'root_causes': mark['root_causes'], 'provider_pagination_complete': coverage['complete'],
                    'coverage_path': str(cov_path), 'coverage_sha256': file_hash(cov_path), **witness})
    previous = Path('reports', config['comparison_audit_run'])
    comparison = {}
    for name in ['event-audits.json', 'statistical_results.json', 'estimator-calibration.json',
                 'confirmation-fairness.json', 'data_quality.json', 'censoring-evidence.json', 'anomalies.json']:
        comparison[name] = read(dest/name) == read(previous/name)
    if not all(comparison.values()):
        raise AssertionError('Independent rerun differs from preserved v1 audit')
    summary = read(dest/'summary.json')
    assert budget.raw_bytes + summary['raw_bytes_read'] <= config['max_raw_bytes']
    primary = [r for r in evidence if r['gap_seconds'] is None]
    write_json(output, evidence)
    result = {'source_manifests_strictly_verified': strict, 'v1_reproduction_identical': comparison,
        'supplement_raw_bytes': budget.raw_bytes, 'total_raw_bytes_with_reconstruction': budget.raw_bytes + summary['raw_bytes_read'],
        'supplement_pages': budget.pages, 'primary_censored_marks': len(primary),
        'primary_raw_window_witnesses': dict(Counter(r['classification'] for r in primary)),
        'primary_freshness_failures': dict(Counter(r['classification'] for r in primary if 'PRICE_MARK_FRESHNESS_FAILURE' in r['root_causes'])),
        'accepted_condition_counts_by_session': {str(k): v for k, v in accepted_by_session.items()},
        'rejected_condition_counts_by_session': {str(k): v for k, v in rejected_by_session.items()},
        'counting_unit': 'All returned/reconstructed messages in 93 event windows; not all 720 opportunity windows',
        'interpretation': 'No recent returned print is compatible with illiquidity, but not independent proof against feed loss or halt. Rejected prints and out-of-cycle targets are separately witnessed.',
        'new_market_requests': 0, 'holdout_accessed': False, 'outcomes_modified': False,
        'code_sha256': file_hash(__file__)}
    write_json(dest/'root-cause-summary.json', result)
    return result


if __name__ == '__main__':
    import argparse
    import socket
    import requests
    from unittest.mock import patch
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    with patch.object(requests.sessions.Session, 'request', denied), patch.object(socket, 'create_connection', denied):
        print(supplement(args.config))
