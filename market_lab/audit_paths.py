"""Independent raw JSON price-path audit. No replay engine or network client calls."""
import json
from collections import Counter,defaultdict
from decimal import Decimal,InvalidOperation
from datetime import datetime
from itertools import groupby
from pathlib import Path
from urllib.parse import urlparse,parse_qsl
from .storage import digest,file_hash

S=10**9


def dec(x):
    try:
        d=Decimal(str(x));return d if d.is_finite() else None
    except (InvalidOperation,ValueError):return None


def cycle_bounds(c):
    return tuple(int(datetime.fromisoformat(c[k]).timestamp()*S) for k in ['anchor_at','afterhours_end','premarket_start','rth_open','end_at'])


def session(t,b):
    if not isinstance(t,int) or isinstance(t,bool) or not b[0]<t<=b[4]:return 'OUTSIDE_CYCLE'
    if t<b[1]:return 'AH'
    if b[2]<=t<b[3]:return 'PRE'
    if b[3]<=t:return 'RTH'
    return 'UNOBSERVED_OVERNIGHT'


def identity(r):return (str(r.get('id')) if r.get('id') is not None else None,r.get('sequence_number'),r.get('exchange'),r.get('trf_id'),r.get('participant_timestamp'))
def order(r):return (r.get('sip_timestamp') or 0,r.get('sequence_number') or 0,r.get('exchange') or 0,str(r.get('id') or ''),r['_id'])


def pages(coverage,budget,keep=True):
    rows=[];seen=set();last=None;previous=None;duplicates=0
    for i,page in enumerate(coverage['pages']):
        budget.check();p=Path(page['path']);budget.raw_bytes+=p.stat().st_size;budget.check()
        assert file_hash(p)==page['sha256'],'Raw hash mismatch'
        body=json.loads(p.read_text());stamps=[r['sip_timestamp'] for r in body.get('results',[])]
        assert stamps==sorted(stamps) and (last is None or not stamps or stamps[0]>=last)
        assert all(coverage['request']['start_ns']<t<=coverage['request']['end_ns'] for t in stamps)
        if stamps:last=stamps[-1]
        if i:
            parsed=urlparse(previous);params=dict(parse_qsl(parsed.query));params.pop('apiKey',None)
            actual=page['request'];actual_params={k:str(v) for k,v in actual['params'].items() if k!='apiKey'}
            assert actual['url']==parsed.scheme+'://'+parsed.netloc+parsed.path and actual_params==params,'Cursor mismatch'
        previous=body.get('next_url');budget.pages+=1
        if not keep:continue
        for j,raw in enumerate(body.get('results',[])):
            h=digest(raw)
            if h in seen:duplicates+=1;continue
            seen.add(h)
            rows.append({**raw,'_id':h,'_source':{'path':page['path'],'sha256':page['sha256'],'row':j}})
            if len(rows)>budget.config['max_window_rows']:raise RuntimeError('WINDOW_ROW_BUDGET')
    assert not coverage['complete'] or previous is None,'Missing terminal page'
    return sorted(rows,key=order),duplicates


def reconstruct(rows):
    notices=defaultdict(list)
    for r in rows:
        if r.get('correction')==12:notices[identity(r)].append(r)
    result=[]
    for r in rows:
        r=dict(r)
        if r.get('correction')==1:
            matches=[n for n in notices[identity(r)] if n['sip_timestamp']>r['sip_timestamp']]
            if len(matches)==1:
                original=matches[0]
                r.update(price=original.get('price'),size=original.get('decimal_size',original.get('size')),conditions=original.get('conditions',[]))
                r.pop('decimal_size',None);r['_restoration_source']=original['_source']
            else:r['_unknown']=True
        result.append(r)
    return result


