"""Hard-budget NBBO feasibility probe. Frozen signals remain read-only."""
import argparse
import fcntl
import hashlib
import json
import signal
import subprocess
import time
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qsl

import pyarrow as pa
import pyarrow.parquet as pq
import requests

from .api import load_key,safe_url,scrub
from .confirmation import causal_quote
from .confirmation_pilot import quotes_for,coverage_for,stats
from .m2_pilot import event_table
from .m2_report import records
from .replay_qa import tree_hashes
from .storage import file_hash,digest,write_json
from .tick_ingest import TICK_SCHEMA
from .tick_replay import SECOND,number,session_label

CONFIG='configs/task-003-2-nbbo-probe-v1.json'


def read(p):return json.loads(Path(p).read_text())
def usage(root):return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
class BudgetStop(RuntimeError):pass
class HardDeadline(BaseException):pass


def freeze(config):
    root=Path('data/runs',config['run_id']);root.mkdir(parents=True,exist_ok=True)
    identity={'config':config,'plan_sha256':file_hash(config['plan']),'qa_sha256':file_hash(config['qa_results']),
              'code_hashes':{str(p):file_hash(p) for p in Path('market_lab').glob('*.py')}}
    if (root/'execution.json').exists():
        old=read(root/'execution.json')
        if any(old[k]!=v for k,v in identity.items()):raise ValueError('Immutable code/config drift')
        return root,old
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if not head.startswith(config['baseline_commit']):raise ValueError('Unexpected baseline')
    plan=read(config['plan']);selected=plan['full_missing_window_queue'][:10]
    assert selected==plan['pilot_queue'] and len(selected)==10
    assert len({(w['security_id'],w['cycle_id'],w['target_ns']) for w in selected})==10
    original=[e for e in records(Path('data/runs',config['source_run'],'events/events.parquet')) if e['condition_policy']=='HIGH_LOW_ONLY']
    assert len(original)==40
    events={e['event_id']:e for e in original}
    for w in selected:
        assert w['endpoint']=='/v3/quotes/'+w['ticker']
        assert w['start_ns']==w['target_ns']-5*SECOND-1 and w['end_ns']==w['target_ns']
        for u in w['uses']:
            e=events[u['initial_event_id']]
            assert all(e[k]==w[k] for k in ['ticker','security_id','cycle_id'])
    protected={}
    for parent in [Path('data/runs'),Path('reports')]:
        for prior in parent.iterdir():
            if prior.is_dir() and prior.name!=config['run_id']:protected.update(tree_hashes(prior))
    for p in ['data/sec-pilot-20261115-v2/results-reviewed-v1.json','configs/task-003-confirmation-v1.json','configs/task-003-1-confirmation-qa-v1.json']:
        protected[p]=file_hash(p)
    identity.update(baseline_commit=head,selected=selected,protected_files=protected,original_initial_event_ids=sorted(events))
    write_json(root/'execution.json',identity)
    return root,identity


