"""Compact full-pilot reporting and parameterized local evidence queries."""
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path
from decimal import Decimal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .storage import write_json, file_hash, parquet


def records(path):
    return [json.loads(r['payload_json']) for r in pq.ParquetFile(path).read().to_pylist()]


def query_pilot(run_id, event_id=None, ticker=None, cycle=None):
    root = Path('data/runs', run_id)
    filters, values = [], []
    for name, value in [('event_id', event_id), ('ticker', ticker), ('cycle_id', cycle)]:
        if value is not None:
            filters.append(name + ' = ?'); values.append(value)
    with duckdb.connect() as db:
        rows = db.execute('SELECT payload_json FROM read_parquet(?)' + (' WHERE ' + ' AND '.join(filters) if filters else ''),
                          [str(root / 'events/events.parquet'), *values]).fetchall()
    return [json.loads(r[0]) for r in rows]


def validate_pilot(run_id):
    from .tick_replay import first_touch, outcomes, ns
    root = Path('data/runs', run_id)
    selection = json.loads((root / 'selection.json').read_text())
    context = json.loads((root / 'context.json').read_text())
    conditions = {r['id']: r for r in context['conditions']}
    events = {e['event_id']: e for e in records(root / 'events/events.parquet')}
    saved = {e['event_id']: e for e in records(root / 'outcomes/outcomes.parquet')}
    cycles = {c['cycle_id']: c for c in selection['calendar']}
    checked, raw_checked = 0, set()
    for p in root.glob('raw/pages/*.meta.json'):
        meta = json.loads(p.read_text())
        assert file_hash(meta['path']) == meta['sha256'], 'raw hash mismatch'
        raw_checked.add(meta['path'])
    for o in records(root / 'opportunities/opportunities.parquet'):
        if 'normalization' not in o:
            continue
        audit = o['normalization']
        assert file_hash(audit['path']) == audit['sha256']
        rows = pq.ParquetFile(audit['path']).read().to_pylist()
        complete = o['status'] == 'PROCESSED'
        replay = first_touch(rows, cycles[o['cycle_id']], o, selection['config'], conditions, complete, run_id)
        if replay['event']:
            e = events[replay['event']['event_id']]
            assert all(e[k] == v for k, v in replay['event'].items()), 'event replay mismatch'
            assert Decimal(e['touch_price']) >= Decimal(e['threshold_price'])
            source = json.loads(e['source_json'])
            raw = json.loads(Path(source['path']).read_text())['results'][source['row']]
            assert raw['sip_timestamp'] == e['event_timestamp']
            actual = {**outcomes(replay, cycles[o['cycle_id']], selection['config'], complete), 'run_id': run_id}
            assert actual == saved[e['event_id']], 'outcome replay mismatch'
            checked += 1
    assert checked == len(events)
    from .m2_pilot import fingerprint
    assert fingerprint(selection['config']['source_m1_run']) == selection['m1_before']
    result = {'status': 'PASS', 'events_replayed': checked, 'raw_pages_hash_checked': len(raw_checked), 'm1_unchanged': True}
    write_json(root / 'validation.json', result)
    return result


