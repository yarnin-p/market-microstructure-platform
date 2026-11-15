"""Package the full QA experiment without raw ticks or local-cache dependencies."""
import json
import subprocess
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from market_lab.m2_pilot import event_table
from market_lab.storage import file_hash, parquet, write_json


def package(dest, config):
    dest = Path(dest)
    export = json.loads((dest / 'event-level-results.json').read_text())
    events, outcomes, opportunities = (export[k] for k in ['events', 'outcomes', 'opportunities'])
    key = lambda r: (r['variant'], r['condition_policy'], r['event_id'])
    by_event = {}
    for outcome in outcomes:
        by_event.setdefault(key(outcome), []).append(outcome)
    event_table(dest / 'event_results.parquet', [{**e, 'outcomes': by_event[key(e)]} for e in events])
    metrics = []
    dimensions = sorted({(o['cycle_id'], o['variant'], o.get('condition_policy', ''), o['sample']) for o in opportunities})
    for cycle, variant, policy, sample in dimensions:
        oo = [o for o in opportunities if (o['cycle_id'], o['variant'], o.get('condition_policy', ''), o['sample']) == (cycle, variant, policy, sample)]
        ee = [e for e in events if (e['cycle_id'], e['variant'], e['condition_policy'], e['sample']) == (cycle, variant, policy, sample)]
        metrics.append({'cycle_id': cycle, 'variant': variant, 'condition_policy': policy, 'sample': sample,
                        'opportunities': len(oo), 'events': len(ee),
                        'complete_observed': sum(o.get('complete_observed_sessions', False) for o in oo),
                        'verified_observed_first': sum(e['observed_sessions_first_verified'] for e in ee),
                        'strict_opportunities': sum(o.get('strict_full_cycle_opportunity_eligible', False) for o in oo),
                        'zero_event_observed': sum(o.get('zero_event_observed', False) for o in oo),
                        'sessions_json': json.dumps(dict(Counter(e['session'] for e in ee)))})
    parquet(dest / 'cycle_metrics.parquet', metrics)
    summary = json.loads((dest / 'summary.json').read_text())
    event_table(dest / 'cohort_metrics.parquet', summary['groups'])
    distributions = []
    for r in outcomes:
        common = {k: r[k] for k in ['event_id', 'variant', 'condition_policy', 'gap_policy', 'cycle_id', 'sample']}
        for mark in r['forward']:
            distributions.append({**common, 'metric': mark['horizon'], 'value': float(mark['return']) if mark['return'] is not None else None, 'censored': mark['censored']})
        for name in ['observed_mfe', 'observed_mae']:
            distributions.append({**common, 'metric': name, 'value': float(r[name]), 'censored': r['excursion_censored']})
    parquet(dest / 'distributions.parquet', distributions)
    write_json(dest / 'statistical_tests.json', {
        'status': 'DESCRIPTIVE_PILOT_ONLY', 'confidence_intervals': 'NOT_ESTIMATED',
        'reason': 'Small clustered fixed selection; diagnostic selection bias; variants and cohorts overlap.',
        'event_policy_variant_records': len(events), 'independent_security_cycle_event_pairs': len({(e['security_id'], e['cycle_id']) for e in events}),
        'systematic_and_diagnostic_pooled': False, 'significance_claim': False})
    repair = json.loads((dest / 'coverage-repair.json').read_text())
    write_json(dest / 'data_quality.json', {
        'coverage_repair': repair, 'integrity': json.loads((dest / 'integrity.json').read_text()),
        'strict_full_cycle_coverage': False, 'overnight': 'UNOBSERVED_NOT_PROOF_OF_CLOSURE',
        'quote_coverage': 'ORIGINAL_EVENT_PLUS_MINUS_60_SECONDS; NOT_CONTINUOUS_FULL_CYCLE',
        'missing_processed_cycles': [], 'historical_float': 'UNRESOLVED; M1 BLOCKED_DATA',
        'opportunity_policy_variant_records_including_exclusions': opportunities})
    write_json(dest / 'anomalies.json', {'published_audit_examples': json.loads((dest / 'requested-raw-nbbo-audit.json').read_text()),
        'condition_sensitivity': 'Eight earlier odd-lot touches and two additional diagnostic events; see first-touch-comparison.json',
        'halt_or_feed_loss_independently_verified': False})
    manifest_path = dest / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['publisher_sha256'] = file_hash('scripts/report_replay_qa.py')
    document = Path('docs/research/task-002-1-replay-methodology-qa.md')
    manifest['methodology_document'] = {'path': str(document), 'sha256': file_hash(document)}
    cycles = sorted({o['cycle_id'] for o in opportunities})
    manifest.update(build_git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        bundle_builder_sha256=file_hash(__file__), completed_at=datetime.now(timezone.utc).isoformat(),
        requested_cycles=cycles, processed_cycles=cycles, missing_cycles=[],
        execution_status='QA_PILOT_COMPLETE_WITH_UNRESOLVED_OVERNIGHT_AND_HISTORICAL_FLOAT',
        event_definition='First eligible >=110% previous RTH close in explicitly defined observed sessions; strict full-cycle unverified',
        outcome_definition='Eligible observed-trade path; 300/900/no mechanical gap sensitivity; 60-second mark age',
        timezone='America/New_York sessions; integer SIP nanoseconds UTC',
        schema='schemas/replay-methodology-qa-v2.json',
        dataset=config['baseline_run'], record_counts={
            'event_results.parquet': len(events), 'cycle_metrics.parquet': len(metrics),
            'cohort_metrics.parquet': len(summary['groups']), 'distributions.parquet': len(distributions)})
    manifest['artifacts'] = {p.name: {'sha256': file_hash(p), 'bytes': p.stat().st_size} for p in sorted(dest.iterdir())
                             if p.is_file() and p.name not in {'manifest.json', 'research_bundle.zip', 'bundle-validation.json'}}
    write_json(manifest_path, manifest)
    archive = dest / 'research_bundle.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in ['manifest.json', *manifest['artifacts']]:
            bundle.write(dest / name, name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        import hashlib
        for name, info in manifest['artifacts'].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == info['sha256']
        import pyarrow.parquet as pq
        for name, count in manifest['record_counts'].items():
            with bundle.open(name) as stream:
                assert pq.read_metadata(stream).num_rows == count
    result = {'status': 'PASS', 'sha256': file_hash(archive), 'bytes': archive.stat().st_size,
              'members': len(manifest['artifacts']) + 1, 'record_counts': manifest['record_counts'],
              'all_processed_cycles_included': cycles, 'raw_ticks_included': False}
    write_json(dest / 'bundle-validation.json', result)
    return result


if __name__ == '__main__':
    config = json.loads(Path('configs/task-002-1-qa-v1.json').read_text())
    print(json.dumps(package(Path('reports') / config['run_id'], config), indent=2))