class ProbeClient:
    def __init__(self,root,config,key=None,session=None):
        self.root,self.config,self.key=root,config,key
        self.session=session or requests.Session()
        self.path=root/'ledger.json'
        self.ledger=read(self.path) if self.path.exists() else {'attempts':[],'pages':0,'decoded_bytes':0,'windows':[],
            'started_epoch':time.time(),'deadline_epoch':time.time()+config['total_wall_seconds']}
        self.deadline=time.monotonic()+max(0,self.ledger['deadline_epoch']-time.time())
        self.save()

    def save(self):write_json(self.path,self.ledger)

    def check(self):
        c,l=self.config,self.ledger
        if time.monotonic()>=self.deadline:raise BudgetStop('WALL_TIME_BUDGET')
        if len(l['attempts'])>=c['max_requests']:raise BudgetStop('HTTP_ATTEMPT_BUDGET')
        if l['pages']>=c['max_pages']:raise BudgetStop('PAGE_BUDGET')
        if l['decoded_bytes']>=c['max_decoded_bytes']:raise BudgetStop('DECODED_BYTE_BUDGET')
        if usage(self.root)+32*1024*1024>c['max_storage_bytes']:raise BudgetStop('STORAGE_HEADROOM_BUDGET')

    def persist(self,path,content):
        # Never write a file that exceeds the remaining hard storage allowance.
        if usage(self.root)+len(content)>self.config['max_storage_bytes']-65536:raise BudgetStop('STORAGE_BUDGET')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)

    def get(self,path,params,ticker):
        url=safe_url(path if path.startswith('https:') else 'https://api.massive.com'+path)
        assert urlparse(url).path=='/v3/quotes/'+ticker,'Unexpected cursor endpoint'
        request={'url':url.split('?',1)[0],'params':dict(parse_qsl(urlparse(url).query))| (params or {})}
        key=digest(request);raw=self.root/'raw'/(key+'.json');meta=raw.with_suffix('.meta.json')
        if meta.exists():
            m=read(meta);assert file_hash(raw)==m['sha256'] and m['request']==request
            body=read(raw)
            if m['http_status']!=200:raise RuntimeError('HTTP_'+str(m['http_status']))
            if 'results' not in body and body.get('results_count')==0:body={**body,'results':[]}
            if not isinstance(body.get('results'),list):raise RuntimeError('INVALID_RESPONSE_SCHEMA')
            return body,m
        self.check()
        if not self.key:raise BudgetStop('MISSING_API_KEY')
        time.sleep(min(self.config['minimum_request_spacing_seconds'],max(0,self.deadline-time.monotonic())))
        self.check()
        attempt={'request':request,'status':'STARTED','bytes':0,'started_at':datetime.now(timezone.utc).isoformat()}
        self.ledger['attempts'].append(attempt);self.save()
        chunks=[]
        try:
            remaining=max(.001,self.deadline-time.monotonic())
            with self.session.get(request['url'],params=request['params'],headers={'Authorization':'Bearer '+self.key},stream=True,
                    allow_redirects=False,timeout=(min(self.config['connect_timeout_seconds'],remaining),min(self.config['read_timeout_seconds'],remaining))) as response:
                attempt['http_status']=response.status_code
                chunks=[];iterator=response.iter_content(16384)
                while True:
                    if time.monotonic()>=self.deadline:raise BudgetStop('WALL_TIME_BUDGET')
                    remaining=min(self.config['max_page_bytes']-attempt['bytes'],self.config['max_decoded_bytes']-self.ledger['decoded_bytes'])
                    # Reserve an entire decoder chunk before requesting it; stop conservatively near a cap.
                    if remaining<16384:raise BudgetStop('DECODED_BYTE_BUDGET')
                    try:block=next(iterator)
                    except StopIteration:break
                    if len(block)>remaining:raise BudgetStop('DECODER_CHUNK_EXCEEDED_RESERVATION')
                    attempt['bytes']+=len(block);self.ledger['decoded_bytes']+=len(block);chunks.append(block);self.save()
                content=b''.join(chunks)
                body=json.loads(content)
                clean=scrub(body,self.key)
                if clean!=body:content=json.dumps(clean,separators=(',',':')).encode()
                self.persist(raw,content)
                m={'path':str(raw.resolve()),'sha256':file_hash(raw),'request':request,'retrieved_at':datetime.now(timezone.utc).isoformat(),
                   'http_status':response.status_code,'decoded_bytes':attempt['bytes']}
                write_json(meta,m)
                if response.status_code!=200:raise RuntimeError('HTTP_'+str(response.status_code))
                self.ledger['pages']+=1
                if not isinstance(clean.get('results'),list):
                    if clean.get('results_count')==0 and 'results' not in clean:clean={**clean,'results':[]}
                    else:raise RuntimeError('INVALID_RESPONSE_SCHEMA')
                attempt['status']='OK';return clean,m
        except requests.RequestException as exc:
            attempt['status']='NETWORK_'+type(exc).__name__;raise RuntimeError(attempt['status']) from None
        except (RuntimeError,ValueError) as exc:
            attempt['status']=str(exc) if isinstance(exc,RuntimeError) else 'INVALID_JSON';raise
        finally:
            if attempt['status']!='OK' and chunks and not raw.exists():
                partial=raw.with_suffix('.partial');self.persist(partial,b''.join(chunks))
                attempt['partial_source']={'path':str(partial.resolve()),'sha256':file_hash(partial)}
            self.save()

    def window(self,w,index):
        p=self.root/'windows'/f'{index:02d}'/'coverage.json'
        if p.exists():return read(p)
        key=digest([w['security_id'],w['cycle_id'],w['target_ns']])
        if key not in self.ledger['windows']:
            if len(self.ledger['windows'])>=self.config['max_windows']:raise BudgetStop('WINDOW_BUDGET')
            self.ledger['windows'].append(key);self.save()
        cov={'window':w,'pages':[],'complete':False,'error':None,'raw_rows':0}
        path,params=w['endpoint'],w['params'];seen=set()
        try:
            for _ in range(self.config['max_pages_per_window']):
                marker=digest([path,params])
                if marker in seen:raise RuntimeError('CURSOR_LOOP')
                seen.add(marker)
                body,source=self.get(path,params,w['ticker']);cov['pages'].append(source);cov['raw_rows']+=len(body['results'])
                path,params=body.get('next_url'),None
                if not path:cov['complete']=True;break
            if path:cov['error']='WINDOW_PAGE_BUDGET'
        except (RuntimeError,ValueError) as exc:cov['error']=str(exc)
        write_json(p,cov);return cov


