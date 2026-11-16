"""Isolated, resumable REST/MCP full-population first-touch census.

No ticks from prior cohorts, no S3, no outcomes. MCP captures are CSV exports,
not original HTTP JSON; their hashes certify the captured representation only.
"""
import argparse
import base64
import csv
import io
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, parse_qsl

import pandas as pd
import pyarrow.parquet as pq

from .calendar import cycles
from .eligibility import identity
from .m2_pilot import control_eligible
from .storage import digest, file_hash, write_json
from .systematic_pilot import float_evidence
from .tick_replay import first_touch, session_label, bounds, chronological, restore_observed_records, eligible_trade, number

RUN = 'census-20261113-rest-20261116-v1'
ROOT = Path('data/runs') / RUN
REPORT = Path('reports') / RUN
SOURCE = Path('data/runs/m1-universe-120-20261115-v2/universe/cycle=2026-11-13/snapshot.parquet')
GATES = ['exchange', 'price', 'type', 'identity', 'currency', 'action']


def read(p):
    return json.loads(Path(p).read_text())


def table(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', lineterminator='\n'); w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, sort_keys=True, default=str) if isinstance(v, (dict,list)) else v for k,v in r.items()})


def source_audit(rows):
    """Verify both historical cursor chains independently, not just row count."""
    sources = json.loads(rows[0]['provenance_json'])['sources']
    chains, prices = [], None
    refs = {}
    for s in sources:
        assert file_hash(s['path']) == s['sha256'], s['path']
        raw = pq.read_table(s['path']).to_pylist()[0]
        req, body = json.loads(raw['request']), json.loads(raw['response'])
        if 'grouped' in req['url']:
            assert req['params']['adjusted'] == 'false'
            assert req['url'].endswith('/2026-11-12')
            prices = body['results']; continue
        if 'date' in req['params']:
            chains.append({'date': req['params']['date'], 'pages': [], 'rows': []})
        chain = chains[-1]
        if chain['pages']:
            expected = dict(parse_qsl(urlparse(chain['pages'][-1]['next']).query))
            assert req['params'] == expected, 'broken reference cursor chain'
        chain['pages'].append({'source':s, 'count':len(body['results']), 'next':body.get('next_url')})
        chain['rows'].extend(body['results'])
    assert len(chains) == 2 and [c['date'] for c in chains] == ['2026-11-12','2026-11-13']
    for c in chains:
        assert not c['pages'][-1]['next'], 'incomplete historical references'
        assert len({r['ticker'] for r in c['rows']}) == len(c['rows'])
        refs[c['date']] = c['rows']
    assert prices is not None and len({r['T'] for r in prices})==len(prices),'AMBIGUOUS_GROUPED_CLOSE_ROWS'
    a,b=({r['ticker']:r for r in refs[d]} for d in ['2026-11-12','2026-11-13'])
    assert set(a)=={r['ticker'] for r in rows}
    # Study-only names require a separate unresolved entry, never silently drop.
    return {'sources':sources, 'chains':[{'date':c['date'],'pages':len(c['pages']),'rows':len(c['rows'])} for c in chains],
            'study_only': sorted(set(b)-set(a)), 'anchor_only': sorted(set(a)-set(b)),
            'study_reference':b, 'prices':{r['T']:r for r in prices}}


def prepare():
    if (ROOT/'frozen.json').exists():
        frozen=read(ROOT/'frozen.json')
        for p,h in frozen['protected_hashes'].items():
            assert file_hash(p)==h
        return read(ROOT/'queue.json')
    rows=pq.read_table(SOURCE).to_pylist()
    assert file_hash(SOURCE)==read(SOURCE.with_name('checkpoint.json'))['snapshot_hash']
    audit=source_audit(rows)
    assert not audit['study_only'], 'study-only listings require historical attribute repair before freeze'
    ctx_path=Path('data/runs/m4-temporal-10cycles-20261115-v1/context.json'); ctx=read(ctx_path)
    current,floats=defaultdict(list),defaultdict(list)
    for s in ctx['reference_sources']:
        assert file_hash(s['path'])==s['sha256']
        for r in read(s['path']).get('results',[]):
            r={**r,'_source':s}
            if '/reference/tickers' in s['request']['url'] and identity(r):current[identity(r)].append(r)
            if '/float' in s['request']['url'] and r.get('ticker'):floats[r['ticker']].append(r)
    manifest=[];queue=[]; eligible_ids=[]
    for r in rows:
        p=json.loads(r['provenance_json']); study=audit['study_reference'].get(r['ticker'])
        eligible=control_eligible(r)
        if eligible:
            # Independent historical attributes and price check, no current listing gate.
            assert study and study.get('primary_exchange') in {'XNAS','XASE','XNYS'} and study.get('type')=='CS'
            assert identity(study)==r['security_id'] and study.get('currency_name','').lower()=='usd'
            assert Decimal(str(audit['prices'][r['ticker']]['c']))==r['previous_rth_close']
            assert 0<r['previous_rth_close']<=3
            eligible_ids.append(r['security_id'])
        disposition='ELIGIBLE' if eligible else 'EXCLUDED' if any(r[g+'_status']=='INELIGIBLE' for g in GATES) else 'UNKNOWN_HISTORICAL_ATTRIBUTES'
        ev=float_evidence(r,current,floats)
        item={'ticker':r['ticker'],'security_id':r['security_id'],'historical_exchange':r['canonical_exchange'],
              'security_type':r['security_type'],'previous_rth_close':str(r['previous_rth_close']) if r['previous_rth_close'] is not None else None,
              'float_proxy_stratum':'PROXY_FLOAT_IN_RANGE' if ev['status']=='ELIGIBLE' else 'OTHER_EXCHANGE_PRICE_ELIGIBLE',
              'float_proxy':ev,'disposition':disposition,'gates':{g:{'status':r[g+'_status'],'reason':r[g+'_reason']} for g in GATES},
              'change_status':r['change_status'],'reference_provenance':p,'m1_record_id':r['record_id']}
        manifest.append(item)
        if eligible:queue.append({**item,'sample':'FULL_CENSUS','cohorts':['EXCHANGE_PRICE_ONLY']+(['MASSIVE_CURRENT_FLOAT_PROXY'] if ev['status']=='ELIGIBLE' else [])})
    assert len(set(eligible_ids))==len(eligible_ids) and all(eligible_ids)
    cycle=cycles('2026-11-13',1)[0];cycle['split_group']='EXPLORATORY_SINGLE_DATE'
    cfg={**read('configs/m2-pilot-v1.json'),'run_id':RUN,'cycle':cycle,'transport':'MASSIVE_REST_VIA_MCP',
         'trade_page_limit':50000,'batch_max_calls':4096,'batch_max_seconds':1800,'batch_max_decoded_bytes':2**31,
         'max_page_bytes':32*2**20,'max_local_storage_bytes':64*2**30,'max_workers':4,'sampling':'CENSUS_NO_SAMPLE',
         'confirmation_models':False,'holdout_access':False}
    protected={str(p):file_hash(p) for p in Path('configs').glob('*.json')}
    protected.update({str(SOURCE):file_hash(SOURCE),str(ctx_path):file_hash(ctx_path),
                      'market_lab/tick_replay.py':file_hash('market_lab/tick_replay.py')})
    # All versioned old artifacts pinned, plus immutable run manifests; no old tick outcomes read.
    import subprocess
    for name in subprocess.check_output(['git','ls-files','reports','research','docs','configs'],text=True).splitlines():
        p=Path(name)
        if p.is_file():protected[name]=file_hash(p)
    write_json(ROOT/'config.json',cfg);write_json(ROOT/'queue.json',queue);write_json(ROOT/'universe.json',manifest)
    write_json(ROOT/'conditions.json',ctx['conditions'])
    write_json(ROOT/'reference-audit.json',{k:v for k,v in audit.items() if k not in {'prices','study_reference'}})
    write_json(ROOT/'frozen.json',{'run_id':RUN,'protected_hashes':protected,'universe_sha256':file_hash(ROOT/'universe.json'),
                                 'queue_sha256':file_hash(ROOT/'queue.json'),'conditions_sha256':file_hash(ROOT/'conditions.json'),
                                 'config_sha256':file_hash(ROOT/'config.json'),'frozen_before_census_acquisition':True,
                                 'pre_freeze_transport_tests':['ASTC 3/50000 limit','ABAT 50000 limit; no census selection by outcomes']})
    REPORT.mkdir(parents=True,exist_ok=True)
    export_universe(manifest)
    write_json(Path('configs/census-20261113-rest-v1.json'),cfg)
    return queue


def export_universe(manifest):
    compact=[]
    for row in manifest:
        p=row['reference_provenance'];f=row['float_proxy']
        compact.append({k:v for k,v in row.items() if k not in {'reference_provenance','float_proxy'}} | {
            'float_proxy_status':f['status'],'float_proxy_value':f['value'],'float_proxy_reason':f['reason'],
            'float_effective_date':f.get('effective_date'),'float_source_sha256':f.get('source',{}).get('sha256'),
            'reference_source':p['source_reference'],'price_source':p['source_price']})
    table(REPORT/'universe.csv',compact)
    table(REPORT/'historical-unknown.csv',[r for r in compact if r['disposition']=='UNKNOWN_HISTORICAL_ATTRIBUTES'])


def parse_csv(text, expected=None):
    if '[truncated' in text.lower():raise ValueError('MCP_EXPORT_TRUNCATED')
    out=[]
    for r in csv.DictReader(io.StringIO(text)):
        if not r.get('sip_timestamp'):raise ValueError('MISSING_SIP_TIMESTAMP')
        if 'decimal_size' in r and not r['decimal_size']:
            raise ValueError('MCP_DECIMAL_SIZE_NULL_FIELD_PRESENCE_AMBIGUOUS')
        d={}
        for k,v in r.items():
            if v in ('',None):continue
            if k in {'conditions','indicators'}:d[k]=json.loads(v)
            elif k in {'sip_timestamp','participant_timestamp','sequence_number','exchange','correction','trf_id','trf_timestamp','tape'}:
                # Never round nanoseconds via binary float.
                value=Decimal(v)
                if value!=value.to_integral_value():raise ValueError('NONINTEGRAL_TIMESTAMP_OR_CODE')
                d[k]=int(value)
            else:d[k]=v
        out.append(d)
    if expected is not None and len(out)!=expected:raise ValueError(f'MCP_ROW_COUNT_MISMATCH {len(out)} != {expected}')
    return out


def cursor_tail_audit(params, rows):
    """Optional independent check of the currently observed provider cursor format.

    Pagination itself follows opaque cursors verbatim. No synthesized cursors.
    """
    if not params:return 'TERMINAL'
    if not rows:raise ValueError('NONTERMINAL_EMPTY_PAGE')
    cursor=params.get('cursor','')
    try:
        decoded=base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)).decode()
        fields=dict(parse_qsl(decoded))
    except (ValueError,UnicodeError):return 'OPAQUE_CURSOR_NOT_DECODED'
    if fields.get('sort')=='timestamp' and fields.get('order')=='asc' and 'timestamp.gte' in fields and fields.get('ap','').isdigit():
        assert int(fields['ap'])==rows[-1]['sequence_number'],'CURSOR_SEQUENCE_VS_EXPORT_TAIL_MISMATCH'
        assert pd.Timestamp(fields['timestamp.gte']).value==rows[-1]['sip_timestamp'],'CURSOR_TIMESTAMP_VS_EXPORT_TAIL_MISMATCH'
        return 'TAIL_SEQUENCE_AND_NANOSECOND_MATCH'
    return 'OPAQUE_CURSOR_FORMAT'


