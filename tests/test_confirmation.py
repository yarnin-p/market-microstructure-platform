import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from market_lab.confirmation import (bid_confirmation, causal_quote, confirmation_outcomes,
    execution_mark_estimates, signal_result, trade_confirmation)
from market_lab.confirmation_pilot import coverage_for, stats, summarize
from market_lab.tick_replay import SECOND
from test_m2 import CYCLE, CONFIG as OLD_CONFIG, tick

CONFIG = {**OLD_CONFIG, **json.loads(Path('configs/task-003-confirmation-v1.json').read_text())}
T = tick()['sip_timestamp']
INITIAL = {'event_id': 'initial', 'event_timestamp': T, 'record_id': 'a', 'threshold_price': '1.1',
           'touch_price': '1.1', 'previous_rth_close': '1', 'security_id': 'id', 'ticker': 'TEST',
           'cycle_id': CYCLE['cycle_id'], 'sample': 'SYSTEMATIC', 'session': 'RTH',
           'first_touch_status': 'OBSERVED_SESSIONS_FIRST_VERIFIED'}


def trade(second, price='1.1', ident=None):
    return tick(price, ident=ident or str(second), sip_timestamp=T + second * SECOND,
                participant_timestamp=T + second * SECOND)


def state(rows, **kw):
    return SimpleNamespace(eligible=rows, complete=True, unknown_times=[], invalidations=[],
                          policy='HIGH_LOW_ONLY', replay=lambda: None, **kw)


def quote(second, bid='1.1', ident=None, **kw):
    return {'record_id': ident or 'q' + str(second), 'sip_timestamp': T + second * SECOND,
            'bid_price': bid, 'ask_price': '1.2', 'bid_size': '100', 'ask_size': '100',
            'normalization_status': 'OK', 'conditions_json': '[]', 'source_json': '{}', **kw}


def cov(end=60):
    return {'complete': True, 'request': {'start_ns': T - 60 * SECOND, 'end_ns': T + end * SECOND}}


def test_c1_counts_touch_but_never_backdates_signal_or_reuses_price():
    s = state([tick(), trade(10, '1.12'), trade(29, '1.15'), trade(30, '1.2')])
    result = trade_confirmation(s, INITIAL, CYCLE, CONFIG, [])
    assert result['signal_timestamp'] == T + 30 * SECOND
    assert result['market_observation_price'] == '1.2'
    assert result['qualifying_span_ns'] == 30 * SECOND


def test_distinct_trade_records_and_minimum_observation_count():
    a = tick()
    s = state([a, a, trade(30, ident='b')])
    assert trade_confirmation(s, INITIAL, CYCLE, CONFIG, [])['status'] == 'UNCONFIRMED'
    assert trade_confirmation(state([a, trade(10), trade(29)]), INITIAL, CYCLE, CONFIG, [])['status'] == 'UNCONFIRMED'


def test_c1_is_counted_persistence_and_has_no_unrequested_60_second_deadline():
    s = state([tick(), trade(10, '.9'), trade(15, '1.2'), trade(120, '1.3')])
    r = trade_confirmation(s, INITIAL, CYCLE, CONFIG, [])
    assert r['signal_timestamp'] == T + 120 * SECOND
    assert r['intervening_subthreshold_trades'] == 1


def test_c1_resets_across_overnight_but_not_premarket_open():
    ah = tick(when='2026-05-26T23:59:59Z')
    pre = tick(when='2026-05-27T08:00:00Z', ident='b')
    pre2 = tick(when='2026-05-27T08:00:01Z', ident='c')
    initial = {**INITIAL, 'event_timestamp': ah['sip_timestamp'], 'session': 'AH'}
    assert trade_confirmation(state([ah, pre, pre2]), initial, CYCLE, CONFIG, [])['status'] == 'UNCONFIRMED'


