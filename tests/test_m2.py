import json
from pathlib import Path
from copy import deepcopy
import pytest
from market_lab.tick_replay import ns, session_label, first_touch, outcomes, SECOND, quote_at_event
from market_lab.tick_ingest import TickClient, normalize
from market_lab.storage import write_json, file_hash
from market_lab.api import APIError
from market_lab.m2_pilot import control_eligible

CONFIG = json.loads(Path('configs/m2-pilot-v1.json').read_text())
CYCLE = {'cycle_id':'2026-05-27','anchor_at':'2026-05-26T20:00:00Z','afterhours_end':'2026-05-27T00:00:00Z',
         'premarket_start':'2026-05-27T08:00:00Z','rth_open':'2026-05-27T13:30:00Z','end_at':'2026-05-27T20:00:00Z'}
OPP = {'previous_rth_close':'1','security_id':'id','ticker':'TEST','sample':'SYSTEMATIC','cohorts':['EXCHANGE_PRICE_ONLY']}

def tick(price='1.1', when='2026-05-27T13:31:00Z', ident='a', **kw):
    t = ns(when)
    return {'price':price,'size':'100','sip_timestamp':t,'participant_timestamp':t,'record_id':ident,'trade_id':ident,
            'sequence_number':1,'exchange':4,'trf_id':None,'correction':0,'session':session_label(CYCLE,t),
            'normalization_status':'OK','conditions_json':'[]','source_json':'{}',**kw}

def replay(rows, complete=True, **kw):
    return first_touch(rows,CYCLE,OPP,CONFIG,{37:{'update_rules':{}}},complete,'test',**kw)

@pytest.mark.parametrize('price,event',[('1.099999',False),('1.10',True),('1.11',True),('NaN',False),('-1',False)])
def test_threshold(price,event):
    assert bool(replay([tick(price)])['event']) == event

@pytest.mark.parametrize('when,session,verified',[('2026-05-26T20:01:00Z','AH',True),('2026-05-27T08:01:00Z','PRE',False),('2026-05-27T13:31:00Z','RTH',False)])
def test_sessions(when,session,verified):
    e=replay([tick(when=when)])['event']
    assert e['session']==session
    assert (e['first_touch_status']=='VERIFIED_FIRST_TOUCH')==verified

def test_multiple_sorting_missing_prior():
    a=tick(); b=tick('1.0','2026-05-27T13:32:00Z','b'); c=tick('1.2','2026-05-27T13:33:00Z','c')
    r=replay([c,b,a],False)
    assert r['event']['record_id']=='a'
    assert r['event']['first_touch_status']=='FIRST_TOUCH_UNVERIFIED'
    assert r['candidates'][0]['candidate_status']=='SUBSEQUENT_CROSSING'

@pytest.mark.parametrize('kw,reason',[({'conditions_json':'[37]'},'NON_PRICE_FORMING_CONDITION'),({'conditions_json':'[9999]'},'UNKNOWN_TRADE_CONDITION'),({'conditions_json':'[13]'},'OUT_OF_SEQUENCE_OR_REFERENCE_PRICE'),({'participant_timestamp':ns('2026-05-27T13:30:00Z')},'DELAYED_PRINT')])
def test_conditions(kw,reason):
    r=replay([tick(**kw)])
    assert r['event'] is None and r['reject_counts'][reason]==1

def test_cancellation_no_future_leak():
    a=tick(correction=8); notice={**a,'sip_timestamp':a['sip_timestamp']+SECOND,'correction':10,'record_id':'notice'}
    r=replay([notice,a])
    assert r['event']['touch_price']=='1.1' and r['event']['later_invalidated']
    assert all(m['censored'] for m in outcomes(r,CYCLE,CONFIG,True)['forward'])

def test_corrected_original_reconstructed():
    a=tick('2',correction=1)
    notice={**a,'price':'1.0','correction':12,'sip_timestamp':a['sip_timestamp']+SECOND,'record_id':'notice'}
    assert replay([a,notice])['event'] is None
    r=replay([a,tick('1.2','2026-05-27T13:32:00Z','b')])
    assert not r['event']['observed_window_first_verified']

