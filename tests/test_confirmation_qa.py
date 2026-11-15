import json
from pathlib import Path

import pytest

from market_lab.confirmation import signal_result
from market_lab.confirmation_qa import c1_signal, common_marks, quote_audit, waiting_path
from market_lab.confirmation_qa_run import summarize
from market_lab.tick_replay import SECOND
from test_confirmation import CONFIG as BASE_CONFIG, INITIAL, T, cov, quote, state, trade
from test_m2 import CYCLE, tick

CONFIG={**BASE_CONFIG,**json.loads(Path('configs/task-003-1-confirmation-qa-v1.json').read_text())}


def test_observed_acceptance_resets_below_but_counted_original_does_not():
    s=state([tick(),trade(10,'1.11'),trade(20,'1.0'),trade(30,'1.12'),trade(40,'1.13'),trade(60,'1.14')])
    counted,_=c1_signal(s,INITIAL,CYCLE,CONFIG,[],'C1_COUNTED_ORIGINAL')
    acceptance,_=c1_signal(s,INITIAL,CYCLE,CONFIG,[],'C1_OBSERVED_ACCEPTANCE')
    assert counted['signal_timestamp']==T+30*SECOND
    assert acceptance['signal_timestamp']==T+60*SECOND
    assert acceptance['qualifying_span_ns']==30*SECOND
    assert acceptance['below_threshold_resets']==1


@pytest.mark.parametrize('definition',['C1_COUNTED_ORIGINAL','C1_OBSERVED_ACCEPTANCE','C1_SESSION_BOUND'])
def test_predeclared_deadline_inclusive_without_changing_threshold(definition):
    s=state([tick(),trade(10),trade(61,'1.2')])
    unlimited,_=c1_signal(s,INITIAL,CYCLE,CONFIG,[],definition)
    bounded,_=c1_signal(s,INITIAL,CYCLE,CONFIG,[],definition,60)
    assert unlimited['status']=='CONFIRMED' and bounded['status']=='UNCONFIRMED'
    exact,_=c1_signal(state([tick(),trade(10),trade(60,'1.2')]),INITIAL,CYCLE,CONFIG,[],definition,60)
    assert exact['signal_timestamp']==T+60*SECOND


def test_session_bound_prevents_premarket_to_rth_even_without_overnight_gap():
    a=tick(when='2026-05-27T13:29:40Z')
    b=tick(when='2026-05-27T13:29:50Z',ident='b')
    c=tick(when='2026-05-27T13:30:10Z',ident='c')
    initial={**INITIAL,'event_timestamp':a['sip_timestamp'],'session':'PRE'}
    s=state([a,b,c])
    original,_=c1_signal(s,initial,CYCLE,CONFIG,[],'C1_COUNTED_ORIGINAL')
    bounded,_=c1_signal(s,initial,CYCLE,CONFIG,[],'C1_SESSION_BOUND')
    assert original['status']=='CONFIRMED'
    assert bounded['status']=='UNCONFIRMED'


def test_session_bound_never_restarts_in_next_session_after_overnight():
    a=tick(when='2026-05-26T23:59:50Z')
    rows=[a]+[tick(when=f'2026-05-27T08:00:{n:02}Z',ident=str(n)) for n in [0,10,30]]
    initial={**INITIAL,'event_timestamp':a['sip_timestamp'],'session':'AH'}
    s=state(rows)
    assert c1_signal(s,initial,CYCLE,CONFIG,[],'C1_COUNTED_ORIGINAL')[0]['status']=='CONFIRMED'
    assert c1_signal(s,initial,CYCLE,CONFIG,[],'C1_SESSION_BOUND')[0]['status']=='UNCONFIRMED'


def test_corrections_remove_observations_and_unknown_prior_is_not_verified():
    rows=[tick(),trade(10),trade(30)]
    notice={**rows[1],'sip_timestamp':T+20*SECOND,'correction':10}
    assert c1_signal(state(rows),INITIAL,CYCLE,CONFIG,[notice],'C1_OBSERVED_ACCEPTANCE')[0]['status']=='UNCONFIRMED'
    s=state(rows);s.unknown_times=[T+15*SECOND]
    assert c1_signal(s,INITIAL,CYCLE,CONFIG,[],'C1_OBSERVED_ACCEPTANCE')[0]['status']=='INSUFFICIENT_DATA'


def test_common_exit_clock_is_touch_anchored_and_not_own_signal_plus_five_minutes():
    s=state([tick(),trade(60,'1.2'),trade(300,'1.3'),trade(360,'1.4')])
    signal=signal_result('C1','CONFIRMED','test',T+60*SECOND,'1.2',trade_record_id='60')
    m=common_marks(s,INITIAL,signal,CYCLE,CONFIG,[])[0]
    assert m['target_ns']==T+300*SECOND and m['exit_price']=='1.3'
    assert float(m['return'])==pytest.approx(1.3/1.2-1)


def test_late_confirmation_remains_not_yet_confirmed_at_common_landmark():
    s=state([tick(),trade(300,'1.2'),trade(400,'1.3')])
    signal=signal_result('C1','CONFIRMED','test',T+400*SECOND,'1.3')
    marks=common_marks(s,INITIAL,signal,CYCLE,CONFIG,[])
    assert marks[0]['status']=='NOT_YET_CONFIRMED' and marks[0]['return'] is None
    assert marks[1]['confirmed_before_or_at_landmark']


