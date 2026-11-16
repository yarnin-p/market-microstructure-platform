"""Original40 risk-set revalidation; new source lineage, frozen trade evidence."""
import argparse
import json
import socket
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import duckdb
import pyarrow.parquet as pq
import requests

from .confirmation import bid_confirmation, confirmation_outcomes, signal_result
from .confirmation_qa import common_marks, waiting_path
from .confirmation_qa_run import execute as reproduce_qa
from .flatfile_cache import CONFIG, atomic_json, memory_bytes
from .flatfile_ingest import selected_mapping
from .m2_report import records
from .preholdout_audit import denied
from .quote_state import QuoteState, state_confirmation
from .replay_qa import iter_normalized
from .storage import digest, file_hash
from .systematic_pilot import replay
from .temporal_design import read
from .tick_replay import SECOND, bounds, number


def codes(text):
    if text in ['',None]:return []
    if str(text).startswith('['):out=json.loads(text)
    else:out=[int(x.strip()) for x in str(text).split(',')]
    if any(not isinstance(x,int) or isinstance(x,bool) for x in out):raise ValueError('Invalid condition encoding')
    return out


def normalized(row, source, cycle, security_id):
    raw={k:v for k,v in row.items() if not k.startswith('_')}
    result={'record_id':digest(['S3',raw]),'security_id':security_id,'ticker':row['ticker'],'kind':source['dataset'],
        'cycle_id':cycle['cycle_id'],'sip_timestamp':row['_sip_timestamp_ns'],
        'normalization_status':'OK','raw_json':json.dumps(raw,sort_keys=True),
        'source_json':json.dumps({'kind':'S3_CSV','key':source['key'],'sha256':source['sha256'],
                                  'local_path':source['local_path'],'row':row['_source_row']})}
    try:
        result['conditions_json']=json.dumps(codes(row.get('conditions')))
        result['indicators_json']=json.dumps(codes(row.get('indicators')))
    except (ValueError,TypeError,json.JSONDecodeError):
        result.update(conditions_json='[999999]',indicators_json='[]',normalization_status='INVALID_CONDITION_ENCODING')
    for k in ['bid_price','ask_price','bid_size','ask_size','price','size']:
        result[k]=row.get('decimal_size',row.get(k)) if k=='size' and row.get('decimal_size') not in ['',None] else row.get(k)
    for k in ['participant_timestamp','sequence_number','bid_exchange','ask_exchange','exchange','correction','trf_id','trf_timestamp']:
        v=row.get(k)
        try:result[k]=int(v) if v not in ['',None] else None
        except ValueError:result[k]=None;result['normalization_status']='INVALID_INTEGER_FIELD'
    result['trade_id']=row.get('id')
    return result


def source_interval(manifest):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    day=datetime.fromisoformat(manifest['source']['date']).date()
    zone=ZoneInfo('America/New_York')
    opened=int(datetime(day.year,day.month,day.day,4,tzinfo=zone).timestamp())*SECOND
    closed=int(datetime(day.year,day.month,day.day,20,tzinfo=zone).timestamp())*SECOND
    intersects=(manifest.get('min_sip_timestamp') is not None and manifest.get('max_sip_timestamp') is not None
                and manifest['min_sip_timestamp']<closed and manifest['max_sip_timestamp']>=opened)
    return {'start_ns':opened-1,'end_ns':closed-1,
        'complete':manifest['complete'] and manifest['gzip_crc_validated'] and intersects,
        'source_key':manifest['source']['key'],'source_sha256':manifest['source']['sha256'],
        'rows_outside_utc_date_retained':manifest['rows_outside_object_utc_date'],
        'session_basis':'America/New_York 04:00-20:00; original cycle session masks still apply',
        'scope':'COMPLETE_PROVIDER_OBSERVED_SESSION_OBJECT_NOT_INDEPENDENT_EXCHANGE_COVERAGE'}


