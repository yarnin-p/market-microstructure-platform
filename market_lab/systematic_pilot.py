"""TASK 002.2: frozen daily stratified sampling and bounded observed-session replay."""
import argparse
import fcntl
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import pyarrow.parquet as pq

from .api import APIError, load_key, safe_url
from .eligibility import identity
from .m2_pilot import control_eligible, source_rows, event_table
from .m2_report import records
from .replay_methodology import ReplayState, condition_maps, outcome_sensitivity
from .replay_qa import iter_normalized, tree_hashes
from .storage import digest, file_hash, write_json
from .tick_ingest import TickClient, normalize
from .tick_replay import SECOND, ns, correction_key, number, quote_at_event

CONFIG = 'configs/task-002-2-systematic-v1.json'


def read(path):
    return json.loads(Path(path).read_text())


def size(root):
    return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())


def freeze(config):
    root=Path('data/runs',config['run_id']);root.mkdir(parents=True,exist_ok=True)
    p=root/'execution.json'
    frozen={'config':config,'code_hashes':{str(p):file_hash(p) for p in Path('market_lab').glob('*.py')}}
    if p.exists():
        prior=read(p)
        if any(prior[k]!=v for k,v in frozen.items()): raise ValueError('code/config drift: use a new run ID')
        return root,prior
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if not head.startswith(config['baseline_commit']): raise ValueError('unexpected implementation baseline')
    frozen['baseline_commit']=head
    frozen['protected_files']={}
    for parent in [Path('data/runs'),Path('reports')]:
        for old in sorted(parent.iterdir()):
            if old.is_dir() and old.name!=config['run_id']:
                frozen['protected_files'].update(tree_hashes(old))
    write_json(p,frozen)
    return root,frozen


class BudgetClient(TickClient):
    def get(self,path,params=None):
        # Reserve space for a response, its normalized partition and metadata.
        if not self.offline and size(self.root.parent)+4*self.config['max_page_bytes']>self.config['max_storage_bytes']:
            raise APIError('M2_STORAGE_BUDGET')
        return super().get(path,params)


def reference_pages(client,path,params):
    rows,sources=[],[]
    error=None
    for _ in range(client.config['max_reference_pages']):
        try:
            body,source=client.get(path,params)
            if not isinstance(body['results'],list): raise APIError('REFERENCE_RESULTS_NOT_ARRAY')
            rows.extend({**r,'_source':source} for r in body['results']);sources.append(source)
            path,params=body.get('next_url'),None
            if not path: return rows,sources,None
        except APIError as exc:
            error=str(exc);break
    return rows,sources,error or 'REFERENCE_PAGE_BUDGET'


def float_evidence(row,current,floats):
    sid=row['security_id']
    matches=current.get(sid,[])
    ev={'status':'UNRESOLVED','original_ticker':row['ticker'],'historical_security_id':sid,
        'cohort':'MASSIVE_CURRENT_FLOAT_PROXY','is_verified_pit':False,'endpoint':'/stocks/vX/float','field':'free_float','value':None}
    # Alias resolution uses security identity, never a current listing gate.
    if len(matches)!=1:
        return {**ev,'reason':'MISSING_OR_AMBIGUOUS_CURRENT_SECURITY_IDENTITY'}
    ref=matches[0];found=floats.get(ref['ticker'],[])
    ev.update(resolved_ticker=ref['ticker'],resolved_security_id=identity(ref),identity_source=ref['_source'])
    if len(found)!=1 or not isinstance(found[0].get('free_float'),int) or isinstance(found[0]['free_float'],bool):
        return {**ev,'reason':'MISSING_OR_AMBIGUOUS_FREE_FLOAT'}
    f=found[0];value=f['free_float']
    ev.update(value=value,status='ELIGIBLE' if 100000<=value<=15000000 else 'INELIGIBLE',
              effective_date=f.get('effective_date'),retrieved_at=f['_source']['retrieved_at'],source=f['_source'],
              reason='CURRENT_FLOAT_RETROSPECTIVE_PROXY')
    return ev


def sample_frame(frame,config):
    selected,strata=[],[]
    for cycle in sorted({r['cycle_id'] for r in frame}):
        for stratum in config['strata']:
            pool=sorted([r for r in frame if r['cycle_id']==cycle and r['stratum']==stratum],key=lambda r:r['security_id'])
            n=min(config['per_stratum'],len(pool));N=len(pool)
            seed=int(digest([config['master_seed'],cycle,stratum])[:16],16)
            strata.append({'cycle_id':cycle,'stratum':stratum,'population_N':N,'sample_n':n,'seed':seed,
                           'selection_probability':n/N if N else None})
            for r in random.Random(seed).sample(pool,n):
                selected.append({**r,'sample':'SYSTEMATIC','selection_probability':n/N,'sampling_weight':N/n,
                                 'population_N':N,'sample_n':n,'sampling_seed':seed})
    return selected,strata


