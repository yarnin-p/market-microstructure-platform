"""TASK005 bounded offline audit runner; all source runs remain read-only."""
import argparse
import json
import signal
import socket
import time
import zipfile
from collections import Counter,defaultdict
from pathlib import Path
from unittest.mock import patch
import pyarrow.parquet as pq

from .storage import digest,file_hash,write_json
from .temporal_design import read,protected_hashes
from .temporal_pilot import runtime_config
from .m2_pilot import event_table
from .audit_paths import pages,reconstruct,eligible,cycle_bounds,session,identity,evidence,quote_mark,path_outcomes,dec,S
from .audit_statistics import groups_from_rows,ratio,simulate
from .temporal_statistics import design_incidence,clustered_ratio

CONFIG='configs/task-005-audit-v1.json'


class Budget:
    def __init__(self,config):self.config=config;self.started=time.monotonic();self.raw_bytes=0;self.pages=0
    def check(self):
        if time.monotonic()-self.started>self.config['max_wall_seconds']:raise RuntimeError('WALL_BUDGET')
        if self.raw_bytes>self.config['max_raw_bytes']:raise RuntimeError('RAW_READ_BUDGET')


def denied(*args,**kwargs):raise RuntimeError('NETWORK_FORBIDDEN_IN_OFFLINE_AUDIT')


