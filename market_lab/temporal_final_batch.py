"""TASK 004.2: acquire exactly the final frozen block, without resampling."""
import argparse
import copy
import fcntl
import json
import subprocess
from pathlib import Path

from .api import load_key
from .storage import file_hash,write_json
from .temporal_design import read,protected_hashes
from .temporal_batch import statistics
from .m2_report import records
from . import temporal_pilot as pilot

CONFIG='configs/task-004-2-batch3-v1.json'


def batch_view(original,inventory,config):
    dates=original['calendar'][20:30]
    if config['batch_index']!=3 or len(dates)!=10:raise ValueError('Only frozen batch3 authorized')
    if [c['cycle_id'] for c in dates]!=config['expected_dates']:raise ValueError('Unexpected frozen dates')
    if inventory['calendar']!=dates:raise ValueError('Remaining calendar differs from original')
    if any(c['split_group']!='EXPLORATION' for c in dates):raise ValueError('Holdout forbidden')
    ids={c['cycle_id'] for c in dates}
    members=[r for r in original['selected'] if r['cycle_id'] in ids]
    canonical=lambda rows:sorted(json.dumps(r,sort_keys=True) for r in rows)
    if len(members)!=240 or canonical(members)!=canonical(inventory['opportunities']):raise ValueError('Frozen opportunities changed')
    plan=copy.deepcopy(original);plan['config']=config
    plan['calendar']=[*plan['calendar'][20:],*plan['calendar'][:20]]
    for c in plan['calendar']:c['execute_in_initial_batch']=c['cycle_id'] in ids
    for r in plan['selected']:r['execute_in_initial_batch']=r['cycle_id'] in ids
    return plan


def prepare(config):
    source=Path('data/runs',config['source_temporal_run']);original=read(source/'selection.json')
    assert file_hash(source/'selection.json')==read(source/'selection.sha256.json')['sha256']
    inventory=read(config['remaining_inventory']);plan=batch_view(original,inventory,config)
    root=Path('data/runs',config['run_id'])
    if (root/'selection.json').exists():
        assert read(root/'selection.json')==plan and read(root/'source-selection.json')==original
        assert read(root/'statistical-protocol.json')['inventory_sha256']==file_hash(config['remaining_inventory'])
        return root,plan
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert head.startswith(config['baseline_commit']) and not root.exists()
    root.mkdir(parents=True)
    write_json(root/'source-selection.json',original);write_json(root/'selection.json',plan)
    write_json(root/'selection.sha256.json',{'sha256':file_hash(root/'selection.json')})
    write_json(root/'context.json',read(source/'context.json'))
    write_json(root/'statistical-protocol.json',{'frozen_before_acquisition':True,'baseline_commit':head,
        'inventory_sha256':file_hash(config['remaining_inventory']),'source_selection_sha256':file_hash(source/'selection.json'),
        'dates':config['expected_dates'],'opportunities':240,'source_weights_unchanged':True,'batch_month_allocation':[1,4,4,1],
        'batch_uncertainty':'One sampled June/September date: Taylor SE suppressed if a date stratum has fewer than two dates.',
        'cumulative30_weights':'Derive separately from original date-plan 6/14,9/22,9/21,6/13 times original security n/N. Never reuse batch1 marginal or batch2 analytical probabilities.',
        'development':'Separate, never pooled','holdout':'No outcomes parsed','quote_top_up_385':'Not authorized, not requested',
        'budgets':config,'source_remaining_inventory_untouched':True})
    write_json(root/'protected.json',protected_hashes(config['run_id']))
    return root,plan


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
                recovered=read(root/'acquisition-status.json')
                write_json(root/'acquisition-status.json',{**status,'completed_checkpoints':recovered['completed_checkpoints'],'offline_salvage_after_stop':True})
            return
        tables=pilot.analyze(config,root,plan) if a.command=='analyze' else {n:records(root/n/(n+'.parquet')) for n in ['opportunities','events','first_outcomes','confirmation']}
        dest=pilot.reports(config,root,plan,tables);result=pilot.validate(config,root,plan,tables)
        result.pop('reserved_20_dates_untouched',None);result.update(batch_index=3,no_out_of_batch_cycles_acquired=True)
        write_json(dest/'validation.json',result)
        primary=[r for r in tables['opportunities'] if r['condition_policy']=='HIGH_LOW_ONLY']
        write_json(dest/'statistical-preparation.json',statistics(primary,read(root/'source-selection.json')['calendar'][20:30],plan,config))
        write_json(dest/'original-weight-warning.json',{'scope':'cohort_metrics and inherited stratum-incidence retain original batch1 weights; use separate derived statistics for batch3 and full30 inference.'})
        write_json(dest/'statistical-protocol.json',read(root/'statistical-protocol.json'))
        pilot.package(config,root,dest,plan);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