def normalized(raw,source,security,cycle):
    t=raw.get('sip_timestamp'); valid=isinstance(t,int) and bounds(cycle)[0]<t<=bounds(cycle)[-1]
    return {**raw,'record_id':digest(raw),'security_id':security,'kind':'trades','trade_id':str(raw.get('id','')),
            'price':raw.get('price'),'size':raw.get('decimal_size',raw.get('size')),'exchange':raw.get('exchange'),
            'conditions_json':json.dumps(raw.get('conditions',[])),'source_json':json.dumps(source,sort_keys=True),
            'session':session_label(cycle,t) if valid else 'INVALID','normalization_status':'OK' if valid else 'INVALID_TIMESTAMP'}


def continuation_check(cap, expected, previous_tail, cycle):
    actual=cap['params']
    if actual==expected:return 'EXACT_CURSOR'
    if cap.get('coverage_join')=='TIMESTAMP_OVERLAP_TAIL':
        assert cap['prior_next_params']==expected and previous_tail is not None
        assert bounds(cycle)[0]<previous_tail<=bounds(cycle)[-1]
        assert actual=={'timestamp.gte':str(previous_tail),'timestamp.lte':str(bounds(cycle)[-1]),
                       'sort':'timestamp','order':'asc','limit':actual['limit']}
        assert actual['limit'] in {10000,15000,50000}
        return 'PREFIX_PLUS_INCLUSIVE_TIMESTAMP_TAIL_UNION'
    assert set(actual)=={'cursor','limit'} and set(expected)=={'cursor'}
    assert actual['cursor']==expected['cursor'] and actual['limit']in {5000,10000,15000,50000}
    return 'UNCHANGED_CURSOR_WITH_PAGE_LIMIT_ARGUMENT'


