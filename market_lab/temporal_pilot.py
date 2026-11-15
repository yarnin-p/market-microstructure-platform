"""Bounded acquisition and frozen replay across temporally sampled dates."""
import argparse
import fcntl
import json
import signal
import time
import zipfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

import pyarrow.parquet as pq

from .api import load_key
from .confirmation import bid_confirmation,confirmation_outcomes,signal_result
from .confirmation_pilot import coverage_for,quotes_for,stats
from .confirmation_qa import c1_signal,common_marks,waiting_path
from .confirmation_qa_run import summarize
from .m2_pilot import event_table
from .m2_report import records
from .nbbo_probe import BudgetStop
from .replay_methodology import outcome_sensitivity
from .replay_qa import iter_normalized
from .storage import digest,file_hash,write_json
from .systematic_pilot import normalized_pages,replay,nbbo_context
from .temporal_client import TemporalClient
from .temporal_design import CONFIG,prepare,read
from .temporal_statistics import design_incidence,clustered_ratio,crossed_cluster_bootstrap
from .tick_replay import SECOND,ns,number,session_label


class PhaseDeadline(BaseException):pass


def runtime_config(config):
    return {**read('configs/task-002-2-systematic-v1.json'),**read('configs/task-003-confirmation-v1.json'),
            **read('configs/task-003-1-confirmation-qa-v1.json'),**config}


def freeze_execution(config,root):
    frozen={'config':config,'selection_sha256':file_hash(root/'selection.json'),
            'code_hashes':{str(p):file_hash(p) for p in Path('market_lab').glob('*.py')}}
    p=root/'execution.json'
    if p.exists():assert read(p)==frozen,'Immutable execution code/config drift'
    else:write_json(p,frozen)
    return frozen


def ordered_opportunities(plan):
    cycles=[c for c in plan['calendar'] if c['execute_in_initial_batch']]
    buckets={}
    for c in cycles:
        ss=[[o for o in plan['selected'] if o['cycle_id']==c['cycle_id'] and o['stratum']==s] for s in plan['config']['strata']]
        buckets[c['cycle_id']]=[bucket[i] for i in range(12) for bucket in ss]
    return [buckets[c['cycle_id']][i] for i in range(24) for c in cycles]


