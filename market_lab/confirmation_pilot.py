"""Offline, immutable TASK 003 experiment and complete risk-set reporting."""
import argparse
import fcntl
import json
import subprocess
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from .confirmation import (bid_confirmation, causal_quote, confirmation_outcomes,
                           execution_mark_estimates, signal_result, trade_confirmation)
from .m2_pilot import event_table
from .m2_report import records
from .replay_qa import iter_normalized, tree_hashes
from .storage import digest, file_hash, write_json
from .systematic_pilot import replay
from .tick_replay import SECOND, number, ns, session_label

CONFIG = 'configs/task-003-confirmation-v1.json'


def read(path):
    return json.loads(Path(path).read_text())


def freeze(config):
    root = Path('data/runs', config['run_id'])
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'execution.json'
    source = Path('data/runs', config['source_run'])
    selection = read(source / 'selection.json')
    if len(selection['calendar']) != 10 or any(c['split_group'] != 'EXPLORATION' for c in selection['calendar']):
        raise ValueError('Only the existing ten exploration cycles are authorized')
    code = {str(p): file_hash(p) for p in Path('market_lab').glob('*.py')}
    if target.exists():
        frozen = read(target)
        if frozen['config'] != config or frozen['code_hashes'] != code:
            raise ValueError('Immutable run drift; choose a new run ID')
        return root, frozen
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if not head.startswith(config['baseline_commit']):
        raise ValueError('Unexpected baseline')
    protected = {}
    for parent in [Path('data/runs'), Path('reports')]:
        for old in sorted(parent.iterdir()):
            if old.is_dir() and old.name != config['run_id']:
                protected.update(tree_hashes(old))
    frozen = {'config': config, 'code_hashes': code, 'baseline_commit': head,
              'protected_files': protected, 'http_requests': 0,
              'source_selection_sha256': file_hash(source / 'selection.json'),
              'created_at': datetime.now(timezone.utc).isoformat()}
    write_json(target, frozen)
    return root, frozen


def quotes_for(pair):
    """Union existing quote windows only; retain explicit coverage intervals."""
    found, intervals = {}, []
    for manifest in sorted((pair / 'quotes').glob('*/coverage.json')):
        cov = read(manifest)
        paths = sorted((manifest.parent / 'normalized').glob('*.parquet'))
        valid = True
        for p in paths:
            for q in pq.ParquetFile(p).read().to_pylist():
                valid &= q['normalization_status'] == 'OK'
                found[q['record_id']] = q
        intervals.append({**cov['request'], 'complete': cov['complete'] and valid,
                          'manifest': str(manifest), 'manifest_sha256': file_hash(manifest)})
    return sorted(found.values(), key=lambda r: (r['sip_timestamp'], r.get('sequence_number') or 0, r['record_id'])), intervals


def coverage_for(intervals, start, end):
    # Merge only terminal, overlapping intervals; a gap is never filled by union.
    relevant = sorted([i for i in intervals if i['complete']], key=lambda x: x['start_ns'])
    merged = []
    for interval in relevant:
        if merged and interval['start_ns'] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], interval['end_ns'])
        else:
            merged.append([interval['start_ns'], interval['end_ns']])
    match = next((x for x in merged if x[0] < start and x[1] >= end), None)
    return {'complete': match is not None, 'request': {'start_ns': match[0], 'end_ns': match[1]} if match else {},
            'intervals': intervals, 'scope': 'ORIGINAL_BOUNDED_QUOTE_WINDOWS_ONLY'}


