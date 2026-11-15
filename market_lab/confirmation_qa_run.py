"""Offline execution, risk-set comparisons and packaging for TASK 003.1."""
import argparse
import fcntl
import json
import subprocess
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import requests

from .confirmation import bid_confirmation, causal_quote, confirmation_outcomes, signal_result, trade_confirmation
from .confirmation_pilot import coverage_for, quotes_for, read, stats
from .confirmation_qa import c1_signal, common_marks, quote_audit, waiting_path
from .m2_pilot import event_table
from .m2_report import records
from .replay_qa import iter_normalized, tree_hashes
from .storage import digest, file_hash, write_json
from .systematic_pilot import replay
from .tick_replay import SECOND, ns, number, session_label

CONFIG='configs/task-003-1-confirmation-qa-v1.json'


def freeze(config):
    root=Path('data/runs',config['run_id']); root.mkdir(parents=True,exist_ok=True)
    code={str(p):file_hash(p) for p in Path('market_lab').glob('*.py')}
    target=root/'execution.json'
    if target.exists():
        frozen=read(target)
        if frozen['config']!=config or frozen['code_hashes']!=code:raise ValueError('Immutable run drift: new run ID required')
        return root,frozen
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if not head.startswith(config['baseline_commit']):raise ValueError('Unexpected baseline')
    protected={}
    for parent in [Path('data'),Path('reports')]:
        for p in parent.rglob('*'):
            if p.is_file() and p.name!='.writer.lock' and root not in p.parents and p.parent!=Path('reports',config['run_id']):
                protected[str(p)]=file_hash(p)
    tracked=subprocess.check_output(['git','ls-files'],text=True).splitlines()
    protected.update({p:file_hash(p) for p in tracked})
    frozen={'config':config,'code_hashes':code,'baseline_commit':head,'protected_files':protected,
            'created_at':datetime.now(timezone.utc).isoformat(),'http_requests':0}
    write_json(target,frozen)
    return root,frozen