def normalized(cov,cycle):
    rows=[];seen=set();invalid=duplicates=0;w=cov['window']
    for page in cov['pages']:
        assert file_hash(page['path'])==page['sha256']
        for i,raw in enumerate(read(page['path']).get('results',[])):
            rid=digest(raw)
            if rid in seen:duplicates+=1;continue
            seen.add(rid);t=raw.get('sip_timestamp');valid=isinstance(t,int) and not isinstance(t,bool) and w['start_ns']<t<=w['end_ns'] and -(2**63)<=t<2**63
            invalid+=not valid
            row={k:None for k in TICK_SCHEMA.names}
            row.update(record_id=rid,security_id=w['security_id'],ticker=w['ticker'],cycle_id=w['cycle_id'],kind='quotes',
                       session=session_label(cycle,t) if valid else 'INVALID',conditions_json=json.dumps(raw.get('conditions',[])),
                       indicators_json=json.dumps(raw.get('indicators',[])),raw_json=json.dumps(raw,sort_keys=True),
                       source_json=json.dumps({'path':page['path'],'sha256':page['sha256'],'row':i}),normalization_status='OK' if valid else 'INVALID_TIMESTAMP')
            for f in TICK_SCHEMA:
                value=raw.get(f.name)
                if pa.types.is_int64(f.type):row[f.name]=value if isinstance(value,int) and not isinstance(value,bool) and -(2**63)<=value<2**63 else None
            for k in ['bid_price','ask_price','bid_size','ask_size']:row[k]=str(raw[k]) if raw.get(k) is not None else None
            rows.append(row)
    rows.sort(key=lambda q:(q.get('sip_timestamp') or 0,q.get('sequence_number') or 0,q['record_id']))
    return rows,{'invalid_timestamps':invalid,'exact_duplicates':duplicates}


def mark(rows,intervals,t,config):
    complete=coverage_for(intervals,t-5*SECOND,t)['complete']
    q=causal_quote(rows,t,config,complete)
    if q.get('record_id'):
        raw=next(r for r in rows if r['record_id']==q['record_id'])
        if raw.get('correction') not in {None,0} or 81 in json.loads(raw['conditions_json']):
            q['flags']=sorted(set(q['flags']+['CORRECTED_QUOTE_NOT_ORIGINAL_PIT']));q['status']='FLAGGED'
    q['target_ns']=t
    if q['status']=='OK':
        q['spread']=str(number(q['ask'])-number(q['bid']))
        q['relative_spread']=str((number(q['ask'])-number(q['bid']))/((number(q['ask'])+number(q['bid']))/2))
    return q


def recommendation(complete,fresh,pairs,stopped):
    if complete>=8 and fresh>=8 and pairs>=3 and not stopped:return 'QUOTE_EXPANSION_FEASIBLE'
    if complete and fresh:return 'QUOTE_EXPANSION_CONDITIONALLY_FEASIBLE'
    return 'QUOTE_EXPANSION_NOT_JUSTIFIED'