def build(config, root, recompute=False):
    source = Path('data/runs', config['source_run'])
    selection = read(source / 'selection.json')
    context = read(source / 'context.json')
    source_config = read('configs/task-002-2-systematic-v1.json')
    replay_config = {**source_config, **config}
    initial = [e for e in records(source / 'events/events.parquet') if e['condition_policy'] == 'HIGH_LOW_ONLY']
    if len(initial) != config['initial_primary_events'] or not all(e['observed_sessions_first_verified'] for e in initial):
        raise ValueError('Expected the existing 40 verified primary events')
    baseline_out = {o['event_id']: o for o in records(source / 'outcomes/outcomes.parquet')
                    if o['condition_policy'] == 'HIGH_LOW_ONLY' and o['gap_policy'] == 'NO_MECHANICAL_GAP'}
    cycles = {c['cycle_id']: c for c in selection['calendar']}
    selected = {(o['cycle_id'], o['security_id']): o for o in selection['selected']}
    results = []
    checkpoints = root / 'checkpoints'
    checkpoints.mkdir(exist_ok=True)
    for index, event in enumerate(sorted(initial, key=lambda e: (e['cycle_id'], e['security_id']))):
        checkpoint = checkpoints / (event['event_id'] + '.json')
        if checkpoint.exists() and not recompute:
            results.extend(read(checkpoint))
            continue
        pair = source / 'ticks' / ('cycle=' + event['cycle_id']) / ('security=' + event['security_id'])
        saved = read(pair / 'result.json')
        # Validate all immutable checkpoint dependencies before consuming ticks.
        for path, h in saved['input_hashes'].items():
            if file_hash(path) != h:
                raise ValueError('Source input changed: ' + path)
        paths = sorted((pair / 'trades/normalized').glob('*.parquet'))
        cycle = cycles[event['cycle_id']]
        states, _, _ = replay(paths, read(pair / 'trades/coverage.json'), selected[event['cycle_id'], event['security_id']],
                               cycle, source_config, {r['id']: r for r in context['conditions']})
        state = states['HIGH_LOW_ONLY']
        assert state.event['record_id'] == event['record_id'] and state.event['event_timestamp'] == event['event_timestamp']
        quotes, intervals = quotes_for(pair)
        notices = [r for r in iter_normalized(paths) if r.get('correction') in {10, 11, 12}]
        deadline = min(event['event_timestamp'] + config['c2_window_seconds'] * SECOND, ns(cycle['end_at']))
        c2_coverage = coverage_for(intervals, event['event_timestamp'], deadline)
        pair_results = []
        for condition in config['condition_policies']:
            state = states[condition]
            c0 = signal_result('C0', 'CONFIRMED', 'ORIGINAL_FIRST_TOUCH', event['event_timestamp'], event['touch_price'],
                [{'record_id': event['record_id'], 'timestamp': event['event_timestamp'], 'source_json': event['source_json'],
                  'restoration_source': event.get('restoration_source')}], trade_record_id=event['record_id'],
                market_price_timestamp=event['event_timestamp'], market_price_source=event['source_json'])
            signals = [c0, trade_confirmation(state, event, cycle, config, notices),
                       bid_confirmation(state, event, cycle, config, quotes, c2_coverage)]
            for signal in signals:
                t = signal['signal_timestamp']
                if signal['signal_policy'] != 'C0' and t is not None and any(x is None or event['event_timestamp'] <= x <= t for x in state.unknown_times):
                    signal.update(status='INSUFFICIENT_DATA', reason='UNKNOWN_EVIDENCE_BEFORE_CANDIDATE_CONFIRMATION')
                outs = [confirmation_outcomes(state, event, signal, cycle, replay_config, notices, gap)
                        for gap in config['gap_sensitivities_seconds']]
                outs = [o for o in outs if o is not None]
                primary = next((o for o in outs if o['gap_policy'] == 'NO_MECHANICAL_GAP'), None)
                if signal['signal_policy'] == 'C0' and condition == 'HIGH_LOW_ONLY':
                    old = baseline_out[event['event_id']]
                    assert all(primary[k] == old[k] for k in ['forward', 'barriers', 'observed_mfe', 'observed_mae', 'excursion_censored']), 'C0 must reproduce baseline exactly'
                qcov = coverage_for(intervals, t, t) if t else {'complete': False, 'request': {}, 'intervals': intervals}
                quote = causal_quote(quotes, t, config, qcov['complete']) if t else {'status': 'NO_SIGNAL'}
                price = number(signal['market_observation_price'])
                deterioration = price / number(event['touch_price']) - 1 if price is not None else None
                delayed = t - event['event_timestamp'] if t is not None else None
                confirm_by = {str(m): signal['status'] == 'CONFIRMED' and t <= event['event_timestamp'] + m * 60 * SECOND for m in config['forward_minutes']}
                prior_barriers = [{**b, 'occurred_before_signal': t is not None and b['first_passage_ns'] is not None and b['first_passage_ns'] < t}
                                  for b in baseline_out[event['event_id']]['barriers']]
                evidence_times = {r['record_id']: r['sip_timestamp'] for r in state.eligible}
                row = {'event_id': digest([config['methodology_version'], condition, signal['signal_policy'], event['event_id']]),
                    'run_id': config['run_id'], 'methodology_version': config['methodology_version'],
                    'initial_event_id': event['event_id'], 'initial_event_timestamp': event['event_timestamp'],
                    'initial_touch_price': event['touch_price'], 'original_threshold_price': event['threshold_price'],
                    'ticker': event['ticker'], 'security_id': event['security_id'], 'cycle_id': event['cycle_id'],
                    'initial_session': event['session'], 'signal_session': session_label(cycle, t) if t else None,
                    'condition_policy': condition, 'stratum': event['stratum'], 'cohorts': event['cohorts'],
                    'sampling_weight': event['sampling_weight'], 'selection_probability': event['selection_probability'],
                    'population_N': selected[event['cycle_id'], event['security_id']]['population_N'],
                    'sample_n': selected[event['cycle_id'], event['security_id']]['sample_n'],
                    'float_proxy': event['float_proxy'], 'sec_evidence': event['sec_evidence'],
                    'initial_quality': {'quote': event['quote'], 'later_invalidated': event['later_invalidated'],
                                        'strict_full_cycle_first_verified': False, 'restoration_status': event['restoration_status']},
                    'signal': signal, 'confirmation_delay_seconds': delayed / SECOND if delayed is not None else None,
                    'market_price_change_while_waiting': str(deterioration) if deterioration is not None else None,
                    'confirmed_by_minutes_from_initial_touch': confirm_by, 'initial_c0_barriers': prior_barriers,
                    'causal_entry_nbbo': quote, 'price_relation': ('ABOVE_ASK' if price is not None and quote['status'] == 'OK' and price > number(quote['ask']) else
                        'BELOW_BID' if price is not None and quote['status'] == 'OK' and price < number(quote['bid']) else
                        'WITHIN_NBBO' if price is not None and quote['status'] == 'OK' else 'QUOTE_OR_TRADE_MARK_UNAVAILABLE'),
                    'quote_mark_estimates': execution_mark_estimates(signal, primary, quotes, qcov, config),
                    'outcomes': outs, 'post_signal_outcome_status': 'AVAILABLE_WITH_CENSORING' if primary else 'NO_SIGNAL_OR_NO_FRESH_TRADE_MARK',
                    'quote_intervals': intervals, 'first_touch_anchor_unchanged': True}
                # Causal source bound applies even to reconstructed REST fields.
                assert all(evidence_times.get(e['record_id'], e['timestamp']) <= t for e in signal['evidence'])
                pair_results.append(row)
        if not recompute:
            write_json(checkpoint, pair_results)
        results.extend(pair_results)
        print(json.dumps({'processed_initial_events': index + 1, 'ticker': event['ticker'], 'cycle': event['cycle_id']}), flush=True)
    if not recompute:
        event_table(root / 'events/event_results.parquet', results)
    return results, selection