def prepare(config,client,root):
    if (root/'selection.json').exists(): return read(root/'selection.json')
    calendar=read(Path('data/runs',config['source_m1_run'],'calendar.json'))[:config['cycle_count']]
    if len(calendar)!=10 or any(c['split_group']!='EXPLORATION' for c in calendar): raise ValueError('10 exploration cycles required')
    sources=[];historical=[];frame_counts=[]
    for cycle in calendar:
        rows,source=source_rows(config['source_m1_run'],cycle['cycle_id']);sources.append(source)
        eligible=[r for r in rows if control_eligible(r)]
        counts=Counter(r['security_id'] for r in eligible)
        ambiguous={sid for sid,n in counts.items() if n!=1 or not sid}
        frame_counts.append({'cycle_id':cycle['cycle_id'],'m1_records':len(rows),'non_float_eligible':len(eligible),
                             'ambiguous_identity_records':sum(r['security_id'] in ambiguous for r in eligible)})
        for r in eligible:
            if r['security_id'] not in ambiguous:
                historical.append({'cycle_id':cycle['cycle_id'],'security_id':r['security_id'],'ticker':r['ticker'],
                                   'previous_rth_close':str(r['previous_rth_close']),'m1_record_id':r['record_id'],'source_m1':source})
    current,cur_sources,cur_error=reference_pages(client,'/v3/reference/tickers',{'market':'stocks','active':'true','limit':1000,'sort':'ticker','order':'asc'})
    floats,float_sources,float_error=reference_pages(client,'/stocks/vX/float',{'limit':5000,'sort':'ticker.asc'})
    conditions,condition_sources,condition_error=reference_pages(client,'/v3/reference/conditions',{'asset_class':'stocks','data_type':'trade','limit':1000})
    current_by_id,by_ticker=defaultdict(list),defaultdict(list)
    for r in current:
        if identity(r):current_by_id[identity(r)].append(r)
    unmapped_float=[]
    for r in floats:
        if isinstance(r.get('ticker'),str) and r['ticker']:by_ticker[r['ticker']].append(r)
        else:unmapped_float.append({'reason':'MISSING_TICKER_CANNOT_RESOLVE_SECURITY','provider_record':r})
    sec_path=Path('data/sec-pilot-20261115-v2/results-reviewed-v1.json')
    sec={r['security']['security_id']:r for r in read(sec_path)['results']}
    frame=[]
    for r in historical:
        ev=float_evidence(r,current_by_id,by_ticker)
        cohorts=['EXCHANGE_PRICE_ONLY']
        if ev['status']=='ELIGIBLE':cohorts.append('MASSIVE_CURRENT_FLOAT_PROXY')
        se=sec.get(r['security_id'])
        frame.append({**r,'float_proxy':ev,'cohorts':cohorts,'sec_evidence':({'classification':se['status'],'derived_estimates':se.get('derived_estimates',[]),'source':{'path':str(sec_path.resolve()),'sha256':file_hash(sec_path)},'carry_forward':False} if se else None),
                      'stratum':'PROXY_FLOAT_IN_RANGE' if ev['status']=='ELIGIBLE' else 'OTHER_EXCHANGE_PRICE_ELIGIBLE'})
    selected,strata=sample_frame(frame,config)
    context={'unmapped_float_records':unmapped_float,'conditions':[ {k:v for k,v in c.items() if k!='_source'} for c in conditions] if not condition_error else [],
             'reference_sources':cur_sources+float_sources+condition_sources,
             'errors':{'current_identity':cur_error,'float':float_error,'conditions':condition_error},
             'sec_source':{'path':str(sec_path.resolve()),'sha256':file_hash(sec_path)}}
    write_json(root/'context.json',context)
    event_table(root/'population/frame.parquet',frame)
    selection={'calendar':calendar,'selected':selected,'strata':strata,'frame_counts':frame_counts,'sources':sources,
               'context_sha256':file_hash(root/'context.json'),'config_hash':digest(config),'frame_sha256':file_hash(root/'population/frame.parquet'),
               'selection_method':'Independent daily stratified SRS without replacement; 12 proxy + 12 complementary control; no future price outcomes',
               'diagnostic_sample_size':0,'population_inference':False}
    write_json(root/'selection.json',selection)
    write_json(root/'selection.sha256.json',{'sha256':file_hash(root/'selection.json')})
    return selection


