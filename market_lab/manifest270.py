"""Approval-gated 270-seed + AH discovery manifest; never fetches trades."""
import argparse,csv,io,json,shutil
from collections import Counter
from decimal import Decimal
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
from . import census as old,candidate_census as aggregates
from .storage import write_json,file_hash,digest
from .tick_replay import bounds

RUN='manifest270-ah-20261113-20261116-v3'
ROOT=Path('data/runs')/RUN
REPORT=Path('reports')/RUN
SEED=Path('configs/census-seed-270-20261113.txt')

def read(p):return json.loads(Path(p).read_text())

def classify(row):
    if row is None:return 'CANDIDATE_UNRESOLVED',['HISTORICAL_REFERENCE_NOT_FOUND']
    excluded=[g+':'+v['reason'] for g,v in row['gates'].items()if v['status']=='INELIGIBLE']
    unresolved=[g+':'+v['reason'] for g,v in row['gates'].items()if v['status']=='UNRESOLVED']
    f=row['float_proxy']
    if f['status']=='INELIGIBLE':excluded.append(f"CURRENT_FLOAT_PROXY_OUT_OF_RANGE:{f['value']}")
    elif f['status']!='ELIGIBLE':unresolved.append('CURRENT_FLOAT_PROXY:'+f['reason'])
    if row['change_status']!='NO_CHANGE_OBSERVED':unresolved.append('SECURITY_CONTINUITY:'+row['change_status'])
    return ('CANDIDATE_EXCLUDED',excluded)if excluded else ('CANDIDATE_UNRESOLVED',unresolved)if unresolved else ('CANDIDATE_PASS',[])