def execute(config,root,recompute=False):
    src=Path('data/runs',config['source_run'])
    selection=read(src/'selection.json')
    assert len(selection['calendar'])==10 and all(c['split_group']=='EXPLORATION' for c in selection['calendar'])
    baseline=read(Path('reports',config['baseline_run'],'event-level-results.json'))['records']
    baseline_index={(r['initial_event_id'],r['condition_policy'],r['signal']['signal_policy']):r for r in baseline}
    initial=[e for e in records(src/'events/events.parquet') if e['condition_policy']=='HIGH_LOW_ONLY']
    assert len(initial)==config['initial_events']==40
    selection_index={(o['cycle_id'],o['security_id']):o for o in selection['selected']}
    cycles={c['cycle_id']:c for c in selection['calendar']}
    old_config={**read('configs/task-002-2-systematic-v1.json'),**read('configs/task-003-confirmation-v1.json')}
    calc_config={**old_config,**config}
    conditions={r['id']:r for r in read(src/'context.json')['conditions']}
    output=[];audits=[];baseline_checks=0
    for i,event in enumerate(sorted(initial,key=lambda e:(e['cycle_id'],e['security_id']))):
        checkpoint=root/'checkpoints'/(event['event_id']+'.json')
        if checkpoint.exists() and not recompute:
            saved=read(checkpoint); output.extend(saved['rows']); audits.extend(saved['audits']); baseline_checks+=saved['baseline_checks']
            continue
        pair=src/'ticks'/('cycle='+event['cycle_id'])/('security='+event['security_id'])
        for p,h in read(pair/'result.json')['input_hashes'].items():assert file_hash(p)==h,'Input checksum mismatch'
        paths=sorted((pair/'trades/normalized').glob('*.parquet'))
        cycle=cycles[event['cycle_id']]
        states,_,_=replay(paths,read(pair/'trades/coverage.json'),selection_index[event['cycle_id'],event['security_id']],
                          cycle,read('configs/task-002-2-systematic-v1.json'),conditions)
        notices=[r for r in iter_normalized(paths) if r.get('correction') in {10,11,12}]
        quotes,intervals=quotes_for(pair)
        rows=[];pair_audits=[];checks=0
        for condition,state in states.items():
            base={p:baseline_index[event['event_id'],condition,p] for p in ['C0','C1','C2']}
            deadline=min(event['event_timestamp']+60*SECOND,ns(cycle['end_at']))
            anchor=next(r for r in state.eligible if r['record_id']==event['record_id'])
            assert anchor['price']==event['touch_price'] or number(anchor['price'])==number(event['touch_price'])
            c0_signal=signal_result('C0','CONFIRMED','ORIGINAL_FIRST_TOUCH',event['event_timestamp'],event['touch_price'],
                [{'record_id':event['record_id'],'timestamp':event['event_timestamp'],'source_json':event['source_json'],
                  'restoration_source':event.get('restoration_source')}],trade_record_id=event['record_id'],
                market_price_timestamp=event['event_timestamp'],market_price_source=event['source_json'])
            recomputed={'C0':c0_signal,
                'C1':trade_confirmation(state,event,cycle,old_config,notices),
                'C2':bid_confirmation(state,event,cycle,old_config,quotes,coverage_for(intervals,event['event_timestamp'],deadline))}
            for policy,signal in recomputed.items():
                if policy!='C0' and signal['signal_timestamp'] is not None and any(t is None or event['event_timestamp']<=t<=signal['signal_timestamp'] for t in state.unknown_times):
                    signal.update(status='INSUFFICIENT_DATA',reason='UNKNOWN_EVIDENCE_BEFORE_CANDIDATE_CONFIRMATION')
                assert signal==base[policy]['signal'],'Frozen signal changed: '+policy
                outs=[confirmation_outcomes(state,event,signal,cycle,old_config,notices,g) for g in old_config['gap_sensitivities_seconds']]
                assert [o for o in outs if o is not None]==base[policy]['outcomes'],'Frozen outcome changed: '+policy
                checks+=1
            if condition=='HIGH_LOW_ONLY':pair_audits.append(quote_audit(quotes,event,cycle,old_config,base['C2']['signal']))
            candidates=[('C0_FROZEN',None,None,base['C0']['signal'],ns(cycle['end_at'])),
                        ('C2_FROZEN',None,None,base['C2']['signal'],deadline)]
            for definition in config['c1_definitions']:
                for d in config['deadline_seconds']:
                    signal,end=c1_signal(state,event,cycle,calc_config,notices,definition,d)
                    if definition=='C1_COUNTED_ORIGINAL' and d is None:assert signal==base['C1']['signal']
                    candidates.append((definition+('_D60' if d else ''),definition,d,signal,end))
            for policy,definition,d,signal,end in candidates:
                outs=[confirmation_outcomes(state,event,signal,cycle,calc_config,notices,g) for g in config['gap_sensitivities_seconds']]
                outs=[o for o in outs if o is not None]
                price=number(signal['market_observation_price']); t=signal['signal_timestamp']
                row={k:base['C0'][k] for k in ['initial_event_id','initial_event_timestamp','initial_touch_price','original_threshold_price',
                    'ticker','security_id','cycle_id','initial_session','stratum','cohorts','sampling_weight','selection_probability',
                    'population_N','sample_n','float_proxy','sec_evidence','initial_quality']}
                row.update(event_id=digest([config['methodology_version'],condition,policy,event['event_id']]),run_id=config['run_id'],
                    methodology_version=config['methodology_version'],condition_policy=condition,policy=policy,definition=definition,
                    deadline_seconds=d,signal=signal,operational_end_ns=end,signal_session=session_label(cycle,t) if t else None,
                    delay_seconds=(t-event['event_timestamp'])/SECOND if signal['status']=='CONFIRMED' else None,
                    waiting_price_change=str(price/number(event['touch_price'])-1) if price is not None and signal['status']=='CONFIRMED' else None,
                    own_signal_outcomes=outs,common_landmarks=common_marks(state,event,signal,cycle,calc_config,notices),
                    pre_confirmation=waiting_path(state,event,signal,cycle,calc_config,notices,end),
                    quote_intervals=intervals,first_touch_anchor_unchanged=True)
                rows.append(row)
        saved={'rows':rows,'audits':pair_audits,'baseline_checks':checks}
        if not recompute:write_json(checkpoint,saved)
        output.extend(rows);audits.extend(pair_audits);baseline_checks+=checks
        print(json.dumps({'events_processed':i+1,'ticker':event['ticker'],'cycle_id':event['cycle_id']}),flush=True)
    if not recompute:event_table(root/'events/event_results.parquet',output)
    return output,audits,selection,baseline_checks


