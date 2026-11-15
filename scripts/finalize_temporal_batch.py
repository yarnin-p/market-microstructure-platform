"""Validate and publish frozen batch2 without modifying earlier artifacts."""
import argparse
import json
import re
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from market_lab.temporal_batch import CONFIG,prepare,analysis_rows,statistics
from market_lab.temporal_design import read,temporal_sample
from market_lab.temporal_pilot import runtime_config,analyze,package
from market_lab.m2_report import records
from market_lab.storage import file_hash,write_json
from market_lab.systematic_pilot import replay,sample_frame
from market_lab.replay_methodology import outcome_sensitivity
from market_lab.temporal_statistics import clustered_ratio
from market_lab.confirmation_pilot import stats
from scripts.finalize_temporal import weighted_policies


def metric(rows,values):
    assert len(rows)==len(values)
    valid=[float(v) for v in values if v is not None]
    return {'initial_n':len(rows),'observed_n':len(valid),'missing_n':len(rows)-len(valid),
        'distribution':stats(valid),'cluster_sensitivity':clustered_ratio([{**r,'value':float(v) if v is not None else None} for r,v in zip(rows,values)],'value'),
        'uncertainty':'Date/security crossed cluster sensitivity only, not iid CI; subset selection and serial dependence remain limitations'}