def test_outcomes_and_ties():
    rows=[tick(),tick('1.2','2026-05-27T13:32:00Z','b'),tick('1.0','2026-05-27T13:33:00Z','c')]
    r=outcomes(replay(rows),CYCLE,CONFIG,True)
    assert r['barriers'][0]['outcome']=='UPSIDE_FIRST'
    assert float(r['observed_mfe'])==pytest.approx(1.2/1.1-1)
    assert float(r['observed_mae'])==pytest.approx(1/1.1-1)
    assert all(m['censored'] for m in r['forward'])
    rows[2]['sip_timestamp']=rows[1]['sip_timestamp']; rows[2]['participant_timestamp']=rows[1]['sip_timestamp']
    assert outcomes(replay(rows),CYCLE,CONFIG,True)['barriers'][0]['outcome']=='AMBIGUOUS_SAME_SIP'

def test_halt_and_overnight():
    a=tick(when='2026-05-26T23:59:00Z'); b=tick('1.2','2026-05-27T08:01:00Z','b')
    assert outcomes(replay([a,b]),CYCLE,CONFIG,True)['barriers'][0]['outcome']=='CENSORED'
    assert replay([a],halt_intervals=[(a['sip_timestamp']-1,a['sip_timestamp']+1)])['event'] is None

def test_split_gate():
    r={k+'_status':'ELIGIBLE' for k in ['exchange','price','type','identity','currency','action']}
    r['change_status']='NO_CHANGE_OBSERVED'; assert control_eligible(r)
    r['action_status']='UNRESOLVED'; assert not control_eligible(r)

def test_dedup_hash_and_cache(tmp_path):
    raw={'sip_timestamp':ns('2026-05-27T13:31:00Z'),'price':1.1,'size':100,'id':'x'}
    path=tmp_path/'raw.json'; write_json(path,{'results':[raw,raw]})
    coverage={'request':{'start_ns':ns(CYCLE['anchor_at']),'end_ns':ns(CYCLE['end_at']),'ticker':'TEST','kind':'trades'},'raw_rows':2,
              'pages':[{'path':str(path),'sha256':file_hash(path)}]}
    rows,audit=normalize(coverage,'id',CYCLE,tmp_path/'ticks.parquet')
    assert len(rows)==1 and audit['exact_duplicates']==1
    path.write_text('{}')
    with pytest.raises(APIError): normalize(coverage,'id',CYCLE,tmp_path/'bad.parquet')

class FakeClient(TickClient):
    def __init__(self,root):
        super().__init__(root,CONFIG,offline=True); self.calls=0
    def get(self,path,params=None):
        self.calls+=1
        p=self.root/f'{self.calls}.json'; body={'results':[]}
        if self.calls==1: body['next_url']='https://api.massive.com/v3/trades/TEST?cursor=2'
        write_json(p,body)
        return body,{'path':str(p),'sha256':file_hash(p)}

def test_pagination_resume(tmp_path):
    c=FakeClient(tmp_path/'raw')
    a=c.window('trades','TEST',1,2,tmp_path/'window')
    assert a['complete'] and len(a['pages'])==2
    assert c.window('trades','TEST',1,2,tmp_path/'window')==a and c.calls==2

def test_budget(tmp_path):
    c=TickClient(tmp_path,{**CONFIG,'max_requests':0},key='test')
    with pytest.raises(APIError,match='BUDGET'): c.get('/v3/trades/TEST')