def summarize(rows):
    status=Counter(r['signal']['status'] for r in rows)
    weight=sum(r['sampling_weight'] for r in rows)
    result={'initial_events':len(rows),'statuses':dict(status),'weighted_confirmation_fraction':
        sum(r['sampling_weight'] for r in rows if r['signal']['status']=='CONFIRMED')/weight if weight else None,
        'delay_seconds':stats(r['delay_seconds'] for r in rows),'waiting_price_change':stats(r['waiting_price_change'] for r in rows),
        'common_landmarks':{},'own_signal_forward':{},'own_signal_barriers':{},'pre_confirmation_mfe':stats(r['pre_confirmation']['mfe'] for r in rows),
        'pre_confirmation_mae':stats(r['pre_confirmation']['mae'] for r in rows),
        'pre_confirmation_censored':sum(r['pre_confirmation']['censored'] for r in rows)}
    for minute in [5,15,30,60]:
        marks=[(next(m for m in r['common_landmarks'] if m['landmark_minutes']==minute),r['sampling_weight']) for r in rows]
        buckets=Counter(m['status'] for m,w in marks); weighted=Counter()
        for m,w in marks:weighted[m['status']]+=w
        vals=[(float(m['return']),w) for m,w in marks if m['status']=='OBSERVED']
        result['common_landmarks'][str(minute)]={'initial_denominator':len(rows),'buckets':dict(buckets),
            'weighted_buckets':dict(weighted),'confirmed_before_or_at':sum(m['confirmed_before_or_at_landmark'] for m,w in marks),
            'observed_return_distribution':stats(v for v,w in vals),
            'conditional_weighted_mean':sum(v*w for v,w in vals)/sum(w for v,w in vals) if vals else None}
        own=[]; own_buckets=Counter()
        for r in rows:
            primary=next((o for o in r['own_signal_outcomes'] if o['gap_policy']=='NO_MECHANICAL_GAP'),None)
            mark=next((m for m in primary['forward'] if m['horizon']==str(minute)+'m'),None) if primary else None
            bucket=mark and ('CENSORED' if mark['censored'] else 'OBSERVED') or r['signal']['status']
            own_buckets[bucket]+=1
            if mark and not mark['censored']:own.append(mark['return'])
        result['own_signal_forward'][str(minute)]={'initial_denominator':len(rows),'buckets':dict(own_buckets),'observed_distribution':stats(own)}
    for up,down in [('0.03','0.03'),('0.05','0.03'),('0.10','0.05')]:
        buckets=Counter()
        for r in rows:
            primary=next((o for o in r['own_signal_outcomes'] if o['gap_policy']=='NO_MECHANICAL_GAP'),None)
            barrier=next((b for b in primary['barriers'] if (b['up'],b['down'])==(up,down)),None) if primary else None
            buckets[barrier['outcome'] if barrier else r['signal']['status']]+=1
        result['own_signal_barriers'][up+'/'+down]={'initial_denominator':len(rows),'buckets':dict(buckets)}
    return result


