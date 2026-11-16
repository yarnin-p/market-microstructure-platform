"""Census transport, completeness and frozen-policy regressions; no market I/O."""
import json
from pathlib import Path
from copy import deepcopy
import pytest
from market_lab import census as c
from market_lab.tick_replay import first_touch,bounds,ns

CFG={**json.loads(Path('configs/m2-pilot-v1.json').read_text()),'cycle':c.cycles('2026-11-13',1)[0]}
OP={'ticker':'TEST','security_id':'sid','previous_rth_close':'1','sample':'FULL_CENSUS','cohorts':['EXCHANGE_PRICE_ONLY'],'float_proxy_stratum':'OTHER_EXCHANGE_PRICE_ELIGIBLE'}
CONDITIONS={37:{'update_rules':{'consolidated':{'updates_high_low':False,'updates_open_close':False}}},2:{'update_rules':{'consolidated':{'updates_high_low':True,'updates_open_close':False}}}}


def row(t,price='1.1',**kw):
    raw={'sip_timestamp':t,'participant_timestamp':t,'price':price,'size':'100','id':'a','exchange':4,'sequence_number':1,**kw}
    return c.normalized(raw,{},'sid',CFG['cycle'])


def run(rows,complete=True):
    return first_touch(rows,CFG['cycle'],OP,CFG,CONDITIONS,complete,'test')


@pytest.mark.parametrize('index,delta,session',[(0,1,'AH'),(2,0,'PRE'),(3,0,'RTH')])
def test_three_session_firsts(index,delta,session):
    t=bounds(CFG['cycle'])[index]+delta
    e=run([row(t)])['event']
    assert e['session']==session and e['observed_window_first_verified']
    assert (e['first_touch_status']=='VERIFIED_FIRST_TOUCH')==(session=='AH')


def test_ah_only_and_cross_session_duplicates():
    a,_,pre,opened,_=bounds(CFG['cycle'])
    r=run([row(opened,id='c'),row(pre,id='b'),row(a+1)])
    assert r['event']['session']=='AH' and len(r['eligible'])==3
    assert len({r['event']['security_id']})==1


def test_blind_interval_not_a_touch():
    _,ah,_,_,_=bounds(CFG['cycle'])
    assert run([row(ah)])['zero_event_status']=='ZERO_EVENT_OBSERVED'


def test_odd_lot_raw_and_highlow_only_not_primary():
    t=bounds(CFG['cycle'])[2]
    r=run([row(t,conditions=[37]),row(t+1,id='b',conditions=[2]),row(t+2,id='c')])
    assert r['event']['event_timestamp']==t+2
    assert r['raw_first_crossing']['sip_timestamp']==t
    assert r['reject_counts']['NON_PRICE_FORMING_CONDITION']==2


def test_cancel_preserved_and_original_restored():
    t=bounds(CFG['cycle'])[2]
    a=row(t,correction=8);b={**a,'record_id':'notice','sip_timestamp':t+1,'correction':10}
    assert run([a,b])['event']['later_invalidated']
    a=row(t,price='2',correction=1);b={**a,'record_id':'notice','sip_timestamp':t+1,'correction':12,'price':'1.0'}
    assert run([a,b])['event'] is None


def test_tie_break_and_exact_nanoseconds():
    t=bounds(CFG['cycle'])[2]+123
    a=row(t,id='z',sequence_number=2);b=row(t,id='a',sequence_number=1)
    assert run([a,b])['event']['record_id']==b['record_id']
    values=c.parse_csv(f'sip_timestamp,participant_timestamp,price,size,id\n{t},{t-1},1.1,100,a\n',1)
    assert values[0]['sip_timestamp']==t and values[0]['participant_timestamp']==t-1


def test_zero_unknown_and_unknown_condition():
    t=bounds(CFG['cycle'])[2]
    assert run([row(t,price='1')])['zero_event_status']=='ZERO_EVENT_OBSERVED'
    assert run([row(t,price='1')],False)['zero_event_status']=='UNKNOWN_INCOMPLETE'
    r=run([row(t,price='1',conditions=[999]),row(t+1,id='b')])
    assert not r['event']['observed_window_first_verified']