def source_quotes(manifests,ticker,cycle,security_id,kind='quotes'):
    rows=[];intervals=[];raw_count=0
    start,end=bounds(cycle)[0]-60*SECOND,bounds(cycle)[-1]
    with duckdb.connect() as db:
        db.execute("SET memory_limit='512MB'");db.execute('SET threads=2')
        for m in manifests:
            if m['source']['dataset']!=kind:continue
            interval=source_interval(m);intervals.append(interval)
            part=next(r for r in m['partitions'] if r['ticker']==ticker)
            if security_id not in part['security_ids']:raise ValueError('Frozen ticker/security mapping mismatch')
            assert file_hash(part['path'])==part['sha256']
            if interval['end_ns']<start or interval['start_ns']>end:continue
            table=db.sql('SELECT * FROM read_parquet(?, hive_partitioning=false) WHERE _sip_timestamp_ns>=? AND _sip_timestamp_ns<=? ORDER BY _sip_timestamp_ns,_sequence_number_int,_source_row',params=[part['path'],start,end]).to_arrow_table()
            for row in table.to_pylist():rows.append(normalized(row,m['source'],cycle,security_id))
    # Full-record duplicates are not distinct confirmation observations.
    unique={};raw_count=len(rows)
    for r in rows:unique.setdefault(r['record_id'],r)
    return sorted(unique.values(),key=lambda r:(r['sip_timestamp'],r.get('sequence_number') or 0,r['record_id'])),intervals,{'raw':raw_count,'unique':len(unique),'duplicates':raw_count-len(unique)}


def reproduce_baseline(config, root):
    target=root/'baseline-reproduction.json'
    if target.exists():return read(target)
    qaconfig=read('configs/task-003-1-confirmation-qa-v1.json')
    rows,_,_,checks=reproduce_qa(qaconfig,root/'baseline-recompute',recompute=True)
    expected=read(Path('reports',config['qa_run'],'event-level-results.json'))['records']
    assert rows==expected,'Frozen C0/C1/C2 or QA outcomes changed'
    result={'status':'PASS','initial_events':40,'condition_policies':2,'frozen_baseline_signal_outcome_checks':checks,
        'qa_rows_recomputed_exactly':len(rows),'c0_c1_unchanged':True,'c2_baseline_unchanged':True,
        'source_sha256':file_hash(Path('reports',config['qa_run'],'event-level-results.json')),
        'row_hashes':[{'initial_event_id':r['initial_event_id'],'condition_policy':r['condition_policy'],'policy':r['policy'],'sha256':digest(r)} for r in rows],
        'rest_requests':0,'holdout_access':False}
    atomic_json(target,result);return result


def trade_state(config,event,cycle,selection,conditions):
    src=Path('data/runs',config['source_run']);pair=src/'ticks'/('cycle='+event['cycle_id'])/('security='+event['security_id'])
    for p,h in read(pair/'result.json')['input_hashes'].items():assert file_hash(p)==h
    paths=sorted((pair/'trades/normalized').glob('*.parquet'))
    op=next(o for o in selection['selected'] if (o['cycle_id'],o['security_id'])==(event['cycle_id'],event['security_id']))
    states,_,_=replay(paths,read(pair/'trades/coverage.json'),op,cycle,read('configs/task-002-2-systematic-v1.json'),conditions)
    notices=[r for r in iter_normalized(paths) if r.get('correction') in [10,11,12]]
    return states,notices


def quote_marks(replay,initial,signal,common,config):
    if signal['status']!='CONFIRMED':return {'status':'NO_SIGNAL','pairs':[],'executable_pnl':None}
    entry=replay.asof(signal['signal_timestamp']);pairs=[]
    for mark in common:
        exit=replay.asof(mark['target_ns'])
        good=entry.get('valid') and entry.get('fresh') and exit.get('valid') and exit.get('fresh') and mark['confirmed_before_or_at_landmark']
        pairs.append({'landmark_minutes':mark['landmark_minutes'],'entry':entry,'exit':exit,
            'ask_entry_bid_exit_mark':str(number(exit['bid'])/number(entry['ask'])-1) if good else None,
            'status':'QUOTE_MARK_NOT_FILL' if good else 'MISSING_OR_NONFRESH_QUOTE_EVIDENCE',
            'trade_path_status':mark['status'],'executable_pnl':None})
    return {'status':'QUOTE_MARKS_ONLY','pairs':pairs,'executable_pnl':None}