def top_up_plan(rows,selection,config):
    needs={};all_targets=[];quote_cache={}
    for r in rows:
        if r['condition_policy']!='HIGH_LOW_ONLY' or r['signal']['status']!='CONFIRMED':continue
        start=r['signal']['signal_timestamp']
        cycle=next(c for c in selection['calendar'] if c['cycle_id']==r['cycle_id'])
        points=[('ENTRY',start)]+[('COMMON_EXIT_'+str(m),r['initial_event_timestamp']+m*60*SECOND) for m in [5,15,30,60]
            if r['initial_event_timestamp']+m*60*SECOND>=start]
        points += [('OWN_EXIT_'+str(m),start+m*60*SECOND) for m in [5,15,30,60]]
        for kind,t in points:
            if t>ns(cycle['end_at']) or session_label(cycle,t) not in {'AH','PRE','RTH'}:continue
            covered=coverage_for(r['quote_intervals'],t,t)['complete']
            key=(r['cycle_id'],r['security_id'],t)
            if key not in needs:needs[key]={'cycle_id':r['cycle_id'],'security_id':r['security_id'],'ticker':r['ticker'],
                'target_ns':t,'existing_complete_time_coverage':covered,'uses':[]}
            needs[key]['uses'].append({'policy':r['policy'],'kind':kind,'initial_event_id':r['initial_event_id']})
    queue=[]
    for key,item in sorted(needs.items()):
        pair=Path('data/runs',config['source_run'],'ticks','cycle='+item['cycle_id'],'security='+item['security_id'])
        if str(pair) not in quote_cache:quote_cache[str(pair)]=quotes_for(pair)[0]
        quotes=quote_cache[str(pair)]
        q=causal_quote(quotes,item['target_ns'],read('configs/task-003-confirmation-v1.json'),item['existing_complete_time_coverage'])
        item['cached_quote_status']=q['status'];item['cached_quote_flags']=q.get('flags',[])
        if not item['existing_complete_time_coverage']:
            queue.append({'cycle_id':item['cycle_id'],'security_id':item['security_id'],'ticker':item['ticker'],
                'start_ns':item['target_ns']-5*SECOND-1,'end_ns':item['target_ns'],'target_ns':item['target_ns'],
                'endpoint':'/v3/quotes/'+item['ticker'],'params':{'timestamp.gt':item['target_ns']-5*SECOND-1,
                    'timestamp.lte':item['target_ns'],'order':'asc','sort':'timestamp','limit':config['top_up_plan']['page_limit']},
                'uses':item['uses']})
        all_targets.append(item)
    # Fixed round-robin cycle scheduling; no selection on realized returns.
    buckets=defaultdict(list)
    for item in queue:buckets[item['cycle_id']].append(item)
    ordered=[buckets[c][i] for i in range(max(map(len,buckets.values()),default=0)) for c in sorted(buckets) if i<len(buckets[c])]
    return {'status':'PLAN_ONLY_NO_AUTHORIZATION_TO_FETCH','execution_http_requests':0,'budget':config['top_up_plan'],
        'unique_entry_exit_targets':len(all_targets),'cached_valid_targets':sum(t['cached_quote_status']=='OK' for t in all_targets),
        'cached_complete_but_invalid_or_stale_targets':sum(t['existing_complete_time_coverage'] and t['cached_quote_status']!='OK' for t in all_targets),
        'missing_coverage_target_windows':len(queue),'minimum_calls_for_all_unmerged_missing_windows':len(queue),
        'quote_seconds_requested_for_full_queue':len(queue)*(5+1/SECOND),
        'pilot_queue':ordered[:config['top_up_plan']['max_windows']],'full_missing_window_queue':ordered,'targets':all_targets,
        'scope':'Primary HIGH_LOW_ONLY; all eight QA policies, common and own exits; no raw quote copies.',
        'limitations':['Top-up can return no quotes; byte/page caps may leave a cursor incomplete.',
                      'Five-second snapshots do not certify path-wide bid/ask barrier or fill evidence.',
                      'Existing corrected/stale covered values are not repaired by silently re-requesting the same interval.',
                      'No order size, queue, latency or executable P&L inferred from ask/bid marks.']}


