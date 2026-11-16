from copy import deepcopy
from market_lab import manifest270 as m
from market_lab.calendar import cycles
from market_lab.tick_replay import bounds


def stock():
    return {'ticker':'NAMEW','security_type':'CS','gates':{k:{'status':'ELIGIBLE','reason':'ok'}for k in ['exchange','type','price','identity','action','currency']},
            'float_proxy':{'status':'ELIGIBLE','value':1000000},'change_status':'NO_CHANGE_OBSERVED'}


def test_security_type_gates_not_name_suffixes():
    r=stock();assert m.classify(r)[0]=='CANDIDATE_PASS'
    r['ticker']='NORMAL';r['security_type']='WARRANT';r['gates']['type']={'status':'INELIGIBLE','reason':'NOT_CS'}
    assert m.classify(r)==('CANDIDATE_EXCLUDED',['type:NOT_CS'])


def test_known_exclusion_precedes_missing_other_fields():
    r=stock();r['gates']['identity']={'status':'UNRESOLVED','reason':'MISSING_FIGI'}
    assert m.classify(r)[0]=='CANDIDATE_UNRESOLVED'
    r['float_proxy']={'status':'INELIGIBLE','value':15000001}
    assert m.classify(r)[0]=='CANDIDATE_EXCLUDED'
    assert m.classify(None)[0]=='CANDIDATE_UNRESOLVED'


def test_ah_is_previous_day_not_study_day_afterhours():
    cycle=cycles('2026-11-13',1)[0];a,ah,pre,opened,end=bounds(cycle)
    bars=[{'t':t//1000000,'h':'2'}for t in [a-60000_000_000,a,ah-60000_000_000,ah,pre,opened,end]]
    assert [r['t']for r in m.ah_bars(bars,cycle)]==[a//1000000,(ah-60000_000_000)//1000000]


def test_v3_cannot_authorize_without_explicit_approval_note():
    import pytest
    with pytest.raises(ValueError,match='EXPLICIT_USER_APPROVAL'):
        m.authorize('')
