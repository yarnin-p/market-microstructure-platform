"""Offline, staged synthetic calibration: development first, one-shot validation.

No market-data files are loaded. Prior artifacts are hashed for immutability.
Independent validation cannot select a method or change frozen configuration.
"""
import argparse
import json
import math
import signal
import socket
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
import requests

from .audit_statistics import ratio as original_ratio
from .preholdout_audit import denied
from .ratio_calibration import CRITICAL, BOX_CRITICAL, confidence_sets, contains, totals_covariance, wilson
from .storage import digest, file_hash, write_json
from .temporal_design import read, protected_hashes

CONFIG = 'configs/task-005-1-calibration-v1.json'
METHODS = ['WALD_T', 'FIELLER_SCORE', 'BONFERRONI_TOTAL_BOX']


def population(spec):
    """Exactly reproduce TASK005 when supplied its original specifications."""
    rng = np.random.default_rng(spec['seed'])
    M = [20, 20] if spec['census'] else [14, 22, 21, 13]
    m = M if spec['census'] else [6, 9, 9, 6]
    security = rng.normal(0, .9, spec['security_pool'])
    result = []
    for size in M:
        days = []
        ar = 0.
        for _ in range(size):
            ar = .75*ar+rng.normal(0, .5)
            strata = []
            for st in range(2):
                N = int(rng.integers(spec['N_min'], spec['N_max']))
                ids = rng.choice(spec['security_pool'], N, replace=False)
                rate = spec['event_rate']
                p = 1/(1+np.exp(-(math.log(rate/(1-rate))+security[ids]+ar+.3*st)))
                z = (rng.random(N) < p).astype(float)
                down = rng.random(N) < 1/(1+np.exp(-(0.4+security[ids]*.5+ar)))
                neither = rng.random(N) < .06
                latent = z*np.where(neither, 0, np.where(down, 1, -1))
                missing = (rng.random(N) < spec['missing_rate']*(1+.7*down)) & (z > 0)
                y = np.where(missing, 0, latent)
                # Unknown remains an explicit indicator, not an imputed outcome.
                strata.append({'y': y, 'z': z, 'ids': ids, 'latent': latent, 'unknown': missing.astype(float)})
            days.append(strata)
        result.append(days)
    Z = sum(g['z'].sum() for days in result for day in days for g in day)
    Y = sum(g['y'].sum() for days in result for day in days for g in day)
    L = sum(g['latent'].sum() for days in result for day in days for g in day)
    C = sum(g['unknown'].sum() for days in result for day in days for g in day)
    if not Z:
        raise ValueError('Synthetic finite population has no event-domain target')
    fingerprint = digest([[[{k: v.tolist() for k, v in g.items()} for g in day] for day in days] for days in result])
    return rng, result, M, m, {'Z': float(Z), 'Y': float(Y), 'truth': float(Y/Z),
        'latent_truth': float(L/Z), 'identification_bounds': [float((Y-C)/Z), float((Y+C)/Z)],
        'unknown_fraction': float(C/Z), 'population_sha256': fingerprint}


def draw(rng, pop, m, sample_n):
    groups = []
    ids = set()
    dates_with_events = down = up = 0
    for month, days in enumerate(pop):
        for day in rng.choice(len(days), m[month], replace=False):
            count = 0
            for st, g in enumerate(days[day]):
                ix = rng.choice(len(g['y']), min(sample_n, len(g['y'])), replace=False)
                y, z = g['y'][ix], g['z'][ix]
                groups.append({'month': str(month), 'cycle_id': str(day), 'stratum': st,
                               'N': len(g['y']), 'y': y, 'z': z})
                count += int(z.sum())
                ids.update(g['ids'][ix][z > 0].tolist())
                down += int((y > 0).sum())
                up += int((y < 0).sum())
            dates_with_events += count > 0
    return groups, {'securities': len(ids), 'event_dates': dates_with_events, 'down': down, 'up': up}


def qstats(values):
    values = [x for x in values if x is not None]
    if not values:
        return None
    a = np.array(values, float)
    return {'n': len(a), 'mean': float(a.mean()), 'median': float(np.median(a)),
            'min': float(a.min()), 'p05': float(np.quantile(a, .05)),
            'p95': float(np.quantile(a, .95)), 'max': float(a.max())}


