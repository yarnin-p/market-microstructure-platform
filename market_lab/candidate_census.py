"""Candidate-first single-cycle discovery; preserves the stopped full-tick cache."""
import argparse
import csv
import io
import json
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
from datetime import datetime,timezone

import pandas as pd
from . import census as legacy
from .storage import write_json,file_hash,digest
from .tick_replay import bounds,session_label,number

RUN='census-candidates-20261113-rest-20261116-v2'
ROOT=Path('data/runs')/RUN
REPORT=Path('reports')/RUN

def read(path):return json.loads(Path(path).read_text())

def tick_pages(ticker):return sorted((legacy.ROOT/'raw'/ticker).glob('page-[0-9][0-9][0-9][0-9][0-9].json'))

def validated_cached(ticker,cycle):
    paths=tick_pages(ticker);expected=None;last=None;sources=[];rows=[]
    for i,p in enumerate(paths):
        legacy.seal(p);cap=read(p)
        assert cap['page_index']==i
        if i:assert expected is not None and cap['params']==expected
        else:
            assert cap['path']==f'/v3/trades/{ticker}'
            assert cap['params']=={'timestamp.gt':str(bounds(cycle)[0]),'timestamp.lte':str(bounds(cycle)[-1]),'sort':'timestamp','order':'asc','limit':cap['params']['limit']}
        rr=legacy.parse_csv(cap['csv'],cap['expected_rows']);legacy.cursor_tail_audit(cap['next_params'],rr)
        if rr:
            assert all(a['sip_timestamp']<=b['sip_timestamp']for a,b in zip(rr,rr[1:]))
            if last is not None:assert rr[0]['sip_timestamp']>=last
            last=rr[-1]['sip_timestamp']
        rows.extend(rr);sources.append({'path':str(p.resolve()),'sha256':file_hash(p),'rows':len(rr)})
        expected=cap['next_params']
    return rows,sources,bool(paths)and expected is None


def derived_minutes(rows,cycle):
    highs={}
    for r in rows:
        t=r['sip_timestamp'];p=number(r.get('price'))
        if p is None or p<=0 or session_label(cycle,t)not in {'AH','PRE','RTH'}:continue
        m=t//60_000_000_000*60000
        if m not in highs or p>highs[m]:highs[m]=p
    return [{'t':t,'h':str(h)}for t,h in sorted(highs.items())]


def prepare():
    cfg=legacy.read(legacy.ROOT/'config.json');queue=legacy.read(legacy.ROOT/'queue.json')
    if (ROOT/'config.json').exists():return state()
    write_json(legacy.ROOT/'acquisition-paused.json',{'status':'STOPPED_BY_USER','at':datetime.now(timezone.utc).isoformat(),'reason':'Replaced with aggregate candidate-first protocol; preserve all raw pages/checkpoints','replacement_run':RUN})
    config={'run_id':RUN,'cycle':cfg['cycle'],'replay_policy':'sip-first-touch-v1','trigger_multiplier':'1.10',
            'universe_source':{'path':str((legacy.ROOT/'universe.json').resolve()),'sha256':file_hash(legacy.ROOT/'universe.json')},
            'queue_source':{'path':str((legacy.ROOT/'queue.json').resolve()),'sha256':file_hash(legacy.ROOT/'queue.json')},
            'historical_eligibility':'all original non-float gates; no float substitution',
            'float_policy':'retrospective proxy annotation only; never a future eligibility gate',
            'aggregate_policy':'complete cached REST trades -> conservative observed-session raw minute highs; remaining opportunities -> unadjusted REST minute bars',
            'aggregate_padding':'one minute before AH/PRE start; full 16:00 ET end minute included conservatively; ticks enforce exact boundaries',
            'aggregate_from_ms':bounds(cfg['cycle'])[0]//1000000-60000,'aggregate_to_ms':bounds(cfg['cycle'])[-1]//1000000-1,
            'aggregate_limit':50000,'aggregate_adjusted':False,'max_workers':4,'batch_seconds':1750,'batch_requests':2000,
            'max_page_bytes':33554432,'batch_decoded_bytes':2**30,'max_local_storage_bytes':64*2**30,
            'original_observed_touch_coverage_limit':'final vendor bars can omit subsequently cancelled/corrected prints; aggregate-negative is not a verified tick zero',
            'tick_fetch_authorized':False}
    ROOT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    write_json(ROOT/'config.json',config)
    for i,op in enumerate(queue):
        rows,sources,complete=validated_cached(op['ticker'],cfg['cycle'])
        if complete:
            write_json(ROOT/'aggregates'/f"{op['ticker']}.json",{'ticker':op['ticker'],'complete':True,'source_kind':'CACHED_REST_TRADES_RAW_MINUTE_HIGH',
              'bars':derived_minutes(rows,cfg['cycle']),'raw_sources':sources,'raw_rows':len(rows),'covers_exact_sip_sessions':True})
        if i%100==0:print('prepared cache summaries',i,flush=True)
    write_json(ROOT/'frozen.json',{'config_sha256':file_hash(ROOT/'config.json'),'population':len(queue),
        'float_strata':dict(Counter(x['float_proxy_stratum']for x in queue)),
        'legacy_raw_cache_preserved':True,'policy_code_sha256':file_hash(__file__)})
    return state()


