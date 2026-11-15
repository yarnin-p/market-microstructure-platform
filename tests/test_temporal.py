import json
from pathlib import Path
from copy import deepcopy

import pytest

from market_lab.temporal_design import allocate,temporal_sample
from market_lab.temporal_statistics import design_incidence,clustered_ratio,crossed_cluster_bootstrap
from market_lab.temporal_client import TemporalClient
from market_lab.api import APIError
from market_lab.nbbo_probe import BudgetStop

CONFIG=json.loads(Path('configs/task-004-temporal-v1.json').read_text())


def calendar():
    rows=[]
    for month,N in [('06',14),('07',22),('08',21),('09',13)]:
        rows += [{'cycle_id':f'2026-{month}-{i+1:02}','split_group':'EXPLORATION'} for i in range(N)]
    rows += [{'cycle_id':'holdout','split_group':'HOLDOUT'}]
    return rows


def test_proportional_date_design_and_distributed_first_batch_are_reproducible():
    plan,strata=temporal_sample(calendar(),set(),CONFIG)
    again,_=temporal_sample(calendar(),set(),CONFIG)
    assert plan==again and len({r['cycle_id'] for r in plan})==30
    assert [s['plan_n'] for s in strata]==[6,9,9,6]
    assert [s['batch_n'] for s in strata]==[2,3,3,2]
    assert len([r for r in plan if r['execute_in_initial_batch']])==10
    assert all(r['execute_in_initial_batch'] for r in plan[:10])
    assert not any(r['execute_in_initial_batch'] for r in plan[10:])
    for r in plan:
        assert r['date_plan_probability']*r['date_batch_conditional_probability']==pytest.approx(r['date_inclusion_probability'])
        assert r['split_group']=='EXPLORATION'


def test_invalid_date_population_and_census_allocation():
    with pytest.raises(ValueError):temporal_sample(calendar()[:-2],set(),CONFIG)
    assert allocate({'a':2,'b':3},5)=={'a':2,'b':3}
    with pytest.raises(ValueError):allocate({'a':2},3)


def test_unplanned_endpoint_is_rejected_before_any_http(tmp_path):
    c=TemporalClient(tmp_path,CONFIG,{'TEST'},key='not-a-real-key')
    with pytest.raises(APIError,match='UNPLANNED'):c.get('/v3/trades/OTHER')
    assert not c.ledger['attempts']


def test_hard_request_budget_has_no_network_side_effect(tmp_path):
    c=TemporalClient(tmp_path,{**CONFIG,'max_requests':0},{'TEST'},key='fake')
    with pytest.raises(BudgetStop,match='ATTEMPT'):c.get('/v3/trades/TEST')
    assert not c.ledger['attempts']


def test_offline_cache_miss_is_explicit_not_empty_success(tmp_path):
    c=TemporalClient(tmp_path,CONFIG,{'TEST'},offline=True)
    with pytest.raises(APIError,match='OFFLINE'):c.get('/v3/trades/TEST')


def test_two_way_cluster_keys_and_negative_variance_are_explicit():
    rows=[{'cycle_id':'d1','security_id':'same','v':0,'joint_sampling_weight':1},
          {'cycle_id':'d2','security_id':'same','v':1,'joint_sampling_weight':1},
          {'cycle_id':'d1','security_id':'other','v':1,'joint_sampling_weight':2}]
    result=clustered_ratio(rows,'v')
    assert result['date_clusters']==2 and result['security_clusters']==2
    assert result['ratio']==pytest.approx(.75) and result['confidence_interval'] is None


def design_rows():
    rows=[]
    for day in ['2026-06-01','2026-06-02']:
        for st in ['proxy','other']:
            for i in range(2):rows.append({'cycle_id':day,'security_id':str(i),'stratum':st,'population_N':4,'sample_n':2,
                'sampling_weight':2,'date_inclusion_probability':.5,'joint_sampling_weight':4,
                'complete_observed_sessions':True,'event_id':'event' if i==0 else None})
    return rows


def test_two_stage_variance_keeps_zero_events_and_suppresses_nonresponse():
    rows=design_rows();strata=[{'month':'2026-06','population_N':4,'batch_n':2}]
    result=design_incidence(rows,strata)
    assert result['weighted_incidence']==.5 and result['selected_denominator']==8
    assert result['two_stage_taylor_se']==pytest.approx(.125)
    rows[0]['complete_observed_sessions']=False
    assert design_incidence(rows,strata)['two_stage_taylor_se'] is None


def test_crossed_cluster_resampling_is_seeded_and_not_labeled_iid_ci():
    a=crossed_cluster_bootstrap(design_rows(),30,7)
    assert a==crossed_cluster_bootstrap(design_rows(),30,7)
    assert a['replicates']>0 and 'NOT_CALIBRATED_CI' in a['status']


def test_policy_means_use_joint_date_security_weights_and_keep_missing_buckets():
    from scripts.finalize_temporal import weighted_policies
    def row(weight,value,status='CONFIRMED'):
        return {'condition_policy':'HIGH_LOW_ONLY','stratum':'PROXY_FLOAT_IN_RANGE','initial_session':'RTH','policy':'C0_FROZEN',
            'joint_sampling_weight':weight,'sampling_weight':1,'signal':{'status':status},
            'common_landmarks':[{'landmark_minutes':m,'status':'OBSERVED' if value is not None else 'UNCONFIRMED',
                'return':str(value) if value is not None else None} for m in [5,15,30,60]]}
    rows=[row(10,.1),row(1,-.1)]
    panel=next(g for g in weighted_policies(rows) if g['stratum']==g['initial_session']=='ALL')
    assert panel['common_landmarks']['5']['conditional_weighted_mean']==pytest.approx(.9/11)
    rows[1]=row(1,None,'UNCONFIRMED')
    panel=next(g for g in weighted_policies(rows) if g['stratum']==g['initial_session']=='ALL')
    assert panel['joint_weighted_confirmation_fraction']==pytest.approx(10/11)
    assert panel['common_landmarks']['5']['joint_design_weight_buckets']=={'OBSERVED':10,'UNCONFIRMED':1}