@pytest.mark.parametrize('value,status',[(100000,'ELIGIBLE'),(15000000,'ELIGIBLE'),(99999,'INELIGIBLE'),(15000001,'INELIGIBLE'),(None,'UNRESOLVED')])
def test_float_proxy_and_sec_independent(tmp_path,monkeypatch,value,status):
    from market_lab.m2_pilot import collect_context
    monkeypatch.chdir(tmp_path)
    sec=Path('data/sec-pilot-20261115-v2/results-reviewed-v1.json')
    write_json(sec,{'results':[{'security':{'security_id':'id'},'status':'SEC_DERIVED_HISTORICAL_ESTIMATE','derived_estimates':[{'shares':999999999,'measurement_date':'2020-01-01'}]}]})
    class Client:
        config=CONFIG
        def get(self,path,params=None):
            result=[] if 'conditions' in path else {'share_class_figi':'id'} if '/tickers/' in path else [{'ticker':'TEST','free_float':value}]
            return {'results':result},{'retrieved_at':'2026-11-15T00:00:00Z'}
    root=tmp_path/'run';root.mkdir()
    c=collect_context(Client(),[{'security_id':'id','ticker':'TEST'}],root)
    assert c['float']['id']['status']==status
    assert not c['float']['id']['is_verified_pit']
    assert c['SEC']['id']['derived_estimates'][0]['measurement_date']=='2020-01-01'

def test_forward_precise_mark_and_quote_censor():
    a=tick(); b=tick('1.2','2026-05-27T13:36:00Z','b')
    r=outcomes(replay([a,b]),CYCLE,CONFIG,True)
    assert r['forward'][0]['return'] is not None
    quote={'normalization_status':'OK','sip_timestamp':a['sip_timestamp']-6*SECOND,'bid_price':'1.09','ask_price':'1.11','conditions_json':'[]','source_json':'{}'}
    q=quote_at_event([quote],replay([a])['event'],CONFIG,False)
    assert 'STALE_NBBO' in q['flags'] and 'INCOMPLETE_QUOTE_WINDOW' in q['flags']

def test_early_close_dst_session_labels():
    c={**CYCLE,'anchor_at':'2026-11-25T21:00:00Z','afterhours_end':'2026-11-26T01:00:00Z','premarket_start':'2026-11-27T09:00:00Z','rth_open':'2026-11-27T14:30:00Z','end_at':'2026-11-27T18:00:00Z'}
    assert session_label(c,ns('2026-11-27T14:29:59Z'))=='PRE'
    assert session_label(c,ns('2026-11-27T18:00:00Z'))=='RTH'
    assert session_label(c,ns('2026-11-27T18:00:01Z'))=='OUTSIDE_CYCLE'

def test_incomplete_pages_and_resume(tmp_path):
    class Failing(FakeClient):
        def get(self,path,params=None):
            if 'cursor' in path: raise APIError('HTTP_429')
            return super().get(path,params)
    c=Failing(tmp_path/'raw')
    result=c.window('trades','TEST',1,2,tmp_path/'window')
    assert not result['complete'] and result['error']=='HTTP_429'
    # Retained first-page evidence survives interruption; complete replay can restart.
    good=FakeClient(tmp_path/'raw')
    assert good.window('trades','TEST',1,2,tmp_path/'window')['complete']

def test_unknown_prior_makes_touch_unverified():
    earlier=tick('1.0','2026-05-27T13:30:00Z','prior',conditions_json='[9999]')
    r=replay([earlier,tick()])
    assert not r['event']['observed_window_first_verified']
    assert 'UNKNOWN_PRIOR_PRICE_EVIDENCE' in r['event']['quality_flags']

def test_no_event_denominator_not_incomplete_negative():
    assert replay([tick('1.0')])['zero_event_status']=='ZERO_EVENT_OBSERVED'
    assert replay([tick('1.0')],False)['zero_event_status']=='UNKNOWN_INCOMPLETE'

def test_query_filter_and_extract_counts(tmp_path,monkeypatch):
    import runpy
    from types import SimpleNamespace
    from market_lab.m2_pilot import event_table
    query=runpy.run_path('scripts/m2_query.py')['query']
    monkeypatch.chdir(tmp_path)
    event_table(Path('data/runs/test/events/events.parquet'),[{'event_id':str(i),'ticker':'TEST','security_id':'id','cycle_id':'day','session':'AH','sample':'SYSTEMATIC'} for i in range(3)])
    args=SimpleNamespace(run_id='test',kind='events',cycle_id='day',security_id='id',ticker='TEST',session='AH',event_id=None,limit=1,output=None)
    result=query(args)
    assert result['matching_rows']==3 and result['returned_rows']==1 and result['truncated']
    args.event_id='2'
    assert query(args)['rows'][0]['event_id']=='2'