def report(config,root,rows,audits,selection):
    dest=Path('reports',config['run_id']);dest.mkdir(parents=True,exist_ok=True)
    groups=[]
    for condition in config['condition_policies']:
        for stratum in ['ALL','PROXY_FLOAT_IN_RANGE','OTHER_EXCHANGE_PRICE_ELIGIBLE']:
            for session in ['ALL','AH','PRE','RTH']:
                for policy in sorted({r['policy'] for r in rows}):
                    rr=[r for r in rows if r['condition_policy']==condition and r['policy']==policy and
                        (stratum=='ALL' or r['stratum']==stratum) and (session=='ALL' or r['initial_session']==session)]
                    groups.append({'condition_policy':condition,'stratum':stratum,'initial_session':session,'policy':policy,**summarize(rr)})
    c0={(r['initial_event_id'],r['condition_policy']):r for r in rows if r['policy']=='C0_FROZEN'}
    pairs=[]
    for r in rows:
        if r['policy']=='C0_FROZEN':continue
        baseline=c0[r['initial_event_id'],r['condition_policy']]
        for a,b in zip(baseline['common_landmarks'],r['common_landmarks']):
            assert a['target_ns']==b['target_ns'] and a['exit_price']==b['exit_price'] and a['exit_observation_ns']==b['exit_observation_ns']
            matched=a['status']==b['status']=='OBSERVED'
            pairs.append({'initial_event_id':r['initial_event_id'],'condition_policy':r['condition_policy'],'policy':r['policy'],
                'cycle_id':r['cycle_id'],'stratum':r['stratum'],'sampling_weight':r['sampling_weight'],'landmark_minutes':a['landmark_minutes'],
                'common_target_ns':a['target_ns'],'c0':a,'policy_mark':b,'matched_observable_pair':matched,
                'paired_return_difference':str(number(b['return'])-number(a['return'])) if matched else None,
                'unconditional_policy_pnl':None})
    primary=[g for g in groups if g['condition_policy']=='HIGH_LOW_ONLY' and g['stratum']==g['initial_session']=='ALL']
    paired_summary=[]
    for condition in config['condition_policies']:
        for policy in sorted({p['policy'] for p in pairs}):
            for minute in config['landmarks_minutes']:
                pp=[p for p in pairs if (p['condition_policy'],p['policy'],p['landmark_minutes'])==(condition,policy,minute)]
                matched=[p for p in pp if p['matched_observable_pair']]
                paired_summary.append({'condition_policy':condition,'policy':policy,'landmark_minutes':minute,'initial_denominator':len(pp),
                    'matched_pairs':len(matched),'c0_statuses':dict(Counter(p['c0']['status'] for p in pp)),
                    'policy_statuses':dict(Counter(p['policy_mark']['status'] for p in pp)),
                    'conditional_return_difference':stats(p['paired_return_difference'] for p in matched),
                    'conditional_weighted_difference':sum(float(p['paired_return_difference'])*p['sampling_weight'] for p in matched)/sum(p['sampling_weight'] for p in matched) if matched else None})
    plan=top_up_plan(rows,selection,config)
    values={'summary':{'run_id':config['run_id'],'primary_policies':primary,'http_requests':0,'holdout_analyzed':False,
        'conditional_pairs_are_not_unconditional_performance':True},'event-level-results':{'records':rows},'cohort_metrics':groups,
        'common-landmark-pairs':pairs,'paired_summary':paired_summary,
        'c2-quote-audit':{'all_40':audits,'original_10_insufficient':[a for a in audits if a['frozen_status']=='INSUFFICIENT_DATA'],
                        'assessments':dict(Counter(a['assessment'] for a in audits))},
        'quote-top-up-plan':plan,'sampling':{'strata':selection['strata'],'selection_method':selection['selection_method'],
            'weights':'Frozen N/n; no survivor reweighting. Descriptive ratios only.','source_selection_sha256':file_hash(Path('data/runs',config['source_run'],'selection.json'))},
        'data_quality':{'strict_full_cycle_verified':False,'historical_float':'UNRESOLVED; current float proxy not PIT',
            'c2_frozen_statuses':dict(Counter(a['frozen_status'] for a in audits)),'quote_downloads':0,'holdout_analyzed':False},
        'statistical_tests':{'status':'NOT_PERFORMED','confidence_intervals':None,'reason':'Small stratified clustered exploratory risk set; no causal, significance or profitability claims'},
        'anomalies':{'late_c1_original':[{'ticker':r['ticker'],'cycle_id':r['cycle_id'],'delay_seconds':r['delay_seconds']}
                    for r in rows if r['condition_policy']=='HIGH_LOW_ONLY' and r['policy']=='C1_COUNTED_ORIGINAL' and (r['delay_seconds'] or 0)>3600]}}
    for name,value in values.items():
        (dest/(name+'.json')).write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
    event_table(dest/'event_results.parquet',rows);event_table(dest/'cohort_metrics.parquet',groups)
    cycle_metrics=[{'cycle_id':c['cycle_id'],'policy':p,**summarize([r for r in rows if r['cycle_id']==c['cycle_id'] and r['policy']==p and r['condition_policy']=='HIGH_LOW_ONLY'])}
                   for c in selection['calendar'] for p in sorted({r['policy'] for r in rows})]
    event_table(dest/'cycle_metrics.parquet',cycle_metrics)
    event_table(dest/'distributions.parquet',[{'event_id':r['event_id'],'initial_event_id':r['initial_event_id'],'policy':r['policy'],
        'condition_policy':r['condition_policy'],'sampling_weight':r['sampling_weight'],**o} for r in rows for o in r['own_signal_outcomes']])
    text='# TASK 003.1 — Confirmation QA\n\n40 initial events per policy; no network requests. Frozen C0/C1/C2 unchanged.\n\n'
    text+='| Policy | Confirmed | Unconfirmed | Insufficient | Median delay seconds | Median waiting price change |\n|---|---:|---:|---:|---:|---:|\n'
    for g in primary:
        s=g['statuses'];cost=g['waiting_price_change']['median'];delay=g['delay_seconds']['median']
        text+=f"| {g['policy']} | {s.get('CONFIRMED',0)} | {s.get('UNCONFIRMED',0)} | {s.get('INSUFFICIENT_DATA',0)} | {delay} | {format(cost,'.4%') if cost is not None else 'NA'} |\n"
    text+='\nCommon exits are anchored to original touch+5/15/30/60 minutes. All unconfirmed, not-yet-confirmed, insufficient and censored cases remain in initial denominators. Matched-return distributions are conditional, never unconditional policy P&L. No observed below-threshold print does not independently certify continuous support.\n\nQuote top-up is a plan only; it was not executed or authorized by this run. Full event, own-clock, common-clock, pre-confirmation path and source evidence is included without truncation.\n'
    (dest/'report.md').write_text(text)
    return dest