def stats(values):
    values = sorted(float(x) for x in values if x is not None)
    n = len(values)
    def q(p):
        index = (n - 1) * p
        a, b = int(index), min(int(index) + 1, n - 1)
        return values[a] + (values[b] - values[a]) * (index - a)
    return {'n': n, 'mean': sum(values) / n if n else None,
            **{name: q(p) if n else None for name, p in [('min', 0), ('p25', .25), ('median', .5), ('p75', .75), ('max', 1)]}}


def summarize(rows):
    n = len(rows)
    weight = sum(r['sampling_weight'] for r in rows)
    statuses = Counter(r['signal']['status'] for r in rows)
    out = {'initial_events': n, 'initial_design_weight_sum': weight, 'signal_status_counts': dict(statuses),
           'confirmed': statuses['CONFIRMED'], 'unconfirmed': statuses['UNCONFIRMED'], 'insufficient_data': statuses['INSUFFICIENT_DATA'],
           'delay_seconds': stats(r['confirmation_delay_seconds'] for r in rows if r['signal']['status'] == 'CONFIRMED'),
           'waiting_price_change': stats(r['market_price_change_while_waiting'] for r in rows if r['signal']['status'] == 'CONFIRMED'),
           'weighted_confirmation_fraction': sum(r['sampling_weight'] for r in rows if r['signal']['status'] == 'CONFIRMED') / weight if weight else None,
           'causal_entry_nbbo_statuses': dict(Counter(r['causal_entry_nbbo']['status'] for r in rows)),
           'forward': {}, 'barriers': {}, 'mfe': {}, 'mae': {},
           'reason_counts': dict(Counter(r['signal']['reason'] for r in rows))}
    for horizon in ['5m', '15m', '30m', '60m', 'session_end', 'cycle_end']:
        buckets, weighted, values = Counter(), Counter(), []
        for row in rows:
            signal = row['signal']
            primary = next((o for o in row['outcomes'] if o['gap_policy'] == 'NO_MECHANICAL_GAP'), None)
            mark = next((m for m in primary['forward'] if m['horizon'] == horizon), None) if primary else None
            bucket = ('NO_CONFIRMATION' if signal['status'] == 'UNCONFIRMED' else 'INSUFFICIENT_CONFIRMATION_DATA'
                      if signal['status'] == 'INSUFFICIENT_DATA' else 'CONFIRMED_NO_TRADE_MARK' if not mark
                      else 'CONFIRMED_CENSORED' if mark['censored'] else 'CONFIRMED_OBSERVED')
            buckets[bucket] += 1
            weighted[bucket] += row['sampling_weight']
            if mark and not mark['censored']:
                values.append(mark['return'])
        assert sum(buckets.values()) == n
        out['forward'][horizon] = {'initial_denominator': n, 'population_buckets': dict(buckets),
            'design_weight_buckets': dict(weighted), 'observed_return_distribution': stats(values),
            'confirmed_by_same_clock_landmark': sum(r['confirmed_by_minutes_from_initial_touch'][horizon[:-1]] for r in rows) if horizon[:-1] in {'5','15','30','60'} else None}
    for up, down in [('0.03', '0.03'), ('0.05', '0.03'), ('0.10', '0.05')]:
        buckets, weighted = Counter(), Counter()
        for row in rows:
            primary = next((o for o in row['outcomes'] if o['gap_policy'] == 'NO_MECHANICAL_GAP'), None)
            result = next((b['outcome'] for b in primary['barriers'] if b['up'] == up and b['down'] == down), None) if primary else None
            if result is None:
                result = 'NO_CONFIRMATION' if row['signal']['status'] == 'UNCONFIRMED' else 'INSUFFICIENT_DATA_OR_MARK'
            buckets[result] += 1
            weighted[result] += row['sampling_weight']
        out['barriers'][up + '/' + down] = {'initial_denominator': n, 'buckets': dict(buckets), 'design_weight_buckets': dict(weighted)}
    for name, field in [('mfe', 'observed_mfe'), ('mae', 'observed_mae')]:
        primary = [o for r in rows for o in r['outcomes'] if o['gap_policy'] == 'NO_MECHANICAL_GAP']
        out[name] = {'observed_trade_path_distribution': stats(o[field] for o in primary),
                     'excursion_censored': sum(o['excursion_censored'] for o in primary), 'outcomes_available': len(primary),
                     'initial_denominator': n}
    return out