def evaluate(config,root,frozen):
    src=Path('data/runs',config['source_run']);cycles={c['cycle_id']:c for c in read(src/'selection.json')['calendar']}
    all_rows=read(config['qa_results'])['records'];cache={};windows=[];marks=[];observations=Counter()
    selected_keys={(w['cycle_id'],w['security_id'],w['target_ns']) for w in frozen['selected']}
    for i,w in enumerate(frozen['selected']):
        p=root/'windows'/f'{i:02d}'/'coverage.json'
        cov=read(p) if p.exists() else {'window':w,'pages':[],'complete':False,'raw_rows':0,'error':'NOT_ATTEMPTED_BUDGET'}
        rows,audit=normalized(cov,cycles[w['cycle_id']]);pair=src/'ticks'/('cycle='+w['cycle_id'])/('security='+w['security_id'])
        old,intervals=quotes_for(pair)
        before=mark(old,intervals,w['target_ns'],config)
        intervals=intervals+[{'start_ns':w['start_ns'],'end_ns':w['end_ns'],'complete':cov['complete'] and not audit['invalid_timestamps']}]
        union={q['record_id']:q for q in old+rows};merged=sorted(union.values(),key=lambda q:(q['sip_timestamp'] or 0,q.get('sequence_number') or 0,q['record_id']))
        cache[w['cycle_id'],w['security_id']]=(merged,intervals)
        after=mark(merged,intervals,w['target_ns'],config)
        for q in rows:
            check=causal_quote([q],q['sip_timestamp'] or w['target_ns'],config)
            corrected=q.get('correction') not in {None,0} or 81 in json.loads(q['conditions_json'])
            observations['corrected']+=corrected;observations['invalid_or_corrected']+=check['status']!='OK' or corrected
            observations['valid_observations']+=check['status']=='OK' and not corrected
        windows.append({'index':i,'ticker':w['ticker'],'cycle_id':w['cycle_id'],'security_id':w['security_id'],'target_ns':w['target_ns'],
                        'uses':w['uses'],'complete':cov['complete'],'error':cov['error'],'raw_rows':cov['raw_rows'],'pages':len(cov['pages']),
                        'empty':cov['complete'] and cov['raw_rows']==0,'audit':audit,'before':before,'after':after})
        marks.append(after)
    pairs={}
    for r in all_rows:
        key=(r['cycle_id'],r['security_id'])
        if r['condition_policy']!='HIGH_LOW_ONLY' or r['signal']['status']!='CONFIRMED' or key not in cache:continue
        rows,intervals=cache[key];entry_t=r['signal']['signal_timestamp'];entry=mark(rows,intervals,entry_t,config)
        exits=[('COMMON',m['target_ns'],m['return'],m['status']=='OBSERVED') for m in r['common_landmarks'] if m['confirmed_before_or_at_landmark']]
        for out in r['own_signal_outcomes']:
            if out['gap_policy']=='NO_MECHANICAL_GAP':
                exits += [('OWN',m['target_ns'],m['return'],not m['censored']) for m in out['forward'] if m['horizon'] in ['5m','15m','30m','60m']]
        for clock,t,trade_return,trade_ok in exits:
            if t<=entry_t or not (key+(t,) in selected_keys or key+(entry_t,) in selected_keys):continue
            ex=mark(rows,intervals,t,config);good=entry['status']==ex['status']=='OK'
            pairkey=key+(entry_t,t)
            if pairkey not in pairs:
                value=number(ex['bid'])/number(entry['ask'])-1 if good else None
                pairs[pairkey]={'pair_id':digest(pairkey),'cycle_id':key[0],'security_id':key[1],'ticker':r['ticker'],
                    'entry_target_ns':entry_t,'exit_target_ns':t,'entry':entry,'exit':ex,'supported':good,
                    'ask_entry_bid_exit_relative_mark_change':str(value) if good else None,
                    'bid_exit_minus_ask_entry':str(number(ex['bid'])-number(entry['ask'])) if good else None,'uses':[],
                    'not_fills_or_realized_pnl':True}
            v=pairs[pairkey]['ask_entry_bid_exit_relative_mark_change']
            pairs[pairkey]['uses'].append({'initial_event_id':r['initial_event_id'],'policy':r['policy'],'clock':clock,
                'observed_trade_path_return':trade_return if trade_ok else None,
                'quote_minus_trade_return_not_pnl':str(number(v)-number(trade_return)) if v is not None and trade_ok and trade_return is not None else None})
    pairs=list(pairs.values());fresh=[m for m in marks if m['status']=='OK'];supported=[p for p in pairs if p['supported']]
    entries={(p['cycle_id'],p['security_id'],p['entry_target_ns']):p['entry'] for p in pairs};exits={(p['cycle_id'],p['security_id'],p['exit_target_ns']):p['exit'] for p in pairs}
    # Distinct security/cycle/clock pairs, not duplicated common/own policy uses.
    ledger=read(root/'ledger.json')
    summary={'requested_windows':len(windows),'attempted_windows':len(ledger['windows']),'complete_windows':sum(w['complete'] for w in windows),
        'empty_complete_windows':sum(w['empty'] for w in windows),'fresh_valid_selected_targets':len(fresh),
        'fresh_valid_selected_entry_targets':sum(w['after']['status']=='OK' and any(u['kind']=='ENTRY' for u in w['uses']) for w in windows),
        'fresh_valid_selected_exit_targets':sum(w['after']['status']=='OK' and any(u['kind']!='ENTRY' for u in w['uses']) for w in windows),
        'fresh_valid_pair_entry_marks':sum(m['status']=='OK' for m in entries.values()),'fresh_valid_pair_exit_marks':sum(m['status']=='OK' for m in exits.values()),
        'candidate_clock_pairs':len(pairs),'complete_matched_quote_mark_pairs':len(supported),
        'unique_securities_with_supported_pairs':len({p['security_id'] for p in supported}),
        'quote_observations':sum(w['raw_rows'] for w in windows),'observation_quality':dict(observations),
        'selected_mark_statuses':dict(Counter(m['status'] for m in marks)),
        'spread_distribution_selected_fresh':stats(float(m['spread']) for m in fresh),
        'quote_age_seconds_selected_fresh':stats(m['age_ns']/SECOND for m in fresh),
        'quote_age_seconds_all_selected_predecessors':stats(m['age_ns']/SECOND for m in marks if m.get('age_ns') is not None),
        'spread_distribution_fresh_pair_entries':stats(float(m['spread']) for m in entries.values() if m['status']=='OK'),
        'spread_distribution_fresh_pair_exits':stats(float(m['spread']) for m in exits.values() if m['status']=='OK'),
        'request_attempts':len(ledger['attempts']),'successful_pages':ledger['pages'],'decoded_bytes':ledger['decoded_bytes'],
        'budget_stops':[w['error'] for w in windows if w['error']],
        'statistical_scope':'DETERMINISTIC_FEASIBILITY_QUEUE_NOT_RETURN_SELECTED_NOT_POPULATION_INFERENCE'}
    summary['recommendation']=recommendation(summary['complete_windows'],len(fresh),len(supported),bool(summary['budget_stops']))
    return {'summary':summary,'windows':windows,'pairs':pairs}