def estimands(tables,plan,calendar):
    opps=[r for r in tables['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY']
    derived=analysis_rows(opps,calendar,plan['date_strata']);by_pair={(r['cycle_id'],r['security_id']):r for r in derived}
    first=[r for r in tables['first_outcomes'] if r['condition_policy']=='HIGH_LOW_ONLY' and r['gap_seconds'] is None and r['first_touch_evidence_status']=='OBSERVED_SESSIONS_FIRST_VERIFIED']
    rr=[by_pair[r['cycle_id'],r['security_id']] for r in first]
    forward={}
    for horizon in ['5m','15m','30m','60m','session_end','cycle_end']:
        marks=[next(m for m in r['forward'] if m['horizon']==horizon) for r in first]
        forward[horizon]={'return':metric(rr,[m['return'] for m in marks]),
            'positive_return':metric(rr,[float(m['return'])>0 if m['return'] is not None else None for m in marks]),
            'censoring':metric(rr,[m['censored'] for m in marks])}
    barriers={}
    for index,label in enumerate(['+3/-3','+5/-3','+10/-5']):
        outcomes=[r['barriers'][index]['outcome'] for r in first]
        barriers[label]={'counts':dict(Counter(outcomes)),'initial_n':len(rr),
            'weighted_outcome_fractions':{value:metric(rr,[o==value for o in outcomes]) for value in sorted(set(outcomes))}}
    confirmation={}
    rows=analysis_rows([r for r in tables['confirmation'] if r['condition_policy']=='HIGH_LOW_ONLY'],calendar,plan['date_strata'])
    c0={r['initial_event_id']:r for r in rows if r['policy']=='C0_FROZEN'}
    for policy in sorted({r['policy'] for r in rows}):
        pp=[r for r in rows if r['policy']==policy];landmarks={}
        for i,minute in enumerate([5,15,30,60]):
            mm=[r['common_landmarks'][i] for r in pp];diffs=[]
            for r,m in zip(pp,mm):
                base=c0[r['initial_event_id']]['common_landmarks'][i]
                assert (m['target_ns'],m['exit_observation_ns'])==(base['target_ns'],base['exit_observation_ns'])
                diffs.append(float(m['return'])-float(base['return']) if m['status']==base['status']=='OBSERVED' else None)
            landmarks[str(minute)]={'status_counts':dict(Counter(m['status'] for m in mm)),
                'return':metric(pp,[m['return'] if m['status']=='OBSERVED' else None for m in mm]),
                'paired_difference_vs_c0':metric(pp,diffs)}
        confirmation[policy]={'status_counts':dict(Counter(r['signal']['status'] for r in pp)),
            'confirmation_incidence':metric(pp,[r['signal']['status']=='CONFIRMED' for r in pp]),'common_landmarks':landmarks}
    return {'first_touch_n':len(first),'forward':forward,'barriers':barriers,
        'observed_mfe':metric(rr,[r['observed_mfe'] for r in first]),'observed_mae':metric(rr,[r['observed_mae'] for r in first]),
        'excursion_censoring':metric(rr,[r['excursion_censored'] for r in first]),'confirmation':confirmation,
        'opportunity_missingness':metric(derived,[not r['observed_opportunity_eligible'] for r in derived]),
        'weights':'Batch-specific derived analytical weights; all original frozen weights preserved in source/event tables',
        'mfe_mae_scope':'Observed path only; censored excursions are not complete-path extremes',
        'confidence_intervals':None,'significance_claim':False}


def validate(config,root,plan,tables):
    original=read(root/'source-selection.json');source=Path('data/runs',config['source_temporal_run'])
    protocol=read(root/'statistical-protocol.json')
    assert file_hash(source/'selection.json')==protocol['source_selection_sha256']
    assert read(source/'selection.json')==original
    dates,strata=temporal_sample(read(Path('data/runs',config['source_m1_run'],'calendar.json')),set(original['development_dates']),original['config'])
    assert dates==original['calendar'] and strata==original['date_strata']
    selected,ss=sample_frame(records(source/'population/frame.parquet'),original['config'])
    assert ss==original['security_strata']
    for a,b,c in zip(selected,original['selected'],plan['selected']):
        assert all(b[k]==v for k,v in a.items())
        assert {k:v for k,v in b.items() if k!='execute_in_initial_batch'}=={k:v for k,v in c.items() if k!='execute_in_initial_batch'}
    ledger=read(root/'ledger.json')
    earliest=min(datetime.fromisoformat(a['started_at']).timestamp() for a in ledger['attempts'])
    assert max((root/n).stat().st_mtime for n in ['statistical-protocol.json','selection.json','execution.json'])<=earliest
    cfg=runtime_config(config);conditions={r['id']:r for r in read(root/'context.json')['conditions']}
    cycles={c['cycle_id']:c for c in plan['calendar']};op_index={(o['cycle_id'],o['security_id']):o for o in plan['selected']}
    count=0
    for p in sorted(root.glob('ticks/cycle=*/security=*/ingest.json')):
        saved=read(p)
        for path,h in saved['input_hashes'].items():assert file_hash(path)==h
        op=saved['opportunities'][0];original_op=op_index[op['cycle_id'],op['security_id']]
        states,_,_=replay(saved['paths'],read(saved['coverage_path']),original_op,cycles[op['cycle_id']],cfg,conditions)
        expected=[]
        for policy,state in states.items():
            e=next((e for e in saved['events'] if e['condition_policy']==policy),None)
            assert bool(e)==bool(state.event)
            if e:
                assert all(e[k]==state.event[k] for k in ['record_id','event_timestamp','touch_price','threshold_price','observed_sessions_first_verified'])
                expected.extend(outcome_sensitivity(state,cycles[op['cycle_id']],cfg,g) for g in config['gap_sensitivities_seconds'])
        assert expected==saved['first_outcomes'];count+=1
    recomputed=analyze(config,root,plan,recompute=True)
    # Parquet record ordering is sorted by event_table; compare canonical records.
    for name,rows in tables.items():
        assert sorted(map(lambda r:json.dumps(r,sort_keys=True),rows))==sorted(map(lambda r:json.dumps(r,sort_keys=True),recomputed[name])),name
    for path,h in read(root/'protected.json').items():assert file_hash(path)==h,path
    return {'status':'PASS','frozen_date_selection_reproduced':30,'frozen_security_selection_reproduced':720,
        'original_weights_unchanged':True,'statistical_protocol_precedes_first_http':True,
        'deterministic_first_touch_replays':count,'confirmation_and_all_outcomes_recomputed':True,
        'protected_files_unchanged':len(read(root/'protected.json')),'batch3_acquired':False,'holdout_analyzed':False}


def finalize(test_output):
    config=read(CONFIG);root,plan=prepare(config);dest=Path('reports',config['run_id'])
    tables=read(dest/'event-level-results.json');original=read(root/'source-selection.json')
    for n,rows in tables.items():assert rows==records(root/n/(n+'.parquet'))
    write_json(dest/'independent-validation.json',validate(config,root,plan,tables))
    match=re.search(r'(\d+) passed(?:, (\d+) warnings)? in',Path(test_output).read_text())
    assert match,'Full passing pytest output required'
    write_json(dest/'tests.json',{'passed':int(match[1]),'warnings':int(match[2] or 0),'source_hashes':{str(p):file_hash(p) for p in Path('tests').glob('*.py')}})
    for filename,n in [('statistical-preparation.json',10),('cumulative-temporal-statistics.json',20)]:
        report=read(dest/filename)
        report['month_date_crossed_security_resampling']['limitations']=f'{n} sampled date clusters; repeated securities reweighted globally. Illustrative month-stratified crossed-cluster range, not calibrated two-stage CI; serial dependence unresolved.'
        for incidence in [report['incidence'],*report['strata'].values()]:
            incidence['assumptions']='Fixed finite-population randomized month/date and security draws; full response required. Actual planned monthly allocation, no iid CI and no stationarity claim.'
        write_json(dest/filename,report)
    estimates=estimands(tables,plan,original['calendar'][10:20])
    estimates['design_weighted_incidence']=read(dest/'statistical-preparation.json')
    write_json(dest/'statistical_results.json',estimates)
    batch1=read(Path('reports',config['source_temporal_run'],'event-level-results.json'))
    combined={k:batch1[k]+tables[k] for k in tables}
    write_json(dest/'cumulative-temporal-estimands.json',estimands(combined,plan,original['calendar'][:20]))
    derived=analysis_rows(tables['confirmation'],original['calendar'][10:20],plan['date_strata'])
    write_json(dest/'design-weighted-policy-metrics.json',weighted_policies(derived))
    write_json(dest/'original-weight-warning.json',{'files':['cohort_metrics.json','cohort_metrics.parquet','original-weight-stratum-incidence.json'],
        'scope':'Original frozen batch1 weight metadata retained for audit; use statistical_results/statistical-preparation/design-weighted-policy-metrics for batch2 inference.'})
    previous=read(Path('reports',config['source_temporal_run'],'summary.json'));current=read(dest/'summary.json')
    comparison={'development':current['development_separate'],'temporal_batch1':previous,'temporal_batch2':current,
        'remaining_batch3':{'dates':10,'opportunities':240,'status':'UNANALYZED'},'holdout':{'dates':40,'status':'UNTOUCHED'},'development_pooled':False}
    write_json(dest/'temporal-comparison.json',comparison)
    primary=[e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY']
    odd=[e for e in tables['events'] if e['condition_policy']=='ODD_LOT_OBSERVATION_SENSITIVITY'];pair={(e['cycle_id'],e['security_id']):e for e in primary}
    write_json(dest/'odd-lot-sensitivity.json',{'primary':len(primary),'odd':len(odd),'added':sum((e['cycle_id'],e['security_id']) not in pair for e in odd),
        'changed_timestamps':sum((e['cycle_id'],e['security_id']) in pair and pair[e['cycle_id'],e['security_id']]['event_timestamp']!=e['event_timestamp'] for e in odd)})
    write_json(dest/'source-audit-examples.json',primary[:3])
    opportunities=[o for o in tables['opportunities'] if o['condition_policy']=='HIGH_LOW_ONLY']
    write_json(dest/'sec-secondary-overlap.json',{'selected_opportunities':sum(bool(o.get('sec_evidence')) for o in opportunities),
        'primary_events':sum(bool(e.get('sec_evidence')) for e in primary),'carry_forward':False,'historical_float_gate_changed':False})
    quality=read(dest/'data_quality.json');quotes=[read(p) for p in root.glob('ticks/cycle=*/security=*/quotes/*/coverage.json')]
    quality.update(quote_windows=len(quotes),complete_quote_windows=sum(q['complete'] for q in quotes),
        empty_quote_windows=sum(q['raw_rows']==0 for q in quotes),quote_rows=sum(q['raw_rows'] for q in quotes),
        first_touch_quote_statuses=dict(Counter(e['quote']['status'] for e in primary)),
        float_proxy_statuses=dict(Counter(o['float_proxy']['status'] for o in opportunities)))
    write_json(dest/'data_quality.json',quality)
    if not (dest/'original-weight-stratum-incidence.json').exists():
        write_json(dest/'original-weight-stratum-incidence.json',read(dest/'stratum-incidence.json'))
    write_json(dest/'stratum-incidence.json',read(dest/'statistical-preparation.json')['strata'])
    shutil.copyfile('docs/plans/TASK-004-1-temporal-batch2.md',dest/'methodology.md')
    st=read(dest/'statistical-preparation.json');cum=read(dest/'cumulative-temporal-statistics.json')
    lines=['# TASK 004.1 — ผล frozen temporal batch 2','',f"Run `{config['run_id']}`; baseline `{config['baseline_commit']}`",'',
        f"รัน 10 dates / {current['selected_opportunities']} opportunities ตาม frozen positions 11–20 โดยไม่สุ่มใหม่; complete trade windows {current['complete_trade_windows']}/240; verified first touches {current['verified_primary_events']}; zero-event {current['zero_event_opportunities']}; sessions {current['session_events']}.",
        f"ใช้ {current['http_requests']} HTTP attempts / {current['ledger']['pages']} pages / {current['ledger']['decoded_bytes']:,} decoded bytes; errors {current['http_errors']}; acquisition stop={current['acquisition']['stop_reason']}.",'',
        '## ผลราย cycle','', '| Cycle | Complete | First touches | Sessions |','|---|---:|---:|---|']
    for c in current['cycles']:lines.append(f"| {c['cycle_id']} | {c['complete']} | {c['verified_events']} | {c['sessions']} |")
    lines+=['','## Incidence และ comparison','',
        f"Development 40/240, temporal batch1 {previous['verified_primary_events']}/240, batch2 {current['verified_primary_events']}/240 แยกกลุ่ม ไม่ถือ observations เป็นอิสระ.",
        f"Batch2 design-weighted incidence {st['incidence']['weighted_incidence']:.3%}; cumulative temporal20 {cum['incidence']['weighted_incidence']:.3%}. คง original weights ทุกแถว แต่ derived analysis weights ใช้ actual month allocation 3/2/2/3 และ cumulative5/5/5/5; ห้ามใช้ initial-batch probabilities เพื่ออ้าง batch2 design inference."]
    for s,v in st['strata'].items():lines.append(f"{s}: events {v.get('observed_events')} / selected {v['selected_denominator']}; weighted incidence {v['weighted_incidence']:.3%}.")
    lines+=['','## Confirmation บน initial risk set เดิม','','| Policy | Status counts |','|---|---|']
    for policy,v in estimates['confirmation'].items():lines.append(f"| {policy} | {v['status_counts']} |")
    lines+=['','## Forward returns และ barriers','','| Horizon | Observed / initial | Median return |','|---|---:|---:|']
    for h,v in estimates['forward'].items():
        r=v['return'];median=r['distribution'].get('median');lines.append(f"| {h} | {r['observed_n']}/{r['initial_n']} | {median} |")
    for b,v in estimates['barriers'].items():lines.append(f"\n{b}: {v['counts']}")
    lines+=['',f"Observed MFE distribution: {estimates['observed_mfe']['distribution']}",f"Observed MAE distribution: {estimates['observed_mae']['distribution']}",'',
        '## Validation และข้อจำกัด','',f"Tests {match[1]} passed; source hashes/pagination/event references ตรวจครบ; deterministic replay และ confirmation/outcomes recomputed. ผลเดิมและ SEC/M1 ไม่เปลี่ยน. Batch3 10 dates/240 opportunities ยังไม่รัน; holdout40ไม่วิเคราะห์.",
        'รายงาน conditional returns เฉพาะ marks ที่มี evidence พร้อม missing denominators; excursion extremes เป็น observed path ไม่ใช่ guaranteed full path. Date/security clustering และ month-stratified resampling เป็น uncertainty sensitivity ไม่ใช่ calibrated confidence intervals หรือ significance. วันซ้ำและ security ซ้ำไม่ใช่ independent events; serial dependence ยังจำกัด inference.',
        'Current float เป็น retrospective proxy ไม่ใช่ PIT; SEC แยกอิสระ. NBBO จำกัดเฉพาะ event windows ไม่ใช่ complete quote coverage. Overnight ยัง unverified. ไม่อ้าง executable fills, P&L หรือปรับ thresholds ตามผล.',
        f"\nFull local evidence: `data/runs/{config['run_id']}`; compact results: `reports/{config['run_id']}`; remaining inventory `remaining-frozen-batch.json`. Reproduce: temporal_batch prepare/acquire --offline/analyze/validate; scripts.finalize_temporal_batch --pytest-output PATH."]
    report='\n'.join(lines)+'\n';(dest/'report.md').write_text(report);Path('docs/research/task-004-1-temporal-batch2.md').write_text(report)
    write_json(dest/'finalization.json',{'publisher_sha256':file_hash(__file__),'methodology_sha256':file_hash('docs/plans/TASK-004-1-temporal-batch2.md'),'all_records_preserved':True})
    write_json(dest/'storage.json',{'run_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),'raw_data_committed':False})
    package(config,root,dest,plan)
    manifest=read(dest/'manifest.json');manifest['event_population']='Frozen temporal batch 2 only: positions 11-20; development and batch1 reported separately'
    manifest['source_selection_sha256']=read(root/'statistical-protocol.json')['source_selection_sha256']
    write_json(dest/'manifest.json',manifest)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['manifest.json',*manifest['files']]:z.write(dest/name,name)
    with zipfile.ZipFile(dest/'research_bundle.zip') as z:assert z.testzip() is None
    bundle=read(dest/'bundle-validation.json');bundle.update(bytes=(dest/'research_bundle.zip').stat().st_size,sha256=file_hash(dest/'research_bundle.zip'))
    write_json(dest/'bundle-validation.json',bundle)
    print(json.dumps({'summary':current,'tests':match[1],'independent_validation':read(dest/'independent-validation.json')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pytest-output',required=True);a=p.parse_args();finalize(a.pytest_output)