def report(config, root, rows, selection):
    dest = Path('reports', config['run_id'])
    dest.mkdir(parents=True, exist_ok=True)
    groups = []
    for condition in config['condition_policies']:
        for stratum in ['ALL', 'PROXY_FLOAT_IN_RANGE', 'OTHER_EXCHANGE_PRICE_ELIGIBLE']:
            for session in ['ALL', 'AH', 'PRE', 'RTH']:
                for signal in config['signal_policies']:
                    chosen = [r for r in rows if r['condition_policy'] == condition and r['signal']['signal_policy'] == signal
                              and (stratum == 'ALL' or r['stratum'] == stratum) and (session == 'ALL' or r['initial_session'] == session)]
                    groups.append({'condition_policy': condition, 'stratum': stratum, 'initial_session': session,
                                   'signal_policy': signal, **summarize(chosen)})
    primary = [g for g in groups if g['condition_policy'] == 'HIGH_LOW_ONLY' and g['stratum'] == g['initial_session'] == 'ALL']
    pairs = []
    by_id = {(r['initial_event_id'], r['condition_policy'], r['signal']['signal_policy']): r for r in rows}
    for row in rows:
        if row['signal']['signal_policy'] == 'C0':
            continue
        c0 = by_id[row['initial_event_id'], row['condition_policy'], 'C0']
        for horizon in ['5m', '15m', '30m', '60m']:
            def mark(r):
                o = next((o for o in r['outcomes'] if o['gap_policy'] == 'NO_MECHANICAL_GAP'), None)
                return next((m for m in o['forward'] if m['horizon'] == horizon), None) if o else None
            a, b = mark(c0), mark(row)
            pairs.append({'initial_event_id': row['initial_event_id'], 'condition_policy': row['condition_policy'],
                'signal_policy': row['signal']['signal_policy'], 'horizon': horizon, 'confirmation_status': row['signal']['status'],
                'c0_return': a['return'] if a else None, 'signal_return': b['return'] if b else None,
                'both_marks_observed': bool(a and b and not a['censored'] and not b['censored']),
                'own_signal_clocks_not_common_exit_time': True, 'sampling_weight': row['sampling_weight']})
    for name, value in [('summary', {'run_id': config['run_id'], 'initial_primary_events': 40, 'policies': primary,
        'http_requests': 0, 'holdout_analyzed': False, 'population_inference': False,
        'performance_basis': 'OBSERVED_TRADE_PATH; no executable P&L', 'strict_full_cycle_verified': False}),
        ('cohort_metrics', groups), ('event-level-results', {'run_id': config['run_id'], 'records': rows}),
        ('paired_comparisons', {'scope': 'Descriptive conditional pairs; no causal or survivor-conditioned success claim', 'pairs': pairs}),
        ('sampling', {'source_selection_sha256': file_hash(Path('data/runs', config['source_run'], 'selection.json')),
            'strata': selection['strata'], 'selected_opportunities': 240, 'risk_set_events': 40,
            'design': selection['selection_method'], 'weights': 'Frozen N/n per cycle/stratum, never recomputed among confirmed survivors; weighted ratios descriptive only',
            'overlapping_experimental_rows_are_not_independent': True}),
        ('statistical_tests', {'status': 'NOT_PERFORMED', 'reason': 'Small stratified clustered exploratory sample; no significance or profitability claim',
            'independent_primary_security_cycle_events': 40, 'repeated_securities': len({r['security_id'] for r in rows}) < 40,
            'confidence_intervals': None, 'confirmation_thresholds_optimized': False}),
        ('data_quality', {'quote_scope': 'Existing bounded windows only; provider cursor exhaustion, not independent SIP certification',
            'historical_float': 'UNRESOLVED; current proxy frozen and not PIT', 'overnight': 'UNVERIFIED',
            'initial_opportunities': 240, 'primary_first_touches': 40, 'unselected_new_odd_only_events': 3,
            'signal_statuses': {g['signal_policy']: g['signal_status_counts'] for g in primary},
            'quote_estimate_marks': dict(Counter(m['status'] for r in rows for m in r['quote_mark_estimates']['marks'])),
            'missing_confirmation_is_not_a_negative_return': True}),
        ('anomalies', {'rows': [{'initial_event_id': r['initial_event_id'], 'ticker': r['ticker'], 'signal_policy': r['signal']['signal_policy'],
            'condition_policy': r['condition_policy'], 'price_relation': r['price_relation'], 'initial_quality': r['initial_quality']}
            for r in rows if r['price_relation'] in {'ABOVE_ASK','BELOW_BID'}], 'events_retained': True})]:
        write_json(dest / (name + '.json'), value)
    event_table(dest / 'event_results.parquet', rows)
    event_table(dest / 'cohort_metrics.parquet', groups)
    cycle_rows = []
    for cycle in selection['calendar']:
        for signal in config['signal_policies']:
            rr = [r for r in rows if r['cycle_id'] == cycle['cycle_id'] and r['condition_policy'] == 'HIGH_LOW_ONLY' and r['signal']['signal_policy'] == signal]
            cycle_rows.append({'cycle_id': cycle['cycle_id'], 'signal_policy': signal, **summarize(rr)})
    event_table(dest / 'cycle_metrics.parquet', cycle_rows)
    event_table(dest / 'distributions.parquet', [{'event_id': r['event_id'], 'initial_event_id': r['initial_event_id'],
        'condition_policy': r['condition_policy'], 'signal_policy': r['signal']['signal_policy'], 'sampling_weight': r['sampling_weight'], **o}
        for r in rows for o in r['outcomes']])
    # Compact full JSON without dropping any records.
    for name in ['event-level-results', 'cohort_metrics', 'paired_comparisons']:
        path = dest / (name + '.json')
        value = read(path)
        path.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    text = '# TASK 003 — Price Confirmation Research Pilot\n\n'
    text += 'Existing 40 primary initial events; no downloads, no holdout, no optimized thresholds.\n\n'
    text += '| Policy | Initial | Confirmed | Unconfirmed | Insufficient data | Median delay (s) | Median waiting price change |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for g in primary:
        delay, cost = g['delay_seconds']['median'], g['waiting_price_change']['median']
        text += f"| {g['signal_policy']} | 40 | {g['confirmed']} | {g['unconfirmed']} | {g['insufficient_data']} | {delay if delay is not None else 'NA'} | {format(cost,'.3%') if cost is not None else 'NA'} |\n"
    text += '\n## Full-risk-set outcomes\n\nEvery denominator includes unconfirmed and insufficient-data events. Observed post-signal return distributions condition on a signal and an uncensored mark; they are not unconditional success probabilities or strategy returns.\n\n'
    text += '| Policy | Horizon | Observed / initial | Censored confirmed | No confirmation | Insufficient confirmation/mark | Median observed return |\n|---|---|---:|---:|---:|---:|---:|\n'
    for g in primary:
        for h in ['5m','15m','30m','60m']:
            f = g['forward'][h]; b = f['population_buckets']; median = f['observed_return_distribution']['median']
            text += f"| {g['signal_policy']} | {h} | {b.get('CONFIRMED_OBSERVED',0)}/40 | {b.get('CONFIRMED_CENSORED',0)} | {b.get('NO_CONFIRMATION',0)} | {b.get('INSUFFICIENT_CONFIRMATION_DATA',0)+b.get('CONFIRMED_NO_TRADE_MARK',0)} | {format(median,'.3%') if median is not None else 'NA'} |\n"
    text += '\n## Limitations\n\nC1 includes the touch and requires three distinct eligible records spanning >=30 seconds, without resetting for intervening below-threshold prints; this is counted persistence, not continuous price support. C1 can signal later in the cycle; only the overnight blind interval resets its accumulated span. C2 needs two distinct fresh bid observations spanning >=10 seconds, resets on invalid/below bids or >5-second freshness gaps, and stops by touch+60 seconds or cycle end. Both retain the exact original +10% threshold.\n\n'
    text += 'C2 signal time is a quote receipt time; its market-observation entry basis is the latest eligible trade at/before that timestamp, no older than 60 seconds. That is an as-of mark, not a new trade or a fill. Ask-to-bid quote marks are a separate dataset; unavailable entry/exit quotes remain missing. No executable P&L is claimed.\n\n'
    text += 'All 40 initial events remain in every policy, including failures/missingness. Delayed signals do not enter retrospectively at C0 prices. Own-signal horizons differ in exit times; paired results are conditional descriptions, not causal strategy comparisons. Confirmation-by-common-landmark indicators and pre-signal C0 barrier outcomes expose waiting risk. Nonconfirmation is not assigned a zero return.\n\n'
    text += 'Odd-lot sensitivity keeps the same 40 original anchors and expands subsequent eligible observations only; three odd-only opportunities from TASK 002.2 are excluded from this fixed-risk-set experiment. AH/PRE/RTH grouping uses the initial session, while signal session is also retained. Original sampling weights N/n are preserved on every row; cohort/weighted summaries are descriptive and account for the two disjoint strata without treating policy copies as independent events. Current float is retrospective, not historical PIT. No independent overnight, halt/feed-loss or official-auction-close certification.\n\n'
    text += 'Reproduce offline: `python -m market_lab.confirmation_pilot run`, then `python -m market_lab.confirmation_pilot validate`. Original local cache is required to revalidate raw source evidence; compact JSON and the single research_bundle.zip can be read independently.\n'
    (dest / 'report.md').write_text(text)
    return dest