def state():
    raise RuntimeError('SUPERSEDED_885_AGGREGATE_PLAN; use manifest270 AH-only discovery')


def bar_overlaps_observed(t,cycle):
    a,ah,pre,opened,end=(x//1000000 for x in bounds(cycle))
    # Conservative superset of both SIP and participant-bucketed minute bars.
    return a-60000<=t<ah or pre-60000<=t<end


def parse_bars(text):
    if '[truncated' in text.lower():raise ValueError('TRUNCATED_AGGREGATES')
    if not text.strip():raise ValueError('EMPTY_UNCLASSIFIED_CONNECTOR_RESPONSE')
    reader=csv.DictReader(io.StringIO(text));assert reader.fieldnames and {'t','h'}<=set(reader.fieldnames),'NOT_AGGREGATE_CSV'
    bars=[]
    for r in reader:
        t=Decimal(r['t']);assert t==t.to_integral_value()
        h=number(r['h']);assert h is not None and h>0
        bars.append({'t':int(t),'h':str(h)})
    assert len({r['t']for r in bars})==len(bars)
    assert [r['t']for r in bars]==sorted(r['t']for r in bars)
    return bars


def import_aggregate(path):
    cap=read(path);cfg=read(ROOT/'config.json');ticker=cap['ticker']
    assert cap['path']==f"/v2/aggs/ticker/{ticker}/range/1/minute/{cfg['aggregate_from_ms']}/{cfg['aggregate_to_ms']}"
    assert cap['params']=={'adjusted':False,'sort':'asc','limit':50000}
    assert not cap.get('next_params'),'UNEXPECTED_AGGREGATE_PAGINATION'
    bars=parse_bars(cap['csv'])
    assert all(cfg['aggregate_from_ms']//60000*60000<=r['t']<=cfg['aggregate_to_ms']for r in bars)
    result={'ticker':ticker,'complete':True,'source_kind':'PROVIDER_REST_MINUTE_HIGH','bars':bars,
            'source':{'path':str(Path(path).resolve()),'sha256':file_hash(path)},'bar_count':len(bars)}
    write_json(ROOT/'aggregates'/f'{ticker}.json',result)
    return {'ticker':ticker,'bars':len(bars)}


def screen():
    cfg=read(ROOT/'config.json');queue=read(cfg['queue_source']['path']);population=[];candidates=[]
    for op in queue:
        p=ROOT/'aggregates'/f"{op['ticker']}.json";threshold=Decimal(op['previous_rth_close'])*Decimal('1.10')
        if not p.exists():
            population.append({'ticker':op['ticker'],'security_id':op['security_id'],'status':'AGGREGATE_UNKNOWN','reason':'NOT_ACQUIRED'});continue
        agg=read(p);bars=[r for r in agg['bars']if bar_overlaps_observed(r['t'],cfg['cycle'])or(agg['source_kind']=='CACHED_REST_TRADES_RAW_MINUTE_HIGH'and r['t']==bounds(cfg['cycle'])[-1]//1000000)]
        crossing=[r for r in bars if Decimal(r['h'])>=threshold]
        partial_path=ROOT/'partial-cache'/f"{op['ticker']}.json"
        rescue=[]
        if partial_path.exists():
            partial=read(partial_path)
            rescue=[r for r in partial['bars']if Decimal(r['h'])>=threshold]
        rescued=bool(rescue)and not crossing
        crossing+=rescue
        entry={'ticker':op['ticker'],'security_id':op['security_id'],'previous_rth_close':op['previous_rth_close'],
               'threshold':str(threshold),'float_proxy_stratum':op['float_proxy_stratum'],'status':'PRICE_CANDIDATE'if crossing else 'AGGREGATE_SCREEN_NEGATIVE',
               'source_kind':agg['source_kind'],'partial_cache_rescue':bool(rescued),'partial_cache_source':({'path':str(partial_path.resolve()),'sha256':file_hash(partial_path)}if partial_path.exists()else None),'bars':len(bars),'crossing_minutes':crossing,'source':{'path':str(p.resolve()),'sha256':file_hash(p)}}
        population.append(entry)
        if crossing:
            rows,sources,complete=validated_cached(op['ticker'],cfg['cycle'])
            candidates.append({**op,'aggregate_screen':entry,'tick_cache_complete':complete,'cached_pages':len(sources)})
    unknown=[r for r in population if r['status']=='AGGREGATE_UNKNOWN']
    counts={'run_id':RUN,'historical_reference_records':13247,'known_eligible_universe':len(queue),
            'float_proxy_annotation':dict(Counter(r['float_proxy_stratum']for r in queue)),
            'aggregate_screen_complete':not unknown,'aggregate_complete':len(queue)-len(unknown),'aggregate_unknown':len(unknown),
            'price_candidates':len(candidates),'candidate_ticks_already_complete':sum(r['tick_cache_complete']for r in candidates),
            'candidates_requiring_additional_ticks':sum(not r['tick_cache_complete']for r in candidates),
            'screen_negative':sum(r['status']=='AGGREGATE_SCREEN_NEGATIVE'for r in population),
            'screen_sources':dict(Counter(r.get('source_kind','UNKNOWN')for r in population)),
            'tick_acquisition_not_yet_authorized':True}
    assert len(queue)==len(candidates)+counts['screen_negative']+len(unknown)
    write_json(ROOT/'screen.json',population);write_json(ROOT/'candidates.json',candidates);write_json(REPORT/'pre-tick-counts.json',counts)
    legacy.table(REPORT/'aggregate-screen.csv',population)
    legacy.table(REPORT/'candidates.csv',[{k:v for k,v in r.items() if k not in {'reference_provenance','float_proxy'}}for r in candidates])
    return counts


def authorize():
    counts=read(REPORT/'pre-tick-counts.json');assert counts['aggregate_screen_complete'],'report aggregate unknowns before authorizing ticks'
    selected=read(ROOT/'candidates.json')
    write_json(legacy.ROOT/'candidate-tick-authorization.json',{'replacement_run':RUN,'tickers':[r['ticker']for r in selected],
        'screen_counts_sha256':file_hash(REPORT/'pre-tick-counts.json'),'candidate_sha256':file_hash(ROOT/'candidates.json'),
        'pre_tick_counts_reported':True,'authorized_at':datetime.now(timezone.utc).isoformat()})
    return {'authorized_candidates':len(selected),'needs_more_ticks':counts['candidates_requiring_additional_ticks']}


def verify():
    cfg=read(ROOT/'config.json');selected=read(ROOT/'candidates.json');base=read(legacy.ROOT/'config.json')
    auth=read(legacy.ROOT/'candidate-tick-authorization.json')
    assert auth['candidate_sha256']==file_hash(ROOT/'candidates.json')
    assert file_hash(cfg['queue_source']['path'])==cfg['queue_source']['sha256']
    assert file_hash(cfg['universe_source']['path'])==cfg['universe_source']['sha256']
    for path,expected in read(legacy.ROOT/'frozen.json')['protected_hashes'].items():assert file_hash(path)==expected
    legacy.source_audit(legacy.pq.read_table(legacy.SOURCE).to_pylist())
    conditions={r['id']:r for r in read(legacy.ROOT/'conditions.json')}
    results=[]
    for op in selected:
        result=legacy.replay_symbol({**op,'sample':'CANDIDATE_FIRST_REST_V2'},base,conditions,run_id=RUN)
        write_json(ROOT/'replay'/f"{op['ticker']}.json",result);results.append(result)
    events=sorted([r['event']for r in results if r['event']],key=lambda e:(e['event_timestamp'],e['security_id']))
    confirmed=[e for e in events if e['observed_window_first_verified']]
    unknown=[r for r in results if r['disposition']=='UNKNOWN_INCOMPLETE']
    negative=[r for r in results if r['disposition']=='ZERO_EVENT_OBSERVED']
    assert len(selected)==len(events)+len(unknown)+len(negative)
    counts=read(REPORT/'pre-tick-counts.json')
    summary={**counts,'tick_acquisition_not_yet_authorized':False,'candidate_events':len(events),
      'confirmed_observed_window_firsts':len(confirmed),'events_with_unknown_prior_or_partial_evidence':len(events)-len(confirmed),
      'frozen_verified_AH':sum(e['first_touch_status']=='VERIFIED_FIRST_TOUCH'for e in events),
      'frozen_unverified_including_overnight_scope':sum(e['first_touch_status']!='VERIFIED_FIRST_TOUCH'for e in events),
      'candidates_with_no_eligible_touch':len(negative),'candidate_unknown':len(unknown),
      'candidate_ticks_fully_acquired':sum(r['complete']for r in results),
      'candidate_tick_coverage_percent':100*sum(r['complete']for r in results)/len(selected)if selected else 100,
      'sessions':dict(Counter(e['session']for e in confirmed)),
      'all_event_sessions':dict(Counter(e['session']for e in events)),
      'status':'COMPLETE_CANDIDATE_VERIFICATION'if all(r['complete']for r in results)and not unknown else 'INCOMPLETE / BLOCKED',
      'continuous_24h_first_touch_proven':False,'original_observed_touch_complete_census_claimed':False,
      'original_json_hash_dependent_trigger_ties':sum(e['source_hash_tie_ambiguity']for e in events),
      'source_http_json_headers_exposed':False,'reconciliation_passed':True}
    fields=['ticker','security_id','cycle_date','session','previous_rth_close','threshold_price','first_touch_price',
            'first_touch_timestamp_et','first_touch_timestamp_utc','first_touch_timestamp_utc_ns','trade_size','trade_conditions',
            'trade_exchange','first_touch_status','observed_window_first_verified','correction_status','quality_flags',
            'float_proxy_stratum','source_reference','run_id','census_event_id','raw_first_crossing','source_hash_tie_ambiguity']
    legacy.table(REPORT/'confirmed-events.csv',confirmed,fields)
    legacy.table(REPORT/'all-candidate-events.csv',events,fields)
    legacy.table(REPORT/'unverified-events.csv',[e for e in events if not e['observed_window_first_verified']],fields)
    for name,rows in [('no-eligible-touch',negative),('unknown',unknown)]:
        legacy.table(REPORT/f'{name}.csv',[{k:v for k,v in r.items()if k not in {'event','raw_first_crossing','pages'}}for r in rows],
             ['ticker','security_id','float_proxy_stratum','disposition','complete','reason','raw_rows','reject_counts'])
    write_json(REPORT/'summary.json',summary)
    write_json(REPORT/'evidence-index.json',{'frozen':read(ROOT/'frozen.json'),'config':cfg,
        'candidate_sha256':file_hash(ROOT/'candidates.json'),'screen_sha256':file_hash(ROOT/'screen.json'),
        'tick_pages':[p for r in results for p in r['pages']],
        'implementation_hashes':{p:file_hash(p)for p in ['market_lab/candidate_census.py','market_lab/census.py','market_lab/tick_replay.py','scripts/candidate_aggregate_batch.js','scripts/census_mcp_batch.js']}})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','state','import','screen','authorize','verify']);parser.add_argument('path',nargs='?');args=parser.parse_args()
    result=prepare()if args.action=='prepare'else state()if args.action=='state'else import_aggregate(args.path)if args.action=='import'else screen()if args.action=='screen'else authorize()if args.action=='authorize'else verify()
    print(json.dumps(result))