def run_scenario(spec, config, output, started):
    rng, pop, M, m, truth = population(spec)
    date_pop = {str(i): n for i, n in enumerate(M)}
    records = []
    for i in range(config['replicates']):
        if time.monotonic()-started > config['max_wall_seconds']:
            raise RuntimeError('WALL_BUDGET')
        groups, counts = draw(rng, pop, m, spec['sample_n'])
        moments = totals_covariance(groups, date_pop)
        results = confidence_sets(moments, config['critical_value'])
        Y, Z, t = moments['Y'], moments['Z'], truth['truth']
        v = np.array(moments['cov'])
        residual_variance_truth = max(0., float(np.array([1., -t])@v@np.array([1., -t])))
        r = {'replicate': i, 'Y': Y, 'Z': Z, 'events': moments['events'], **counts,
             'zero_event_dates': moments['zero_event_dates'], 'zero_event_strata': moments['zero_event_strata'],
             'ratio': Y/Z if Z else None, 'cov': moments['cov'],
             'variance_at_truth': residual_variance_truth, 'residual_at_truth': Y-t*Z,
             'denominator_rse': math.sqrt(v[1, 1])/Z if Z else None,
             'methods': results}
        if i < 3:
            old = original_ratio(groups, date_pop)
            assert old['estimate'] == r['ratio'] or abs(old['estimate']-r['ratio']) < 1e-12
            if old['se'] is not None:
                assert abs(old['se']-results['WALD_T']['width']/(2*config['critical_value'])) < 1e-12
        records.append(r)
    summaries = {}
    for name in METHODS:
        sets = [r['methods'][name] for r in records]
        hits = sum(contains(s, truth['truth']) for s in sets)
        latent_hits = sum(contains(s, truth['latent_truth']) for s in sets)
        informative = [s for s in sets if s['informative']]
        coverage = hits/len(records)
        summaries[name] = {'coverage': coverage, 'hits': hits, 'replicates': len(records),
            'coverage_mc_se': math.sqrt(coverage*(1-coverage)/len(records)),
            'coverage_wilson95_mc_only': wilson(hits, len(records)),
            'latent_target_coverage': latent_hits/len(records),
            'width': qstats([s['width'] for s in sets]),
            'statuses': dict(Counter(s['status'] for s in sets)),
            'raw_geometries': dict(Counter(s['raw_geometry'] for s in sets)),
            'raw_unbounded_count': sum(s['raw_unbounded'] for s in sets),
            'informative_count': len(informative),
            'informative_conditional_coverage_diagnostic_only': sum(contains(s, truth['truth']) for s in informative)/len(informative) if informative else None,
            'empty_domain_count': sum(s['status'] == 'EMPTY_DOMAIN' for s in sets),
            'invalid_or_empty_set_count': sum(not s['components'] for s in sets),
            'meets_floor': coverage >= config['coverage_floor']}
    estimates = [r['ratio'] for r in records if r['ratio'] is not None]
    empirical_variance = float(np.var(estimates, ddof=1))
    plugin_variances = [(r['methods']['WALD_T']['width']/(2*config['critical_value']))**2 for r in records if r['ratio'] is not None]
    error = np.array(estimates)-truth['truth']
    sd = float(np.std(estimates))
    residuals = [r['residual_at_truth'] for r in records]
    gate = config['information_gate']
    info = [r for r in records if r['events'] >= gate['events'] and r['event_dates'] >= gate['event_dates']
            and r['securities'] >= gate['securities'] and min(r['down'], r['up']) >= gate['each_direction']]
    diagnostics = {'ratio_bias': float(np.mean(error)), 'ratio_skewness': float(np.mean(((error-error.mean())/sd)**3)) if sd else None,
        'empirical_ratio_variance': empirical_variance, 'mean_plugin_variance': float(np.mean(plugin_variances)),
        'mean_plugin_to_empirical_variance': float(np.mean(plugin_variances))/empirical_variance if empirical_variance else None,
        'estimated_denominator': qstats([r['Z'] for r in records]), 'denominator_rse': qstats([r['denominator_rse'] for r in records]),
        'sampled_event_count': qstats([r['events'] for r in records]),
        'zero_event_dates': qstats([r['zero_event_dates'] for r in records]),
        'zero_event_strata': qstats([r['zero_event_strata'] for r in records]),
        'ratio_at_physical_boundary': sum(abs(r['ratio']) >= 1-1e-12 for r in records if r['ratio'] is not None),
        'mean_true_residual_variance_estimate': float(np.mean([r['variance_at_truth'] for r in records])),
        'empirical_true_residual_variance': float(np.var(residuals, ddof=1)),
        'adequate_count_information_repetitions': len(info),
        'adequate_count_conditional_primary_coverage_diagnostic_only': sum(contains(r['methods']['FIELLER_SCORE'], truth['truth']) for r in info)/len(info) if info else None,
        'first_stage_variance_included': not spec['census'], 'both_stage_fpc': True,
        'fixed_repeated_security_effects_and_ar1_dates': True,
        'conditional_diagnostics_are_not_clearance_gates': True}
    report = {'specification': spec, 'target': truth, 'methods': summaries, 'diagnostics': diagnostics,
              'synthetic_only': True, 'all_repetitions_retained': True}
    output.write_text(json.dumps({'report': report, 'repetitions': records}, separators=(',', ':'), allow_nan=False)+'\n')
    return report