def acquire(config,root,frozen,key):
    if (root/'results.json').exists():return read(root/'results.json')
    client=ProbeClient(root,config,key)
    def stop(*_):raise HardDeadline('WALL_TIME_BUDGET')
    previous=signal.signal(signal.SIGALRM,stop)
    signal.setitimer(signal.ITIMER_REAL,max(.001,client.deadline-time.monotonic()-1))
    try:
        cycles={c['cycle_id']:c for c in read(Path('data/runs',config['source_run'],'selection.json'))['calendar']}
        for i,w in enumerate(frozen['selected']):
            if time.monotonic()>=client.deadline:break
            cov=client.window(w,i)
            rows,audit=normalized(cov,cycles[w['cycle_id']])
            buf=pa.BufferOutputStream();pq.write_table(pa.Table.from_pylist(rows,schema=TICK_SCHEMA),buf,compression='zstd')
            client.persist(root/'windows'/f'{i:02d}'/'quotes.parquet',buf.getvalue().to_pybytes())
            write_json(root/'windows'/f'{i:02d}'/'normalization.json',{**audit,'sha256':file_hash(root/'windows'/f'{i:02d}'/'quotes.parquet')})
            print(json.dumps({'window':i+1,'ticker':w['ticker'],'complete':cov['complete'],'rows':cov['raw_rows'],'error':cov['error']}),flush=True)
        result=evaluate(config,root,frozen)
        write_json(root/'results.json',result)
        return result
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        client.ledger['execution_wall_seconds']=time.time()-client.ledger['started_epoch'];client.save()