def revalidate(config,root):
    integrity=read(root/'gzip-integrity.json')
    assert integrity['complete'] and len(integrity['sources'])==len(config['objects']),'Mandatory gzip proof incomplete'
    target=root/'confirmation-comparison.json'
    if target.exists():return read(target)
    manifests=read(root/'ingested-sources.json');events,_=selected_mapping(config)
    src=Path('data/runs',config['source_run']);selection=read(src/'selection.json');conditions={r['id']:r for r in read(src/'context.json')['conditions']}
    qa=read(Path('reports',config['qa_run'],'event-level-results.json'))['records']
    baseline={(r['initial_event_id'],r['condition_policy']):r for r in qa if r['policy']=='C2_FROZEN'}
    basecfg={**read('configs/task-002-2-systematic-v1.json'),**read('configs/task-003-confirmation-v1.json'),**read('configs/task-003-1-confirmation-qa-v1.json')}
    rows=[];timelines=[]
    for i,event in enumerate(sorted(events,key=lambda r:(r['cycle_id'],r['security_id']))):
        cycle=next(c for c in selection['calendar'] if c['cycle_id']==event['cycle_id'])
        quotes,intervals,dup=source_quotes(manifests,event['ticker'],cycle,event['security_id'])
        stream=QuoteState(quotes,intervals,cycle,config['max_quote_age_seconds'],config['max_state_age_seconds'])
        start=event['event_timestamp'];deadline=min(start+60*SECOND,bounds(cycle)[-1]);covered=stream.covered(start,deadline)
        timeline_times=sorted(set([start-5*SECOND,start]+[start+n*SECOND for n in [1,5,10,30,60]]+[start+n*60*SECOND for n in [5,15,30,60]]))
        timelines.append({'initial_event_id':event['event_id'],'ticker':event['ticker'],'cycle_id':event['cycle_id'],
            'source_intervals':intervals,'raw_quote_counts':dup,'confirmation_source_window_complete':covered,
            'asof':[stream.asof(t) for t in timeline_times]})
        if not covered:
            for condition in ['HIGH_LOW_ONLY','ODD_LOT_OBSERVATION_SENSITIVITY']:
                for policy in ['C2_S3_FROZEN_RULE','C2_S3_STATE_BASED']:
                    old=baseline[event['event_id'],condition]
                    rows.append({'initial_event_id':event['event_id'],'ticker':event['ticker'],'cycle_id':event['cycle_id'],
                        'condition_policy':condition,'policy':policy,'signal':signal_result(policy,'INSUFFICIENT_DATA','SOURCE_COVERAGE_UNKNOWN'),
                        'baseline_signal':old['signal'],'changed_classification':old['signal']['status']!='INSUFFICIENT_DATA',
                        'comparable_source_coverage':False,'sampling_weight':old['sampling_weight'],
                        'common_landmarks':[{'landmark_minutes':m,'status':'INSUFFICIENT_DATA','return':None,'target_ns':start+m*60*SECOND} for m in [5,15,30,60]],
                        'own_signal_outcomes':[],'pre_confirmation':None,'quote_marks':{'status':'SOURCE_COVERAGE_UNKNOWN','pairs':[]},
                        'not_evidence_of_confirmation_reversal':True})
            continue
        states,notices=trade_state(config,event,cycle,selection,conditions)
        for condition,state in states.items():
            frozen=bid_confirmation(state,event,cycle,basecfg,quotes,{'complete':covered,'request':{'start_ns':start-1,'end_ns':deadline}})
            sensitivity=state_confirmation(stream,state,event,cycle,config)
            for policy,signal in [('C2_S3_FROZEN_RULE',frozen),('C2_S3_STATE_BASED',sensitivity)]:
                # Preserve the exact C2 output structure for frozen-rule comparison.
                if signal['signal_timestamp'] is not None and any(t is None or start<=t<=signal['signal_timestamp'] for t in state.unknown_times):
                    signal.update(status='INSUFFICIENT_DATA',reason='UNKNOWN_TRADE_EVIDENCE_BEFORE_CONFIRMATION')
                adapter={**signal,'signal_policy':'C2'}
                old=baseline[event['event_id'],condition]
                same_clock=signal['status']==old['signal']['status'] and signal['signal_timestamp']==old['signal']['signal_timestamp'] and signal['market_observation_price']==old['signal']['market_observation_price']
                if same_clock:
                    outcomes=old['own_signal_outcomes'];common=old['common_landmarks'];waiting=old['pre_confirmation'];recomputed=False
                else:
                    outcomes=[confirmation_outcomes(state,event,adapter,cycle,basecfg,notices,g) for g in [None,300,900]]
                    outcomes=[r for r in outcomes if r is not None]
                    common=common_marks(state,event,adapter,cycle,basecfg,notices)
                    waiting=waiting_path(state,event,adapter,cycle,basecfg,notices,deadline);recomputed=True
                rows.append({'initial_event_id':event['event_id'],'ticker':event['ticker'],'cycle_id':event['cycle_id'],
                    'condition_policy':condition,'policy':policy,'signal':signal,'baseline_signal':old['signal'],
                    'sampling_weight':old['sampling_weight'],'stratum':old['stratum'],'sec_evidence':old['sec_evidence'],
                    'float_proxy':old['float_proxy'],'comparable_source_coverage':True,'changed_classification':signal['status']!=old['signal']['status'],
                    'changed_signal_clock_or_price':not same_clock,'outcomes_recomputed':recomputed,
                    'delay_seconds':(signal['signal_timestamp']-start)/SECOND if signal['status']=='CONFIRMED' else None,
                    'waiting_price_change':str(number(signal['market_observation_price'])/number(event['touch_price'])-1) if signal['status']=='CONFIRMED' and signal['market_observation_price'] is not None else None,
                    'common_landmarks':common,'own_signal_outcomes':outcomes,'pre_confirmation':waiting,
                    'quote_marks':quote_marks(stream,event,signal,common,config),'source_quote_counts':dup})
        print(json.dumps({'S3_event':i+1,'ticker':event['ticker'],'covered':covered}),flush=True)
    assert len(rows)==160 and len({r['initial_event_id'] for r in rows})==40
    result={'initial_events':40,'rows':rows,'timelines':timelines,
        'policies':{str((c,p)):{'initial_denominator':40,'statuses':dict(Counter(r['signal']['status'] for r in rows if r['condition_policy']==c and r['policy']==p)),
             'source_covered_initial_events':sum(r['comparable_source_coverage'] for r in rows if r['condition_policy']==c and r['policy']==p)}
             for c in ['HIGH_LOW_ONLY','ODD_LOT_OBSERVATION_SENSITIVITY'] for p in ['C2_S3_FROZEN_RULE','C2_S3_STATE_BASED']},
        'rest_requests':0,'holdout_access':False,'frozen_risk_set_unchanged':True,'executable_pnl':None}
    atomic_json(target,result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['baseline','revalidate']);p.add_argument('--config',default=CONFIG);a=p.parse_args()
    cfg=read(a.config);root=Path('data/runs',cfg['run_id'])
    with patch.object(requests.sessions.Session,'request',denied),patch.object(socket,'create_connection',denied):
        result=reproduce_baseline(cfg,root) if a.command=='baseline' else revalidate(cfg,root)
    print(json.dumps({k:v for k,v in result.items() if k not in ['row_hashes','rows','timelines']},indent=2))


if __name__=='__main__':main()