def ah_bars(bars,cycle):
    a,ah,*_=bounds(cycle);return [r for r in bars if a//1000000<=int(r['t'])<ah//1000000]


def prepare():
    ROOT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    seeds=SEED.read_text().split();assert len(seeds)==len(set(seeds))==270
    frame=old.read(old.ROOT/'universe.json');by={r['ticker']:r for r in frame};cycle=old.read(old.ROOT/'config.json')['cycle']
    audit=[]
    for ticker in seeds:
        row=by.get(ticker);status,reasons=classify(row)
        p=row['reference_provenance']if row else {};f=row['float_proxy']if row else {}
        audit.append({'ticker':ticker,'security_id':row['security_id']if row else None,'status':status,'reasons':reasons,
          'security_type':row['security_type']if row else None,'historical_primary_exchange':p.get('ticker_reference',{}).get('primary_exchange'),
          'previous_rth_close':row['previous_rth_close']if row else None,'current_float_proxy_shares':f.get('value'),
          'float_effective_date':f.get('effective_date'),'float_retrieved_at':f.get('retrieved_at'),'float_is_verified_pit':False,
          'reference_source':p.get('source_reference'),'price_source':p.get('source_price'),'float_source':f.get('source')})
    write_json(ROOT/'seed-audit.json',audit);old.table(REPORT/'seed-270-universe-audit.csv',audit)
    eligible=[r for r in frame if classify(r)[0]=='CANDIDATE_PASS']
    assert len({r['security_id']for r in eligible})==len(eligible)
    for row in eligible:
        assert row['security_type']=='CS' and row['security_id']
        assert row['reference_provenance']['ticker_reference']['primary_exchange'] in {'XNAS','XASE','XNYS'}
        assert 0<Decimal(row['previous_rth_close'])<=3
        assert isinstance(row['float_proxy']['value'],int)and 100000<=row['float_proxy']['value']<=15000000
    cfg={'run_id':RUN,'cycle':cycle,'clock':'SIP_UTC_NS','replay_policy':'sip-first-touch-v1','price_multiplier':'1.10',
      'seed_count':270,'seed_sha256':file_hash(SEED),'universe_source':{'path':str((old.ROOT/'universe.json').resolve()),'sha256':file_hash(old.ROOT/'universe.json')},
      'float_gate':'100000 <= current proxy <= 15000000; retrospective, not historical PIT',
      'ah_from_ms':bounds(cycle)[0]//1000000,'ah_to_ms':bounds(cycle)[1]//1000000-1,
      'max_workers':4,'batch_seconds':1750,'batch_requests':500,'batch_decoded_bytes':268435456,'tick_permission':'AWAITING_USER_APPROVAL'}
    if (ROOT/'config.json').exists():assert read(ROOT/'config.json')==cfg
    else:write_json(ROOT/'config.json',cfg)
    write_json(ROOT/'eligible-proxy-universe.json',eligible)
    for row in eligible:
        ticker=row['ticker']
        if ticker in seeds:continue
        p=aggregates.ROOT/'aggregates'/f'{ticker}.json'
        if not p.exists():continue
        source=read(p);bars=ah_bars(source['bars'],cycle);threshold=Decimal(row['previous_rth_close'])*Decimal('1.10')
        positive=any(Decimal(r['h'])>=threshold for r in bars)
        # All-raw cached highs are a conservative negative screen. Positives get
        # official provider aggregates before becoming additional candidates.
        if source['source_kind']=='CACHED_REST_TRADES_RAW_MINUTE_HIGH'and positive:
            write_json(ROOT/'raw-ah-rescue'/f'{ticker}.json',{'ticker':ticker,'bars':bars,'source':{'path':str(p.resolve()),'sha256':file_hash(p)},'note':'Raw-price high is not necessarily eligible; retain as a cache-backed candidate for later SIP checks'})
            continue
        if (ROOT/'ah'/f'{ticker}.json').exists():continue
        write_json(ROOT/'ah'/f'{ticker}.json',{'ticker':ticker,'bars':bars,'complete':True,'source_kind':source['source_kind'],
            'source':{'path':str(p.resolve()),'sha256':file_hash(p)},'selection':'AH_ONLY_OUTSIDE_SEED'})
    return state()


def state():
    cfg=read(ROOT/'config.json');seeds=set(SEED.read_text().split());pool=read(ROOT/'eligible-proxy-universe.json')
    targets=[r['ticker']for r in pool if r['ticker']not in seeds]
    pending=[t for t in targets if not (ROOT/'ah'/f'{t}.json').exists()]
    return {'root':str(ROOT.resolve()),'config':cfg,'tickers':pending,'population_total':len(targets),'completed_before_batch':len(targets)-len(pending)}


def import_ah(path):
    cap=read(path);cfg=read(ROOT/'config.json');ticker=cap['ticker']
    assert cap['path']==f"/v2/aggs/ticker/{ticker}/range/1/minute/{cfg['ah_from_ms']}/{cfg['ah_to_ms']}"
    assert cap['params']=={'adjusted':False,'sort':'asc','limit':50000}
    assert not cap.get('next_params')
    text=cap['csv'].strip()
    if text.startswith('Warning [EMPTY]: API returned 0 records.')or text in {'No results found.','No results returned.','No data found.','No results found','No results returned','No data found'}:
        bars=[];empty='EXPLICIT_EMPTY_CONNECTOR_RESULT'
    else:bars=aggregates.parse_bars(cap['csv']);empty=None
    assert len(ah_bars(bars,cfg['cycle']))==len(bars)
    write_json(ROOT/'ah'/f'{ticker}.json',{'ticker':ticker,'complete':True,'bars':bars,'source_kind':'PROVIDER_REST_AH_MINUTE_HIGH',
       'empty_status':empty,'source':{'path':str(Path(path).resolve()),'sha256':file_hash(path)}})
    return {'ticker':ticker,'bars':len(bars)}


def build():
    cfg=read(ROOT/'config.json');assert file_hash(SEED)==cfg['seed_sha256']
    assert file_hash(cfg['universe_source']['path'])==cfg['universe_source']['sha256']
    seeds=SEED.read_text().split();audit=read(ROOT/'seed-audit.json');pool=read(ROOT/'eligible-proxy-universe.json');by={r['ticker']:r for r in pool}
    daily_cap=read(ROOT/'daily13-capture.json');daily={r['T']:r for r in csv.DictReader(io.StringIO(daily_cap['csv']))}
    initial=[r['ticker']for r in audit if r['status']=='CANDIDATE_PASS'];extras=[];coverage=[]
    for row in pool:
        ticker=row['ticker']
        if ticker in seeds:continue
        p=ROOT/'ah'/f'{ticker}.json'
        if not p.exists():coverage.append({'ticker':ticker,'status':'AH_AGGREGATE_UNRESOLVED'});continue
        cap=read(p);bars=ah_bars(cap['bars'],cfg['cycle']);th=Decimal(row['previous_rth_close'])*Decimal('1.10')
        hits=[r for r in bars if Decimal(r['h'])>=th]
        official_hits=list(hits)
        rescue_path=ROOT/'raw-ah-rescue'/f'{ticker}.json'
        rescue=read(rescue_path)if rescue_path.exists()else None
        raw_hits=[r for r in rescue['bars']if Decimal(r['h'])>=th]if rescue else []
        hits+=raw_hits
        coverage.append({'ticker':ticker,'status':'AH_PRICE_CANDIDATE'if hits else 'AH_SCREEN_NEGATIVE','source_kind':cap['source_kind'],'bars':len(bars),'source':cap['source']})
        if hits:
            evidence_kind='PROVIDER_AH_AGGREGATE'if official_hits else 'RAW_CACHE_MINUTE_HIGH_RESCUE_PENDING_CONDITIONS_CHECK'
            high=number(daily[ticker]['h'])if ticker in daily else None
            reason='DAILY13_HIGH_BELOW_THRESHOLD'if high is not None and high<th else 'DAILY13_HIGH_ALSO_CROSSED_BUT_ABSENT_FROM_USER_SEED'if high is not None else 'DAILY13_RECORD_NOT_RETURNED'
            extras.append({'ticker':ticker,'security_id':row['security_id'],'previous_rth_close':row['previous_rth_close'],'threshold':str(th),
              'ah_high':str(max(Decimal(r['h'])for r in (official_hits or raw_hits))),'ah_crossing_minutes_utc_ms':(official_hits or raw_hits),
              'ah_crossing_minutes_et':[pd.Timestamp(r['t'],unit='ms',tz='UTC').tz_convert('America/New_York').isoformat()for r in (official_hits or raw_hits)],
              'price_evidence_kind':evidence_kind,'provider_ah_high':str(max(Decimal(r['h'])for r in official_hits))if official_hits else None,
              'raw_cache_rescue_source':({'path':str(rescue_path.resolve()),'sha256':file_hash(rescue_path)}if rescue else None),
              'raw_cache_ah_high':str(max(Decimal(r['h'])for r in raw_hits))if raw_hits else None,'daily13_high':str(high)if high is not None else None,'reason_not_in_270':reason,'aggregate_source':cap['source']})
    final=[];seen=set()
    for ticker in initial+[r['ticker']for r in extras]:
        row=by[ticker];sid=row['security_id']
        if sid in seen:continue
        seen.add(sid);_,sources,complete=aggregates.validated_cached(ticker,cfg['cycle'])
        final.append({'ticker':ticker,'security_id':sid,'origin':'SEED_270_PASS'if ticker in initial else 'ADDITIONAL_AH',
            'previous_rth_close':row['previous_rth_close'],'current_float_proxy':row['float_proxy']['value'],
            'price_evidence_kind':('DAILY13_HIGH_SEED'if ticker in initial else next(e['price_evidence_kind']for e in extras if e['ticker']==ticker)),
            'already_cached_complete':complete,'cached_pages':len(sources),'additional_rest_calls_minimum':0 if complete else 1,
            'next_cursor_available':bool(sources)and not complete,'status':'AWAITING_USER_APPROVAL'})
    counts=Counter(r['status']for r in audit);unknown=[r for r in coverage if r['status']=='AH_AGGREGATE_UNRESOLVED']
    summary={'run_id':RUN,'status':'AWAITING_USER_APPROVAL'if not unknown else 'AH_DISCOVERY_INCOMPLETE',
      'Daily Aggregate Candidates':270,'Historical Universe PASS':counts['CANDIDATE_PASS'],'Historical Universe EXCLUDED':counts['CANDIDATE_EXCLUDED'],
      'Historical Universe UNRESOLVED':counts['CANDIDATE_UNRESOLVED'],'Additional AH Candidates':len(extras),'Provider AH Aggregate Candidates':sum(e['price_evidence_kind']=='PROVIDER_AH_AGGREGATE'for e in extras),
      'Raw Cache AH Diagnostics':sum(e['price_evidence_kind']!='PROVIDER_AH_AGGREGATE'for e in extras),
      'AH discovery eligible outside seed':len(coverage),'AH discovery complete':len(coverage)-len(unknown),'AH discovery unresolved':len(unknown),
      'Final Tick Acquisition Manifest':len(final),'Already Cached':sum(r['already_cached_complete']for r in final),
      'Additional REST Calls Required minimum':sum(r['additional_rest_calls_minimum']for r in final),
      'Additional REST Calls Required exact':'UNKNOWN_UNTIL_PAGINATION_EXHAUSTED','tickers':[r['ticker']for r in final],
      'tick_acquisition_authorized':False,'duplicates_removed_by_security_identity':len(initial)+len(extras)-len(final)}
    assert sum(counts.values())==270
    write_json(ROOT/'final-acquisition-manifest.json',final);write_json(REPORT/'summary.json',summary)
    old.table(REPORT/'final-acquisition-manifest.csv',final);old.table(REPORT/'additional-ah-candidates.csv',extras)
    old.table(REPORT/'ah-discovery-coverage.csv',coverage)
    write_json(REPORT/'final-acquisition-manifest.json',final)
    return summary


def number(v):
    try:return Decimal(v)
    except Exception:return None


def authorize(approval_note):
    if not approval_note or not approval_note.strip():raise ValueError('EXPLICIT_USER_APPROVAL_NOTE_REQUIRED')
    cfg=read(ROOT/'config.json')
    assert file_hash(cfg['universe_source']['path'])==cfg['universe_source']['sha256']
    assert file_hash(old.ROOT/'queue.json')==read(old.ROOT/'frozen.json')['queue_sha256']
    manifest=read(ROOT/'final-acquisition-manifest.json');summary=read(REPORT/'summary.json')
    assert not summary['AH discovery unresolved']
    approval={'run_id':RUN,'status':'USER_APPROVED','approval_note':approval_note,
        'approved_at':datetime.now(timezone.utc).isoformat(),'manifest_sha256':file_hash(ROOT/'final-acquisition-manifest.json')}
    by={r['ticker']:r for r in old.read(old.ROOT/'queue.json')}
    selected=[{**by[r['ticker']],'sample':'APPROVED_270_PLUS_AH','manifest_origin':r['origin']}for r in manifest]
    assert len({r['security_id']for r in selected})==len(selected)
    assert all(r['float_proxy']['status']=='ELIGIBLE'for r in selected)
    write_json(ROOT/'candidates.json',selected);write_json(ROOT/'approval.json',approval)
    write_json(old.ROOT/'required-approved-manifest.json',approval)
    write_json(old.ROOT/'candidate-tick-authorization.json',{'replacement_run':RUN,'tickers':[r['ticker']for r in selected],
        'candidate_sha256':file_hash(ROOT/'candidates.json'),'approved_manifest_sha256':approval['manifest_sha256'],'pre_tick_counts_reported':True})
    return {'authorized_tickers':len(selected),'run_id':RUN}


def tick_pages_for_replay(ticker):
    return sorted((old.ROOT/'raw'/ticker).glob('page-[0-9][0-9][0-9][0-9][0-9].json'))

def _replay_approved_job(job):
    row,cfg,conditions=job
    return old.replay_symbol(row,cfg,conditions,run_id=RUN)


def verify_approved():
    approval=read(ROOT/'approval.json')
    assert approval['status']=='USER_APPROVED' and approval['manifest_sha256']==file_hash(ROOT/'final-acquisition-manifest.json')
    frozen=old.read(old.ROOT/'frozen.json')
    for path,h in frozen['protected_hashes'].items():assert file_hash(path)==h
    assert file_hash(old.ROOT/'config.json')==frozen['config_sha256']
    assert file_hash(old.ROOT/'conditions.json')==frozen['conditions_sha256']
    selected=read(ROOT/'candidates.json');cfg=old.read(old.ROOT/'config.json');conditions={r['id']:r for r in old.read(old.ROOT/'conditions.json')}
    results=[]
    from concurrent.futures import ProcessPoolExecutor
    # Two independent per-security workers bound memory and preserve exact replay.
    by_ticker={r['ticker']:r for r in selected}
    jobs=sorted(selected,key=lambda r:sum(p.stat().st_size for p in tick_pages_for_replay(r['ticker'])),reverse=True)
    with ProcessPoolExecutor(max_workers=2) as pool:
        computed=list(pool.map(_replay_approved_job,[(r,cfg,conditions)for r in jobs]))
    for result in computed:
        row=by_ticker[result['ticker']]
        if result['event']:
            e=result['event'];f=row['float_proxy']
            e.update(current_float_proxy_shares=f['value'],float_is_verified_pit=False,
                float_proxy_effective_date=f.get('effective_date'),float_proxy_retrieved_at=f.get('retrieved_at'),
                gain_from_p0_pct=str((Decimal(e['touch_price'])/Decimal(e['previous_rth_close'])-1)*100),
                manifest_origin=row.get('manifest_origin'))
        write_json(ROOT/'replay'/f"{row['ticker']}.json",result);results.append(result)
    events=sorted([r['event']for r in results if r['event']],key=lambda e:(e['event_timestamp'],e['security_id']))
    verified=[e for e in events if e['observed_window_first_verified']]
    unverified=[e for e in events if not e['observed_window_first_verified']]
    rejected=[r for r in results if r['disposition']=='ZERO_EVENT_OBSERVED']
    unknown=[r for r in results if r['disposition']=='UNKNOWN_INCOMPLETE']
    assert len(results)==len(events)+len(rejected)+len(unknown)
    columns=['ticker','security_id','session','current_float_proxy_shares','float_is_verified_pit','float_proxy_effective_date','float_proxy_retrieved_at','manifest_origin','gain_from_p0_pct','previous_rth_close','threshold_price','first_touch_price','first_touch_timestamp_et',
        'first_touch_timestamp_utc_ns','first_touch_status','observed_window_first_verified','trade_size','trade_conditions','trade_exchange',
        'restoration_status','restoration_source','correction_status','quality_flags','source_reference','run_id','census_event_id']
    for name,rows in [('all-first-touches',events),('verified-observed',verified),('unverified',unverified)]:old.table(REPORT/f'{name}.csv',rows,columns)
    for name,rows in [('rejected',rejected),('unknown-incomplete',unknown)]:
        old.table(REPORT/f'{name}.csv',[{k:v for k,v in r.items()if k not in {'event','pages','raw_first_crossing'}}for r in rows],
            ['ticker','security_id','disposition','complete','reason','raw_rows','reject_counts'])
    summary={'run_id':RUN,'approved_candidates':len(results),'first_touch_events':len(events),'verified_observed':len(verified),
       'unverified_prior_or_pagination':len(unverified),'rejected_no_eligible_touch':len(rejected),'unknown':len(unknown),
       'complete_trade_windows':sum(r['complete']for r in results),'candidate_coverage_percent':100*sum(r['complete']for r in results)/len(results)if results else 100,
       'verified_sessions':dict(Counter(e['session']for e in verified)),
       'frozen_verified_AH':sum(e['first_touch_status']=='VERIFIED_FIRST_TOUCH'for e in events),
       'raw_json_hash_dependent_trigger_ties':sum(e['source_hash_tie_ambiguity']for e in events),
       'later_invalidated_events':sum(e['later_invalidated']for e in events),'sessions':dict(Counter(e['session']for e in events)),
       'status':'COMPLETE_APPROVED_MANIFEST_REPLAY'if not unknown and all(r['complete']for r in results)else 'INCOMPLETE / BLOCKED'}
    write_json(REPORT/'replay-summary.json',summary)
    return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','state','import','build','authorize','verify']);ap.add_argument('path',nargs='?');args=ap.parse_args()
    result=prepare()if args.action=='prepare'else state()if args.action=='state'else import_ah(args.path)if args.action=='import'else build()if args.action=='build'else authorize(args.path)if args.action=='authorize'else verify_approved()
    print(json.dumps(result))
