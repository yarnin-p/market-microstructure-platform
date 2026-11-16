from copy import deepcopy
import pytest
from market_lab.temporal_final_batch import batch_view


def fixture():
    source={'calendar':[{'cycle_id':str(i),'split_group':'EXPLORATION'} for i in range(30)],
            'selected':[{'cycle_id':str(i),'security_id':str(j),'sampling_weight':3,'joint_sampling_weight':21} for i in range(30) for j in range(24)]}
    inventory={'calendar':deepcopy(source['calendar'][20:]),'opportunities':deepcopy(source['selected'][480:])}
    return source,inventory,{'batch_index':3,'expected_dates':[str(i) for i in range(20,30)]}


def test_final_batch_uses_exact_inventory_and_never_changes_source_weights():
    source,inventory,config=fixture();before=deepcopy(source)
    view=batch_view(source,inventory,config)
    assert source==before and len([r for r in view['selected'] if r['execute_in_initial_batch']])==240
    assert [c['cycle_id'] for c in view['calendar'][:10]]==config['expected_dates']
    assert all(r['joint_sampling_weight']==21 for r in view['selected'])


@pytest.mark.parametrize('field',['security_id','sampling_weight','joint_sampling_weight'])
def test_changed_inventory_identity_or_weights_is_rejected(field):
    source,inventory,config=fixture();inventory['opportunities'][0][field]='changed'
    with pytest.raises(ValueError,match='opportunities'):batch_view(source,inventory,config)


def test_holdout_or_unexpected_dates_cannot_enter():
    source,inventory,config=fixture();source['calendar'][20]['split_group']='HOLDOUT';inventory['calendar'][0]['split_group']='HOLDOUT'
    with pytest.raises(ValueError,match='Holdout'):batch_view(source,inventory,config)
    source,inventory,config=fixture();config['expected_dates'][0]='different'
    with pytest.raises(ValueError,match='dates'):batch_view(source,inventory,config)


def weighted_fixture():
    dates=[{'cycle_id':f'2026-{month}-{i+1:02}'} for month,n in [('06',6),('07',9),('08',9),('09',6)] for i in range(n)]
    original={'calendar':dates,'selected':[]};rows=[]
    populations={'06':14,'07':22,'08':21,'09':13};initial={'06':2,'07':3,'08':3,'09':2}
    for c in dates:
        month=c['cycle_id'][5:7];p=initial[month]/populations[month]
        for i in range(24):
            r={'cycle_id':c['cycle_id'],'security_id':str(i),'ticker':str(i),'previous_rth_close':'1','m1_record_id':'m1',
               'source_m1':{'sha256':'fixed'},'float_proxy':{'status':'ELIGIBLE'},'stratum':'PROXY_FLOAT_IN_RANGE' if i<12 else 'OTHER_EXCHANGE_PRICE_ELIGIBLE',
               'population_N':24,'sample_n':12,'sampling_weight':2,'selection_probability':.5,'date_inclusion_probability':p,
               'joint_sampling_weight':2/p,'joint_inclusion_probability':.5*p}
            original['selected'].append(deepcopy(r));rows.append({**r,'condition_policy':'HIGH_LOW_ONLY'})
    config={'date_probabilities':{'2026-06':[6,14],'2026-07':[9,22],'2026-08':[9,21],'2026-09':[6,13]}}
    return rows,original,config


def test_full30_uses_original_plan_probabilities_not_initial_batch_weights():
    from scripts.finalize_temporal_final import full_weights
    rows,original,config=weighted_fixture();before=deepcopy(rows)
    sidecar=full_weights(rows,original,config)
    assert len(sidecar)==720 and rows==before
    june=next(r for r in sidecar if r['cycle_id'].startswith('2026-06'))
    assert june['analysis_date_probability']==pytest.approx(6/14)
    assert june['analysis_joint_weight']==pytest.approx(14/3)
    assert june['original_joint_weight']==14
    assert june['analysis_joint_weight']!=june['original_joint_weight']
    assert june['analysis_weight_numerator']/june['analysis_weight_denominator']==pytest.approx(june['analysis_joint_weight'])


def test_cumulative_duplicates_or_source_weight_changes_cannot_be_hidden():
    from scripts.finalize_temporal_final import full_weights
    rows,original,config=weighted_fixture();rows[-1]=deepcopy(rows[0])
    with pytest.raises(ValueError,match='reconciliation'):full_weights(rows,original,config)
    rows,original,config=weighted_fixture();rows[0]['sampling_weight']=999
    with pytest.raises(ValueError,match='weight changed'):full_weights(rows,original,config)


def test_float_stratum_contrast_has_separate_cluster_scores_not_causal_claim():
    from scripts.finalize_temporal_final import stratum_contrast
    rows=[{'cycle_id':d,'security_id':str(i),'stratum':st,'joint_sampling_weight':w,'event_id':'event' if y else None,
           'observed_opportunity_eligible':True} for i,(d,st,w,y) in enumerate([
           ('d1','PROXY_FLOAT_IN_RANGE',2,1),('d2','PROXY_FLOAT_IN_RANGE',1,0),
           ('d1','OTHER_EXCHANGE_PRICE_ELIGIBLE',1,1),('d2','OTHER_EXCHANGE_PRICE_ELIGIBLE',3,0)])]
    result=stratum_contrast(rows)
    assert result['proxy_minus_complementary']==pytest.approx(2/3-1/4)
    assert result['confidence_interval'] is None