def source_check(config,budget):
    source=Path('reports',config['source_run']);manifest=read(source/'manifest.json')
    for name,meta in manifest['files'].items():
        if (source/name).exists():assert file_hash(source/name)==meta['sha256'],name
    tables=read(source/'source-event-level-results.json');sidecar=read(source/'analytical-weights.json')
    weights={(r['cycle_id'],r['security_id']):r for r in sidecar}
    original=read('data/runs/m4-temporal-10cycles-20261115-v1/selection.json')
    selected={(r['cycle_id'],r['security_id']):r for r in original['selected']}
    primary=[r for r in tables['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY']
    assert len(primary)==len(selected)==len(weights)==720
    assert Counter(r['stratum'] for r in primary)=={'PROXY_FLOAT_IN_RANGE':360,'OTHER_EXCHANGE_PRICE_ELIGIBLE':360}
    for r in primary:
        key=(r['cycle_id'],r['security_id']);old=selected[key];w=weights[key]
        for k in ['sampling_weight','joint_sampling_weight','selection_probability','date_inclusion_probability','previous_rth_close','m1_record_id']:
            assert r[k]==old[k],k
        expected=1/(r['sample_n']/r['population_N']*old['date_plan_probability'])
        assert abs(w['analysis_joint_weight']-expected)<1e-10
    assert len({(r['cycle_id'],r['security_id']) for r in primary})==720
    assert not {r['cycle_id'] for r in primary}&set(original['development_dates'])
    assert all(c['split_group']=='EXPLORATION' for c in original['calendar'])
    assert len({r['cycle_id'] for r in primary})==30
    for run in {r['source_run_id'] for r in primary}:
        rp=Path('reports',run);m=read(rp/'manifest.json')
        for name,meta in m['files'].items():
            if (rp/name).exists():assert file_hash(rp/name)==meta['sha256']
        for cov in Path('data/runs',run).glob('ticks/cycle=*/security=*/**/coverage.json'):
            pages(read(cov),budget,keep=False)
    for name,rows in tables.items():
        from .m2_report import records
        assert records(Path('data/runs',config['source_run'],name,name+'.parquet'))==rows
    return tables,original,weights,primary


def audit_event(event,baselines,op,cycle,cfg,conditions,pair,budget):
    coverage=read(pair/'trades/coverage.json');raw,duplicates=pages(coverage,budget)
    rows=reconstruct(raw);b=cycle_bounds(cycle);paths={};reject={};unknown=[]
    for policy,odd in [('HIGH_LOW_ONLY',False),('ODD_LOT_OBSERVATION_SENSITIVITY',True)]:
        accepted=[];counts=Counter()
        for r in rows:
            ok,reason=eligible(r,b,conditions,cfg['max_participant_lag_seconds'],odd)
            if ok:accepted.append(r)
            else:counts[reason]+=1
            if not odd and reason in ['UNKNOWN_TRADE_CONDITION','CORRECTION_RECONSTRUCTION_UNRESOLVED','INVALID_TIMESTAMP']:unknown.append(r['sip_timestamp'])
        paths[policy]=accepted;reject[policy]=dict(counts)
    threshold=dec(op['previous_rth_close'])*dec('1.10');p=paths['HIGH_LOW_ONLY']
    touch=next((r for r in p if dec(r['price'])>=threshold),None);discrepancies=[]
    if touch is None:raise AssertionError('Stored event not independently reconstructed')
    for key,value in [('record_id',touch['_id']),('event_timestamp',touch['sip_timestamp']),('touch_price',str(dec(touch['price']))),('threshold_price',str(threshold))]:
        if event[key]!=value:discrepancies.append({'field':key,'baseline':event[key],'audit':value})
    expected_id=digest(['task-002-1-observed-sessions-v2','HIGH_LOW_ONLY',op['security_id'],cycle['cycle_id'],touch['_id']])
    assert expected_id==event['event_id']
    notices=[r for r in rows if r.get('correction') in [10,11,12]]
    invalidations=[r['sip_timestamp'] for r in notices if identity(r)==identity(touch) and r['sip_timestamp']>=touch['sip_timestamp']]
    qrows=[];qcovs=[]
    for qpath in sorted(pair.glob('quotes/*/coverage.json')):
        qc=read(qpath);qr,_=pages(qc,budget);qrows.extend(qr);qcovs.append(qc)
    qrows=sorted({r['_id']:r for r in qrows}.values(),key=lambda r:(r['sip_timestamp'],r.get('sequence_number') or 0,r['_id']))
    mark=quote_mark(qrows,qcovs,touch['sip_timestamp'],cfg)
    if mark['status']=='OK':mark['trade_relation']='ABOVE_ASK' if dec(touch['price'])>dec(mark['ask']) else 'BELOW_BID' if dec(touch['price'])<dec(mark['bid']) else 'WITHIN_NBBO'
    results=[]
    for gap in [None,300,900]:
        barriers,forward=path_outcomes(p,touch,b,unknown,invalidations,cfg,gap,coverage['complete'])
        baseline=baselines[gap]
        for i,(a,z) in enumerate(zip(barriers,baseline['barriers'])):
            for k in ['outcome','first_passage_ns','observed_direction']:
                if a[k]!=z[k]:discrepancies.append({'gap':gap,'barrier':i,'field':k,'baseline':z[k],'audit':a[k]})
            for support in a['support']:
                support['quote']=quote_mark(qrows,qcovs,support['sip_timestamp'],cfg)
                source_row=next(r for r in p if r['_id']==support['record_id'])
                support['later_correction_notices']=[evidence(n) for n in notices if identity(n)==identity(source_row) and n['sip_timestamp']>=support['sip_timestamp']]
        for a,z in zip(forward,baseline['forward']):
            if a['censored']!=z['censored'] or (dec(a['return']) if a['return'] is not None else None)!=(dec(z['return']) if z['return'] is not None else None):
                discrepancies.append({'gap':gap,'horizon':a['horizon'],'baseline_censored':z['censored'],'audit':a})
            a['baseline_flags']=z['flags']
            if a['censored'] and a['root_causes']==['PRICE_MARK_FRESHNESS_FAILURE']:
                a['missingness_interpretation']='NO_RECENT_ELIGIBLE_PRINT_IN_PAGINATION_COMPLETE_WINDOW; ILLIQUIDITY_COMPATIBLE_NOT_PROOF'
            elif a['censored']:a['missingness_interpretation']=';'.join(a['root_causes'])
            else:a['missingness_interpretation']='COMPLETE_OBSERVED_MARK'
        results.append({'gap_seconds':gap,'barriers':barriers,'forward':forward})
    odd=next((r for r in paths['ODD_LOT_OBSERVATION_SENSITIVITY'] if dec(r['price'])>=threshold),None)
    raw_candidate=next((r for r in rows if dec(r.get('price')) is not None and dec(r['price'])>=threshold),None)
    return {'event_id':event['event_id'],'cycle_id':event['cycle_id'],'security_id':event['security_id'],'ticker':event['ticker'],
        'source_run_id':event['source_run_id'],'session':session(touch['sip_timestamp'],b),'previous_rth_close':str(op['previous_rth_close']),
        'threshold':str(threshold),'touch':evidence(touch),'overshoot_relative_to_threshold':str(dec(touch['price'])/threshold-1),
        'touch_quote':mark,'raw_first_crossing':evidence(raw_candidate),'odd_touch':evidence(odd),
        'odd_touch_changed':odd['_id']!=touch['_id'] if odd else None,'raw_rows':len(raw),'duplicates':duplicates,'eligible_rows':len(p),
        'rejections':reject,'correction_codes':dict(Counter(str(r.get('correction',0)) for r in rows)),
        'touch_correction_notices':[evidence(r) for r in notices if identity(r)==identity(touch)],
        'restored_rows':sum('_restoration_source' in r for r in rows),'unknown_prior':any(t<=touch['sip_timestamp'] for t in unknown),
        'same_sip_touch_rows':sum(r['sip_timestamp']==touch['sip_timestamp'] for r in p),
        'same_sip_multiple_prices':len({str(r['price']) for r in p if r['sip_timestamp']==touch['sip_timestamp']})>1,
        'complete_pagination':coverage['complete'],'outcomes':results,'discrepancies':discrepancies}


def confirmation_audit(tables):
    risk={e['event_id'] for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY'};rows=tables['confirmation'];groups=defaultdict(list);errors=[];paired=0
    for r in rows:groups[r['condition_policy'],r['policy']].append(r)
    for key,rr in groups.items():
        if {r['initial_event_id'] for r in rr}!=risk or len(rr)!=len(risk):errors.append({'risk_set':key})
    c0={(r['condition_policy'],r['initial_event_id']):r for r in rows if r['policy']=='C0_FROZEN'}
    for r in rows:
        for a,b in zip(r['common_landmarks'],c0[r['condition_policy'],r['initial_event_id']]['common_landmarks']):
            if (a['target_ns'],a['exit_observation_ns'],a['exit_price'])!=(b['target_ns'],b['exit_observation_ns'],b['exit_price']):errors.append({'common_clock':r['event_id']})
            if a['return'] is not None and not a['confirmed_before_or_at_landmark']:errors.append({'early_return':r['event_id']})
            paired+=1
    return {'status':'PASS' if not errors else 'BLOCKED','initial_risk_set':len(risk),'common_marks_checked':paired,'errors':errors,
        'policies':{str(k):{'initial':len(v),'statuses':dict(Counter(r['signal']['status'] for r in v)),
            'landmark_statuses':{str(m):dict(Counter(next(a for a in r['common_landmarks'] if a['landmark_minutes']==m)['status'] for r in v)) for m in [5,15,30,60]}} for k,v in groups.items()},
        'c2_underpowered':True,'causal_or_executable_claim':False}


def statistics(primary,audits,weights,original):
    index={(r['cycle_id'],r['security_id']):r for r in audits};rows=[];ys=[];zs=[];unknown=[]
    for r in primary:
        key=(r['cycle_id'],r['security_id']);e=index.get(key);outcome=e['outcomes'][0]['barriers'][0]['outcome'] if e else None
        rows.append({**r,'joint_sampling_weight':weights[key]['analysis_joint_weight'],'date_inclusion_probability':weights[key]['analysis_date_probability']})
        ys.append(1 if outcome=='DOWNSIDE_FIRST' else -1 if outcome=='UPSIDE_FIRST' else 0);zs.append(int(e is not None));unknown.append(int(outcome in ['CENSORED','AMBIGUOUS_SAME_SIP']))
    population={r['month']:r['population_N'] for r in original['date_strata']}
    result=ratio(groups_from_rows(rows,ys,zs),population)
    # Never display a formal interval for an exploratory, selected primary question.
    result['candidate_interval_exploratory_only']=result.pop('interval')
    result['formal_confidence_interval']=None
    result['censoring_identification_bounds']={'lower':ratio(groups_from_rows(rows,[y-u for y,u in zip(ys,unknown)],zs),population)['estimate'],
        'upper':ratio(groups_from_rows(rows,[y+u for y,u in zip(ys,unknown)],zs),population)['estimate']}
    event_rows=[{**r,'contrast':y} for r,y,z in zip(rows,ys,zs) if z]
    result['crossed_date_security_sensitivity']=clustered_ratio(event_rows,'contrast')
    def estimate_domain(predicate):
        zz=[z*predicate(r) for r,z in zip(rows,zs)];yy=[y*predicate(r) for r,y in zip(rows,ys)]
        return ratio(groups_from_rows(rows,yy,zz),population)
    panels={key:{str(v):estimate_domain(lambda r:r[key]==v) for v in sorted({r[key] for r in rows})} for key in ['month','cycle_id','stratum']}
    panels['session']={s:estimate_domain(lambda r:(index.get((r['cycle_id'],r['security_id'])) or {}).get('session')==s) for s in ['AH','PRE','RTH']}
    leave_security={s:estimate_domain(lambda r:r['security_id']!=s)['estimate'] for s in sorted({r['security_id'] for r in event_rows})}
    leave_date={d:estimate_domain(lambda r:r['cycle_id']!=d)['estimate'] for d in sorted({r['cycle_id'] for r in rows})}
    strata=[{**s,'batch_n':s['plan_n']} for s in original['date_strata']]
    old=design_incidence(rows,strata);new=ratio(groups_from_rows(rows,zs,[1]*len(rows)),population)
    assert abs(old['weighted_incidence']-new['estimate'])<1e-12 and abs(old['two_stage_taylor_se']-new['se'])<1e-12
    return {'primary_contrast_down_minus_up':result,'panel_sensitivities':panels,'leave_one_security_out':leave_security,'leave_one_date_out':leave_date,
        'incidence_estimator_reconciliation':{'status':'PASS','old':old,'independent':new},'zero_event_rows_retained_for_variance':len(rows)-sum(zs),
        'missing_return_imputation':False,'primary_origin':'Exploratory hypothesis selected after Full30; not confirmatory evidence',
        'variance_scope':'Fixed finite population under randomized sampling. Repeated-security and serial outcome dependence do not imply independent events; process/generalization uncertainty remains uncalibrated.'}


def execute(config):
    root=Path('data/runs',config['run_id']);dest=Path('reports',config['run_id'])
    if root.exists():raise ValueError('Immutable audit run already exists; use a new explicitly versioned ID')
    root.mkdir(parents=True);dest.mkdir(parents=True)
    write_json(root/'protected.json',protected_hashes(config['run_id']))
    write_json(root/'execution.json',{'config':config,'code_hashes':{str(p):file_hash(p) for p in Path('market_lab').glob('*.py')},
        'source_manifest_sha256':file_hash(Path('reports',config['source_run'],'manifest.json'))})
    budget=Budget(config);audits=[]
    tables,original,weights,primary=source_check(config,budget)
    events=[e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY'];assert len(events)==config['max_events']==93
    assert all(e['observed_sessions_first_verified'] for e in events)
    assert sum(o['zero_event_observed'] for o in primary)==627
    config_cache={};m1cache={};plans={};contexts={}
    for e in sorted(events,key=lambda e:(e['cycle_id'],e['security_id'])):
        budget.check();run=e['source_run_id'];rr=Path('data/runs',run)
        if run not in plans:plans[run]=read(rr/'selection.json');contexts[run]=read(rr/'context.json');config_cache[run]=runtime_config(plans[run]['config'])
        plan=plans[run];op=next(o for o in primary if (o['cycle_id'],o['security_id'])==(e['cycle_id'],e['security_id']))
        cycle=next(c for c in plan['calendar'] if c['cycle_id']==e['cycle_id'])
        source=op['source_m1'];assert file_hash(source['path'])==source['sha256']
        if source['path'] not in m1cache:m1cache[source['path']]={r['record_id']:r for r in pq.ParquetFile(source['path']).read().to_pylist()}
        m1=m1cache[source['path']][op['m1_record_id']]
        assert dec(m1['previous_rth_close'])==dec(op['previous_rth_close']) and m1['security_id']==op['security_id']
        pair=rr/'ticks'/('cycle='+e['cycle_id'])/('security='+e['security_id'])
        baselines={r['gap_seconds']:r for r in tables['first_outcomes'] if r['event_id']==e['event_id']}
        result=audit_event(e,baselines,op,cycle,config_cache[run],{r['id']:r for r in contexts[run]['conditions']},pair,budget)
        result['m1_basis']={k:m1[k] for k in ['primary_exchange_raw','canonical_exchange','exchange_status','action_status','action_reason','change_status','reference_close_method','reference_availability_status']}
        result['m1_source']=source;audits.append(result)
        write_json(root/'checkpoints'/(e['event_id']+'.json'),result)
        print(json.dumps({'audited':len(audits),'ticker':e['ticker'],'cycle':e['cycle_id'],'discrepancies':len(result['discrepancies'])}),flush=True)
    write_json(dest/'event-audits.json',audits);event_table(root/'events/events.parquet',audits)
    stat=statistics(primary,audits,weights,original);write_json(dest/'statistical_results.json',stat)
    fairness=confirmation_audit(tables);write_json(dest/'confirmation-fairness.json',fairness)
    calibration=simulate(config['simulation_replicates'],config['simulation_seed']);write_json(dest/'estimator-calibration.json',calibration)
    counts={str(g):{label:dict(Counter(a['outcomes'][gi]['barriers'][i]['outcome'] for a in audits)) for i,label in enumerate(['+3/-3','+5/-3','+10/-5'])} for gi,g in enumerate([None,300,900])}
    censor=[]
    for a in audits:
        for outcome in a['outcomes']:
            for mark in outcome['forward']:censor.append({'event_id':a['event_id'],'cycle_id':a['cycle_id'],'security_id':a['security_id'],'ticker':a['ticker'],'session':a['session'],'gap_seconds':outcome['gap_seconds'],**mark})
    write_json(dest/'censoring-evidence.json',censor);event_table(root/'censoring/censoring.parquet',censor)
    quality={'barrier_counts':counts,'touch_sizes':dict(Counter('BELOW_100_SHARES' if dec(a['touch']['size'])<100 else 'AT_LEAST_100_SHARES' for a in audits)),
        'odd_touch_changed':sum(a['odd_touch_changed'] for a in audits),'quote_statuses':dict(Counter(a['touch_quote']['status'] for a in audits)),
        'quote_relations':dict(Counter(a['touch_quote'].get('trade_relation','UNAVAILABLE') for a in audits)),
        'touch_correction_cases':sum(bool(a['touch_correction_notices']) for a in audits),'restored_rows':sum(a['restored_rows'] for a in audits),
        'same_sip_multiple_prices':sum(a['same_sip_multiple_prices'] for a in audits),
        'censoring':{str(g):{h:{'observed':sum(not r['censored'] for r in censor if r['gap_seconds']==g and r['horizon']==h),
            'censored':sum(r['censored'] for r in censor if r['gap_seconds']==g and r['horizon']==h),
            'root_causes':dict(Counter(c for r in censor if r['gap_seconds']==g and r['horizon']==h for c in r['root_causes']))} for h in ['5m','15m','30m','60m','session_end','cycle_end']} for g in [None,300,900]},
        'root_causes_overlap':True,'no_eligible_print_is_not_proof_of_feed_loss_or_halt':True,
        'quote_freshness_does_not_censor_trade_only_return':True,'official_auction_close_independently_verified':False}
    write_json(dest/'data_quality.json',quality)
    discrepancy=[{'event_id':a['event_id'],'findings':a['discrepancies']} for a in audits if a['discrepancies']]
    write_json(dest/'anomalies.json',{'discrepancies':discrepancy,'trade_above_ask':[a['event_id'] for a in audits if a['touch_quote'].get('trade_relation')=='ABOVE_ASK'],
        'unknown_prior':[a['event_id'] for a in audits if a['unknown_prior']]})
    for p,h in read(root/'protected.json').items():assert file_hash(p)==h,'Prior artifact changed: '+p
    for p,h in read(root/'execution.json')['code_hashes'].items():assert file_hash(p)==h,'Audit code drift'
    totalbytes=sum(p.stat().st_size for folder in [root,dest] for p in folder.rglob('*') if p.is_file());assert totalbytes<config['max_output_bytes'];budget.check()
    summary={'run_id':config['run_id'],'events_audited':len(audits),'opportunities_verified':len(primary),'zero_event_opportunities':627,
        'discrepancy_events':len(discrepancy),'primary_barrier_counts':counts['None']['+3/-3'],'protected_files_unchanged':len(read(root/'protected.json')),
        'market_data_requests':0,'network_blocked_in_audit_process':True,'holdout_executed':False,'development_pooled':False,
        'raw_bytes_read':budget.raw_bytes,'raw_pages_checked_including_rereads':budget.pages,'elapsed_seconds':time.monotonic()-budget.started,
        'output_bytes_before_package':totalbytes,'readiness':'BLOCKED' if discrepancy or fairness['errors'] else 'CONDITIONAL',
        'calibration_all_scenarios_above_floor':all(r['coverage_all_replicates']>=config['minimum_simulation_coverage'] for r in calibration),
        'formal_statistical_validation':False}
    write_json(dest/'summary.json',summary);write_json(dest/'validation.json',{'status':'PASS' if not discrepancy and not fairness['errors'] else 'FINDINGS',**summary})
    return root,dest,summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);a=p.parse_args();config=read(a.config)
    def timeout(*args):raise RuntimeError('AUDIT_WALL_BUDGET')
    signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,config['max_wall_seconds'])
    import requests
    with patch.object(requests.sessions.Session,'request',denied),patch.object(socket,'create_connection',denied):
        try:
            _,_,result=execute(config);print(json.dumps(result,indent=2))
        except Exception as e:
            d=Path('reports',config['run_id']);d.mkdir(parents=True,exist_ok=True)
            write_json(d/'failure.json',{'status':'BLOCKED','error':type(e).__name__+': '+str(e),'market_data_requests':0,'holdout_executed':False})
            raise
        finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':main()
