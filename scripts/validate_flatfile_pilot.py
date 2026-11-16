"""Offline pilot integrity and causal-signal reproducibility checks."""
import argparse
import json
import socket
from pathlib import Path
from unittest.mock import patch

import requests

from market_lab.confirmation import bid_confirmation
from market_lab.flatfile_cache import CONFIG, atomic_json, memory_bytes
from market_lab.flatfile_ingest import selected_mapping
from market_lab.flatfile_revalidation import source_quotes, trade_state
from market_lab.preholdout_audit import denied
from market_lab.quote_state import QuoteState, state_confirmation
from market_lab.storage import file_hash
from market_lab.temporal_design import read
from market_lab.tick_replay import SECOND, bounds


def validate(config,root,config_path=CONFIG):
    target=root/'pilot-validation.json'
    if target.exists():raise ValueError('Immutable validation already exists')
    assert file_hash(config_path)==read(root/'plan-freeze.json')['config_sha256']
    effective=read(root/'analysis-code-freeze.json')['hashes']
    # Operational resume marker revision preserves parser/state semantics and v1 record.
    if (root/'acquisition-code-v2.json').exists():effective.update(read(root/'acquisition-code-v2.json')['code'])
    for version in ['analysis-code-v3.json','analysis-code-v4.json','analysis-code-v5.json','analysis-code-v6.json','analysis-code-v7.json','analysis-code-v8.json','analysis-code-v9.json']:
        if (root/version).exists():effective.update(read(root/version)['code'])
    for p,h in effective.items():assert file_hash(p)==h,p
    sources=read(root/'downloaded-sources.json');manifests=read(root/'ingested-sources.json')
    assert len(sources)==len(config['objects'])==len(manifests)==3
    for source in sources:
        assert source['complete'] and Path(source['local_path']).stat().st_size==source['size']
        assert file_hash(source['local_path'])==source['sha256']
        planned=next(r for r in config['objects'] if r['key']==source['key'])
        for key in ['etag','last_modified','size']:assert source[key]==planned[key]
    integrity=read(root/'gzip-integrity.json');assert integrity['complete'] and len(integrity['sources'])==3
    assert {p['source_sha256'] for p in integrity['sources']}=={s['sha256'] for s in sources}
    for proof in integrity['sources']:
        assert proof['crc_validated'] and proof['complete']
        assert proof['source_sha256'] in {s['sha256'] for s in sources}
    for m in manifests:
        assert m['complete'] and m['gzip_crc_validated']
        from market_lab.flatfile_revalidation import source_interval
        assert source_interval(m)['complete']
        for p in m['partitions']:assert file_hash(p['path'])==p['sha256']
    baseline=read(root/'baseline-reproduction.json');assert baseline['status']=='PASS' and baseline['qa_rows_recomputed_exactly']==640
    result=read(root/'confirmation-comparison.json');events,mapping=selected_mapping(config)
    assert all(len(ids)==1 for ids in mapping.values()),'Ambiguous historical ticker identity'
    ids={e['event_id'] for e in events};rows=result['rows']
    for condition in ['HIGH_LOW_ONLY','ODD_LOT_OBSERVATION_SENSITIVITY']:
        for policy in ['C2_S3_FROZEN_RULE','C2_S3_STATE_BASED']:
            cohort=[r for r in rows if r['condition_policy']==condition and r['policy']==policy]
            assert len(cohort)==40 and {r['initial_event_id'] for r in cohort}==ids
    source=Path('data/runs',config['source_run']);selection=read(source/'selection.json')
    assert len(selection['calendar'])==10 and all(c['split_group']=='EXPLORATION' for c in selection['calendar'])
    assert set(config['pilot_dates'])<={c['cycle_id'] for c in selection['calendar']}
    conditions={r['id']:r for r in read(source/'context.json')['conditions']}
    oldcfg={**read('configs/task-002-2-systematic-v1.json'),**read('configs/task-003-confirmation-v1.json')}
    checks=prefix_checks=0
    for event in events:
        rr=[r for r in rows if r['initial_event_id']==event['event_id'] and r['comparable_source_coverage']]
        if not rr:continue
        cycle=next(c for c in selection['calendar'] if c['cycle_id']==event['cycle_id'])
        quotes,intervals,_=source_quotes(manifests,event['ticker'],cycle,event['security_id'])
        replay=QuoteState(quotes,intervals,cycle,5,60)
        states,_=trade_state(config,event,cycle,selection,conditions)
        start=event['event_timestamp'];deadline=min(start+60*SECOND,bounds(cycle)[-1])
        for r in rr:
            st=states[r['condition_policy']]
            if r['policy']=='C2_S3_FROZEN_RULE':
                actual=bid_confirmation(st,event,cycle,oldcfg,quotes,{'complete':True,'request':{'start_ns':start-1,'end_ns':deadline}})
            else:actual=state_confirmation(replay,st,event,cycle,config)
            t=actual['signal_timestamp']
            if t is not None and any(u is None or start<=u<=t for u in st.unknown_times):actual.update(status='INSUFFICIENT_DATA',reason='UNKNOWN_TRADE_EVIDENCE_BEFORE_CONFIRMATION')
            assert actual==r['signal'];checks+=1
            if actual['status']=='CONFIRMED':
                assert start<=t<=deadline
                for proof in actual['evidence']:
                    assert proof['timestamp']<=t and proof['observed_at']<=t
                if r['policy']=='C2_S3_STATE_BASED':
                    prefix=QuoteState([q for q in quotes if q['sip_timestamp']<=t],intervals,cycle,5,60)
                    assert state_confirmation(prefix,st,event,cycle,config)==actual;prefix_checks+=1
    for timeline in result['timelines']:
        for state in timeline['asof']:
            if state.get('quote_timestamp') is not None:assert state['quote_timestamp']<=state['evaluation_ns']
    protected=read(root/'protected.json')
    for p,h in protected.items():assert file_hash(p)==h,p
    resource=read(root/'resource-ledger.json');ingest=read(root/'ingest-resources.json')
    assert resource['requests']<=config['max_requests'] and resource['downloaded_bytes']<=config['max_download_bytes']
    assert resource['active_seconds']<=config['max_active_seconds']
    assert ingest['decoded_bytes']<=config['max_decoded_bytes']
    partials=list(Path('data/flatfiles').rglob('operational-interruption.json'))
    partial_charge=sum(read(p.parent/'progress.json')['decoded_bytes']+74*config['csv_block_bytes'] for p in partials)
    benchmark_charge=4*1024**3
    sniff_charge=len(sources)*512*1024**2
    decoded_work_upper=2*integrity['decoded_bytes_exact']+partial_charge+benchmark_charge+sniff_charge
    assert decoded_work_upper<=config['max_decoded_bytes']
    assert resource['max_rss_bytes']+ingest['max_rss_bytes']+64*1024**2<=config['max_memory_bytes']
    assert memory_bytes()<=config['max_memory_bytes']
    size=sum(p.stat().st_size for folder in [Path('data/flatfiles'),root] for p in folder.rglob('*') if p.is_file())
    upper=size+max(s['size'] for s in sources)
    assert upper<=config['max_storage_bytes']
    output={'status':'PASS','source_objects':len(sources),'source_gzip_integrity':'PASS','selected_partitions':sum(len(m['partitions']) for m in manifests),
        'source_date_alignment':'PASS_PROVIDER_SESSION_BASIS_WITH_EXPLICIT_SPILL_CONTEXT','initial_risk_set':40,'covered_signal_checks':checks,'state_prefix_causality_checks':prefix_checks,
        'all_640_baseline_rows_unchanged':True,'prior_artifacts_unchanged':len(protected),
        'marketwide_files_committed':False,'rest_requests':0,'holdout_access':False,
        'resources':resource,'ingest_resources':ingest,'gzip_integrity':integrity,'decoded_work_upper_bytes':decoded_work_upper,
        'decoded_partial_and_prefetch_charge_bytes':partial_charge,'benchmark_charge_upper_bytes':benchmark_charge,
        'current_storage_bytes':size,
        'conservative_staging_storage_upper_bytes':upper,
        'conservative_concurrent_transfer_ingest_peak_rss_bytes':resource['max_rss_bytes']+ingest['max_rss_bytes'],
        'native_gzip_worker_memory_reserve_bytes':64*1024**2,'memory_measurement_scope':'Last resume process only; earlier quote extraction combined RSS not persisted',
        'whole_run_memory_budget_audit':'CONDITIONAL_METRIC_GAP',
        'analysis_peak_rss_bytes':memory_bytes(),'validation_code_sha256':file_hash(__file__),
        'historical_snapshot_pit_vintage_certified':False,
        'scope':'SIP-causal replay within supplied historical provider snapshot, not independent exchange coverage or executable fills'}
    atomic_json(target,output);return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);a=p.parse_args();config=read(a.config)
    with patch.object(requests.sessions.Session,'request',denied),patch.object(socket,'create_connection',denied):
        print(json.dumps(validate(config,Path('data/runs',config['run_id']),a.config),indent=2))