def cursor_page_limit(params):
    try:
        c=params['cursor'];q=dict(parse_qsl(base64.urlsafe_b64decode(c+'='*(-len(c)%4)).decode()))
        return int(q['limit'])
    except (KeyError,ValueError,UnicodeError):return None


def capture_tail(cap):
    if not cap['expected_rows']:return None
    lines=cap['csv'].strip().splitlines()
    return parse_csv(lines[0]+'\n'+lines[-1]+'\n',1)[0]['sip_timestamp']


def replay_symbol(opportunity,cfg,conditions,run_id=None):
    effective_run=run_id or RUN
    folder=ROOT/'raw'/opportunity['ticker']; pages=sorted(folder.glob('page-[0-9][0-9][0-9][0-9][0-9].json'))
    rows=[];seen=set();complete=False;expected_request=None;duplicates=0;total=0;source_audit=[];error=None
    try:
        request_keys=set();previous_tail=None
        for i,p in enumerate(pages):
            seal(p)
            cap=read(p)
            request_key=digest(cap['params'])
            assert request_key not in request_keys, 'CURSOR_LOOP'
            request_keys.add(request_key)
            assert cap['page_index']==i
            assert cap['path']==f"/v3/trades/{opportunity['ticker']}"
            if i==0:
                assert cap['params'].get('limit') in {5000,10000,15000,cfg['trade_page_limit']}
                assert cap['params']=={'timestamp.gt':str(bounds(cfg['cycle'])[0]),'timestamp.lte':str(bounds(cfg['cycle'])[-1]),'sort':'timestamp','order':'asc','limit':cap['params']['limit']}
            else:continuation_check(cap,expected_request,previous_tail,cfg['cycle'])
            assert not complete,'pages after terminal page'
            values=parse_csv(cap['csv'],cap['expected_rows']);total+=len(values)
            if values:
                assert [r['sip_timestamp'] for r in values]==sorted(r['sip_timestamp'] for r in values)
                if previous_tail is not None:assert values[0]['sip_timestamp']>=previous_tail,'CROSS_PAGE_TIMESTAMP_REGRESSION'
                previous_tail=values[-1]['sip_timestamp']
            expected_request=cap.get('next_params'); complete=expected_request is None
            tail_check=cursor_tail_audit(expected_request,values)
            source={'path':str(p.resolve()),'sha256':file_hash(p),'transport':'MASSIVE_REST_VIA_MCP_CSV','http_headers':'NOT_EXPOSED_BY_CONNECTOR'}
            source_audit.append({**source,'rows':len(values),'page_index':i,'next_params':expected_request,'cursor_tail_check':tail_check,'coverage_join':cap.get('coverage_join'),'prior_next_params':cap.get('prior_next_params')})
            for j,raw in enumerate(values):
                row=normalized(raw,{**source,'row_index':j},opportunity['security_id'],cfg['cycle'])
                if row['record_id'] in seen:duplicates+=1;continue
                seen.add(row['record_id']);rows.append(row)
        if not pages:error='NOT_ACQUIRED'
        elif not complete:error='INCOMPLETE_PAGINATION'
    except Exception as exc:
        complete=False;error=f'{type(exc).__name__}: {exc}'
    result=first_touch(rows,cfg['cycle'],opportunity,cfg,conditions,complete,effective_run)
    # Independent full scan of restored raw captures verifies earliest eligible record.
    accepted=[r for r in restore_observed_records(chronological(rows)) if eligible_trade(r,cfg['cycle'],conditions,cfg)[0] and number(r['price'])>=Decimal(opportunity['previous_rth_close'])*Decimal(cfg['trigger_multiplier'])]
    assert len(result['eligible'])+sum(result['reject_counts'].values())==len(rows)
    event=result['event']
    assert (event['record_id'] if event else None)==(accepted[0]['record_id'] if accepted else None)
    if event:
        t=event['event_timestamp'];ties=[r for r in accepted if r['sip_timestamp']==t]
        key=lambda r:(r['sip_timestamp'],r.get('sequence_number'),r.get('exchange'),r.get('trade_id'))
        raw_hash_ties=sum(key(r)==key(accepted[0]) for r in rows)
        event['source_hash_tie_ambiguity']=raw_hash_ties>1
        event.update(census_event_id=digest([effective_run,event['event_id']]),float_proxy_stratum=opportunity['float_proxy_stratum'],
                     first_touch_timestamp_utc_ns=t,first_touch_timestamp_et=pd.Timestamp(t,tz='UTC').tz_convert('America/New_York').isoformat(),
                     first_touch_timestamp_utc=pd.Timestamp(t,tz='UTC').isoformat(),first_touch_price=event['touch_price'],
                     cycle_date=cfg['cycle']['cycle_id'],trade_conditions=event['conditions_json'],source_reference=event['source_json'],
                     correction_status={'original_code':event['correction'],'restoration':event['restoration_status'],'later_invalidated':event['later_invalidated']},
                     same_sip_eligible_crossings=len(ties))
        event['quality_flags']+=['MCP_CSV_SOURCE_REPRESENTATION','RAW_JSON_RECORD_HASH_NOT_AVAILABLE','CORRECTIONS_AFTER_CYCLE_NOT_CERTIFIED']
        if len(ties)>1:event['quality_flags'].append('SAME_SIP_MULTIPLE_CROSSINGS_DETERMINISTIC_TIEBREAK')
        if raw_hash_ties>1:event['quality_flags'].append('ORIGINAL_JSON_HASH_NEEDED_TO_RESOLVE_TIE')
    disposition='FIRST_TOUCH_EVENT' if event else result['zero_event_status']
    return {'ticker':opportunity['ticker'],'security_id':opportunity['security_id'],'float_proxy_stratum':opportunity['float_proxy_stratum'],
            'disposition':disposition,'complete':complete,'reason':error or ('UNKNOWN_PRIOR_EVIDENCE' if disposition=='UNKNOWN_INCOMPLETE' else None),
            'raw_rows':total,'normalized_rows':len(rows),'exact_duplicates':duplicates,'pages':source_audit,
            'reject_counts':result['reject_counts'],'event':event,'raw_first_crossing':result['raw_first_crossing'],
            'session_rows':dict(Counter(r['session'] for r in rows)),
            'eligible_session_rows':dict(Counter(r['session'] for r in result['eligible'])),
            'independent_earliest_scan_passed':True}


