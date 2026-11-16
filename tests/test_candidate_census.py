import json
from decimal import Decimal
import pytest
from market_lab import candidate_census as c
from market_lab.calendar import cycles
from market_lab.tick_replay import bounds

CYCLE=cycles('2026-11-13',1)[0]


def test_cache_highs_cover_ah_pre_rth_without_future_or_blind_interval():
    a,ah,pre,opened,end=bounds(CYCLE)
    rows=[{'sip_timestamp':t,'price':p}for t,p in [(a,'10'),(a+1,'1.2'),(ah,'20'),(pre,'1.3'),(opened,'1.4'),(end,'1.5'),(end+1,'100')]]
    bars=c.derived_minutes(rows,CYCLE)
    assert [Decimal(r['h'])for r in bars]==[Decimal('1.2'),Decimal('1.3'),Decimal('1.4'),Decimal('1.5')]


def test_vendor_minutes_include_past_padding_but_never_future_end_minute():
    a,ah,pre,opened,end=(v//1000000 for v in bounds(CYCLE))
    assert c.bar_overlaps_observed(a-60000,CYCLE)
    assert c.bar_overlaps_observed(pre-60000,CYCLE)
    assert c.bar_overlaps_observed(end-60000,CYCLE)
    assert not c.bar_overlaps_observed(ah,CYCLE)
    assert not c.bar_overlaps_observed(end,CYCLE)


def test_aggregate_validation_preserves_decimals_and_rejects_truncation():
    assert c.parse_bars('t,h\n1794580200000,0.123456789012\n')[0]['h']=='0.123456789012'
    with pytest.raises(ValueError):c.parse_bars('[truncated]')
    with pytest.raises(AssertionError):c.parse_bars('t,h\n2,1\n1,2\n')
    with pytest.raises(AssertionError):c.parse_bars('t,h\n1,2\n1,3\n')


def test_full_universe_tick_resume_is_paused_without_candidate_authorization(tmp_path,monkeypatch):
    from market_lab import census
    monkeypatch.setattr(census,'ROOT',tmp_path)
    (tmp_path/'acquisition-paused.json').write_text('{}')
    with pytest.raises(RuntimeError,match='USER_HALTED'):census.broker_state()


def test_tick_broker_returns_only_hash_bound_candidate_whitelist(tmp_path,monkeypatch):
    from market_lab import census
    from market_lab.storage import write_json,file_hash
    monkeypatch.chdir(tmp_path)
    old=tmp_path/'old';old.mkdir();monkeypatch.setattr(census,'ROOT',old)
    write_json(old/'config.json',{'cycle':CYCLE,'max_local_storage_bytes':64*2**30})
    write_json(old/'queue.json',[{'ticker':'A'},{'ticker':'B'}])
    p=tmp_path/'data/runs/test/candidates.json';write_json(p,[{'ticker':'B'}])
    write_json(old/'candidate-tick-authorization.json',{'replacement_run':'test','candidate_sha256':file_hash(p),'tickers':['B']})
    write_json(tmp_path/'configs/census-20261113-transport-v2.json',{'retry_small_page_tickers':[]})
    state=census.broker_state()
    assert state['tickers']==['B'] and state['population_total']==1


def test_negative_aggregate_is_not_a_verified_tick_zero(tmp_path,monkeypatch):
    from market_lab.storage import write_json
    monkeypatch.setattr(c,'ROOT',tmp_path/'run');monkeypatch.setattr(c,'REPORT',tmp_path/'report')
    queue=tmp_path/'queue.json'
    write_json(queue,[{'ticker':t,'security_id':t,'previous_rth_close':'1','float_proxy_stratum':'OTHER_EXCHANGE_PRICE_ELIGIBLE'}for t in ['A','B']])
    write_json(c.ROOT/'config.json',{'cycle':CYCLE,'queue_source':{'path':str(queue)}})
    for ticker,h in [('A','1.2'),('B','1.0')]:
        write_json(c.ROOT/'aggregates'/f'{ticker}.json',{'complete':True,'source_kind':'PROVIDER_REST_MINUTE_HIGH','bars':[{'t':bounds(CYCLE)[3]//1000000,'h':h}]})
    monkeypatch.setattr(c,'validated_cached',lambda *args:([],[],False))
    result=c.screen()
    assert result['price_candidates']==1 and result['candidates_requiring_additional_ticks']==1
    assert result['screen_negative']==1 and result['tick_acquisition_not_yet_authorized']
    assert not (tmp_path/'candidate-tick-authorization.json').exists()