def eligible(r,b,conditions,lag,odd=False):
    t=r.get('sip_timestamp');label=session(t,b)
    if not isinstance(t,int) or isinstance(t,bool):return False,'INVALID_TIMESTAMP'
    if r.get('_unknown'):return False,'CORRECTION_RECONSTRUCTION_UNRESOLVED'
    if r.get('correction',0) not in (None,0,1,7,8):return False,'CORRECTION_OR_CANCEL_NOTICE'
    p=dec(r.get('price'));size=dec(r.get('decimal_size',r.get('size')))
    if p is None or p<=0 or size is None or size<=0:return False,'INVALID_PRICE_OR_SIZE'
    if label not in ['AH','PRE','RTH']:return False,'OUTSIDE_OBSERVED_SESSION'
    pt=r.get('participant_timestamp')
    if pt is not None:
        if pt<=b[0]:return False,'PRIOR_CYCLE_EXECUTION'
        if pt>t:return False,'PARTICIPANT_AFTER_SIP'
        if t-pt>lag*S:return False,'DELAYED_PRINT'
    for code in r.get('conditions',[]):
        if code==0:continue
        if code in {5,10,13,22,30,31,32,33,38}:return False,'OUT_OF_SEQUENCE_OR_REFERENCE_PRICE'
        if code==12:
            if label not in ['AH','PRE']:return False,'FORM_T_OUTSIDE_EXTENDED_SESSION'
            continue
        if odd and code==37:continue
        c=conditions.get(code)
        if c is None:return False,'UNKNOWN_TRADE_CONDITION'
        if c.get('type') in ['short_sale_restriction_indicator','financial_status_indicator']:continue
        if c.get('update_rules',{}).get('consolidated',{}).get('updates_high_low') is not True:return False,'NON_PRICE_FORMING_CONDITION'
    return True,'ELIGIBLE_OBSERVED_TRADE'


def evidence(r):
    if r is None:return None
    return {'record_id':r['_id'],'sip_timestamp':r['sip_timestamp'],'participant_timestamp':r.get('participant_timestamp'),
        'price':str(r.get('price')),'size':str(r.get('decimal_size',r.get('size'))),'exchange':r.get('exchange'),
        'conditions':r.get('conditions',[]),'correction':r.get('correction',0),'source':r['_source'],
        'restoration_source':r.get('_restoration_source')}


def quote_mark(quotes,coverages,t,cfg):
    before=[r for r in quotes if r['sip_timestamp']<=t]
    if not before:return {'status':'MISSING','future_quote_used':False}
    r=before[-1];bid=dec(r.get('bid_price'));ask=dec(r.get('ask_price'));age=t-r['sip_timestamp'];flags=[]
    if not any(c['complete'] and c['request']['start_ns']<t<=c['request']['end_ns'] for c in coverages):flags.append('OUTSIDE_COMPLETE_QUOTE_WINDOW')
    if age>cfg['max_quote_age_seconds']*S:flags.append('STALE')
    if bid is None or ask is None or not 0<bid<=ask:flags.append('INVALID_OR_CROSSED')
    if any((dec(r.get(k)) or 0)<=0 for k in ['bid_size','ask_size']):flags.append('INVALID_SIZE')
    if any(c not in [0,1] for c in r.get('conditions',[])):flags.append('NONREGULAR_OR_CORRECTED')
    return {'status':'OK' if not flags else 'FLAGGED','flags':flags,'bid':str(bid),'ask':str(ask),'age_ns':age,
        'source':r['_source'],'future_quote_used':False}