def acquire(config,root,plan,key,offline=False):
    cfg=runtime_config(config);ops=ordered_opportunities(plan);cycles={c['cycle_id']:c for c in plan['calendar']}
    client=TemporalClient(root,cfg,{o['ticker'] for o in ops},key,offline)
    context=read(root/'context.json');conditions={r['id']:r for r in context['conditions']}
    stop=None;quote_windows=len(list(root.glob('ticks/cycle=*/security=*/quotes/*/coverage.json')))
    def timeout(*args):raise PhaseDeadline()
    old_handler=signal.signal(signal.SIGALRM,timeout)
    if not offline:signal.setitimer(signal.ITIMER_REAL,max(.001,client.deadline-time.monotonic()))
    try:
        for index,op in enumerate(ops):
            cycle=cycles[op['cycle_id']];pair=root/'ticks'/('cycle='+op['cycle_id'])/('security='+op['security_id'])
            checkpoint=pair/'ingest.json'
            if checkpoint.exists():
                cached=read(checkpoint)
                for p,h in cached['input_hashes'].items():assert file_hash(p)==h
                continue
            if not offline:client.check()
            cov=client.window('trades',op['ticker'],ns(cycle['anchor_at']),ns(cycle['end_at']),pair/'trades')
            if not offline and cov.get('error') in {'HTTP_401','HTTP_403'}:raise BudgetStop('API_AUTHORIZATION_DENIED')
            paths,invalid=normalized_pages(cov,op,cycle,pair/'trades/normalized')
            states,raw_count,sessions=replay(paths,cov,op,cycle,cfg,conditions,invalid)
            events=[];opps=[];first_out=[]
            for policy,state in states.items():
                opps.append({**op,'condition_policy':policy,'complete_observed_sessions':state.complete,
                    'observed_opportunity_eligible':state.complete and not state.unknown_prior,
                    'zero_event_observed':state.complete and not state.unknown_prior and state.event is None,
                    'event_id':state.event['event_id'] if state.event else None,'status':'COMPLETE' if state.complete else 'INCOMPLETE',
                    'provider_pages':len(cov['pages']),'raw_rows':cov['raw_rows'],'normalized_rows':raw_count,'raw_sessions':sessions,
                    'invalid_timestamp_rows':invalid,'coverage_error':cov['error'],'reject_counts':dict(state.reject_counts)})
                if not state.event:continue
                e={**state.event,**{k:op[k] for k in ['stratum','sampling_weight','selection_probability','population_N','sample_n',
                    'month','date_inclusion_probability','joint_sampling_weight','joint_inclusion_probability']}}
                qdir=pair/'quotes'/str(e['event_timestamp'])
                if (qdir/'coverage.json').exists() or quote_windows<config['max_quote_windows']:
                    existed=(qdir/'coverage.json').exists()
                    qcov=client.window('quotes',op['ticker'],max(ns(cycle['anchor_at']),e['event_timestamp']-60*SECOND),
                        min(ns(cycle['end_at']),e['event_timestamp']+60*SECOND),qdir)
                    qpaths,qinvalid=normalized_pages(qcov,op,cycle,qdir/'normalized')
                    quotes=[r for p in qpaths for r in pq.ParquetFile(p).read().to_pylist()]
                    e['quote']=nbbo_context(quotes,e,cfg,qcov['complete'] and not qinvalid)
                    if not existed:quote_windows+=1
                else:e['quote']={'status':'QUOTE_WINDOW_BUDGET','trade_relation':'UNKNOWN'}
                events.append(e)
                for gap in config['gap_sensitivities_seconds']:
                    first_out.append(outcome_sensitivity(state,cycle,cfg,gap))
            dependencies={str(p):file_hash(p) for p in pair.rglob('*') if p.is_file()}
            write_json(checkpoint,{'events':events,'opportunities':opps,'first_outcomes':first_out,'paths':paths,
                'coverage_path':str(pair/'trades/coverage.json'),'input_hashes':dependencies})
            print(json.dumps({'opportunity':index+1,'cycle':op['cycle_id'],'ticker':op['ticker'],'complete':cov['complete'],
                'events':len(events),'requests':len(client.ledger['attempts']),'bytes':client.ledger['decoded_bytes']}),flush=True)
    except (BudgetStop,PhaseDeadline) as exc:
        stop=str(exc) or 'ACQUISITION_WALL_TIME_BUDGET'
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
        write_json(root/'acquisition-status.json',{'stop_reason':stop,'quote_windows':quote_windows,
            'completed_checkpoints':len(list(root.glob('ticks/cycle=*/security=*/ingest.json'))),
            'network_phase_closed':True,'deadline_epoch':client.ledger['deadline_epoch'],'http_requests':len(client.ledger['attempts'])})
    return client