def publish(config,root,result):
    dest=Path('reports',config['run_id']);dest.mkdir(parents=True,exist_ok=True)
    summary={**result['summary'],'execution_wall_seconds':read(root/'ledger.json')['execution_wall_seconds'],'additional_run_storage_bytes':usage(root)}
    write_json(dest/'summary.json',summary);write_json(dest/'coverage-quality.json',result['windows']);write_json(dest/'quote-mark-pairs.json',result['pairs'])
    write_json(dest/'budget.json',{'limits':config,'ledger':read(root/'ledger.json'),'run_storage_bytes':usage(root)})
    write_json(dest/'selection.json',{'plan_sha256':file_hash(config['plan']),'windows':read(root/'execution.json')['selected']})
    event_table(root/'pairs.parquet',result['pairs'])
    write_json(dest/'manifest.json',{'run_id':config['run_id'],'baseline_commit':config['baseline_commit'],'config':config,
        'execution_sha256':file_hash(root/'execution.json'),'results_sha256':file_hash(root/'results.json'),
        'artifacts':{p.name:file_hash(p) for p in dest.iterdir() if p.is_file() and p.name!='manifest.json'}})
    return summary


def validate(config,root,frozen):
    for p,h in frozen['protected_files'].items():assert file_hash(p)==h,'Protected input changed: '+p
    for p,h in frozen['code_hashes'].items():assert file_hash(p)==h
    assert evaluate(config,root,frozen)==read(root/'results.json')
    ledger=read(root/'ledger.json');assert len(ledger['attempts'])<=40 and ledger['pages']<=40 and ledger['decoded_bytes']<=64*1024**2
    assert ledger['execution_wall_seconds']<=600 and usage(root)<=256*1024**2 and len(ledger['windows'])<=10
    checked=0
    for p in root.glob('windows/*/coverage.json'):
        c=read(p);assert len(c['pages'])<=4;previous=None;last_stamp=0
        audit=read(p.with_name('normalization.json'));assert file_hash(p.with_name('quotes.parquet'))==audit['sha256']
        for meta in c['pages']:
            assert file_hash(meta['path'])==meta['sha256'] and meta['decoded_bytes']<=8*1024**2
            b=read(meta['path']);stamps=[q['sip_timestamp'] for q in b.get('results',[])]
            assert stamps==sorted(stamps)
            assert all(c['window']['start_ns']<t<=c['window']['target_ns'] for t in stamps)
            if stamps:assert stamps[0]>=last_stamp;last_stamp=stamps[-1]
            if previous:
                u=safe_url(previous['next_url']);assert meta['request']=={'url':u.split('?',1)[0],'params':dict(parse_qsl(urlparse(u).query))}
            previous=b;checked+=1
        if c['complete']:assert previous is not None and not previous.get('next_url')
    result=read(root/'results.json')
    for pair in result['pairs']:
        for k in ['entry','exit']:
            m=pair[k]
            if m.get('source_json'):
                ref=json.loads(m['source_json']);assert file_hash(ref['path'])==ref['sha256']
                q=read(ref['path'])['results'][ref['row']]
                assert q['sip_timestamp']==m['timestamp']<=m['target_ns']
                if m['status']=='OK':
                    assert 0<=m['age_ns']<=5*SECOND and 81 not in q.get('conditions',[])
                    assert q.get('correction',0)==0
                    assert number(q['bid_price'])==number(m['bid']) and number(q['ask_price'])==number(m['ask'])
    receipt={'status':'PASS','pages_checked':checked,'protected_files_unchanged':len(frozen['protected_files']),
             'deterministic_results_equal':True,'no_future_quote_evidence':True,'hard_budgets_pass':True}
    write_json(Path('reports',config['run_id'],'validation.json'),receipt)
    return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run','validate','report']);p.add_argument('--env-file');args=p.parse_args()
    c=read(CONFIG);root,frozen=freeze(c)
    with (root/'.writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.command=='freeze':result={'selected':len(frozen['selected']),'run_id':c['run_id']}
        elif args.command=='run':result=publish(c,root,acquire(c,root,frozen,load_key(args.env_file)))
        elif args.command=='validate':result=validate(c,root,frozen)
        else:result=publish(c,root,read(root/'results.json'))
        print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
