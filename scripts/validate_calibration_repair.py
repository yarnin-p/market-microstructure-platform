"""Reproduce every frozen draw and verify score membership independently.

This is a deterministic verification pass, not another calibration population
or an opportunity to tune. The original one-shot results are never rewritten.
"""
import argparse
import json
import signal
import socket
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import requests

from market_lab.calibration_repair import (CONFIG, check_freeze, draw, original_specs, population)
from market_lab.ratio_calibration import confidence_sets, contains, totals_covariance
from market_lab.preholdout_audit import denied
from market_lab.storage import file_hash, write_json
from market_lab.temporal_design import read


def validate(config_path):
    config = read(config_path)
    root = Path('reports', config['run_id'])
    target = root/'independent-verification.json'
    if target.exists():
        raise ValueError('Immutable verification already exists')
    freeze = check_freeze(root, config_path)
    started = time.monotonic()
    records = []
    for prefix, specs in [('development', original_specs(config)), ('validation', config['independent'])]:
        for spec in specs:
            path = root/(prefix+'-'+spec['name']+'.json')
            source = read(path)
            rng, pop, M, m, truth = population(spec)
            assert truth == source['report']['target']
            counts = {name: 0 for name in source['report']['methods']}
            for saved in source['repetitions']:
                groups, _ = draw(rng, pop, m, spec['sample_n'])
                moment = totals_covariance(groups, {str(i): v for i, v in enumerate(M)})
                assert moment['Y'] == saved['Y'] and moment['Z'] == saved['Z']
                assert moment['cov'] == saved['cov']
                assert moment['events'] == saved['events']
                assert moment['zero_event_dates'] == saved['zero_event_dates']
                assert confidence_sets(moment, config['critical_value']) == saved['methods']
                # Direct linear-contrast inequality does not use root solver.
                theta = truth['truth']
                a = np.array([1., -theta])
                variance = float(a@np.array(saved['cov'])@a)
                left = (saved['Y']-theta*saved['Z'])**2
                right = config['critical_value']**2*max(0., variance)
                actual = contains(saved['methods']['FIELLER_SCORE'], theta)
                expected = left <= right
                if actual != expected:
                    assert abs(left-right) <= 1e-9*max(1., abs(left), abs(right)), 'Score inversion differs from direct test'
                for name, result in saved['methods'].items():
                    counts[name] += contains(result, theta)
            assert len(source['repetitions']) == config['replicates']
            for name, hits in counts.items():
                assert hits == source['report']['methods'][name]['hits']
            records.append({'stage': prefix, 'scenario': spec['name'], 'draws_reproduced': len(source['repetitions']),
                            'file_sha256': file_hash(path), 'direct_score_membership': 'PASS'})
            print(spec['name'], 'REPRODUCED', flush=True)
    protected = read(root/'protected.json')
    for p, sha in protected.items():
        assert file_hash(p) == sha, p
    write_json(target, {'status': 'PASS', 'records': records, 'total_draws': sum(r['draws_reproduced'] for r in records),
        'protected_files_unchanged': len(protected), 'frozen_implementation': freeze['code_hashes'],
        'verification_code_sha256': file_hash(__file__), 'elapsed_seconds': time.monotonic()-started,
        'new_population_seeds': False, 'method_tuning': False, 'market_requests': 0, 'holdout_access': False})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--config', default=CONFIG); args = p.parse_args()
    def timeout(*_):
        raise RuntimeError('VERIFICATION_WALL_BUDGET')
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, read(args.config)['max_wall_seconds'])
    try:
        with patch.object(requests.sessions.Session, 'request', denied), patch.object(socket, 'create_connection', denied):
            validate(args.config)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
