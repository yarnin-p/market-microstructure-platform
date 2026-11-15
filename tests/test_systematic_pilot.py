import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from market_lab.systematic_pilot import sample_frame,float_evidence,nbbo_context,BudgetClient
from market_lab.api import APIError
from market_lab.systematic_report import metrics
from test_m2 import tick,CONFIG as OLD

CONFIG=json.loads(Path('configs/task-002-2-systematic-v1.json').read_text())


def frame():
    return [{'cycle_id':c,'security_id':str(i),'ticker':str(i),'stratum':s,'future_return':999}
            for c in ['day1','day2'] for s,span in [('PROXY_FLOAT_IN_RANGE',range(20)),('OTHER_EXCHANGE_PRICE_ELIGIBLE',range(20,50))] for i in span]


def test_daily_stratified_probabilities_and_weights():
    selected,strata=sample_frame(frame(),CONFIG)
    assert len(selected)==48
    assert len({(r['cycle_id'],r['security_id']) for r in selected})==48
    for group in strata:
        pool=[r for r in selected if r['cycle_id']==group['cycle_id'] and r['stratum']==group['stratum']]
        assert len(pool)==12
        assert sum(r['sampling_weight'] for r in pool)==pytest.approx(group['population_N'])
        assert all(r['selection_probability']==12/group['population_N'] for r in pool)


def test_later_cycle_candidates_and_outcome_independence():
    f=frame()
    for r in f:
        if r['cycle_id']=='day2':r['security_id']='new_'+r['security_id']
    a,_=sample_frame(f,CONFIG)
    for r in f:r['future_return']=-999
    b,_=sample_frame(list(reversed(f)),CONFIG)
    assert [(r['cycle_id'],r['security_id']) for r in a]==[(r['cycle_id'],r['security_id']) for r in b]
    assert all(r['security_id'].startswith('new_') for r in a if r['cycle_id']=='day2')


def test_small_stratum_is_census_without_duplicate_topup():
    f=frame()[:3]
    a,_=sample_frame(f,CONFIG)
    assert len(a)==3 and all(r['selection_probability']==1 and r['sampling_weight']==1 for r in a)


@pytest.mark.parametrize('value,status',[(100000,'ELIGIBLE'),(15000000,'ELIGIBLE'),(99999,'INELIGIBLE'),(None,'UNRESOLVED')])
def test_identity_resolved_current_float_not_outstanding(value,status):
    source={'retrieved_at':'now'}
    ev=float_evidence({'ticker':'OLD','security_id':'FIGI'},{'FIGI':[{'ticker':'NEW','share_class_figi':'FIGI','_source':source}]},
                      {'NEW':[{'ticker':'NEW','free_float':value,'shares_outstanding':1_000_000,'_source':source}]})
    assert ev['status']==status and ev['original_ticker']=='OLD' and ev['resolved_ticker']=='NEW'
    assert not ev['is_verified_pit']


def test_missing_identity_kept_unresolved():
    e=float_evidence({'ticker':'OLD','security_id':'id'},{},{'OLD':[{'free_float':100000}]})
    assert e['status']=='UNRESOLVED' and e['value'] is None


def test_above_ask_retained_as_context():
    event={'event_timestamp':10000000000,'touch_price':'1.50'}
    quote={'normalization_status':'OK','sip_timestamp':9999999999,'bid_price':'1.48','ask_price':'1.49','conditions_json':'[]','source_json':'{}'}
    context=nbbo_context([quote],event,CONFIG,True)
    assert context['trade_relation']=='ABOVE_PRECEDING_ASK'
    assert not context['trade_discarded_for_nbbo_relation'] and not context['used_for_trigger']


def test_storage_budget_stops_before_request(tmp_path):
    client=BudgetClient(tmp_path/'raw',{**CONFIG,'max_storage_bytes':1},key='fake')
    with pytest.raises(APIError,match='STORAGE_BUDGET'):client.get('/v3/trades/TEST')
    assert not client.ledger['attempts']


def test_empty_statistics_are_undefined_not_zero_return():
    result=metrics([])
    assert result['forward']['5m']['mean'] is None and result['forward']['5m']['events']==0

def test_prepare_retains_unmapped_provider_float_before_sampling(tmp_path,monkeypatch):
    import market_lab.systematic_pilot as module
    from market_lab.storage import write_json
    monkeypatch.chdir(tmp_path)
    calendar=[{'cycle_id':f'day{i:02}','split_group':'EXPLORATION'} for i in range(10)]
    write_json(Path('data/runs',CONFIG['source_m1_run'],'calendar.json'),calendar)
    write_json(Path('data/sec-pilot-20261115-v2/results-reviewed-v1.json'),{'results':[]})
    row={k+'_status':'ELIGIBLE' for k in ['exchange','price','type','identity','currency','action']}
    row.update(change_status='NO_CHANGE_OBSERVED',security_id='id',ticker='T',previous_rth_close=1,record_id='m1')
    monkeypatch.setattr(module,'source_rows',lambda *args:([row],{'path':'historical','sha256':'hash'}))
    source={'retrieved_at':'2026-11-15T00:00:00Z'}
    def references(client,path,params):
        if path.endswith('tickers'):return [{'ticker':'T','share_class_figi':'id','_source':source}],[source],None
        if path.endswith('float'):return [{'ticker':'T','free_float':100000,'_source':source},{'free_float':3950100,'_source':source}],[source],None
        return [{'id':0,'_source':source}],[source],None
    monkeypatch.setattr(module,'reference_pages',references)
    root=tmp_path/'new';root.mkdir()
    result=module.prepare(CONFIG,None,root)
    assert len(result['selected'])==10
    context=json.loads((root/'context.json').read_text())
    assert len(context['unmapped_float_records'])==1
    assert context['unmapped_float_records'][0]['provider_record']['free_float']==3950100
    assert all(o['selection_probability']==1 for o in result['selected'])