def validate(config,root,frozen,rows,audits,checks):
    for p,h in frozen['protected_files'].items():assert file_hash(p)==h,'Protected artifact changed: '+p
    for p,h in frozen['code_hashes'].items():assert file_hash(p)==h,'Code drift'
    assert checks==240 and len(rows)==640 and len(audits)==40
    assert len({r['event_id'] for r in rows})==640
    assert len([a for a in audits if a['frozen_status']=='INSUFFICIENT_DATA'])==10
    assert rows==records(root/'events/event_results.parquet')
    sources={};checked=0
    def source(ref,expected_ns=None,record_id=None):
        nonlocal checked
        if not ref:return
        ref=json.loads(ref) if isinstance(ref,str) else ref
        p=ref['path']
        if p not in sources:
            assert file_hash(p)==ref['sha256'];sources[p]=read(p)
        raw=sources[p]['results'][ref['row']]
        if expected_ns is not None:assert raw['sip_timestamp']==expected_ns
        if record_id is not None:assert digest(raw)==record_id
        checked+=1
    for r in rows:
        assert r['sampling_weight']==r['population_N']/r['sample_n']
        for e in r['signal']['evidence']:
            assert e['timestamp']<=r['signal']['signal_timestamp'];source(e['source_json'],e['timestamp'],e['record_id'])
        for mark in r['common_landmarks']:
            source(mark['exit_source_json'],mark['exit_observation_ns'])
            if mark['return'] is not None:
                assert mark['confirmed_before_or_at_landmark'] and mark['status']=='OBSERVED'
                assert mark['entry_timestamp']<=mark['target_ns'] and mark['exit_observation_ns']<=mark['target_ns']
        pre=r['pre_confirmation'];source(pre['mfe_source'],pre['mfe_ns']);source(pre['mae_source'],pre['mae_ns'])
        if r['signal']['status']=='CONFIRMED':
            assert r['signal']['signal_timestamp']<=r['operational_end_ns']
            if r['deadline_seconds']:assert r['delay_seconds']<=60
            if r['definition']=='C1_SESSION_BOUND':assert r['signal_session']==r['initial_session']
    for a in audits:
        for point in a['timeline']:
            q=point['quote']
            if 'source_json' in q:source(q['source_json'],q['timestamp'],q['record_id'])
    result={'status':'PASS','baseline_signal_condition_records_exactly_reproduced':checks,'initial_events_per_policy':40,
        'event_rows':640,'c2_audits':40,'original_insufficient_cases_audited':10,'protected_files_unchanged':len(frozen['protected_files']),
        'source_pages_checked':len(sources),'source_references_checked':checked,'http_requests':0,'holdout_analyzed':False}
    write_json(Path('reports',config['run_id'],'validation.json'),result)
    return result