def analyze(config,root,plan,recompute=False):
    cfg=runtime_config(config);cycles={c['cycle_id']:c for c in plan['calendar']};conditions={r['id']:r for r in read(root/'context.json')['conditions']}
    opportunities=[];events=[];first_out=[];qa=[];stopped=None
    began=time.monotonic()
    def timeout(*args):raise PhaseDeadline()
    old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,config['analysis_wall_seconds'])
    try:
        for op in ordered_opportunities(plan):
            pair=root/'ticks'/('cycle='+op['cycle_id'])/('security='+op['security_id']);checkpoint=pair/'ingest.json'
            if not checkpoint.exists():
                for policy in config['condition_policies']:
                    opportunities.append({**op,'condition_policy':policy,'complete_observed_sessions':False,'observed_opportunity_eligible':False,
                        'zero_event_observed':False,'event_id':None,'status':'NOT_ACQUIRED','coverage_error':'BUDGET_OR_INTERRUPTION'})
                continue
            saved=read(checkpoint);opportunities.extend(saved['opportunities']);events.extend(saved['events']);first_out.extend(saved['first_outcomes'])
            initial=next((e for e in saved['events'] if e['condition_policy']=='HIGH_LOW_ONLY' and e['observed_sessions_first_verified']),None)
            if not initial:continue
            qacheck=pair/'confirmation.json'
            if qacheck.exists() and not recompute:
                qa.extend(read(qacheck));continue
            cycle=cycles[op['cycle_id']]
            states,_,_=replay(saved['paths'],read(saved['coverage_path']),op,cycle,cfg,conditions)
            notices=[r for r in iter_normalized(saved['paths']) if r.get('correction') in {10,11,12}]
            quotes,intervals=quotes_for(pair);rows=[]
            for condition,state in states.items():
                t0=initial['event_timestamp'];deadline=min(t0+60*SECOND,ns(cycle['end_at']))
                c0=signal_result('C0','CONFIRMED','ORIGINAL_FIRST_TOUCH',t0,initial['touch_price'],
                    [{'record_id':initial['record_id'],'timestamp':t0,'source_json':initial['source_json'],'restoration_source':initial.get('restoration_source')}],
                    trade_record_id=initial['record_id'],market_price_timestamp=t0,market_price_source=initial['source_json'])
                candidates=[('C0_FROZEN',None,None,c0,ns(cycle['end_at'])),('C2_FROZEN',None,None,
                    bid_confirmation(state,initial,cycle,cfg,quotes,coverage_for(intervals,t0,deadline)),deadline)]
                for definition in cfg['c1_definitions']:
                    for d in cfg['deadline_seconds']:
                        sig,end=c1_signal(state,initial,cycle,cfg,notices,definition,d)
                        candidates.append((definition+('_D60' if d else ''),definition,d,sig,end))
                for policy,definition,d,sig,end in candidates:
                    t=sig['signal_timestamp'];price=number(sig['market_observation_price'])
                    if policy=='C2_FROZEN' and t is not None and any(v is None or t0<=v<=t for v in state.unknown_times):
                        sig.update(status='INSUFFICIENT_DATA',reason='UNKNOWN_EVIDENCE_BEFORE_CANDIDATE_CONFIRMATION')
                    outs=[confirmation_outcomes(state,initial,sig,cycle,cfg,notices,g) for g in config['gap_sensitivities_seconds']]
                    row={**op,'event_id':digest([config['run_id'],initial['event_id'],condition,policy]),'initial_event_id':initial['event_id'],
                        'run_id':config['run_id'],'initial_event_timestamp':t0,'initial_touch_price':initial['touch_price'],
                        'original_threshold_price':initial['threshold_price'],'initial_session':initial['session'],'condition_policy':condition,
                        'policy':policy,'definition':definition,'deadline_seconds':d,'signal':sig,'signal_session':session_label(cycle,t) if t else None,
                        'operational_end_ns':end,'delay_seconds':(t-t0)/SECOND if sig['status']=='CONFIRMED' else None,
                        'waiting_price_change':str(price/number(initial['touch_price'])-1) if price is not None and sig['status']=='CONFIRMED' else None,
                        'own_signal_outcomes':[o for o in outs if o is not None],
                        'common_landmarks':common_marks(state,initial,sig,cycle,cfg,notices),
                        'pre_confirmation':waiting_path(state,initial,sig,cycle,cfg,notices,end),'quote_intervals':intervals,
                        'initial_quality':{'quote':initial['quote'],'strict_full_cycle_first_verified':False,'restoration_status':initial['restoration_status']}}
                    rows.append(row)
            if not recompute:write_json(qacheck,rows)
            qa.extend(rows)
            print(json.dumps({'confirmation_event':initial['ticker'],'cycle':initial['cycle_id'],'policy_rows':len(rows)}),flush=True)
    except PhaseDeadline:stopped='ANALYSIS_WALL_TIME_BUDGET'
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    # On analysis interruption, the complete acquisition table still retains every selected opportunity.
    if stopped:
        opportunities=[];events=[];first_out=[]
        for op in ordered_opportunities(plan):
            pair=root/'ticks'/('cycle='+op['cycle_id'])/('security='+op['security_id']);p=pair/'ingest.json'
            if p.exists():
                v=read(p);opportunities.extend(v['opportunities']);events.extend(v['events']);first_out.extend(v['first_outcomes'])
            else:
                opportunities.extend({**op,'condition_policy':c,'complete_observed_sessions':False,'observed_opportunity_eligible':False,
                    'zero_event_observed':False,'event_id':None,'status':'NOT_ACQUIRED'} for c in config['condition_policies'])
    tables={'opportunities':opportunities,'events':events,'first_outcomes':first_out,'confirmation':qa}
    if not recompute:
        for name,rows in tables.items():event_table(root/name/(name+'.parquet'),rows)
        write_json(root/'analysis-status.json',{'stop_reason':stopped,'elapsed_seconds':time.monotonic()-began,'confirmation_rows':len(qa)})
    return tables