def finish():
    prior_audit=REPORT/'source-audit.json'
    if prior_audit.exists():
        for page in read(prior_audit)['trade_pages']:
            assert file_hash(page['path'])==page['sha256'], 'captured source changed since replay'
    frozen=read(ROOT/'frozen.json')
    for p,h in frozen['protected_hashes'].items():assert file_hash(p)==h,p
    for name in ['universe','queue','conditions','config']:assert file_hash(ROOT/f'{name}.json')==frozen[f'{name}_sha256']
    from .corporate_actions import load_actions, action_index, action_gate
    cfg=read(ROOT/'config.json')
    verified_reference=source_audit(pq.read_table(SOURCE).to_pylist())
    assert verified_reference['chains']==read(ROOT/'reference-audit.json')['chains']
    context=read('data/runs/m4-temporal-10cycles-20261115-v1/context.json')
    for source in context['reference_sources']:assert file_hash(source['path'])==source['sha256']
    actions=load_actions('data/runs/m1-universe-120-20261115-v2/corporate_actions.json',[cfg['cycle']])
    action_map=action_index(actions)
    for op in read(ROOT/'queue.json'):
        assert action_gate(cfg['cycle'],op['ticker'],action_map,actions['complete'])[0]=='ELIGIBLE'
    write_json(REPORT/'action-audit.json',{'complete':actions['complete'],'sources':actions['sources'],'independently_checked_eligible':len(read(ROOT/'queue.json'))})
    conditions={r['id']:r for r in read(ROOT/'conditions.json')};queue=read(ROOT/'queue.json')
    results=[]
    for i,op in enumerate(queue):
        result=replay_symbol(op,cfg,conditions);write_json(ROOT/'replay'/f"{op['ticker']}.json",result);results.append(result)
        if i%100==0:print('replayed',i,flush=True)
    events=sorted([r['event'] for r in results if r['event']],key=lambda e:(e['event_timestamp'],e['security_id']))
    zero=[{k:v for k,v in r.items() if k not in {'event','pages','raw_first_crossing'}} for r in results if r['disposition']=='ZERO_EVENT_OBSERVED']
    unknown=[{k:v for k,v in r.items() if k not in {'event','pages','raw_first_crossing'}} for r in results if r['disposition']=='UNKNOWN_INCOMPLETE']
    assert len(queue)==len(events)+len(zero)+len(unknown)
    manifest=read(ROOT/'universe.json');historical_unknown=sum(r['disposition']=='UNKNOWN_HISTORICAL_ATTRIBUTES' for r in manifest)
    coverage=sum(r['complete'] for r in results)
    summary={'run_id':RUN,'status':'COMPLETE_KNOWN_ELIGIBLE_FRAME_WITH_UNRESOLVED_HISTORICAL_ATTRIBUTES' if coverage==len(queue) and not unknown else 'INCOMPLETE / BLOCKED',
             'complete_historical_census':coverage==len(queue) and not unknown and not historical_unknown,
             'census_api_pages_with_durable_response':sum(len(r['pages'])for r in results),
             'request_count_limitation':'Captured pages exclude interrupted/preflight requests. MCP does not expose HTTP request IDs, status or headers. See operational ledger for bounded attempt counts.',
             'historical_universe_rows':len(manifest),
             'exchange_price_common_stock_candidates':sum(all(r['gates'][g]['status']=='ELIGIBLE' for g in ['exchange','price','type','currency']) for r in manifest),
             'eligible_opportunities':len(queue),'historical_attributes_unknown':historical_unknown,
             'fully_acquired':coverage,'incomplete_acquisition':len(queue)-coverage,'acquisition_coverage_percent':100*coverage/len(queue),
             'events':len(events),'original_json_hash_dependent_trigger_ties':sum(e['source_hash_tie_ambiguity']for e in events),'verified':sum(e['first_touch_status']=='VERIFIED_FIRST_TOUCH' for e in events),
             'unverified':sum(e['first_touch_status']!='VERIFIED_FIRST_TOUCH' for e in events),
             'observed_window_verified':sum(e['observed_window_first_verified'] for e in events),'zero':len(zero),'unknown':len(unknown),
             'sessions':dict(Counter(e['session'] for e in events)),'strata':{},'pages':sum(len(r['pages'])for r in results),
             'trade_rows':sum(r['raw_rows']for r in results),'captured_bytes':sum(p.stat().st_size for p in (ROOT/'raw').glob('*/page-[0-9][0-9][0-9][0-9][0-9].json')),
             'reconciliation_passed':True,'protected_hashes_passed':True,'independent_earliest_scan_all_symbols':True,
             'raw_http_json_and_headers_available':False,'unobserved_interval':'20:00–04:00 ET','p0_method':'UNADJUSTED_PROVIDER_DAILY_CLOSE',
             'holdout_date_now_unblinded':True}
    if historical_unknown:summary['status']='INCOMPLETE / BLOCKED'
    for s in ['PROXY_FLOAT_IN_RANGE','OTHER_EXCHANGE_PRICE_ELIGIBLE']:
        rr=[r for r in results if r['float_proxy_stratum']==s]
        summary['strata'][s]={'eligible':len(rr),'events':sum(bool(r['event'])for r in rr),'zero':sum(r['disposition']=='ZERO_EVENT_OBSERVED'for r in rr),'unknown':sum(r['disposition']=='UNKNOWN_INCOMPLETE'for r in rr)}
    quality={'reject_counts':dict(sum((Counter(r['reject_counts'])for r in results),Counter())),
             'raw_sessions':dict(sum((Counter(r['session_rows'])for r in results),Counter())),
             'eligible_sessions':dict(sum((Counter(r['eligible_session_rows'])for r in results),Counter())),
             'later_invalidated_events':sum(e['later_invalidated']for e in events),
             'original_json_hash_dependent_trigger_ties':summary['original_json_hash_dependent_trigger_ties'],
             'same_sip_multiple_crossing_events':sum(e['same_sip_eligible_crossings']>1 for e in events),
             'cursor_tail_checks':dict(Counter(p['cursor_tail_check']for r in results for p in r['pages']))}
    write_json(REPORT/'quality.json',quality)
    table(REPORT/'events.csv',events, list(events[0]) if events else ['ticker','security_id','first_touch_timestamp_utc_ns','first_touch_timestamp_et','first_touch_status'])
    table(REPORT/'zero.csv',zero,['ticker','security_id','float_proxy_stratum','disposition','complete','reason','raw_rows','normalized_rows','exact_duplicates','reject_counts','session_rows','independent_earliest_scan_passed'])
    table(REPORT/'unknown.csv',unknown,['ticker','security_id','float_proxy_stratum','disposition','complete','reason','raw_rows'])
    table(REPORT/'raw-crossings.csv',[{'ticker':r['ticker'],'security_id':r['security_id'],'disposition':r['disposition'],
        'raw_first_crossing':r['raw_first_crossing']} for r in results if r['raw_first_crossing']])
    table(REPORT/'coverage.csv',[{k:v for k,v in r.items() if k not in {'event','pages','raw_first_crossing'}}for r in results])
    write_json(REPORT/'summary.json',summary)
    write_json(REPORT/'source-audit.json',{'reference':read(ROOT/'reference-audit.json'),'protected_hashes':frozen['protected_hashes'],
                                        'trade_pages':[p for r in results for p in r['pages']]})
    export_universe(manifest)
    write_json(REPORT/'artifact-hashes.json',{p.name:file_hash(p) for p in sorted(REPORT.iterdir()) if p.is_file() and p.name!='artifact-hashes.json'})
    print(json.dumps(summary,indent=2))


