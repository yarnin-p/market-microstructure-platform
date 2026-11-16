"""Batch3/full30 validation and separately weighted cumulative research export."""
import argparse
import json
import math
import re
import shutil
import zipfile
from collections import Counter,defaultdict
from pathlib import Path

from market_lab.temporal_final_batch import CONFIG,prepare
from market_lab.temporal_batch import analysis_rows,statistics
from market_lab.temporal_design import read
from market_lab.temporal_pilot import package,runtime_config
from market_lab.storage import file_hash,write_json,digest
from market_lab.m2_pilot import event_table
from market_lab.m2_report import records
from market_lab.systematic_pilot import replay
from market_lab.tick_replay import number,correction_key
from market_lab.replay_qa import iter_normalized
from scripts.finalize_temporal_batch import validate as validate_replay,estimands
from scripts.finalize_temporal import weighted_policies

CUM_CONFIG='configs/task-004-2-cumulative30-v1.json'


def full_weights(opportunities,original,cfg):
    expected={(r['cycle_id'],r['security_id']):r for r in original['selected']}
    primary=[r for r in opportunities if r['condition_policy']=='HIGH_LOW_ONLY']
    keys=[(r['cycle_id'],r['security_id']) for r in primary]
    if len(primary)!=720 or len(set(keys))!=720 or set(keys)!=set(expected):raise ValueError('Full30 opportunity reconciliation failed')
    counts=Counter(r['cycle_id'][:7] for r in original['calendar'])
    sidecar=[]
    immutable=['ticker','previous_rth_close','m1_record_id','source_m1','float_proxy','stratum','sampling_weight',
               'selection_probability','population_N','sample_n','joint_sampling_weight','joint_inclusion_probability','date_inclusion_probability']
    for row in primary:
        old=expected[row['cycle_id'],row['security_id']]
        if any(row[k]!=old[k] for k in immutable):raise ValueError('Source identity/provenance/weight changed')
        num,den=cfg['date_probabilities'][row['cycle_id'][:7]]
        if counts[row['cycle_id'][:7]]!=num:raise ValueError('Incorrect planned month allocation')
        sec_p=row['sample_n']/row['population_N'];date_p=num/den
        sidecar.append({'cycle_id':row['cycle_id'],'security_id':row['security_id'],'stratum':row['stratum'],
            'security_population_N':row['population_N'],'security_sample_n':row['sample_n'],
            'original_security_probability':row['selection_probability'],'original_security_weight':row['sampling_weight'],
            'original_date_probability':row['date_inclusion_probability'],'original_joint_weight':row['joint_sampling_weight'],
            'analysis_date_probability':date_p,'analysis_security_probability':sec_p,'analysis_joint_probability':date_p*sec_p,
            'analysis_joint_weight':1/(date_p*sec_p),'month_planned_n':num,'month_remaining_population_N':den,
            'analysis_weight_numerator':den*row['population_N'],'analysis_weight_denominator':num*row['sample_n']})
    return sorted(sidecar,key=lambda r:(r['cycle_id'],r['security_id']))


def stratum_contrast(rows):
    valid=[r for r in rows if r['observed_opportunity_eligible']]
    weighted={}
    for s in ['PROXY_FLOAT_IN_RANGE','OTHER_EXCHANGE_PRICE_ELIGIBLE']:
        rr=[r for r in valid if r['stratum']==s];W=sum(r['joint_sampling_weight'] for r in rr)
        weighted[s]={'weight':W,'rate':sum(r['joint_sampling_weight']*bool(r['event_id']) for r in rr)/W if W else None,'n':len(rr)}
    if any(v['rate'] is None for v in weighted.values()):return {'status':'INSUFFICIENT_STRATA','strata':weighted}
    scores=[]
    for r in valid:
        st=weighted[r['stratum']];sign=1 if r['stratum']=='PROXY_FLOAT_IN_RANGE' else -1
        scores.append((r,sign*r['joint_sampling_weight']*(bool(r['event_id'])-st['rate'])/st['weight']))
    def cluster(keys):
        sums=defaultdict(float)
        for r,s in scores:sums[tuple(r[k] for k in keys)]+=s
        G=len(sums)
        return G/(G-1)*sum(s*s for s in sums.values()) if G>1 else None
    terms=[cluster(['cycle_id']),cluster(['security_id']),cluster(['cycle_id','security_id'])]
    variance=terms[0]+terms[1]-terms[2] if None not in terms else None
    return {'strata':weighted,'proxy_minus_complementary':weighted['PROXY_FLOAT_IN_RANGE']['rate']-weighted['OTHER_EXCHANGE_PRICE_ELIGIBLE']['rate'],
        'two_way_score_variance':variance,'two_way_score_se':math.sqrt(variance) if variance is not None and variance>=0 else None,
        'confidence_interval':None,'scope':'Descriptive retrospective-proxy association; date/security cluster sensitivity, not a causal float effect or significance test'}