def reports(config,root,plan,tables):
    dest=Path('reports',config['run_id']);dest.mkdir(parents=True,exist_ok=True)
    primary=[o for o in tables['opportunities'] if o['condition_policy']=='HIGH_LOW_ONLY']
    primary_events=[e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY']
    verified=[e for e in primary_events if e['observed_sessions_first_verified']]
    cycles=[]
    for c in plan['calendar'][:10]:
        oo=[o for o in primary if o['cycle_id']==c['cycle_id']];ee=[e for e in primary_events if e['cycle_id']==c['cycle_id']]
        cycles.append({'cycle_id':c['cycle_id'],'month':c['month'],'selected':len(oo),'complete':sum(o['complete_observed_sessions'] for o in oo),
            'verified_risk_set':sum(o['observed_opportunity_eligible'] for o in oo),'events':len(ee),
            'verified_events':sum(e['observed_sessions_first_verified'] for e in ee),'zero_events':sum(o['zero_event_observed'] for o in oo),
            'sessions':dict(Counter(e['session'] for e in ee))})
    groups=[]
    for condition in config['condition_policies']:
        for stratum in ['ALL',*config['strata']]:
            for session in ['ALL','AH','PRE','RTH']:
                for policy in sorted({r['policy'] for r in tables['confirmation']}):
                    rr=[r for r in tables['confirmation'] if r['condition_policy']==condition and r['policy']==policy and
                        (stratum=='ALL' or r['stratum']==stratum) and (session=='ALL' or r['initial_session']==session)]
                    # Preserve within-date weights; include joint date/security weight summaries separately.
                    g=summarize(rr);W=sum(r['joint_sampling_weight'] for r in rr)
                    g['joint_design_weight_sum']=W;g['joint_weighted_confirmation_fraction']=sum(r['joint_sampling_weight'] for r in rr if r['signal']['status']=='CONFIRMED')/W if W else None
                    groups.append({'condition_policy':condition,'stratum':stratum,'initial_session':session,'policy':policy,**g})
    pairs=[];c0={(r['initial_event_id'],r['condition_policy']):r for r in tables['confirmation'] if r['policy']=='C0_FROZEN'}
    for r in tables['confirmation']:
        if r['policy']=='C0_FROZEN':continue
        for a,b in zip(c0[r['initial_event_id'],r['condition_policy']]['common_landmarks'],r['common_landmarks']):
            assert a['target_ns']==b['target_ns'] and a['exit_observation_ns']==b['exit_observation_ns']
            matched=a['status']==b['status']=='OBSERVED'
            pairs.append({'initial_event_id':r['initial_event_id'],'cycle_id':r['cycle_id'],'security_id':r['security_id'],
                'condition_policy':r['condition_policy'],'policy':r['policy'],'stratum':r['stratum'],'sampling_weight':r['sampling_weight'],
                'joint_sampling_weight':r['joint_sampling_weight'],'landmark_minutes':a['landmark_minutes'],'target_ns':a['target_ns'],
                'c0':a,'policy_mark':b,'matched':matched,'difference':str(number(b['return'])-number(a['return'])) if matched else None})
    statrows=[{**r,'incidence':float(bool(r['event_id'])) if r['observed_opportunity_eligible'] else None} for r in primary]
    statistics={'design_weighted_incidence':design_incidence(primary,plan['date_strata']),
        'two_way_cluster_sensitivity':clustered_ratio(statrows,'incidence'),
        'crossed_cluster_resampling':crossed_cluster_bootstrap(primary,config['bootstrap_replicates'],config['bootstrap_seed']),
        'confidence_intervals_reported':False,'significance_claim':False,'development_dates_are_not_independent_validation':True}
    development=read(Path('reports',config['development_run'],'summary.json'))
    summary={'run_id':config['run_id'],'planned_dates':30,'batch_dates':10,'cycles':cycles,'selected_opportunities':len(primary),
        'complete_trade_windows':sum(o['complete_observed_sessions'] for o in primary),'primary_events':len(primary_events),
        'verified_primary_events':len(verified),'zero_event_opportunities':sum(o['zero_event_observed'] for o in primary),
        'unknown_opportunities':sum(not o['complete_observed_sessions'] for o in primary),'session_events':dict(Counter(e['session'] for e in verified)),
        'unverified_opportunities_including_unknown_prior_evidence':sum(not o['observed_opportunity_eligible'] for o in primary),
        'confirmation_initial_risk_set':len(verified),'analyzed_confirmation_initial_events':len({r['initial_event_id'] for r in tables['confirmation']}),
        'acquisition':read(root/'acquisition-status.json'),'analysis':read(root/'analysis-status.json'),
        'ledger':{k:v for k,v in read(root/'ledger.json').items() if k in ['pages','decoded_bytes','started_epoch','deadline_epoch']},
        'http_requests':len(read(root/'ledger.json')['attempts']),'http_errors':sum(a['status']!='OK' for a in read(root/'ledger.json')['attempts']),
        'development_separate':{'run_id':config['development_run'],'opportunities':development['selected_opportunities'],
            'events':development['primary_events'],'sessions':development['session_events'],'date_sampling':'Original consecutive ten development dates; not pooled as validation'},
        'holdout_analyzed':False,'executable_profitability':'NOT_ASSESSED','strict_full_cycle_first':'UNVERIFIED_OVERNIGHT'}
    stratum_incidence=[]
    for st in config['strata']:
        rr=[r for r in primary if r['stratum']==st]
        stratum_incidence.append({'stratum':st,'selected':len(rr),'complete':sum(r['complete_observed_sessions'] for r in rr),
            'events':sum(bool(r['event_id']) for r in rr),'statistics':design_incidence(rr,plan['date_strata'])})
    session_risk=[]
    for condition in config['condition_policies']:
        ee=[e for e in tables['events'] if e['condition_policy']==condition]
        oo=[o for o in tables['opportunities'] if o['condition_policy']==condition]
        for session,rank in [('AH',0),('PRE',1),('RTH',2)]:
            earlier={(e['cycle_id'],e['security_id']) for e in ee if {'AH':0,'PRE':1,'RTH':2}[e['session']]<rank}
            risk=[o for o in oo if o['observed_opportunity_eligible'] and (o['cycle_id'],o['security_id']) not in earlier]
            session_risk.append({'condition_policy':condition,'session':session,'verified_risk_set':len(risk),
                'events':sum(e['session']==session and e['observed_sessions_first_verified'] for e in ee)})
    values={'summary':summary,'frozen-selection':plan,'event-level-results':tables,'cohort_metrics':groups,'common-landmark-pairs':pairs,
        'statistical-preparation':statistics,'stratum-incidence':stratum_incidence,'session-risk-sets':session_risk,
        'cycle_metrics':cycles,'statistical_tests':{'status':'NO_SIGNIFICANCE_TEST','reason':'Ten date clusters; development separate; missingness disclosed; no iid event intervals'},
        'data_quality':{'incomplete':[{'cycle_id':o['cycle_id'],'ticker':o['ticker'],'status':o['status']} for o in primary if not o['complete_observed_sessions']],
            'historical_float':'UNRESOLVED; current float retrospective only','sec_evidence_separate':True,
            'quote_scope':'Bounded +/-60 seconds around first touches; not exhaustive execution coverage','unverified_touch_candidates':len(primary_events)-len(verified)},
        'anomalies':{'first_touch_quotes':[{'event_id':e['event_id'],'ticker':e['ticker'],'cycle_id':e['cycle_id'],'quote':e['quote']}
            for e in primary_events if e['quote'].get('trade_relation')!='WITHIN_NBBO']}}
    for name,value in values.items():(dest/(name+'.json')).write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
    event_table(dest/'event_results.parquet',tables['confirmation']);event_table(dest/'cycle_metrics.parquet',cycles)
    event_table(dest/'cohort_metrics.parquet',groups);event_table(dest/'distributions.parquet',tables['first_outcomes'])
    text='# TASK 004 — Temporal expansion\n\n'+json.dumps(summary,indent=2)+'\n\nNo profitability, significance or full-cycle coverage claim. Development dates remain separate. All frozen date/security weights, missing opportunities and censored policy outcomes are retained.\n'
    (dest/'report.md').write_text(text)
    return dest


def validate(config,root,plan,tables):
    assert file_hash(root/'selection.json')==read(root/'selection.sha256.json')['sha256']
    assert len(plan['selected'])==720 and len(plan['calendar'])==30
    assert len(ordered_opportunities(plan))==240
    reserved={c['cycle_id'] for c in plan['calendar'] if not c['execute_in_initial_batch']}
    assert not any(p.name.removeprefix('cycle=') in reserved for p in (root/'ticks').glob('cycle=*'))
    for p,h in read(root/'protected.json').items():assert file_hash(p)==h,'Protected artifact changed: '+p
    for p,h in read(root/'execution.json')['code_hashes'].items():assert file_hash(p)==h,'Execution code drift'
    pages=0;raw_records=0;cache={}
    for path in (root/'ticks').glob('cycle=*/security=*/**/coverage.json'):
        cov=read(path);prior_next=None;last=0
        for i,page in enumerate(cov['pages']):
            assert file_hash(page['path'])==page['sha256'];body=read(page['path']);pages+=1
            stamps=[r['sip_timestamp'] for r in body.get('results',[])]
            assert stamps==sorted(stamps) and (not stamps or stamps[0]>=last)
            assert all(cov['request']['start_ns']<t<=cov['request']['end_ns'] for t in stamps)
            if stamps:last=stamps[-1]
            if i:
                from .api import safe_url
                from urllib.parse import urlparse,parse_qsl
                u=safe_url(prior_next)
                assert page['request']=={'url':u.split('?',1)[0],'params':dict(parse_qsl(urlparse(u).query))}
            prior_next=body.get('next_url')
        assert not cov['complete'] or prior_next is None
    def source(e):
        nonlocal raw_records
        ref=json.loads(e['source_json']);p=ref['path']
        if p not in cache:assert file_hash(p)==ref['sha256'];cache[p]=read(p)
        body=cache[p]['results'][ref['row']]
        assert digest(body)==e['record_id'] and body['sip_timestamp']==e.get('timestamp',e.get('event_timestamp'))
        raw_records+=1
    for e in tables['events']:source(e)
    risk={e['event_id'] for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY' and e['observed_sessions_first_verified']}
    for r in tables['confirmation']:
        assert r['initial_event_id'] in risk
        assert r['sampling_weight']==r['population_N']/r['sample_n']
        for e in r['signal']['evidence']:
            assert e['timestamp']<=r['signal']['signal_timestamp'];source(e)
        if r['signal']['status']=='CONFIRMED':
            if r['deadline_seconds']:assert r['delay_seconds']<=60
            if r['definition']=='C1_SESSION_BOUND':assert r['signal_session']==r['initial_session']
    counts=Counter((r['condition_policy'],r['policy']) for r in tables['confirmation'])
    assert all(n==len(risk) for n in counts.values()) or read(root/'analysis-status.json')['stop_reason']
    ledger=read(root/'ledger.json')
    assert len(ledger['attempts'])<=config['max_requests'] and ledger['pages']<=config['max_pages'] and ledger['decoded_bytes']<=config['max_decoded_bytes']
    result={'status':'PASS','planned_dates':30,'planned_securities':720,'selected_initial_batch_opportunities':240,
        'coverage_pages_checked':pages,'raw_signal_references_checked':raw_records,'protected_files_unchanged':len(read(root/'protected.json')),
        'confirmation_risk_set':len(risk),'policy_counts':{str(k):v for k,v in counts.items()},'reserved_20_dates_untouched':True,'holdout_analyzed':False}
    write_json(Path('reports',config['run_id'],'validation.json'),result)
    return result


def package(config,root,dest,plan):
    files={p.name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in dest.iterdir() if p.is_file() and p.name not in ['manifest.json','research_bundle.zip','bundle-validation.json']}
    counts={p.name:pq.ParquetFile(p).metadata.num_rows for p in dest.glob('*.parquet')}
    summary=read(dest/'summary.json')
    complete=summary['complete_trade_windows']==240 and not read(root/'analysis-status.json')['stop_reason'] and not summary['acquisition']['stop_reason']
    evidenced={o['cycle_id'] for o in records(root/'opportunities/opportunities.parquet') if o.get('provider_pages',0)>0}
    m={'contract_version':'research-bundle-v1','experiment_id':config['run_id'],'research_configuration':config,'configuration_hash':digest(config),
        'baseline_commit':config['baseline_commit'],'selection_sha256':file_hash(root/'selection.json'),'code_hashes':read(root/'execution.json')['code_hashes'],
        'requested_trading_cycles':[c['cycle_id'] for c in plan['calendar'][:10]],'processed_trading_cycles':sorted(evidenced),
        'event_definitions':'Frozen observed-session first touch and unchanged TASK 003.1 policies','outcome_definitions':'Own and common touch-anchored landmarks; all missingness retained',
        'timezone':'America/New_York; UTC SIP nanoseconds','schema_versions':{'event':'confirmation-qa-v1','sampling':'temporal-two-stage-v1'},
        'files':files,'record_counts':counts,'execution_status':'COMPLETE' if complete else 'INCOMPLETE','event_population':'Initial batch only, not 30 or 80 cycles',
        'size_policy':'Full records, no raw ticks, no truncation','raw_ticks_included':False,'completed_at':datetime.now(timezone.utc).isoformat()}
    write_json(dest/'manifest.json',m)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['manifest.json',*files]:z.write(dest/name,name)
    with zipfile.ZipFile(dest/'research_bundle.zip') as z:
        import hashlib
        assert z.testzip() is None
        for n,v in files.items():assert hashlib.sha256(z.read(n)).hexdigest()==v['sha256']
    write_json(dest/'bundle-validation.json',{'status':'PASS','bytes':(dest/'research_bundle.zip').stat().st_size,
        'sha256':file_hash(dest/'research_bundle.zip'),'record_counts':counts,'raw_ticks_included':False})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','acquire','analyze','validate']);p.add_argument('--config',default=CONFIG)
    p.add_argument('--env-file');p.add_argument('--offline',action='store_true');a=p.parse_args();config=read(a.config)
    root,plan=prepare(config)
    if a.command=='prepare':print(json.dumps({'selection_sha256':file_hash(root/'selection.json'),'dates':[c['cycle_id'] for c in plan['calendar']],'batch':[c['cycle_id'] for c in plan['calendar'][:10]]},indent=2));return
    freeze_execution(config,root)
    with (root/'.writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.command=='acquire':
            acquire(config,root,plan,load_key(a.env_file),a.offline)
            status=read(root/'acquisition-status.json')
            if status['stop_reason'] and not a.offline:
                # Recover cached complete/partial trades and explicit missing rows,
                # without issuing any request after a global resource stop.
                acquire(config,root,plan,None,True)
                recovered=read(root/'acquisition-status.json')
                write_json(root/'acquisition-status.json',{**status,'completed_checkpoints':recovered['completed_checkpoints'],
                    'offline_salvage_after_resource_stop':True})
            return
        if a.command=='analyze':tables=analyze(config,root,plan)
        else:tables={name:records(root/name/(name+'.parquet')) for name in ['opportunities','events','first_outcomes','confirmation']}
        dest=reports(config,root,plan,tables);v=validate(config,root,plan,tables);package(config,root,dest,plan);print(json.dumps(v,indent=2))


if __name__=='__main__':main()