def validate(config, root, frozen, rows, selection):
    for path, h in frozen['protected_files'].items():
        assert file_hash(path) == h, 'Protected original artifact changed: ' + path
    for path, h in frozen['code_hashes'].items():
        assert file_hash(path) == h, 'Execution code drift'
    assert len(rows) == 240
    assert len({r['event_id'] for r in rows}) == len(rows)
    assert rows == records(root / 'events/event_results.parquet')
    source = Path('data/runs', config['source_run'])
    original = {e['event_id']: e for e in records(source / 'events/events.parquet') if e['condition_policy'] == 'HIGH_LOW_ONLY'}
    for condition in config['condition_policies']:
        for policy in config['signal_policies']:
            subset = [r for r in rows if r['condition_policy'] == condition and r['signal']['signal_policy'] == policy]
            assert {r['initial_event_id'] for r in subset} == set(original)
    page_hashes = {}
    source_records = 0
    for row in rows:
        initial = original[row['initial_event_id']]
        assert row['sampling_weight'] == initial['sampling_weight']
        assert row['original_threshold_price'] == initial['threshold_price']
        signal = row['signal']
        if signal['signal_timestamp'] is not None:
            assert signal['signal_timestamp'] >= row['initial_event_timestamp']
            for ev in signal['evidence']:
                assert ev['timestamp'] <= signal['signal_timestamp']
                source_ref = json.loads(ev['source_json'])
                path = source_ref['path']
                if path not in page_hashes:
                    assert file_hash(path) == source_ref['sha256']
                    page_hashes[path] = json.loads(Path(path).read_text())
                raw = page_hashes[path]['results'][source_ref['row']]
                assert digest(raw) == ev['record_id'] and raw['sip_timestamp'] == ev['timestamp']
                source_records += 1
            if signal['signal_policy'] == 'C2':
                assert signal['signal_timestamp'] <= row['initial_event_timestamp'] + 60 * SECOND
            assert all(m['return'] is None for o in row['outcomes'] for m in o['forward'] if m['censored'])
        if signal['status'] != 'CONFIRMED':
            assert not row['outcomes']
    result = {'status': 'PASS', 'initial_events_per_policy': 40, 'event_policy_condition_rows': len(rows),
        'protected_artifacts_unchanged': len(frozen['protected_files']), 'holdout_analyzed': False,
        'http_requests': 0, 'source_pages_checked': len(page_hashes), 'signal_evidence_records_checked': source_records,
        'same_risk_set_for_all_policies': True, 'sampling_weights_unchanged': True,
        'original_c0_outcomes_reproduced': 40}
    write_json(Path('reports', config['run_id'], 'validation.json'), result)
    return result


