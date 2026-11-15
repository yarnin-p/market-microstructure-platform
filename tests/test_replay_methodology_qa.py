import json
import shutil
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from market_lab.api import APIError
from market_lab.replay_methodology import (ReplayState, condition_maps, first_touch_scope,
                                          gap_diagnostics, outcome_sensitivity)
from market_lab.replay_qa import repair_window
from market_lab.storage import file_hash, write_json
from market_lab.tick_replay import eligible_trade, ns, SECOND
from test_m2 import CYCLE, CONFIG, OPP, tick


def test_full_bundle_preserves_all_events_and_three_gap_outcomes(tmp_path):
    from scripts.bundle_replay_qa import package
    source = Path('reports/m2-methodology-qa-20261115-v1')
    for p in source.iterdir():
        if p.suffix in {'.json', '.md'}:
            shutil.copyfile(p, tmp_path / p.name)
    config = json.loads(Path('configs/task-002-1-qa-v1.json').read_text())
    result = package(tmp_path, config)
    assert result['status'] == 'PASS'
    assert result['record_counts']['event_results.parquet'] == 124
    assert result['all_processed_cycles_included'] == ['2026-05-27', '2026-05-28', '2026-05-29']
    import pyarrow.parquet as pq
    with zipfile.ZipFile(tmp_path / 'research_bundle.zip') as archive:
        assert 'data_quality.json' in archive.namelist()
        assert not any('/raw/' in name for name in archive.namelist())
        with archive.open('event_results.parquet') as stream:
            rows = pq.read_table(stream).to_pylist()
        assert all(len(json.loads(r['payload_json'])['outcomes']) == 3 for r in rows)


def test_requested_audit_matches_published_cycle_not_first_event_for_ticker():
    from scripts.report_replay_qa import requested_examples

    old = {'ticker': 'HOTH', 'cycle_id': '2026-05-28', 'record_id': 'published'}
    earlier = {**old, 'cycle_id': '2026-05-27', 'record_id': 'earlier',
               'variant': 'QA_REPAIRED', 'condition_policy': 'HIGH_LOW_ONLY'}
    correct = {**earlier, **old}
    sensitivity = {**correct, 'condition_policy': 'ODD_LOT_OBSERVATION_SENSITIVITY'}
    assert requested_examples([old], [earlier, sensitivity, correct]) == [(old, correct)]


def state(rows, complete=True, policy="HIGH_LOW_ONLY", conditions=None):
    maps = condition_maps(conditions or {})
    s = ReplayState(policy, CYCLE, OPP, CONFIG, maps[policy], complete, "test", max(r['sip_timestamp'] for r in rows))
    for row in rows:
        s.feed(row)
    return s


def test_high_low_without_open_close_is_audited_independently_of_explicit_veto():
    conditions = {99: {"type": "sale_condition", "update_rules": {"consolidated": {
        "updates_high_low": True, "updates_open_close": False}}}}
    maps = condition_maps(conditions)
    row = tick(conditions_json='[99]')
    assert eligible_trade(row, CYCLE, maps['LEGACY_BOTH'], CONFIG)[0] is False
    assert eligible_trade(row, CYCLE, maps['HIGH_LOW_ONLY'], CONFIG)[0] is True
    # Prior-reference and out-of-sequence codes remain explicit vetoes even
    # when the provider's aggregate high/low flag is true.
    for code in [5, 10, 22, 32]:
        r = tick(conditions_json=json.dumps([code]))
        assert not eligible_trade(r, CYCLE, maps['HIGH_LOW_ONLY'], CONFIG)[0]


@pytest.mark.parametrize('when', ['2026-05-26T21:00:00Z','2026-05-27T08:00:00Z','2026-05-27T14:00:00Z'])
def test_odd_lots_are_explicit_sensitivity_and_do_not_override_combined_rejections(when):
    odd = {37: {'type':'sale_condition','update_rules':{'consolidated':{'updates_high_low':False,'updates_open_close':False}}}}
    r = tick(when=when, conditions_json='[37]')
    assert state([r],conditions=odd).event is None
    assert state([r],conditions=odd,policy='ODD_LOT_OBSERVATION_SENSITIVITY').event is not None
    r['conditions_json']='[37,22]'
    assert state([r],conditions=odd,policy='ODD_LOT_OBSERVATION_SENSITIVITY').event is None


def test_form_t_is_session_dependent_and_multi_condition_rules_remain():
    maps = condition_maps({37: {'update_rules': {'consolidated': {}}}})
    assert eligible_trade(tick(when='2026-05-26T21:00:00Z',conditions_json='[12]'),CYCLE,maps['HIGH_LOW_ONLY'],CONFIG)[0]
    assert not eligible_trade(tick(conditions_json='[12]'),CYCLE,maps['HIGH_LOW_ONLY'],CONFIG)[0]
    assert not eligible_trade(tick(when='2026-05-26T21:00:00Z',conditions_json='[12,37]'),CYCLE,maps['HIGH_LOW_ONLY'],CONFIG)[0]