def normalized_pages(coverage,opportunity,cycle,directory):
    paths=[];invalid=0
    for i,page in enumerate(coverage['pages']):
        p=directory/f'page-{i:04d}.parquet'
        if p.exists():
            a=read(p.with_suffix('.audit.json'))
            if a['sha256']!=file_hash(p):raise ValueError('normalized partition hash mismatch')
        else:
            _,a=normalize({**coverage,'pages':[page],'raw_rows':page['rows']},opportunity['security_id'],cycle,p)
        invalid+=a['invalid_timestamp_rows'];paths.append(str(p))
    return paths,invalid


def replay(paths,coverage,opportunity,cycle,config,conditions,invalid=0):
    pairs=defaultdict(list);observed_end=0
    for row in iter_normalized(paths):
        observed_end=max(observed_end,row.get('sip_timestamp') or 0)
        if row.get('correction')==12:pairs[correction_key(row)].append(row)
    complete=coverage['complete'] and invalid==0 and bool(conditions)
    maps=condition_maps(conditions)
    states={policy:ReplayState(policy,cycle,opportunity,config,maps[policy],complete,config['run_id'],observed_end)
            for policy in config['condition_policies']}
    raw_sessions=Counter();raw_count=0
    for raw in iter_normalized(paths):
        row=dict(raw);raw_count+=1;raw_sessions[row['session']]+=1
        row['restoration_status']='AS_RECORDED'
        if row.get('correction')==1:
            match=[r for r in pairs[correction_key(row)] if r['sip_timestamp']>row['sip_timestamp']]
            if len(match)==1:
                row.update({k:match[0][k] for k in ['price','size','conditions_json']})
                row.update(restoration_status='ORIGINAL_FIELDS_FROM_MATCHING_12',restoration_source=match[0]['source_json'])
            else:row['restoration_status']='CORRECTION_RECONSTRUCTION_UNRESOLVED'
        for state in states.values():state.feed(row)
    return states,raw_count,dict(raw_sessions)


def nbbo_context(rows,event,config,complete):
    quote=quote_at_event(rows,event,config,complete)
    p=number(event['touch_price']);bid=number(quote.get('bid'));ask=number(quote.get('ask'))
    if bid is not None and ask is not None and bid>0 and ask>=bid:
        quote['trade_relation']='ABOVE_PRECEDING_ASK' if p>ask else 'BELOW_PRECEDING_BID' if p<bid else 'WITHIN_NBBO'
    else:quote['trade_relation']='NBBO_UNAVAILABLE_OR_INVALID'
    quote['trade_discarded_for_nbbo_relation']=False
    quote['used_for_trigger']=False
    return quote