def report(run_id, selection, context, opportunities, events, outcomes, ledger, integrity):
    root = Path('data/runs', run_id)
    dest = Path('reports', run_id); dest.mkdir(parents=True, exist_ok=True)
    by_event = {e['event_id']: e for e in events}
    groups = []
    for sample in ['SYSTEMATIC', 'DIAGNOSTIC']:
        for cohort in ['EXCHANGE_PRICE_ONLY', 'MASSIVE_CURRENT_FLOAT_PROXY']:
            oo = [o for o in opportunities if o['sample'] == sample and cohort in o['cohorts']]
            ee = [e for e in events if e['sample'] == sample and cohort in e['cohorts']]
            groups.append({'sample': sample, 'cohort': cohort, 'opportunities': len(oo), 'events': len(ee),
                           'complete_windows': sum(o['status'] == 'PROCESSED' for o in oo),
                           'verified_first_touches': sum(e['first_touch_status'] == 'VERIFIED_FIRST_TOUCH' for e in ee),
                           'zero_event_observed': sum(o.get('zero_event_status') == 'ZERO_EVENT_OBSERVED' for o in oo),
                           'session_counts_json': json.dumps(dict(Counter(e['session'] for e in ee)))})
    distributions = []
    for r in outcomes:
        for m in r['forward']:
            distributions.append({'event_id': r['event_id'], 'sample': r['sample'], 'metric': m['horizon'],
                                  'value': float(m['return']) if m['return'] is not None else None, 'censored': m['censored']})
        for name in ['observed_mfe', 'observed_mae']:
            distributions.append({'event_id': r['event_id'], 'sample': r['sample'], 'metric': name,
                                  'value': float(r[name]), 'censored': r['excursion_censored']})
    counts = Counter(o['status'] for o in opportunities)
    errors = [a for a in ledger['attempts'] if a['status'] != 'OK']
    summary = {'run_id': run_id, 'cycles': selection['config']['cycles'], 'selected_securities': len(selection['selected']),
               'security_cycle_opportunities': len(opportunities), 'window_status_counts': dict(counts),
               'events': len(events), 'verified_first_touches': sum(e['first_touch_status'] == 'VERIFIED_FIRST_TOUCH' for e in events),
               'observed_window_first_verified': sum(e['observed_window_first_verified'] for e in events),
               'session_counts': dict(Counter(e['session'] for e in events)), 'sample_cohort_counts': groups,
               'float_proxy_status_counts': dict(Counter(v['status'] for v in context['float'].values())),
               'sec_overlap_events': sum(bool(e['sec_evidence']) for e in events),
               'requests': len(ledger['attempts']), 'pages': ledger['pages'], 'decoded_bytes': ledger['decoded_bytes'],
               'api_errors': len(errors), 'statistics_scope': 'FULL_PILOT_SAMPLE_NOT_FULL_UNIVERSE',
               'statuses': {'ENGINEERING_VALIDATED': False, 'DATA_COVERAGE_VALIDATED': counts['INCOMPLETE'] == 0,
                            'PILOT_RESULTS_AVAILABLE': True, 'RESEARCH_STATISTICALLY_VALIDATED': False}}
    quality = {'window_status_counts': dict(counts), 'api_errors': errors, 'context_errors': context['errors'],
               'incomplete_windows': [{'cycle': o['cycle_id'], 'ticker': o['ticker'], 'error': o.get('trade_coverage', {}).get('error')} for o in opportunities if o['status'] == 'INCOMPLETE'],
               'quote_scope': 'EVENT_PLUS_MINUS_60_SECONDS_ONLY', 'unobserved_interval': '20:00-04:00 America/New_York',
               'halt_history': 'NOT_CERTIFIED; long trade gaps censored; bounded NBBO halt indicators retained',
               'rejected_trades': dict(sum((Counter(o.get('reject_counts', {})) for o in opportunities), Counter())),
               'integrity': integrity}
    statistical = {'scope': 'Descriptive, full selected pilot population only; no significance or profitability claim',
                   'confidence_intervals': {'status': 'NOT_ESTIMATED', 'reason': 'Tiny clustered selected sample and diagnostic selection bias'},
                   'forward': {}, 'barriers': {}}
    for sample in ['SYSTEMATIC', 'DIAGNOSTIC']:
        statistical['forward'][sample] = {}
        for horizon in ['5m', '15m', '30m', '60m', 'session_end', 'cycle_end']:
            vals = [d['value'] for d in distributions if d['sample'] == sample and d['metric'] == horizon and d['value'] is not None]
            total = sum(d['sample'] == sample and d['metric'] == horizon for d in distributions)
            statistical['forward'][sample][horizon] = {'n': len(vals), 'censored': total-len(vals), 'mean': sum(vals)/len(vals) if vals else None,
                                                      'min': min(vals) if vals else None, 'max': max(vals) if vals else None}
        statistical['barriers'][sample] = {f'{u}/{d}': dict(Counter(b['outcome'] for r in outcomes if r['sample'] == sample for b in r['barriers'] if b['up'] == u and b['down'] == d)) for u,d in selection['config']['barriers']}
    anomalies = {'events': [{'event_id': e['event_id'], 'flags': e['quality_flags'], 'quote': e.get('quote')} for e in events],
                 'crossing_candidates_path': str((root / 'candidates/candidates.parquet').resolve())}
    for name, content in [('summary', summary), ('data_quality', quality), ('statistical_results', statistical), ('statistical_tests', statistical), ('anomalies', anomalies)]:
        write_json(dest / (name + '.json'), content)
    # Full event/outcome payloads; never truncate research evidence to fit a report.
    from .m2_pilot import event_table
    event_table(dest / 'event_results.parquet', [{**e, 'outcomes': next(r for r in outcomes if r['event_id'] == e['event_id'])} for e in events])
    parquet(dest / 'cohort_metrics.parquet', groups, pa.Table.from_pylist(groups).schema)
    cycle_rows = [{'cycle_id': c, 'opportunities': sum(o['cycle_id'] == c for o in opportunities),
                   'complete_windows': sum(o['cycle_id'] == c and o['status'] == 'PROCESSED' for o in opportunities),
                   'events': sum(e['cycle_id'] == c for e in events)} for c in selection['config']['cycles']]
    parquet(dest / 'cycle_metrics.parquet', cycle_rows, pa.Table.from_pylist(cycle_rows).schema)
    parquet(dest / 'distributions.parquet', distributions, pa.schema([('event_id',pa.string()),('sample',pa.string()),('metric',pa.string()),('value',pa.float64()),('censored',pa.bool_())]))
    audits = [{**e, 'outcomes': next(r for r in outcomes if r['event_id'] == e['event_id'])} for e in events[:3]]
    write_json(dest / 'audit_examples.json', audits)
    text = '# M2 first-touch pilot\n\n' + json.dumps(summary, indent=2) + '\n\n## Interpretation limits\n\nCurrent float is a retrospective proxy, never verified PIT. Survivorship, dilution, splits and float changes can misclassify past eligibility. Diagnostic selection uses first-day high; it cannot estimate population probabilities. Systematic selection is seeded from the first-cycle historical frame, with later-cycle gates reapplied. Zero events mean no eligible crossing in observed sessions, not proof of no overnight trading.\n\nSIP observation clock; all returns are gross observed-price changes, not executable fills. Marks use the last eligible trade at or before the wall-clock horizon, maximum age 60 seconds. Long intertrade gaps (>300 seconds), overnight intervals, missing pages and touch invalidation censor outcomes. MFE/MAE retain observed extrema even when censored. Barrier ties at identical SIP timestamps are ambiguous. Conditions, correction reconstruction and thresholds are versioned in configs.\n\nQuotes cover only ±60 seconds around events. No complete halt feed or overnight coverage is claimed. Historical P0 and quality gates are inherited from M1, including its retrospective reference-data limitations. SEC context is independent and never forward-filled. Confidence intervals and significance tests are not estimated for this tiny clustered pilot.\n\n## Reproduction\n\nUse `python -m market_lab.m2_pilot validate --run-id ' + run_id + '` and `query --run-id ' + run_id + ' --ticker SYMBOL`. Full data remain in local `data/runs/' + run_id + '`. Selection, policies, source hashes, execution code hashes and request accounting are preserved. Three source-linked examples (or all if fewer) are in audit_examples.json.\n'
    (dest / 'report.md').write_text(text)
    write_json(dest / 'manifest.json', {'run_id': run_id, 'config': selection['config'], 'selection': selection['selected'],
                                       'policy_hash': selection['policy_hash'], 'artifacts': {p.name: {'sha256': file_hash(p), 'bytes': p.stat().st_size} for p in sorted(dest.iterdir()) if p.is_file() and p.name not in {'manifest.json','research_bundle.zip'}},
                                       'full_evidence_root': str(root.resolve()), 'statistics_scope': 'FULL_PILOT_SAMPLE'})
    with zipfile.ZipFile(dest / 'research_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.iterdir()):
            if p.name != 'research_bundle.zip' and p.is_file(): z.write(p,p.name)
    return summary
