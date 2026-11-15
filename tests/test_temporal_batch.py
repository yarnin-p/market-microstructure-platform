from copy import deepcopy
import pytest
from market_lab.temporal_batch import batch_view,analysis_rows


def source():
    return {'calendar':[{'cycle_id':str(i),'split_group':'EXPLORATION','execute_in_initial_batch':i<10} for i in range(30)],
        'selected':[{'cycle_id':str(i),'joint_sampling_weight':7,'execute_in_initial_batch':i<10} for i in range(30)]}


def test_batch_two_preserves_source_order_members_and_weights():
    s=source();before=deepcopy(s);p=batch_view(s,{'batch_index':2})
    assert s==before
    assert [c['cycle_id'] for c in p['calendar'][:10]]==[str(i) for i in range(10,20)]
    assert [r['cycle_id'] for r in p['selected'] if r['execute_in_initial_batch']]==[str(i) for i in range(10,20)]
    assert all(r['joint_sampling_weight']==7 for r in p['selected'])


def test_final_batch_and_holdout_cannot_be_selected():
    with pytest.raises(ValueError):batch_view(source(),{'batch_index':3})
    s=source();s['calendar'][15]['split_group']='HOLDOUT'
    with pytest.raises(ValueError):batch_view(s,{'batch_index':2})


def test_analysis_weights_are_separate_and_follow_actual_month_allocation():
    rows=[{'cycle_id':'2026-06-12','sampling_weight':4,'joint_sampling_weight':28}]
    derived=analysis_rows(rows,[{'cycle_id':f'2026-06-{i}'} for i in range(3)],[{'month':'2026-06','population_N':14}])
    assert rows[0]['joint_sampling_weight']==28
    assert derived[0]['joint_sampling_weight']==pytest.approx(4*14/3)
    assert derived[0]['original_joint_sampling_weight']==28


def test_metric_keeps_missing_denominators_and_clusters_repeated_security():
    from scripts.finalize_temporal_batch import metric
    rows=[{'cycle_id':d,'security_id':'same','joint_sampling_weight':w} for d,w in [('d1',2),('d2',1),('d3',4)]]
    result=metric(rows,[.1,-.1,None])
    assert result['initial_n']==3 and result['missing_n']==1
    assert result['cluster_sensitivity']['ratio']==pytest.approx(.1/3)
    assert result['cluster_sensitivity']['security_clusters']==1
    assert result['cluster_sensitivity']['confidence_interval'] is None


def test_cumulative_date_weights_do_not_pool_development():
    calendar=[{'cycle_id':f'2026-06-{i}'} for i in range(5)]
    rows=[{'cycle_id':'2026-06-1','sampling_weight':2,'joint_sampling_weight':14}]
    result=analysis_rows(rows,calendar,[{'month':'2026-06','population_N':14}])
    assert result[0]['joint_sampling_weight']==pytest.approx(5.6)