@pytest.mark.parametrize('same_sip',[False,True])
def test_raw_audit_checks_chronological_first_hit_and_same_sip_ambiguity(tmp_path,monkeypatch,same_sip):
    import json
    from types import SimpleNamespace
    from scripts import finalize_temporal_final as module
    from market_lab.storage import digest,file_hash,write_json
    from test_m2 import tick,CYCLE
    t=tick()['sip_timestamp'];bodies=[{'sip_timestamp':t,'price':1.1,'size':100},
        {'sip_timestamp':t+10_000_000_000,'price':1.0,'size':100},
        {'sip_timestamp':t+(10 if same_sip else 20)*1_000_000_000,'price':1.2,'size':100}]
    path=tmp_path/'raw.json';write_json(path,{'results':bodies})
    rows=[tick(str(b['price']),ident=str(i),sip_timestamp=b['sip_timestamp'],record_id=digest(b),
        source_json=json.dumps({'path':str(path),'sha256':file_hash(path),'row':i})) for i,b in enumerate(bodies)]
    event={'event_id':'e','record_id':rows[0]['record_id'],'touch_price':'1.1','ticker':'T','cycle_id':CYCLE['cycle_id'],
           'security_id':'id','condition_policy':'HIGH_LOW_ONLY'}
    category='AMBIGUOUS_SAME_SIP' if same_sip else 'DOWNSIDE_FIRST'
    outcome={'event_id':'e','cycle_id':CYCLE['cycle_id'],'security_id':'id','condition_policy':'HIGH_LOW_ONLY','gap_seconds':None,
             'barriers':[{'outcome':category,'observed_direction':category,'first_passage_ns':t+10_000_000_000}]}
    original_read=module.read
    def read(p):
        name=str(p)
        if name.endswith('selection.json'):return {'config':{},'selected':[{'cycle_id':CYCLE['cycle_id'],'security_id':'id'}],'calendar':[CYCLE]}
        if name.endswith('ingest.json'):return {'paths':[],'coverage_path':'coverage'}
        if name.endswith('context.json'):return {'conditions':[]}
        if name=='coverage':return {}
        return original_read(p)
    monkeypatch.setattr(module,'read',read);monkeypatch.setattr(module,'runtime_config',lambda c:{})
    monkeypatch.setattr(module,'replay',lambda *a:({'HIGH_LOW_ONLY':SimpleNamespace(event=event,eligible=rows,unknown_times=[])},0,{}))
    monkeypatch.setattr(module,'iter_normalized',lambda p:iter([]))
    audit=module.barrier_audit({'events':[event],'first_outcomes':[outcome]},{CYCLE['cycle_id']:'mock'}, {})
    assert audit['examples'][0]['chronological_first_hit_verified']
    assert audit['examples'][0]['earlier_eligible_barrier_hits']==0
    outcome['barriers'][0]['first_passage_ns']+=1
    with pytest.raises(AssertionError):module.barrier_audit({'events':[event],'first_outcomes':[outcome]},{CYCLE['cycle_id']:'mock'}, {})


def test_canonical_publication_uses_derived_weights_without_overwriting_source(tmp_path):
    from scripts.publish_temporal_final import correct_batch_views
    from market_lab.storage import write_json,file_hash
    from market_lab.m2_pilot import event_table
    from market_lab.temporal_design import read
    write_json(tmp_path/'stratum-incidence.json',{'inherited_initial_batch_weights':True})
    write_json(tmp_path/'cohort_metrics.json',[{'inherited_initial_batch_weights':True}])
    event_table(tmp_path/'cohort_metrics.parquet',[{'inherited_initial_batch_weights':True}])
    write_json(tmp_path/'statistical-preparation.json',{'strata':{'proxy':{'weighted_incidence':.2}}})
    correct=[{'joint_weighted_confirmation_fraction':.5}]
    write_json(tmp_path/'design-weighted-policy-metrics.json',correct)
    write_json(tmp_path/'event-level-results.json',{'source_joint_sampling_weight':14})
    before=file_hash(tmp_path/'event-level-results.json')
    correct_batch_views(tmp_path)
    assert read(tmp_path/'cohort_metrics.json')==correct
    assert read(tmp_path/'stratum-incidence.json')=={'proxy':{'weighted_incidence':.2}}
    assert read(tmp_path/'original-weight-stratum-incidence.json')['inherited_initial_batch_weights']
    assert file_hash(tmp_path/'event-level-results.json')==before
    original_hash=file_hash(tmp_path/'original-weight-cohort_metrics.json')
    correct_batch_views(tmp_path)
    assert file_hash(tmp_path/'original-weight-cohort_metrics.json')==original_hash