def package(config,root,dest,selection):
    files={p.name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in dest.iterdir()
           if p.is_file() and p.name not in {'manifest.json','research_bundle.zip','bundle-validation.json'}}
    counts={p.name:pq.ParquetFile(p).metadata.num_rows for p in dest.glob('*.parquet')}
    manifest={'contract_version':'research-bundle-v1','experiment_id':config['run_id'],'research_configuration':config,
        'configuration_hash':digest(config),'baseline_commit':config['baseline_commit'],'execution_sha256':file_hash(root/'execution.json'),
        'code_hashes':read(root/'execution.json')['code_hashes'],'requested_trading_cycles':[c['cycle_id'] for c in selection['calendar']],
        'processed_trading_cycles':[c['cycle_id'] for c in selection['calendar']],'event_definitions':'Frozen 40-event risk set; independent C1 definition and deadline sensitivities; C0/C2 frozen',
        'outcome_definitions':'Own signal horizons plus common t0+5/15/30/60m exits, explicit matched/missing/censored populations',
        'timezone':'America/New_York sessions; UTC SIP nanoseconds','schema_versions':{'event':'confirmation-qa-v1'},
        'files':files,'record_counts':counts,'execution_status':'COMPLETE','event_population':'40 initial events, 640 dependent policy-condition rows',
        'size_policy':'All event records; no raw ticks; no truncation','raw_ticks_included':False,'completed_at':datetime.now(timezone.utc).isoformat()}
    write_json(dest/'manifest.json',manifest)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['manifest.json',*files]:z.write(dest/name,name)
    with zipfile.ZipFile(dest/'research_bundle.zip') as z:
        import hashlib
        assert z.testzip() is None
        for name,info in files.items():assert hashlib.sha256(z.read(name)).hexdigest()==info['sha256']
        for name,n in counts.items():
            with z.open(name) as stream:assert pq.read_metadata(stream).num_rows==n
    write_json(dest/'bundle-validation.json',{'status':'PASS','bytes':(dest/'research_bundle.zip').stat().st_size,
        'sha256':file_hash(dest/'research_bundle.zip'),'members':len(files)+1,'record_counts':counts,'raw_ticks_included':False})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['run','validate']);parser.add_argument('--config',default=CONFIG)
    args=parser.parse_args();config=read(args.config)
    def forbidden(*a,**kw):raise AssertionError('Offline QA: HTTP forbidden')
    requests.sessions.Session.request=forbidden
    root,frozen=freeze(config)
    with (root/'.writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rows,audits,selection,checks=execute(config,root,recompute=args.command=='validate')
        if args.command=='validate':assert rows==records(root/'events/event_results.parquet'),'Deterministic QA replay changed'
        dest=report(config,root,rows,audits,selection)
        result=validate(config,root,frozen,rows,audits,checks)
        package(config,root,dest,selection);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