def test_export_count_and_truncation():
    with pytest.raises(ValueError,match='MISMATCH'):c.parse_csv('sip_timestamp\n1\n',2)
    with pytest.raises(ValueError,match='TRUNCATED'):c.parse_csv('[truncated: 5 more chars]')
    with pytest.raises(ValueError):c.parse_csv('sip_timestamp\n1.5\n')
    assert c.parse_csv('',0)==[]


def capture(params,rows,next_params=None,index=0):
    return {'path':'/v3/trades/TEST','params':params,'csv':rows,'expected_rows':1,'next_params':next_params,'page_index':index}


def test_multi_page_exhaustion_and_incomplete(tmp_path,monkeypatch):
    monkeypatch.setattr(c,'ROOT',tmp_path)
    folder=tmp_path/'raw/TEST';folder.mkdir(parents=True)
    a,_,pre,_,end=bounds(CFG['cycle'])
    params={'timestamp.gt':str(a),'timestamp.lte':str(end),'sort':'timestamp','order':'asc','limit':50000}
    text=f'sip_timestamp,participant_timestamp,price,size,id\n{pre},{pre},1,100,a\n'
    (folder/'page-00000.json').write_text(json.dumps(capture(params,text,{'cursor':'two'})))
    r=c.replay_symbol(OP,CFG,CONDITIONS)
    assert not r['complete'] and r['disposition']=='UNKNOWN_INCOMPLETE'
    text=f'sip_timestamp,participant_timestamp,price,size,id\n{pre+1},{pre+1},1.1,100,b\n'
    (folder/'page-00001.json').write_text(json.dumps(capture({'cursor':'two'},text,index=1)))
    r=c.replay_symbol(OP,CFG,CONDITIONS)
    assert r['complete'] and r['event']['event_timestamp']==pre+1
    cap=capture({'cursor':'wrong'},text,index=1)
    (folder/'page-00001.json').write_text(json.dumps(cap))
    assert not c.replay_symbol(OP,CFG,CONDITIONS)['complete']


def test_missing_historical_attributes_are_not_eligible():
    from market_lab.m2_pilot import control_eligible
    row={g+'_status':'ELIGIBLE'for g in c.GATES}|{'change_status':'NO_CHANGE_OBSERVED'}
    for g in ['exchange','type','identity']:
        r={**row,g+'_status':'UNRESOLVED'}
        assert not control_eligible(r)


def test_receipts_are_not_trade_pages_and_tamper_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(c,'ROOT',tmp_path)
    folder=tmp_path/'raw/TEST';folder.mkdir(parents=True)
    a,_,pre,_,end=bounds(CFG['cycle'])
    params={'timestamp.gt':str(a),'timestamp.lte':str(end),'sort':'timestamp','order':'asc','limit':5000}
    text=f'sip_timestamp,participant_timestamp,price,size,id\n{pre},{pre},1,100,a\n'
    p=folder/'page-00000.json';p.write_text(json.dumps(capture(params,text)))
    c.seal(p)
    assert c.replay_symbol(OP,CFG,CONDITIONS)['complete']
    p.write_text(p.read_text().replace(',1,100,',',2,100,'))
    with pytest.raises(AssertionError):c.seal(p)


def test_cursor_export_tail_reconciliation():
    import base64
    payload='ap=17&order=asc&sort=timestamp&timestamp.gte=2026-11-13T10%3A14%3A16.538269921Z'
    cursor=base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')
    rows=[{'sequence_number':17,'sip_timestamp':1794564856538269921}]
    assert c.cursor_tail_audit({'cursor':cursor},rows)=='TAIL_SEQUENCE_AND_NANOSECOND_MATCH'
    with pytest.raises(AssertionError):c.cursor_tail_audit({'cursor':cursor},[{**rows[0],'sequence_number':16}])


def test_null_decimal_size_presence_remains_unknown():
    with pytest.raises(ValueError,match='FIELD_PRESENCE_AMBIGUOUS'):
        c.parse_csv('sip_timestamp,price,size,decimal_size\n1794560400000000000,1.1,100,\n',1)


@pytest.mark.parametrize('index,allowed',[(0,True),(2,True),(3,False)])
def test_form_t_session_rule_is_frozen(index,allowed):
    t=bounds(CFG['cycle'])[index]+1
    assert bool(run([row(t,conditions=[12])])['event'])==allowed
