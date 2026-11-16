from decimal import Decimal
import pytest
from market_lab.audit_paths import eligible,reconstruct,path_outcomes,session,S
from market_lab.audit_statistics import ratio,groups_from_rows,simulate
from market_lab.preholdout_audit import denied

B=(0,10*S,20*S,30*S,100*S)
CFG={'barriers':[['0.03','0.03'],['0.05','0.03'],['0.10','0.05']],'forward_minutes':[5,15,30,60],'max_mark_age_seconds':60}


def trade(t,p,code=0,ident='a',**kw):
    return {'sip_timestamp':t,'participant_timestamp':t,'price':str(p),'size':100,'conditions':[],
        'correction':code,'id':ident,'_id':ident+str(t)+str(code),'_source':{},**kw}


def test_high_low_eligibility_and_odd_lot_segregation():
    conditions={37:{'update_rules':{'consolidated':{'updates_high_low':False}}},99:{'update_rules':{'consolidated':{'updates_high_low':True,'updates_open_close':False}}}}
    assert eligible(trade(25*S,1,conditions=[99]),B,conditions,10)[0]
    assert not eligible(trade(25*S,1,conditions=[37]),B,conditions,10)[0]
    assert eligible(trade(25*S,1,conditions=[37]),B,conditions,10,True)[0]
    assert not eligible(trade(25*S,1,conditions=[22]),B,conditions,10,True)[0]


def test_corrections_restore_original_fields_not_future_corrected_price():
    r=trade(21*S,2,1);n=trade(25*S,1,12,participant_timestamp=21*S)
    out=reconstruct([r,n]);assert out[0]['price']=='1' and '_restoration_source' in out[0]
    assert reconstruct([r])[0]['_unknown']
    assert not eligible(n,B,{},10)[0]


def test_barriers_exact_equality_and_same_sip_ambiguity():
    t=trade(31*S,1);path=[t,trade(32*S,'1.03',ident='b'),trade(32*S,'.97',ident='c')]
    b,_=path_outcomes(path,t,B,[],[],CFG)
    assert b[0]['outcome']=='AMBIGUOUS_SAME_SIP'
    assert b[0]['first_passage_ns']==32*S
    b,_=path_outcomes(path[:2],t,B,[],[],CFG)
    assert b[0]['outcome']=='UPSIDE_FIRST'


def test_overnight_censors_future_barrier_and_stale_returns_are_not_zero():
    t=trade(9*S,1);path=[t,trade(21*S,'1.04')]
    b,marks=path_outcomes(path,t,B,[],[],CFG)
    assert b[0]['outcome']=='CENSORED' and 'UNOBSERVED_INTERVAL' in b[0]['flags']
    assert marks[0]['return'] is None and marks[0]['censored']


def test_touch_invalidation_and_unknown_evidence_censor():
    t=trade(31*S,1);path=[t,trade(34*S,'1.04')]
    assert path_outcomes(path,t,B,[],[33*S],CFG)[0][0]['outcome']=='CENSORED'
    assert path_outcomes(path,t,B,[33*S],[],CFG)[0][0]['outcome']=='CENSORED'


def test_finite_population_census_variance_zero_and_zero_event_rows_kept():
    groups=[{'month':'m','N':4,'y':[1,-1,0,0],'z':[1,1,0,0]}]
    r=ratio(groups,{'m':1});assert r['estimate']==0 and r['se']==0
    assert r['domain_total']==2
    with pytest.raises(ValueError):ratio([{'month':'m','N':1,'y':[1,0],'z':[1,1]}],{'m':1})


def test_linearization_known_two_stage_variance():
    groups=[{'month':'m','cycle_id':str(i//2),'N':4,'y':[0,1],'z':[1,1]} for i in range(4)]
    r=ratio(groups,{'m':4});assert r['estimate']==.5 and r['se']==pytest.approx(.125)


def test_empty_event_domain_is_not_a_zero_probability():
    r=ratio([{'month':'m','N':4,'y':[0,0],'z':[0,0]}],{'m':1})
    assert r['estimate'] is None and r['status']=='EMPTY_DOMAIN'


def test_network_guard():
    with pytest.raises(RuntimeError,match='NETWORK_FORBIDDEN'):denied('https://api.massive.com')


def test_synthetic_calibration_is_seeded_and_labeled():
    a=simulate(3,5);b=simulate(3,5)
    assert a==b and all(r['synthetic_only'] and r['replicates']==3 for r in a)