def uncertainty_labels(report,calendar):
    n=len(calendar);counts=dict(Counter(c['cycle_id'][:7] for c in calendar))
    report['month_date_crossed_security_resampling']['limitations']=f'{n} date clusters, allocation {counts}; crossed-security reweighting, not calibrated two-stage confidence interval; temporal serial dependence unresolved.'
    for inc in [report['incidence'],*report['strata'].values()]:
        inc['assumptions']=f'Fixed finite population, planned month allocation {counts}, original security SRSWOR, full response only. Taylor linearization approximation; no iid/normal confidence interval or stationarity claim.'
    return report


def first_counts(tables):
    rows=[r for r in tables['first_outcomes'] if r['condition_policy']=='HIGH_LOW_ONLY' and r['gap_seconds'] is None
          and r['first_touch_evidence_status']=='OBSERVED_SESSIONS_FIRST_VERIFIED']
    return {'initial_events':len(rows),'barriers':{label:dict(Counter(r['barriers'][i]['outcome'] for r in rows))
        for i,label in enumerate(['+3/-3','+5/-3','+10/-5'])}}


def barrier_audit(tables,run_by_cycle,config,limit_per_category=2):
    events={e['event_id']:e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY'}
    first=[o for o in tables['first_outcomes'] if o['condition_policy']=='HIGH_LOW_ONLY' and o['gap_seconds'] is None]
    chosen=[]
    for category in ['UPSIDE_FIRST','DOWNSIDE_FIRST','CENSORED','NEITHER','AMBIGUOUS_SAME_SIP']:
        group=sorted([o for o in first if o['barriers'][0]['outcome']==category],key=lambda r:(r['cycle_id'],r['security_id']))
        chosen.extend(group[:limit_per_category])
    result=[];source_cache={}
    def raw(ref):
        ref=json.loads(ref) if isinstance(ref,str) else ref
        if ref['path'] not in source_cache:
            assert file_hash(ref['path'])==ref['sha256'];source_cache[ref['path']]=read(ref['path'])
        body=source_cache[ref['path']]['results'][ref['row']]
        return body,ref
    for outcome in chosen:
        event=events[outcome['event_id']];root=Path('data/runs',run_by_cycle[event['cycle_id']])
        plan=read(root/'selection.json');op=next(o for o in plan['selected'] if (o['cycle_id'],o['security_id'])==(event['cycle_id'],event['security_id']))
        cycle=next(c for c in plan['calendar'] if c['cycle_id']==event['cycle_id']);cfg=runtime_config(plan['config'])
        pair=root/'ticks'/('cycle='+event['cycle_id'])/('security='+event['security_id']);saved=read(pair/'ingest.json')
        conditions={r['id']:r for r in read(root/'context.json')['conditions']}
        states,_,_=replay(saved['paths'],read(saved['coverage_path']),op,cycle,cfg,conditions)
        state=states['HIGH_LOW_ONLY'];anchor=next(i for i,r in enumerate(state.eligible) if r['record_id']==event['record_id'])
        assert state.event['record_id']==event['record_id']
        entry=number(event['touch_price']);upper=entry*number('1.03');lower=entry*number('.97')
        grouped=defaultdict(list)
        for r in state.eligible[anchor+1:]:grouped[r['sip_timestamp']].append(r)
        hit=None;support=[];earlier_groups=0
        for t,rows in sorted(grouped.items()):
            up=any(number(r['price'])>=upper for r in rows);down=any(number(r['price'])<=lower for r in rows)
            if up or down:
                hit=t;direction='AMBIGUOUS_SAME_SIP' if up and down else 'UPSIDE_FIRST' if up else 'DOWNSIDE_FIRST'
                support=[r for r in rows if number(r['price'])>=upper or number(r['price'])<=lower]
                break
            earlier_groups+=1
        barrier=outcome['barriers'][0]
        assert hit==barrier['first_passage_ns']
        if hit is not None:assert direction==barrier['observed_direction']
        evidence=[]
        for row in [state.eligible[anchor],*support[:2]]:
            body,ref=raw(row['source_json']);assert digest(body)==row['record_id'] and body['sip_timestamp']==row['sip_timestamp']
            restored=None
            if row.get('restoration_source'):
                restored,_=raw(row['restoration_source']);assert number(restored['price'])==number(row['price'])
            else:assert number(body['price'])==number(row['price'])
            evidence.append({'eligible_record':row,'raw_trade':body,'source':ref,'restored_original_fields':restored})
        key=correction_key(state.eligible[anchor])
        notices=[r for r in iter_normalized(saved['paths']) if r.get('correction') in {10,11,12} and correction_key(r)==key]
        corrections=[]
        for notice in notices:
            body,ref=raw(notice['source_json']);corrections.append({'timestamp':notice['sip_timestamp'],'raw_notice':body,'source':ref,
                'known_by_barrier':hit is not None and notice['sip_timestamp']<=hit})
        result.append({'event_id':event['event_id'],'ticker':event['ticker'],'cycle_id':event['cycle_id'],'source_run':run_by_cycle[event['cycle_id']],
            'initial_price':event['touch_price'],'upper_price':str(upper),'lower_price':str(lower),'frozen_barrier':barrier,
            'earlier_eligible_sip_groups_without_a_hit':earlier_groups,'earlier_eligible_barrier_hits':0,
            'chronological_first_hit_verified':True,'raw_evidence':evidence,'initial_trade_correction_notices':corrections,
            'unmatched_correction_evidence_times':state.unknown_times,'executable_fill_claim':False})
    return {'examples':result,'selection':'Earliest cycle/security within each observed result category; up to two, not selected by return magnitude.',
            'all_first_hits_verified':True,'thresholds_unchanged':True}


def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')


def supplement(tables,plan,calendar,config,dest):
    primary=[r for r in tables['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY']
    st=uncertainty_labels(statistics(primary,calendar,plan,config),calendar)
    es=estimands(tables,plan,calendar)
    es['weights']='Separate derived month/date plan probabilities times original security n/N; source values unchanged.'
    weighted=analysis_rows(tables['confirmation'],calendar,plan['date_strata'])
    by_stratum={}
    for stratum in config['strata']:
        subset={k:[r for r in rows if r.get('stratum')==stratum or
                    (r.get('cycle_id'),r.get('security_id')) in {(p['cycle_id'],p['security_id']) for p in primary if p['stratum']==stratum}]
                for k,rows in tables.items()}
        by_stratum[stratum]=estimands(subset,plan,calendar)
    dump(dest/'statistical-preparation.json',st);dump(dest/'statistical-results.json',es)
    dump(dest/'stratum-estimands.json',by_stratum)
    dump(dest/'design-weighted-policy-metrics.json',weighted_policies(weighted))
    derived=analysis_rows(primary,calendar,plan['date_strata'])
    dump(dest/'float-stratum-difference.json',stratum_contrast(derived))
    dump(dest/'first-passage-counts.json',first_counts(tables))
    sec=[r for r in primary if r.get('sec_evidence')]
    dump(dest/'sec-secondary-overlap.json',{'opportunities':len(sec),'classifications':dict(Counter(r['sec_evidence']['classification'] for r in sec)),
        'verified_primary_events':sum(bool(e.get('sec_evidence')) and e['observed_sessions_first_verified'] for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY'),
        'carry_forward':False,'historical_float_gate_changed':False})
    ev=[e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY'];odd=[e for e in tables['events'] if e['condition_policy']=='ODD_LOT_OBSERVATION_SENSITIVITY']
    index={(e['cycle_id'],e['security_id']):e for e in ev}
    dump(dest/'odd-lot-sensitivity.json',{'primary_events':len(ev),'odd_events':len(odd),'added_events':sum((e['cycle_id'],e['security_id']) not in index for e in odd),
        'changed_touch_timestamps':sum((e['cycle_id'],e['security_id']) in index and e['event_timestamp']!=index[e['cycle_id'],e['security_id']]['event_timestamp'] for e in odd),
        'fixed_primary_confirmation_risk_set':True})
    gap=[]
    for policy in config['condition_policies']:
        for gp in ['NO_MECHANICAL_GAP','GAP_300_SECONDS','GAP_900_SECONDS']:
            rr=[r for r in tables['first_outcomes'] if r['condition_policy']==policy and r['gap_policy']==gp]
            gap.append({'condition_policy':policy,'gap_policy':gp,'initial_events':len(rr),
                'barriers':{label:dict(Counter(r['barriers'][i]['outcome'] for r in rr)) for i,label in enumerate(['+3/-3','+5/-3','+10/-5'])}})
    dump(dest/'gap-sensitivity.json',gap)
    return st,es


def cumulative(batch_config,batch_tables,test_receipt):
    cfg=read(CUM_CONFIG);root=Path('data/runs',cfg['run_id']);dest=Path('reports',cfg['run_id'])
    original=read(Path('data/runs',cfg['source_temporal_run'],'selection.json'));source_files={};tables={};run_by_cycle={}
    for run in cfg['source_runs']:
        path=Path('reports',run,'event-level-results.json');source_files[str(path)]=file_hash(path);part=read(path)
        for name,rows in part.items():
            tables.setdefault(name,[]).extend({**r,'source_run_id':run} for r in rows)
        dates={r['cycle_id'] for r in part['opportunities']}
        if set(run_by_cycle)&dates:raise ValueError('Overlapping batch dates')
        run_by_cycle.update({c:run for c in dates})
    if len(run_by_cycle)!=30 or set(run_by_cycle)!={c['cycle_id'] for c in original['calendar']}:raise ValueError('Full30 dates differ')
    sidecar=full_weights(tables['opportunities'],original,cfg)
    if Counter(r['stratum'] for r in sidecar)!=Counter({'PROXY_FLOAT_IN_RANGE':360,'OTHER_EXCHANGE_PRICE_ELIGIBLE':360}):raise ValueError('Strata do not reconcile')
    metadata=read(Path('data/runs',batch_config['source_m1_run'],'calendar.json'))
    assert sum(c['split_group']=='EXPLORATION' for c in metadata)==80 and sum(c['split_group']=='HOLDOUT' for c in metadata)==40
    assert not {c['cycle_id'] for c in metadata if c['split_group']=='HOLDOUT'} & set(run_by_cycle)
    identity={'config':cfg,'source_files':source_files,'original_selection_sha256':file_hash(Path('data/runs',cfg['source_temporal_run'],'selection.json')),
        'analysis_code_sha256':file_hash(__file__)}
    root.mkdir(parents=True,exist_ok=True);dest.mkdir(parents=True,exist_ok=True)
    if (root/'execution.json').exists():assert read(root/'execution.json')==identity,'Cumulative immutable analysis drift'
    dump(dest/'source-event-level-results.json',tables);dump(dest/'analytical-weights.json',sidecar)
    for name,rows in tables.items():event_table(root/name/(name+'.parquet'),rows)
    st,es=supplement(tables,original,original['calendar'],batch_config,dest)
    event_table(dest/'event_results.parquet',tables['confirmation']);event_table(dest/'distributions.parquet',tables['first_outcomes'])
    event_table(dest/'cohort_metrics.parquet',read(dest/'design-weighted-policy-metrics.json'))
    cycles=[]
    for c in original['calendar']:
        oo=[r for r in tables['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY' and r['cycle_id']==c['cycle_id']]
        ee=[e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY' and e['cycle_id']==c['cycle_id']]
        cycles.append({'cycle_id':c['cycle_id'],'source_run':run_by_cycle[c['cycle_id']],'selected':len(oo),'complete':sum(r['complete_observed_sessions'] for r in oo),
            'known_first_touch_denominator':sum(r['observed_opportunity_eligible'] for r in oo),'events':len(ee),
            'zero_events':sum(r['zero_event_observed'] for r in oo),'sessions':dict(Counter(e['session'] for e in ee))})
    event_table(dest/'cycle_metrics.parquet',cycles);dump(dest/'cycle_metrics.json',cycles)
    audit=barrier_audit(tables,run_by_cycle,batch_config);dump(dest/'raw-barrier-audit.json',audit)
    primary=[r for r in tables['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY']
    summary={'run_id':cfg['run_id'],'dates':30,'selected_opportunities':len(primary),'complete_trade_windows':sum(r['complete_observed_sessions'] for r in primary),
        'known_first_touch_denominator':sum(r['observed_opportunity_eligible'] for r in primary),
        'verified_first_touch_events':es['first_touch_n'],'zero_events':sum(r['zero_event_observed'] for r in primary),
        'sessions':dict(Counter(e['session'] for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY' and e['observed_sessions_first_verified'])),
        'source_runs':cfg['source_runs'],'development_pooled':False,'holdout_analyzed':False,'analytical_month_allocation':[6,9,9,6]}
    dump(dest/'summary.json',summary);dump(dest/'sampling-weight-audit.json',{'original_weights_unchanged':True,'sidecar_rows':720,
        'source_selection_sha256':identity['original_selection_sha256'],'date_plan_probabilities':cfg['date_probabilities'],
        'definition':'Separate analytical weights = inverse(original planned date probability * original security probability); never batch1 or batch2 conditional weights',
        'source_table_hashes':source_files,'original_partition':{'EXPLORATION':80,'HOLDOUT':40},'development_dates_in_cumulative':0,'duplicate_security_cycle_opportunities':0})
    for name in tables:assert records(root/name/(name+'.parquet'))==tables[name]
    risk={e['event_id'] for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY' and e['observed_sessions_first_verified']}
    counts=Counter((r['condition_policy'],r['policy']) for r in tables['confirmation'])
    assert all(v==len(risk) for v in counts.values())
    dump(dest/'validation.json',{'status':'PASS','dates':30,'opportunities':720,'derived_weight_rows':720,
        'source_weights_unchanged':True,'no_duplicate_opportunities':True,'full_json_equals_parquet':True,
        'confirmation_initial_risk_set':len(risk),'confirmation_policy_rows':len(tables['confirmation']),
        'raw_barrier_examples_verified':len(audit['examples']),'source_hashes':source_files,'holdout_analyzed':False})
    dump(dest/'data_quality.json',{'unknown_opportunities':sum(not r['observed_opportunity_eligible'] for r in primary),
        'strict_full_cycle_verified':False,'current_float_is_historical_pit':False,'source_runs':cfg['source_runs'],'quote_scope':'Event-centered only; no executable coverage claim'})
    dump(dest/'statistical_tests.json',{'formal_confidence_intervals':None,'significance_claim':False,'bootstrap_ranges_are_uncalibrated':True})
    dump(dest/'anomalies.json',{'source_price_quality_flags_preserved':True,'raw_audit':'raw-barrier-audit.json'})
    dump(dest/'tests.json',test_receipt)
    write_json(root/'execution.json',identity)
    return cfg,root,dest,original,tables,st,es


def bundle(root,dest,cfg,calendar):
    import hashlib
    import pyarrow.parquet as pq
    files={p.name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in dest.iterdir() if p.is_file() and p.name not in {'manifest.json','research_bundle.zip','bundle-validation.json'}}
    manifest={'contract_version':'research-bundle-v1','experiment_id':cfg['run_id'],'research_configuration':cfg,'configuration_hash':digest(cfg),
        'requested_trading_cycles':[c['cycle_id'] for c in calendar],'processed_trading_cycles':[c['cycle_id'] for c in calendar],
        'event_definitions':'Unchanged frozen observed first-touch and TASK003.1 confirmation policies',
        'outcome_definitions':'Own/common clocks, original barriers/corrections/censoring; all missingness retained',
        'timezone':'America/New_York; SIP UTC nanoseconds','schema_versions':{'weights':'full30-analytical-weights-v1'},'files':files,
        'execution_status':'COMPLETE' if read(dest/'summary.json')['complete_trade_windows']==len(calendar)*24 else 'INCOMPLETE',
        'event_population':f'{len(calendar)} frozen temporal dates; development excluded','size_policy':'Full results, no raw ticks, no truncation',
        'raw_ticks_included':False,'execution_sha256':file_hash(root/'execution.json'),
        'record_counts':{p.name:pq.ParquetFile(p).metadata.num_rows for p in dest.glob('*.parquet')}}
    write_json(dest/'manifest.json',manifest)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['manifest.json',*files]:z.write(dest/name,name)
    with zipfile.ZipFile(dest/'research_bundle.zip') as z:
        assert z.testzip() is None
        for name,info in files.items():assert hashlib.sha256(z.read(name)).hexdigest()==info['sha256']
    write_json(dest/'bundle-validation.json',{'status':'PASS','bytes':(dest/'research_bundle.zip').stat().st_size,
        'sha256':file_hash(dest/'research_bundle.zip'),'record_counts':manifest['record_counts'],'raw_ticks_included':False})


def thai_report(dest,cfg,summary,st,es,batch2_counts,kind):
    n=es['first_touch_n'];lines=[f'# TASK 004.2 — {kind}','',f"Run `{cfg['run_id']}`; baseline `89b1a6a`",'',
        f"Selected {summary['selected_opportunities']}; complete trade windows {summary['complete_trade_windows']}; verified first touches {n}; development10แยก; holdout40ไม่วิเคราะห์.",'',
        f"Design-weighted first-touch incidence {st['incidence']['weighted_incidence']:.3%}; date clusters {st['incidence'].get('date_clusters')}; security clusters {st['incidence'].get('security_clusters')}.",
        'Original source weightsไม่เปลี่ยน; batch3วิเคราะห์allocation1/4/4/1 และfull30ใช้6/14,9/22,9/21,6/13คูณsecurity n/Nในsidecarแยก ห้ามใช้batch1conditionalweightsหรือbatch2weightsแทนfull30.',
        '', '## First-passage audit','',f"Batch2 frozen +3/-3 ยังเป็น {batch2_counts} ไม่แก้ข้อมูล/threshold.",'', '| Barrier | Outcomes |','|---|---|']
    for label,b in es['barriers'].items():lines.append(f"| {label} | {b['counts']} |")
    lines+=['','Weighted bucket fractions, denominator/missingness และdate/security cluster sensitivitiesอยู่ใน statistical-results.json ไม่ตัดcensoredทิ้ง ไม่ใช้trade barriersเป็นexecutable fills.',
        '', '## Confirmation บน initial risk set เดียวกัน','','| Policy | Initial | Status counts |','|---|---:|---|']
    for policy,value in es['confirmation'].items():lines.append(f"| {policy} | {n} | {value['status_counts']} |")
    lines+=['','## Common/own clocks และ censoring','', '| Own horizon C0 | Observed / initial | Median observed return |','|---|---:|---:|']
    for h,value in es['forward'].items():
        r=value['return'];lines.append(f"| {h} | {r['observed_n']}/{r['initial_n']} | {r['distribution']['median']} |")
    lines += ['',f"Observed MFE: {es['observed_mfe']['distribution']}",f"Observed MAE: {es['observed_mae']['distribution']}",
        'Common touch+5/15/30/60-minute paired comparisonsเก็บunmatched/unconfirmed/insufficient/censoredครบ Own-signal horizonsแยกกัน ไม่ตีความsurvivor-onlyreturnmeanเป็นcausal improvement. Pre-confirmation paths, odd-lot, gap300/900s และSECsecondarycontextเก็บแยก ไม่มีhistoricalfloatapproval.',
        '', '## Uncertainty และข้อจำกัด','',f"Taylor incidence SE {st['incidence'].get('two_stage_taylor_se')}; status {st['incidence']['uncertainty_status']}.",
        f"Resampling {st['month_date_crossed_security_resampling']} เป็นillustrative range ไม่ใช่formalconfidenceinterval. Date/securityclustering, repeatedsecurities, serialdependence และcensoringจำกัดinference. ไม่อ้างstatisticallysignificantcontinuation, executableprofitabilityหรือเปลี่ยนpolicyให้ผลดีขึ้น.",
        'Current floatเป็นretrospectiveproxy; historicalfloatยังunresolved, SECไม่forwardfill. Overnight/feedcontinuityและofficialauctioncloseยังไม่ได้รับรองอิสระ. BoundedNBBOเฉพาะfirst-touchquality/C2 ไม่ใช่entry-exitcoverageครบ.',
        '', '## ขั้นถัดไปก่อน holdout','',
        'ควรทำmethodological checksแบบofflineก่อนformal holdout: ตรวจprice-quality/correctionและchronologicalbarriers, วิเคราะห์censoring/quote freshness และกำหนดprimary estimand, nonresponse rules, clustering/uncertaintyและdecision criteriaล่วงหน้า. หากต้องการเพิ่มexploration ต้องอนุมัติและfreezeแผนแยก ไม่ใช้holdoutมาปรับthreshold. หลักฐาน30cyclesนี้ยังไม่เพียงพอให้เริ่มformalholdoutอัตโนมัติ.',
        '', 'Source hashes/weights/source-run links และraw representative auditอยู่ในbundle ไม่มีrawtickbulkหรือcredentialsเข้าGit. Raw revalidationต้องมีlocalimmutablecache. No385quote-topup, noholdout.' ]
    (dest/'report.md').write_text('\n'.join(lines)+'\n')


def finalize(test_output):
    config=read(CONFIG);root,plan=prepare(config);dest=Path('reports',config['run_id']);tables=read(dest/'event-level-results.json')
    for name,rows in tables.items():assert rows==records(root/name/(name+'.parquet'))
    proof=validate_replay(config,root,plan,tables);proof.pop('batch3_acquired',None);proof.update(batch_index=3,batch3_acquired=True)
    write_json(dest/'independent-validation.json',proof)
    m=re.search(r'(?m)^(\d+) passed, (\d+) warnings in [^\n]+$',Path(test_output).read_text());assert m
    tests={'status':'PASS','passed':int(m[1]),'warnings':int(m[2]),'source_hashes':{str(p):file_hash(p) for p in Path('tests').glob('*.py')}}
    write_json(dest/'tests.json',tests)
    original=read(root/'source-selection.json');st,es=supplement(tables,plan,original['calendar'][20:],config,dest)
    by_cycle={c['cycle_id']:config['run_id'] for c in plan['calendar'][:10]}
    dump(dest/'raw-barrier-audit.json',barrier_audit(tables,by_cycle,config))
    previous=read('reports/m4-temporal-batch2-20261115-v1/statistical_results.json')['barriers']['+3/-3']['counts']
    assert previous=={'UPSIDE_FIRST':5,'DOWNSIDE_FIRST':25},'Frozen Batch2 special audit changed'
    dump(dest/'batch2-special-result-preserved.json',{'counts':previous,'source_sha256':file_hash('reports/m4-temporal-batch2-20261115-v1/statistical_results.json'),'unchanged':True})
    thai_report(dest,config,read(dest/'summary.json'),st,es,previous,'Batch 3')
    shutil.copyfile(dest/'report.md','docs/research/task-004-2-temporal-batch3.md')
    shutil.copyfile('docs/plans/TASK-004-2-temporal-batch3.md',dest/'methodology.md')
    package(config,root,dest,plan)
    c_cfg,c_root,c_dest,c_plan,combined,c_st,c_es=cumulative(config,tables,tests)
    thai_report(c_dest,c_cfg,read(c_dest/'summary.json'),c_st,c_es,previous,'Full 30-cycle cumulative temporal analysis')
    shutil.copyfile(c_dest/'report.md','docs/research/task-004-2-cumulative30.md')
    shutil.copyfile('docs/plans/TASK-004-2-temporal-batch3.md',c_dest/'methodology.md')
    dump(c_dest/'development-separate.json',read(Path('reports',config['development_run'],'summary.json')))
    dump(c_dest/'batch2-special-result-preserved.json',read(dest/'batch2-special-result-preserved.json'))
    bundle(c_root,c_dest,c_cfg,c_plan['calendar'])
    print(json.dumps({'batch3':first_counts(tables),'full30':first_counts(combined),'batch3_validation':proof,
                      'full30_summary':read(c_dest/'summary.json'),'full30_incidence':c_st['incidence']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pytest-output',required=True);a=p.parse_args();finalize(a.pytest_output)