def path_outcomes(eligible_rows,touch,b,unknown,invalidations,cfg,gap=None,complete=True):
    i=next(i for i,r in enumerate(eligible_rows) if r['_id']==touch['_id']);path=eligible_rows[i:];start=touch['sip_timestamp'];price=dec(touch['price'])
    intervals=[(b[1],b[2],'UNOBSERVED_INTERVAL')]
    if gap is not None:
        intervals += [(a['sip_timestamp'],z['sip_timestamp'],'MECHANICAL_GAP_SENSITIVITY') for a,z in zip(eligible_rows,eligible_rows[1:])
            if session(a['sip_timestamp'],b)==session(z['sip_timestamp'],b) and z['sip_timestamp']-a['sip_timestamp']>gap*S]
    def flags(t):
        f=[]
        if not complete:f.append('COVERAGE_INCOMPLETE')
        f.extend(label for a,z,label in intervals if a<t and z>start)
        if any(start<u<=t for u in unknown):f.append('UNKNOWN_PATH_PRICE_EVIDENCE')
        if any(u<=t for u in invalidations):f.append('TOUCH_INVALIDATED')
        return sorted(set(f))
    barriers=[]
    for up,down in cfg['barriers']:
        U=price*(1+dec(up));D=price*(1-dec(down));hit=None;direction=None;support=[]
        for t,group in groupby(path[1:],lambda r:r['sip_timestamp']):
            group=list(group);upper=[r for r in group if dec(r['price'])>=U];lower=[r for r in group if dec(r['price'])<=D]
            if upper or lower:
                hit=t;direction='AMBIGUOUS_SAME_SIP' if upper and lower else 'UPSIDE_FIRST' if upper else 'DOWNSIDE_FIRST';support=upper+lower;break
        f=flags(hit if hit is not None else b[4]);tail_stale=b[4]-path[-1]['sip_timestamp']>cfg['max_mark_age_seconds']*S
        result='CENSORED' if f or (hit is None and tail_stale) else direction or 'NEITHER'
        if hit is None and tail_stale:f.append('PRICE_MARK_FRESHNESS_FAILURE')
        censor_points=[a for a,z,label in intervals if start<a<b[4]]+[u for u in invalidations+unknown if start<=u<=b[4]]
        if hit is None and tail_stale:censor_points.append(path[-1]['sip_timestamp'])
        observation_class=('COMPETING_FIRST_PASSAGE_OBSERVED' if result in ['UPSIDE_FIRST','DOWNSIDE_FIRST'] else
            'ADMINISTRATIVE_RIGHT_CENSORING_WITH_KNOWN_NEITHER_CATEGORY' if result=='NEITHER' else
            'MISSING_OR_UNCLASSIFIABLE' if result=='AMBIGUOUS_SAME_SIP' or not complete or 'UNKNOWN_PATH_PRICE_EVIDENCE' in f or 'TOUCH_INVALIDATED' in f else
            'RIGHT_CENSORED_OBSERVATION_NOT_PROOF_OF_NONINFORMATIVE_CENSORING')
        barriers.append({'up':up,'down':down,'outcome':result,'first_passage_ns':hit,'observed_direction':direction,'flags':f,
            'support':[evidence(r) for r in support],'administrative_end_ns':b[4],'observation_class':observation_class,
            'censoring_time_ns':min(censor_points+[b[4]]) if result=='CENSORED' else b[4] if result=='NEITHER' else None})
    label=session(start,b);end=b[1] if label=='AH' else b[3] if label=='PRE' else b[4]
    marks=[]
    for name,target in [(f'{n}m',start+n*60*S) for n in cfg['forward_minutes']]+[('session_end',end),('cycle_end',b[4])]:
        f=flags(min(target,b[4]));candidates=[r for r in path if r['sip_timestamp']<=min(target,b[4]) and (name!='session_end' or session(r['sip_timestamp'],b)==label)]
        mark=candidates[-1] if candidates else None;age=target-mark['sip_timestamp'] if mark else None
        if target>b[4]:f.append('OBSERVED_SESSION_ENDED')
        if mark is None:f.append('NO_ELIGIBLE_PRICE_OBSERVATION')
        elif age>cfg['max_mark_age_seconds']*S:f.append('PRICE_MARK_FRESHNESS_FAILURE')
        marks.append({'horizon':name,'target_ns':target,'mark':evidence(mark),'age_ns':age,'censored':bool(f),
            'root_causes':sorted(set(f)),'return':str(dec(mark['price'])/price-1) if mark is not None and not f else None,
            'provider_coverage_complete':complete,'gap_not_proof_of_halt_or_provider_loss':True})
    return barriers,marks
