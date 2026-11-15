import json
import time
from pathlib import Path
import pytest
from market_lab.nbbo_probe import ProbeClient,BudgetStop,mark,recommendation,normalized
from market_lab.storage import write_json,file_hash
from test_m2 import CYCLE

CONFIG=json.loads(Path('configs/task-003-2-nbbo-probe-v1.json').read_text())
T=1780000000000000000

def q(t=T,**kw):
    return {'sip_timestamp':t,'bid_price':'1','ask_price':'1.02','bid_size':'100','ask_size':'100','conditions_json':'[]','normalization_status':'OK','record_id':str(t),'source_json':'{}',**kw}

def intervals():return [{'start_ns':T-5_000_000_001,'end_ns':T,'complete':True}]

def test_causal_fresh_boundary_and_future():
    assert mark([q(T-5_000_000_000),q(T+1,ask_price='999')],intervals(),T,CONFIG)['ask']=='1.02'
    assert mark([q(T-5_000_000_001)],intervals(),T,CONFIG)['status']=='FLAGGED'
    assert mark([q(T+1)],intervals(),T,CONFIG)['status']=='MISSING'

@pytest.mark.parametrize('kw',[{'ask_price':'0.9'},{'bid_size':'0'},{'conditions_json':'[81]'},{'correction':1}])
def test_invalid_corrected_never_supported(kw):
    assert mark([q(**kw)],intervals(),T,CONFIG)['status']=='FLAGGED'

def test_missing_lookback_cannot_certify_mark():
    assert mark([q()],[],T,CONFIG)['status']=='FLAGGED'

class Response:
    status_code=200
    def __init__(self,body):self.data=json.dumps(body).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,n):
        for i in range(0,len(self.data),n):yield self.data[i:i+n]

class Session:
    def __init__(self,bodies):self.bodies=iter(bodies);self.calls=0
    def get(self,*a,**kw):self.calls+=1;return Response(next(self.bodies))

def test_empty_and_cached_response(tmp_path):
    s=Session([{'status':'OK','results_count':0}]);c=ProbeClient(tmp_path,CONFIG,key='fake',session=s)
    a,_=c.get('/v3/quotes/T',{},'T');b,_=c.get('/v3/quotes/T',{},'T')
    assert a['results']==b['results']==[] and s.calls==1

@pytest.mark.parametrize('limit,error',[({'max_requests':0},'HTTP_ATTEMPT'),({'max_pages':0},'PAGE_BUDGET'),({'max_decoded_bytes':0},'DECODED'),({'max_storage_bytes':1},'STORAGE')])
def test_global_budget_no_request(tmp_path,limit,error):
    s=Session([]);c=ProbeClient(tmp_path,{**CONFIG,**limit},key='fake',session=s)
    with pytest.raises(BudgetStop,match=error):c.get('/v3/quotes/T',{},'T')
    assert s.calls==0

def test_wall_budget_persists(tmp_path):
    c=ProbeClient(tmp_path,{**CONFIG,'total_wall_seconds':-1},key='fake',session=Session([]))
    with pytest.raises(BudgetStop,match='WALL_TIME'):c.get('/v3/quotes/T',{},'T')

def test_byte_budget_retains_partial_no_overrun(tmp_path):
    s=Session([{'results':['x'*40000]}]);c=ProbeClient(tmp_path,{**CONFIG,'max_page_bytes':20000},key='fake',session=s)
    with pytest.raises(BudgetStop):c.get('/v3/quotes/T',{},'T')
    assert c.ledger['decoded_bytes']==16384 and list((tmp_path/'raw').glob('*.partial'))

def test_page_limit_explicit_incomplete(tmp_path):
    s=Session([{'results':[],'next_url':'https://api.massive.com/v3/quotes/T?cursor=a'}]);c=ProbeClient(tmp_path,{**CONFIG,'max_pages_per_window':1},key='fake',session=s)
    w={'security_id':'id','cycle_id':'day','target_ns':T,'endpoint':'/v3/quotes/T','params':{},'ticker':'T'}
    r=c.window(w,0);assert not r['complete'] and r['error']=='WINDOW_PAGE_BUDGET'
    assert c.window(w,0)==r and s.calls==1

def test_recommendation_only_coverage_not_returns():
    assert recommendation(10,9,4,False)=='QUOTE_EXPANSION_FEASIBLE'
    assert recommendation(10,2,1,False)=='QUOTE_EXPANSION_CONDITIONALLY_FEASIBLE'
    assert recommendation(10,0,0,False)=='QUOTE_EXPANSION_NOT_JUSTIFIED'

def test_hard_deadline_interrupts_blocking_io(tmp_path,monkeypatch):
    import market_lab.nbbo_probe as module
    class SlowSession:
        def get(self,*args,**kwargs):time.sleep(10);raise AssertionError('watchdog failed')
    monkeypatch.setattr(module.requests,'Session',SlowSession)
    window=json.loads(Path(CONFIG['plan']).read_text())['pilot_queue'][0]
    started=time.monotonic()
    with pytest.raises(module.HardDeadline):
        module.acquire({**CONFIG,'total_wall_seconds':1.6},tmp_path,{'selected':[window]},'fake')
    assert time.monotonic()-started<1.6
    assert json.loads((tmp_path/'ledger.json').read_text())['execution_wall_seconds']<1.6


def test_latest_invalid_is_not_replaced_by_earlier_good_quote():
    result=mark([q(T-1),q(T,conditions_json='[81]')],intervals(),T,CONFIG)
    assert result['status']=='FLAGGED' and result['timestamp']==T