def execute(config,root,client):
    selection=prepare(config,client,root);selection_hash=file_hash(root/'selection.json')
    if selection_hash!=read(root/'selection.sha256.json')['sha256']:raise ValueError('selection changed')
    context=read(root/'context.json');conditions={r['id']:r for r in context['conditions']}
    cycles={c['cycle_id']:c for c in selection['calendar']}
    all_events,all_outcomes,all_opportunities=[],[],[]
    quote_windows=len(list(root.glob('ticks/cycle=*/security=*/quotes/*/coverage.json')))
    # Round-robin cycles makes early budget exhaustion less concentrated in dates.
    grouped={}
    for c in cycles:
        buckets=[[o for o in selection['selected'] if o['cycle_id']==c and o['stratum']==st] for st in config['strata']]
        grouped[c]=[bucket[i] for i in range(max(map(len,buckets))) for bucket in buckets if i<len(bucket)]
    ordered=[grouped[c][i] for i in range(max(map(len,grouped.values()))) for c in cycles if i<len(grouped[c])]
    for position,op in enumerate(ordered):
        cycle=cycles[op['cycle_id']];pair=root/'ticks'/('cycle='+op['cycle_id'])/('security='+op['security_id'])
        saved=pair/'result.json'
        if saved.exists():
            result=read(saved)
            if result['selection_hash']!=selection_hash:raise ValueError('checkpoint selection mismatch')
            # Resume trusts no mutable input: validate hashes of all checkpoint dependencies.
            for p,h in result['input_hashes'].items():
                if file_hash(p)!=h:raise ValueError('checkpoint input hash mismatch')
        else:
            coverage=client.window('trades',op['ticker'],ns(cycle['anchor_at']),ns(cycle['end_at']),pair/'trades')
            paths,invalid=normalized_pages(coverage,op,cycle,pair/'trades/normalized')
            states,raw_count,raw_sessions=replay(paths,coverage,op,cycle,config,conditions,invalid)
            events,outs,opps=[],[],[];q_count=0
            for policy,state in states.items():
                opportunity={**op,'run_id':config['run_id'],'condition_policy':policy,'complete_observed_sessions':state.complete,
                             'observed_opportunity_eligible':state.complete and not state.unknown_prior,
                             'zero_event_observed':state.complete and not state.unknown_prior and state.event is None,
                             'strict_full_cycle_opportunity_eligible':False,'raw_rows':coverage['raw_rows'],'normalized_rows':raw_count,
                             'raw_session_counts':raw_sessions,'invalid_timestamp_rows':invalid,'provider_pages':len(coverage['pages']),
                             'coverage_error':coverage['error'],'eligible_trades':len(state.eligible),'reject_counts':dict(state.reject_counts),
                             'rejected_crossings':state.rejected_crossings,'subsequent_crossings':state.recrosses,
                             'event_id':state.event['event_id'] if state.event else None}
                opps.append(opportunity)
                if state.event:
                    event={**state.event,'selection_probability':op['selection_probability'],'sampling_weight':op['sampling_weight'],
                           'stratum':op['stratum'],'experiment_version':'task-002-2-systematic-v1'}
                    qdir=pair/'quotes'/str(event['event_timestamp'])
                    if (qdir/'coverage.json').exists() or quote_windows<config['max_quote_windows']:
                        # Same event across sensitivity policies shares one immutable quote window.
                        existed=(qdir/'coverage.json').exists()
                        qcov=client.window('quotes',op['ticker'],max(ns(cycle['anchor_at']),event['event_timestamp']-config['quote_radius_seconds']*SECOND),
                                          min(ns(cycle['end_at']),event['event_timestamp']+config['quote_radius_seconds']*SECOND),qdir)
                        qpaths,qinvalid=normalized_pages(qcov,op,cycle,qdir/'normalized')
                        quotes=[]
                        for p in qpaths:quotes.extend(pq.ParquetFile(p).read().to_pylist())
                        event['quote']=nbbo_context(quotes,event,config,qcov['complete'] and not qinvalid)
                        if not existed:quote_windows+=1;q_count+=1
                    else:event['quote']={'status':'QUOTE_WINDOW_BUDGET','trade_relation':'UNKNOWN'}
                    events.append(event)
                    for seconds in config['gap_sensitivities_seconds']:
                        outs.append({**outcome_sensitivity(state,cycle,config,seconds),'run_id':config['run_id'],
                                     'cohorts':op['cohorts'],'selection_probability':op['selection_probability'],'sampling_weight':op['sampling_weight']})
            dependencies={str(p):file_hash(p) for p in pair.rglob('*') if p.is_file()}
            for p in pair.rglob('coverage.json'):
                for page in read(p)['pages']:dependencies[page['path']]=page['sha256']
            result={'selection_hash':selection_hash,'events':events,'outcomes':outs,'opportunities':opps,'quote_windows':q_count,'input_hashes':dependencies}
            write_json(saved,result)
        all_events.extend(result['events']);all_outcomes.extend(result['outcomes']);all_opportunities.extend(result['opportunities'])
        print(json.dumps({'processed':position+1,'cycle':op['cycle_id'],'ticker':op['ticker'],'complete':result['opportunities'][0]['complete_observed_sessions'],
                          'primary_event':any(e['condition_policy']=='HIGH_LOW_ONLY' for e in result['events']),
                          'requests':len(client.ledger['attempts']),'bytes':client.ledger['decoded_bytes']}),flush=True)
    for name,rows in [('events',all_events),('outcomes',all_outcomes),('opportunities',all_opportunities)]:
        event_table(root/name/(name+'.parquet'),rows)
    from .systematic_report import report
    return report(config,root,selection,all_events,all_outcomes,all_opportunities,client.ledger)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','run','validate','report'])
    p.add_argument('--config',default=CONFIG);p.add_argument('--env-file');p.add_argument('--offline',action='store_true')
    args=p.parse_args();config=read(args.config)
    root,execution=freeze(config)
    with (root/'.writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        client=BudgetClient(root/'raw',config,load_key(args.env_file),args.offline)
        if args.command=='prepare':
            selection=prepare(config,client,root);result={'selected':len(selection['selected']),'strata':selection['strata']}
        elif args.command=='run':result=execute(config,root,client)
        else:
            from .systematic_report import validate,report
            result=validate(config,root,execution) if args.command=='validate' else report(config,root,read(root/'selection.json'),records(root/'events/events.parquet'),records(root/'outcomes/outcomes.parquet'),records(root/'opportunities/opportunities.parquet'),client.ledger)
        print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