def test_cancellation_before_confirmation_removes_prior_observation_without_future_leak():
    rows = [tick(), trade(10), trade(30)]
    cancel = {**rows[1], 'sip_timestamp': T + 20 * SECOND, 'correction': 10}
    assert trade_confirmation(state(rows), INITIAL, CYCLE, CONFIG, [cancel])['status'] == 'UNCONFIRMED'
    cancel['sip_timestamp'] = T + 40 * SECOND
    assert trade_confirmation(state(rows), INITIAL, CYCLE, CONFIG, [cancel])['status'] == 'CONFIRMED'


def test_c2_fresh_bid_uses_no_future_quote_and_resets_below_threshold():
    quotes = [quote(i) for i in [0,5,10]]
    s = state([tick(), trade(9, '1.15')])
    r = bid_confirmation(s, INITIAL, CYCLE, CONFIG, quotes, cov())
    assert r['status'] == 'CONFIRMED' and r['signal_timestamp'] == T + 10 * SECOND
    assert r['market_observation_price'] == '1.15' and r['market_price_timestamp'] == T + 9 * SECOND
    broken = [quote(0), quote(5, '1.09'), quote(10), quote(15), quote(20)]
    assert bid_confirmation(s, INITIAL, CYCLE, CONFIG, broken, cov())['signal_timestamp'] == T + 20 * SECOND
    assert causal_quote(quotes + [quote(11, conditions_json='[43]')], T + 10 * SECOND, CONFIG)['status'] == 'OK'


def test_two_far_apart_quotes_do_not_establish_fresh_support_and_repeated_quote_cannot_confirm():
    assert bid_confirmation(state([tick()]), INITIAL, CYCLE, CONFIG, [quote(0), quote(10)], cov())['status'] == 'UNCONFIRMED'
    qs = [quote(i, ident='same') for i in [0,5,10]]
    assert bid_confirmation(state([tick()]), INITIAL, CYCLE, CONFIG, qs, cov())['status'] == 'UNCONFIRMED'


@pytest.mark.parametrize('kw', [{'bid_price':'0'}, {'ask_price':'1.0'}, {'bid_size':'0'}, {'conditions_json':'[43]'}])
def test_invalid_nbbo_never_confirms(kw):
    qs = [quote(i, **kw) for i in [0,5,10]]
    assert bid_confirmation(state([tick()]), INITIAL, CYCLE, CONFIG, qs, cov())['status'] == 'INSUFFICIENT_DATA'


def test_c2_deadline_includes_60_seconds_and_missing_quotes_are_not_negative_returns():
    qs = [quote(i) for i in [50,55,60,61]]
    s = state([tick(), trade(59, '1.3')])
    assert bid_confirmation(s, INITIAL, CYCLE, CONFIG, qs, cov())['signal_timestamp'] == T + 60 * SECOND
    assert bid_confirmation(s, INITIAL, CYCLE, CONFIG, qs, cov(59))['status'] == 'INSUFFICIENT_DATA'
    assert bid_confirmation(s, INITIAL, CYCLE, CONFIG, [], cov())['status'] == 'INSUFFICIENT_DATA'


def test_quote_coverage_union_never_bridges_a_missing_interval():
    intervals = [{'start_ns':0,'end_ns':10,'complete':True}, {'start_ns':11,'end_ns':30,'complete':True}]
    assert not coverage_for(intervals, 1, 30)['complete']
    intervals[1]['start_ns'] = 10
    assert coverage_for(intervals, 1, 30)['complete']


def test_c2_synthetic_mark_excludes_pre_signal_extremes_and_correctly_shifts_horizons():
    # Use a ReplayState for the inherited outcome_sensitivity API.
    from market_lab.replay_methodology import ReplayState
    from test_m2 import OPP
    rows = [tick(), trade(5, '2'), trade(9, '1.1'), trade(311, '1.2')]
    s = ReplayState('HIGH_LOW_ONLY', CYCLE, OPP, CONFIG, {}, True, 'test', rows[-1]['sip_timestamp'])
    for row in rows:
        s.feed(row)
    signal = signal_result('C2','CONFIRMED','test',T+11*SECOND,'1.1', trade_record_id='9',
        market_price_timestamp=T+9*SECOND, market_price_source='{}')
    out = confirmation_outcomes(s, INITIAL, signal, CYCLE, CONFIG, [])
    assert out['forward'][0]['target_ns'] == T + 311 * SECOND
    assert float(out['observed_mfe']) == pytest.approx(1.2/1.1-1)
    assert out['mfe_ns'] > signal['signal_timestamp']
    assert out['window_start_ns'] == signal['signal_timestamp']