def seal(path):
    p=Path(path).resolve()
    assert p.is_relative_to((ROOT/'raw').resolve()) and p.name.startswith('page-') and p.suffix=='.json'
    sidecar=p.with_suffix('.sha256.json')
    sha=file_hash(p)
    if sidecar.exists():
        receipt=read(sidecar)
        assert receipt['path']==str(p) and receipt['sha256']==sha
        return receipt
    cap=read(p);parse_csv(cap['csv'],cap['expected_rows'])
    receipt={'path':str(p),'sha256':sha,'rows':cap['expected_rows']}
    write_json(sidecar,receipt)
    return receipt


def broker_state():
    # The original full-universe acquisition was stopped by the user.
    required_path=ROOT/'required-approved-manifest.json'
    if required_path.exists() and read(required_path)['status']!='USER_APPROVED':
        raise RuntimeError('USER_APPROVAL_REQUIRED_FOR_FINAL_270_PLUS_AH_MANIFEST')
    auth_path=ROOT/'candidate-tick-authorization.json'
    if not auth_path.exists():
        raise RuntimeError('USER_HALTED_UNIVERSE_TICK_ACQUISITION; candidate counts must be reported first')
    authorization=read(auth_path)
    if required_path.exists():
        required=read(required_path)
        assert authorization['replacement_run']==required['run_id']
        approved_path=Path('data/runs')/required['run_id']/'final-acquisition-manifest.json'
        assert file_hash(approved_path)==required['manifest_sha256']
    candidate_path=Path('data/runs')/authorization['replacement_run']/'candidates.json'
    assert file_hash(candidate_path)==authorization['candidate_sha256']
    assert set(authorization['tickers'])=={r['ticker']for r in read(candidate_path)}
    cfg=read(ROOT/'config.json');resume={};total=0;completed=set();groups=defaultdict(list)
    for p in sorted((ROOT/'raw').glob('*/page-[0-9][0-9][0-9][0-9][0-9].json')):
        seal(p);groups[p.parent.name].append(p);total+=p.stat().st_size
    for ticker,paths in groups.items():
        expected=None;seen=set();previous_tail=None
        for index,p in enumerate(paths):
            cap=read(p);assert cap['page_index']==index,'MISSING_CACHED_PAGE'
            assert cap['path']==f'/v3/trades/{ticker}'
            if index:
                assert expected is not None,'UNEXPECTED_PAGE_AFTER_TERMINAL'
                continuation_check(cap,expected,previous_tail,cfg['cycle'])
            else:
                assert cap['params'].get('limit') in {5000,10000,15000,50000}
                assert cap['params']=={'timestamp.gt':str(bounds(cfg['cycle'])[0]),'timestamp.lte':str(bounds(cfg['cycle'])[-1]),'sort':'timestamp','order':'asc','limit':cap['params']['limit']}
            key=digest(cap['params']);assert key not in seen,'CACHED_CURSOR_LOOP';seen.add(key)
            previous_tail=capture_tail(cap)
            expected=cap['next_params']
        if expected is None:completed.add(ticker)
        else:resume[ticker]={'page_index':len(paths),'next_params':expected,'last_sip_timestamp':str(previous_tail),'cursor_page_limit':cursor_page_limit(expected)}
    total=sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
    assert total+2**31<cfg['max_local_storage_bytes'],'STORAGE_BUDGET'
    transport=read('configs/census-20261113-transport-v3.json')
    if transport.get('adaptive_retry_on_transport_closed'):
        failed=set(transport['retry_small_page_tickers'])
        for p in (ROOT/'errors').glob('*.json'):
            error=read(p)
            if 'Transport closed' in error['error']:
                failed.add(error['request']['path'].rsplit('/',1)[-1])
        transport['retry_small_page_tickers']=sorted(failed)
    queue=read(ROOT/'queue.json')
    if authorization is not None:
        allowed=set(authorization['tickers']);queue=[r for r in queue if r['ticker']in allowed]
        completed.intersection_update(allowed)
    assert all(re.fullmatch(r'[A-Z0-9][A-Z0-9.-]*',r['ticker']) for r in queue),'UNSAFE_HISTORICAL_TICKER'
    return {'root':str(ROOT.resolve()),'tickers':[r['ticker']for r in queue if r['ticker'] not in completed],
            'population_total':len(queue),'completed_before_batch':len(completed),
            'transport':transport,'resume':resume,'start_ns':str(bounds(cfg['cycle'])[0]),'end_ns':str(bounds(cfg['cycle'])[-1])}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','finish','broker-state','seal']);parser.add_argument('path',nargs='?');args=parser.parse_args()
    if args.action=='prepare':
        q=prepare();print(json.dumps({'run_id':RUN,'eligible':len(q),'tickers':[r['ticker']for r in q]}))
    elif args.action=='broker-state':print(json.dumps(broker_state()))
    elif args.action=='seal':print(json.dumps(seal(args.path)))
    else:raise RuntimeError('SUPERSEDED_FULL_UNIVERSE_REPLAY; use approved manifest270 verification')