def test_observed_prefix_and_strict_cycle_are_different_proofs():
    event={'session':'AH','event_timestamp':ns('2026-05-26T21:00:00Z')}
    proof=first_touch_scope(event,CYCLE,True,False,ns(CYCLE['end_at']))
    assert proof['observed_sessions_first_verified'] and proof['prefix_first_verified']
    assert not proof['strict_full_cycle_first_verified']
    pre={**event,'session':'PRE','event_timestamp':ns('2026-05-27T08:01:00Z')}
    proof=first_touch_scope(pre,CYCLE,True,False,ns(CYCLE['end_at']))
    assert proof['observed_sessions_first_verified'] and not proof['prefix_first_verified']
    incomplete=first_touch_scope(event,CYCLE,False,False,event['event_timestamp']+SECOND)
    assert incomplete['prefix_first_verified'] and not incomplete['observed_sessions_first_verified']
    assert not first_touch_scope(event,CYCLE,True,True,ns(CYCLE['end_at']))['prefix_first_verified']


def test_incomplete_pages_or_unknown_prior_never_become_verified_observed_first():
    r=tick()
    assert state([r],complete=False).event['first_touch_status']=='UNVERIFIED_TOUCH'
    unknown=tick('1.2','2026-05-27T13:30:00Z','unknown',conditions_json='[999]')
    s=state([unknown,r])
    assert not s.event['observed_sessions_first_verified']


def test_illiquid_gap_is_not_missing_page_and_has_fixed_mark_age():
    rows=[tick(),tick('1.2','2026-05-27T13:41:00Z','b'),tick('1.15','2026-05-27T13:46:00Z','c')]
    s=state(rows)
    conservative=outcome_sensitivity(s,CYCLE,CONFIG,300)
    no_gap=outcome_sensitivity(s,CYCLE,CONFIG,None)
    m=lambda result,h:next(m for m in result['forward'] if m['horizon']==h)
    assert m(conservative,'15m')['censored']
    assert not m(no_gap,'15m')['censored']
    assert m(no_gap,'5m')['censored']  # Fixed 60-second mark age still applies.
    assert conservative['barriers'][0]['outcome']=='CENSORED'
    assert no_gap['barriers'][0]['outcome']=='UPSIDE_FIRST'
    gaps=gap_diagnostics(rows,CYCLE,True)
    assert gaps['intervals'][0]['independent_feed_loss_or_halt_proof'] is False


def test_no_gap_sensitivity_does_not_rescue_incomplete_overnight_or_unknown_path():
    s=state([tick(),tick('1.2','2026-05-27T13:36:00Z','b')],complete=False)
    assert all(m['censored'] for m in outcome_sensitivity(s,CYCLE,CONFIG,None)['forward'])
    rows=[tick(when='2026-05-26T23:59:00Z'),tick('1.2','2026-05-27T08:01:00Z','b')]
    assert outcome_sensitivity(state(rows),CYCLE,CONFIG,None)['barriers'][0]['outcome']=='CENSORED'
    rows=[tick(),tick('1.1','2026-05-27T13:32:00Z','u',conditions_json='[999]'),tick('1.2','2026-05-27T13:36:00Z','b')]
    r=outcome_sensitivity(state(rows),CYCLE,CONFIG,None)
    assert r['forward'][0]['censored'] and 'UNKNOWN_PATH_PRICE_EVIDENCE' in r['forward'][0]['flags']


def original_coverage(tmp_path):
    p=tmp_path/'original.json'
    write_json(p,{'results':[{'sip_timestamp':10}],'next_url':'https://api.massive.com/v3/trades/TEST?cursor=next'})
    return {'request':{'kind':'trades','ticker':'TEST','start_ns':0,'end_ns':100},'pages':[{'path':str(p),'sha256':file_hash(p),'rows':1}],
            'raw_rows':1,'complete':False,'error':'WINDOW_PAGE_BUDGET'}


class Client:
    def __init__(self,root,body=None,error=None):
        self.root=root;self.body=body;self.error=error;self.ledger={'pages':0};self.calls=[]
    def get(self,path):
        self.calls.append(path)
        if self.error:raise APIError(self.error)
        p=self.root/'tail.json';write_json(p,self.body)
        self.ledger['pages']+=1
        return self.body,{'path':str(p),'sha256':file_hash(p)}


def test_repair_only_terminal_cursor_can_mark_complete_and_preserves_prefix(tmp_path):
    original=original_coverage(tmp_path);before=deepcopy(original)
    client=Client(tmp_path,{'results':[{'sip_timestamp':20}]})
    repaired=repair_window(client,original,tmp_path/'repair',10)
    assert repaired['complete'] and len(repaired['pages'])==2 and repaired['raw_rows']==2
    assert original==before and len(client.calls)==1
    assert repair_window(client,original,tmp_path/'repair',10)==repaired
    assert len(client.calls)==1


@pytest.mark.parametrize('kind',['budget','http','nonmonotone'])
def test_partial_repair_never_silently_completes(tmp_path,kind):
    original=original_coverage(tmp_path)
    client=Client(tmp_path,{'results':[{'sip_timestamp':5}],'next_url':'https://api.massive.com/v3/trades/TEST?cursor=more'})
    if kind=='budget':client.ledger['pages']=10
    if kind=='http':client.error='HTTP_500'
    repaired=repair_window(client,original,tmp_path/'repair',10)
    assert not repaired['complete'] and repaired['error']
    assert repaired['raw_rows']==1