def test_own_signal_quote_estimates_do_not_invent_exit_evidence():
    signal = signal_result('C0','CONFIRMED','touch',T,'1.1')
    outcome = {'forward':[{'horizon':'5m','target_ns':T+300*SECOND,'censored':False}]}
    result = execution_mark_estimates(signal, outcome, [quote(0)], cov(), CONFIG)
    assert result['executable_pnl'] is None
    assert result['marks'][0]['ask_to_bid_mark_return'] is None


def test_c2_pre_touch_quote_does_not_backdate_support_clock():
    qs = [quote(-4), quote(1), quote(6), quote(11)]
    result = bid_confirmation(state([tick()]), INITIAL, CYCLE, CONFIG, qs, cov())
    assert result['signal_timestamp'] == T + 11*SECOND
    assert result['qualifying_span_ns'] == 11*SECOND


def test_counted_trade_invalidation_after_c1_signal_censors_future_outcome():
    from market_lab.replay_methodology import ReplayState
    from test_m2 import OPP
    rows = [tick(), trade(10), trade(30, '1.2'), trade(330, '1.3')]
    s = ReplayState('HIGH_LOW_ONLY', CYCLE, OPP, CONFIG, {}, True, 'test', rows[-1]['sip_timestamp'])
    for row in rows:
        s.feed(row)
    notice = {**rows[1], 'sip_timestamp': T+40*SECOND, 'correction':10}
    signal = trade_confirmation(s, INITIAL, CYCLE, CONFIG, [notice])
    assert signal['status'] == 'CONFIRMED'
    result = confirmation_outcomes(s, INITIAL, signal, CYCLE, CONFIG, [notice])
    assert result['forward'][0]['censored']
    assert 'TOUCH_LATER_INVALIDATED' in result['forward'][0]['flags']


def test_empty_distributions_are_undefined():
    assert stats([])['median'] is None
    assert summarize([])['weighted_confirmation_fraction'] is None


def test_unconfirmed_and_missing_rows_stay_in_weighted_initial_denominator():
    def row(status, weight):
        return {'sampling_weight': weight, 'signal': {'status': status, 'reason': 'test'},
                'confirmation_delay_seconds': None, 'market_price_change_while_waiting': None,
                'causal_entry_nbbo': {'status':'MISSING'}, 'outcomes': [],
                'confirmed_by_minutes_from_initial_touch': {str(m):False for m in [5,15,30,60]}}
    result = summarize([row('CONFIRMED', 2), row('UNCONFIRMED', 10), row('INSUFFICIENT_DATA', 1)])
    assert result['initial_events'] == 3
    assert result['weighted_confirmation_fraction'] == pytest.approx(2/13)
    assert sum(result['forward']['5m']['population_buckets'].values()) == 3
    assert result['forward']['5m']['observed_return_distribution']['n'] == 0
    assert sum(result['barriers']['0.03/0.03']['buckets'].values()) == 3


def test_weighted_conditional_means_and_gap_panels_retain_nonconfirmations():
    from scripts.analyze_confirmation import gap_panel, weighted_mean
    assert weighted_mean([(1,1),(0,3)]) == pytest.approx(.25)
    assert weighted_mean([(None,9)]) is None
    result = gap_panel([{'signal':{'status':'UNCONFIRMED'},'outcomes':[],'sampling_weight':2}], 'NO_MECHANICAL_GAP')
    assert result['forward']['5m']['initial_population_buckets'] == {'UNCONFIRMED':1}
    assert result['barriers']['0.03/0.03'] == {'UNCONFIRMED':1}
