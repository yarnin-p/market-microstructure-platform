"""Execute only the next frozen temporal block; never resample or alter source evidence."""
import argparse
import copy
import json
import fcntl
from collections import Counter
from pathlib import Path

from .api import load_key
from .storage import file_hash,write_json
from .temporal_design import read,protected_hashes
from . import temporal_pilot as pilot
from .temporal_statistics import design_incidence,clustered_ratio,crossed_cluster_bootstrap
from .m2_report import records

CONFIG='configs/task-004-1-batch2-v1.json'


def batch_view(source,config):
    if config['batch_index']!=2:raise ValueError('Only batch 2 authorized')
    dates=source['calendar'][10:20]
    if len(dates)!=10 or any(c['split_group']!='EXPLORATION' for c in dates):raise ValueError('Invalid frozen batch')
    active={c['cycle_id'] for c in dates}
    plan=copy.deepcopy(source)
    plan['config']=config
    plan['calendar']=[*plan['calendar'][10:20],*plan['calendar'][:10],*plan['calendar'][20:]]
    for c in plan['calendar']:c['execute_in_initial_batch']=c['cycle_id'] in active
    for r in plan['selected']:r['execute_in_initial_batch']=r['cycle_id'] in active
    return plan


def prepare(config):
    root=Path('data/runs',config['run_id']);source=Path('data/runs',config['source_temporal_run'])
    original=read(source/'selection.json')
    assert file_hash(source/'selection.json')==read(source/'selection.sha256.json')['sha256']
    assert read(Path('reports',config['source_temporal_run'],'validation.json'))['status']=='PASS'
    plan=batch_view(original,config)
    if (root/'selection.json').exists():
        assert read(root/'selection.json')==plan
        assert read(root/'source-selection.json')==original
        return root,plan
    assert not root.exists(),'Run directory must be new'
    root.mkdir(parents=True)
    write_json(root/'source-selection.json',original)
    write_json(root/'selection.json',plan)
    write_json(root/'selection.sha256.json',{'sha256':file_hash(root/'selection.json')})
    write_json(root/'context.json',read(source/'context.json'))
    protocol={'frozen_before_acquisition':True,'source_selection_path':str(source/'selection.json'),
        'source_selection_sha256':file_hash(source/'selection.json'),'batch_positions':[11,20],
        'dates':[c['cycle_id'] for c in plan['calendar'][:10]],'budget':config,
        'estimands':['first-touch incidence','incidence by float stratum','conditional forward continuation',
            'first-passage outcome buckets','confirmation incidence on initial risk set','paired common-landmark differences versus C0','censoring and missingness'],
        'original_weights':'Preserved byte-for-value in selected records; original probabilities describe batch 1 allocation.',
        'analysis_weights':'Separate derived weights N_month / observed planned dates in month times original security sampling_weight. Batch2 allocation 3/2/2/3; cumulative20 allocation5/5/5/5. No source fields overwritten.',
        'uncertainty':'Two-stage finite-population Taylor incidence SE with full response only; date/security crossed cluster score sensitivity for other estimands; month-stratified date and globally repeated-security bootstrap for incidence. No iid event intervals, calibrated CI or significance claims.',
        'missingness':'Retain all selected opportunities and initial events; conditional means report observed denominators; unknown never a zero.',
        'development':'Separate descriptive comparison; never pooled into temporal inference',
        'batch3':'NOT_ACQUIRED_NOT_ANALYZED','holdout':'UNTOUCHED'}
    write_json(root/'statistical-protocol.json',protocol)
    write_json(root/'protected.json',protected_hashes(config['run_id']))
    return root,plan


def analysis_rows(rows,calendar,date_strata):
    counts=Counter(c['cycle_id'][:7] for c in calendar)
    populations={s['month']:s['population_N'] for s in date_strata}
    # Derived views only; immutable source opportunities retain every original weight.
    return [{**r,'original_joint_sampling_weight':r['joint_sampling_weight'],
        'date_inclusion_probability':counts[r['cycle_id'][:7]]/populations[r['cycle_id'][:7]],
        'joint_sampling_weight':r['sampling_weight']*populations[r['cycle_id'][:7]]/counts[r['cycle_id'][:7]]} for r in rows]


def statistics(rows,calendar,plan,config):
    rr=analysis_rows(rows,calendar,plan['date_strata']);counts=Counter(c['cycle_id'][:7] for c in calendar)
    strata=[{**s,'batch_n':counts[s['month']]} for s in plan['date_strata']]
    return {'incidence':design_incidence(rr,strata),'strata':{s:design_incidence([r for r in rr if r['stratum']==s],strata) for s in config['strata']},
        'cluster_sensitivity':clustered_ratio([{**r,'value':float(bool(r['event_id'])) if r['observed_opportunity_eligible'] else None} for r in rr],'value'),
        'month_date_crossed_security_resampling':crossed_cluster_bootstrap(rr,config['bootstrap_replicates'],config['bootstrap_seed']),
        'weight_definition':'Derived batch-specific month/date inclusion probability; original frozen weights retained in event-level outputs',
        'significance_claim':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','acquire','analyze','validate']);p.add_argument('--env-file');p.add_argument('--offline',action='store_true');a=p.parse_args()
    config=read(CONFIG);root,plan=prepare(config)
    if a.command=='prepare':print(json.dumps(read(root/'statistical-protocol.json'),indent=2));return
    pilot.freeze_execution(config,root)
    with (root/'.writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.command=='acquire':
            pilot.acquire(config,root,plan,None if a.offline else load_key(a.env_file),a.offline)
            status=read(root/'acquisition-status.json')
            if status['stop_reason'] and not a.offline:
                pilot.acquire(config,root,plan,None,True)
                write_json(root/'acquisition-status.json',status)
            return
        tables=pilot.analyze(config,root,plan) if a.command=='analyze' else {n:records(root/n/(n+'.parquet')) for n in ['opportunities','events','first_outcomes','confirmation']}
        dest=pilot.reports(config,root,plan,tables)
        result=pilot.validate(config,root,plan,tables)
        result.pop('reserved_20_dates_untouched',None)
        result.update(batch_index=2,prior_batch_unchanged=True,remaining_frozen_10_dates_untouched=True)
        write_json(dest/'validation.json',result)
        primary=[r for r in tables['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY']
        previous=read(Path('reports',config['source_temporal_run'],'event-level-results.json'))
        previous_rows=[r for r in previous['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY']
        source=read(root/'source-selection.json')
        write_json(dest/'statistical-preparation.json',statistics(primary,source['calendar'][10:20],plan,config))
        write_json(dest/'cumulative-temporal-statistics.json',statistics(previous_rows+primary,source['calendar'][:20],plan,config))
        write_json(dest/'statistical-protocol.json',read(root/'statistical-protocol.json'))
        write_json(dest/'remaining-frozen-batch.json',{'status':'NOT_ACQUIRED_NOT_ANALYZED','calendar':source['calendar'][20:],
            'opportunities':[r for r in source['selected'] if r['cycle_id'] in {c['cycle_id'] for c in source['calendar'][20:]}]})
        pilot.package(config,root,dest,plan)
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