def test_common_landmark_stale_marks_and_corrections_stay_censored():
    rows=[tick(),trade(30,'1.2'),trade(300,'1.3')]
    signal=signal_result('C1','CONFIRMED','test',T+30*SECOND,'1.2',
                         evidence=[{'record_id':'30'}])
    cancel={**rows[1],'sip_timestamp':T+40*SECOND,'correction':10}
    m=common_marks(state(rows),INITIAL,signal,CYCLE,CONFIG,[cancel])[0]
    assert m['status']=='CENSORED' and 'INITIAL_OR_CONFIRMATION_EVIDENCE_INVALIDATED' in m['flags']
    stale=common_marks(state(rows[:2]),INITIAL,signal,CYCLE,CONFIG,[])[0]
    assert stale['return'] is None


def test_preconfirmation_extremes_and_barriers_exclude_signal_trade():
    rows=[tick(),trade(10,'1.2'),trade(20,'.9'),trade(30,'1.5')]
    signal=signal_result('C1','CONFIRMED','test',T+30*SECOND,'1.5')
    result=waiting_path(state(rows),INITIAL,signal,CYCLE,CONFIG,[],T+60*SECOND)
    assert float(result['mfe'])==pytest.approx(1.2/1.1-1)
    assert result['barriers'][0]['first_observed_crossing']['timestamp']==T+10*SECOND
    assert result['end_exclusive_ns']==T+30*SECOND


def test_no_quotes_and_corrected_conditions_are_different_from_observed_failure():
    frozen={'status':'INSUFFICIENT_DATA','reason':'old'}
    assert quote_audit([],INITIAL,CYCLE,CONFIG,frozen)['assessment']=='NO_QUOTE_RETURNED'
    corrected=quote_audit([quote(0,conditions_json='[1,81]')],INITIAL,CYCLE,CONFIG,frozen)
    assert corrected['assessment']=='INVALID_OR_CORRECTED_QUOTES'
    assert not corrected['missing_update_implies_failure']
    below=quote_audit([quote(0,'1.0')],INITIAL,CYCLE,CONFIG,{'status':'UNCONFIRMED','reason':'old'})
    assert below['assessment']=='EXPLICIT_BELOW_THRESHOLD_BID'


def test_missing_updates_after_valid_support_are_not_called_support_failure():
    result=quote_audit([quote(0)],INITIAL,CYCLE,CONFIG,{'status':'UNCONFIRMED','reason':'old'})
    assert result['no_updates_despite_prior_fresh_valid_support']
    assert result['assessment']=='SUPPORT_UNPROVEN_FRESHNESS_GAPS_NOT_FAILURE'
    broken=quote_audit([quote(0),quote(5,'1.0')],INITIAL,CYCLE,CONFIG,{'status':'UNCONFIRMED','reason':'old'})
    assert broken['assessment']=='EXPLICIT_OBSERVED_SUPPORT_BREAK'


def test_old_preceding_quote_can_expire_before_first_new_update():
    result=quote_audit([quote(-4),quote(3),quote(8)],INITIAL,CYCLE,CONFIG,{'status':'UNCONFIRMED','reason':'old'})
    assert result['freshness_gaps_after_support']>=1
    assert result['longest_observed_support_span_seconds']==5


def test_detail_audit_does_not_count_missing_or_stale_checks_as_invalid_raw_quotes(tmp_path):
    from scripts.finalize_confirmation_qa import quote_detail
    from market_lab.storage import digest, file_hash, write_json
    cases=[];event_rows=[]
    for name,qs in [('missing',[]),('stale',[quote(-10)]),('corrected',[quote(0,conditions_json='[1,81]')])]:
        initial={**INITIAL,'event_id':name,'ticker':name}
        normalized=[]
        for q in qs:
            raw={k:q[k] for k in ['sip_timestamp','bid_price','ask_price','bid_size','ask_size']}
            raw['conditions']=json.loads(q['conditions_json'])
            path=tmp_path/(name+'-source.json');write_json(path,{'results':[raw]})
            normalized.append({**q,'record_id':digest(raw),'source_json':json.dumps({'path':str(path),'sha256':file_hash(path),'row':0})})
        cases.append(quote_audit(normalized,initial,CYCLE,CONFIG,{'status':'INSUFFICIENT_DATA','reason':'baseline'}))
        event_rows.append({'initial_event_id':name,'original_threshold_price':'1.1'})
    write_json(tmp_path/'c2-quote-audit.json',{'all_40':cases})
    write_json(tmp_path/'event-level-results.json',{'records':event_rows})
    detailed=quote_detail(CONFIG,tmp_path)
    assert [d['invalid_or_corrected_quote_observations'] for d in detailed]==[0,0,1]
    assert detailed[0]['missing_preceding_observation_checks']==1
    assert detailed[1]['stale_quote_observation_checks']==1
    assert detailed[1]['no_updates_after_prior_support_including_now_stale_quotes']