def package(config, root, dest, selection):
    files = {p.name: {'sha256': file_hash(p), 'bytes': p.stat().st_size} for p in dest.iterdir()
             if p.is_file() and p.name not in {'manifest.json','research_bundle.zip','bundle-validation.json'}}
    counts = {p.name: pq.ParquetFile(p).metadata.num_rows for p in dest.glob('*.parquet')}
    manifest = {'contract_version': 'research-bundle-v1', 'experiment_id': config['run_id'],
        'research_configuration': config, 'configuration_hash': digest(config),
        'baseline_commit': config['baseline_commit'], 'code_hashes': read(root / 'execution.json')['code_hashes'],
        'input_dataset': config['source_run'], 'source_selection_sha256': file_hash(Path('data/runs', config['source_run'], 'selection.json')),
        'requested_trading_cycles': [c['cycle_id'] for c in selection['calendar']],
        'processed_trading_cycles': [c['cycle_id'] for c in selection['calendar']],
        'event_definitions': 'Fixed 40 original anchors, C0 touch; C1 three trades over 30s; C2 fresh bid support >=10s by +60s',
        'outcome_definitions': 'Own-signal gross trade-mark 5/15/30/60m, excursions and first passage; censoring retained',
        'timezone': 'America/New_York sessions, UTC integer SIP nanoseconds',
        'schema_versions': {'event': 'confirmation-event-v1'}, 'files': files, 'record_counts': counts,
        'execution_status': 'COMPLETE', 'event_population': '40 fixed initial primary events, six repeated analyses each; not 240 independent events',
        'size_policy': 'Full event results; no raw ticks; no truncation', 'raw_ticks_included': False,
        'completed_at': datetime.now(timezone.utc).isoformat()}
    write_json(dest / 'manifest.json', manifest)
    with zipfile.ZipFile(dest / 'research_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ['manifest.json', *files]:
            archive.write(dest / name, name)
    with zipfile.ZipFile(dest / 'research_bundle.zip') as archive:
        import hashlib
        assert archive.testzip() is None
        for name, item in files.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == item['sha256']
        for name, count in counts.items():
            with archive.open(name) as stream:
                assert pq.read_metadata(stream).num_rows == count
    write_json(dest / 'bundle-validation.json', {'status': 'PASS', 'members': len(files)+1,
        'bytes': (dest/'research_bundle.zip').stat().st_size, 'sha256': file_hash(dest/'research_bundle.zip'),
        'record_counts': counts, 'all_ten_cycles_included': True, 'raw_ticks_included': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'validate', 'report'])
    parser.add_argument('--config', default=CONFIG)
    args = parser.parse_args()
    config = read(args.config)
    root, frozen = freeze(config)
    with (root / '.writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'run':
            rows, selection = build(config, root)
        else:
            rows = records(root / 'events/event_results.parquet')
            selection = read(Path('data/runs', config['source_run'], 'selection.json'))
            if args.command == 'validate':
                recomputed, _ = build(config, root, recompute=True)
                assert rows == recomputed, 'Deterministic confirmation replay mismatch'
        dest = report(config, root, rows, selection)
        validation = validate(config, root, frozen, rows, selection)
        package(config, root, dest, selection)
        print(json.dumps(validation, indent=2))


if __name__ == '__main__':
    main()