def original_specs(config):
    return [dict(name=name, family=name, event_rate=rate, missing_rate=missing, census=census,
                 seed=config['original_seed']+i, N_min=30, N_max=100, security_pool=240, sample_n=12)
            for i, (name, rate, missing, census) in enumerate([
                ('regular', .13, 0., False), ('rare_domain', .02, 0., False),
                ('informative_missing', .13, .2, False), ('holdout_census_dates', .13, 0., True)])]


def check_freeze(root, config_path):
    freeze = read(root/'freeze.json')
    assert file_hash(config_path) == freeze['config_sha256'], 'Config changed after freeze'
    for path, sha in freeze['code_hashes'].items():
        assert file_hash(path) == sha, 'Code changed after freeze: '+path
    return freeze


def stage(command, config_path=CONFIG):
    config = read(config_path)
    root = Path('reports', config['run_id'])
    started = time.monotonic()
    if command == 'prepare':
        root.mkdir(parents=True, exist_ok=False)
        prior = protected_hashes(config['run_id'])
        write_json(root/'protected.json', prior)
        write_json(root/'freeze.json', {'config_sha256': file_hash(config_path), 'config': config,
            'code_hashes': {p: file_hash(p) for p in ['market_lab/ratio_calibration.py', 'market_lab/calibration_repair.py']},
            'prior_artifact_count': len(prior), 'frozen_before_simulation': True,
            'method_selected_before_independent_validation': 'FIELLER_SCORE',
            'box_critical': BOX_CRITICAL, 'primary_critical_unchanged': CRITICAL,
            'independent_seeds_predeclared': True, 'market_requests': 0, 'holdout_access': False})
        print('FROZEN', root, flush=True)
        return
    check_freeze(root, config_path)
    independent = command == 'validate'
    if independent:
        assert (root/'development-summary.json').exists(), 'Development diagnosis must precede validation'
    filename = 'validation' if independent else 'development'
    assert not (root/(filename+'-started.json')).exists(), 'Immutable stage already attempted; do not retune or rerun under this ID'
    write_json(root/(filename+'-started.json'), {'config_sha256': file_hash(config_path),
               'prior_stage_sha256': file_hash(root/'development-summary.json') if independent else None})
    specs = config['independent'] if independent else original_specs(config)
    reports = []
    for spec in specs:
        result = run_scenario(spec, config, root/(filename+'-'+spec['name']+'.json'), started)
        reports.append(result)
        print(json.dumps({'stage': filename, 'scenario': spec['name'],
                          'coverage': {k: v['coverage'] for k, v in result['methods'].items()}}), flush=True)
    if not independent:
        old = read('reports/m5-preholdout-audit-20261116-v2/estimator-calibration.json')
        for expected, observed in zip(old, reports):
            assert expected['scenario'] == observed['specification']['name']
            assert expected['coverage_all_replicates'] == observed['methods']['WALD_T']['coverage']
            assert abs(expected['known_population_target']-observed['target']['truth']) < 1e-12
            assert abs(expected['bias']-observed['diagnostics']['ratio_bias']) < 1e-12
        write_json(root/'baseline-reproduction.json', {'status': 'PASS', 'original_failure_preserved': True,
            'original_sha256': file_hash('reports/m5-preholdout-audit-20261116-v2/estimator-calibration.json')})
    for p, h in read(root/'protected.json').items():
        assert file_hash(p) == h, 'Prior artifact changed: '+p
    size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    assert size <= config['max_output_bytes']
    write_json(root/(filename+'-summary.json'), {'reports': reports, 'elapsed_seconds': time.monotonic()-started,
        'market_requests': 0, 'holdout_access': False, 'output_bytes': size,
        'all_primary_scenarios_meet_floor': all(r['methods']['FIELLER_SCORE']['meets_floor'] for r in reports),
        'config_sha256': file_hash(config_path), 'independent_suite_used_for_tuning': False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'develop', 'validate'])
    parser.add_argument('--config', default=CONFIG)
    args = parser.parse_args()
    config = read(args.config)
    def timeout(*args):
        raise RuntimeError('WALL_BUDGET')
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, config['max_wall_seconds'])
    try:
        with patch.object(requests.sessions.Session, 'request', denied), patch.object(socket, 'create_connection', denied):
            stage(args.command, args.config)
    except Exception as exc:
        root = Path('reports', config['run_id'])
        if root.exists():
            failure = root/(args.command+'-failure.json')
            if not failure.exists():
                write_json(failure, {'status': 'BLOCKED', 'error': type(exc).__name__+': '+str(exc),
                                    'market_requests': 0, 'holdout_access': False})
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == '__main__':
    main()
