"""Outcome-independent two-stage temporal/security sampling for TASK 004."""
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from .eligibility import identity
from .m2_pilot import control_eligible, event_table, source_rows
from .storage import digest, file_hash, write_json
from .systematic_pilot import float_evidence, sample_frame

CONFIG='configs/task-004-temporal-v1.json'


def read(path):return json.loads(Path(path).read_text())


def allocate(counts,total):
    """Hamilton proportional allocation with deterministic month tie breaks."""
    N=sum(counts.values())
    if total>N or total<0:raise ValueError('Invalid date allocation')
    out={k:total*v//N for k,v in counts.items()}
    order=sorted(counts,key=lambda k:(-(total*counts[k]%N),k))
    for k in order[:total-sum(out.values())]:out[k]+=1
    return out


def temporal_sample(calendar,development_dates,config):
    remaining=[c for c in calendar if c['split_group']=='EXPLORATION' and c['cycle_id'] not in development_dates]
    if len(remaining)!=70:raise ValueError('Expected 70 unused exploration dates')
    months=Counter(c['cycle_id'][:7] for c in remaining)
    if set(months)!={'2026-06','2026-07','2026-08','2026-09'}:raise ValueError('Unexpected temporal population')
    plan_n=allocate(months,config['plan_cycles']);batch_n=allocate(plan_n,config['batch_cycles'])
    strata=[];buckets={}
    for month in sorted(months):
        pool=sorted([c for c in remaining if c['cycle_id'].startswith(month)],key=lambda c:c['cycle_id'])
        seed=int(digest([config['master_seed'],'DATE_PLAN',month])[:16],16)
        picked=random.Random(seed).sample(pool,plan_n[month])
        batch_seed=int(digest([config['master_seed'],'DATE_BATCH',month])[:16],16)
        order=random.Random(batch_seed).sample(picked,len(picked))
        buckets[month]=[{**c,'month':month,'date_population_N':months[month],'date_plan_n':plan_n[month],
            'date_batch_n':batch_n[month],'date_plan_probability':plan_n[month]/months[month],
            'date_batch_conditional_probability':batch_n[month]/plan_n[month],
            'date_inclusion_probability':batch_n[month]/months[month],
            'date_plan_seed':seed,'date_batch_seed':batch_seed,'execute_in_initial_batch':i<batch_n[month]}
            for i,c in enumerate(order)]
        strata.append({'month':month,'population_N':months[month],'plan_n':plan_n[month],'batch_n':batch_n[month],
                       'plan_seed':seed,'batch_seed':batch_seed})
    first=[buckets[m][i] for i in range(max(batch_n.values())) for m in sorted(months) if i<batch_n[m]]
    reserve=[buckets[m][i] for i in range(max(plan_n.values())) for m in sorted(months) if batch_n[m]<=i<plan_n[m]]
    return first+reserve,strata


def protected_hashes(excluded_run):
    result={}
    skip=Path('data/runs',excluded_run)
    for parent in [Path('data'),Path('reports')]:
        for p in parent.rglob('*'):
            if p.is_file() and p.name!='.writer.lock' and skip not in p.parents and p.parent!=Path('reports',excluded_run):
                result[str(p)]=file_hash(p)
    result.update({p:file_hash(p) for p in subprocess.check_output(['git','ls-files'],text=True).splitlines()})
    return result


def prepare(config):
    root=Path('data/runs',config['run_id']);root.mkdir(parents=True,exist_ok=True)
    target=root/'selection.json'
    if target.exists():
        plan=read(target)
        assert plan['config']==config and file_hash(target)==read(root/'selection.sha256.json')['sha256']
        return root,plan
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if not head.startswith(config['baseline_commit']):raise ValueError('Unexpected baseline')
    old=Path('data/runs',config['development_run'])
    development=read(old/'selection.json')
    dates={c['cycle_id'] for c in development['calendar']}
    calendar=read(Path('data/runs',config['source_m1_run'],'calendar.json'))
    chosen,date_strata=temporal_sample(calendar,dates,config)
    context=read(old/'context.json');current=defaultdict(list);floats=defaultdict(list)
    for source in context['reference_sources']:
        assert file_hash(source['path'])==source['sha256']
        kind=source['request']['url'].split('/')[-1]
        if kind not in {'tickers','float'}:continue
        for row in read(source['path'])['results']:
            value={**row,'_source':source}
            if kind=='tickers' and identity(row):current[identity(row)].append(value)
            elif kind=='float' and isinstance(row.get('ticker'),str):floats[row['ticker']].append(value)
    sec_path=Path(context['sec_source']['path']);assert file_hash(sec_path)==context['sec_source']['sha256']
    sec={r['security']['security_id']:r for r in read(sec_path)['results']}
    frame=[];fingerprints=[];frame_counts=[]
    for cycle in chosen:
        rows,source=source_rows(config['source_m1_run'],cycle['cycle_id']);fingerprints.append(source)
        eligible=[r for r in rows if control_eligible(r)];counts=Counter(r['security_id'] for r in eligible)
        accepted=[r for r in eligible if r['security_id'] and counts[r['security_id']]==1]
        frame_counts.append({'cycle_id':cycle['cycle_id'],'non_float_eligible':len(accepted),'ambiguous_records':len(eligible)-len(accepted)})
        for r in accepted:
            base={'cycle_id':cycle['cycle_id'],'ticker':r['ticker'],'security_id':r['security_id'],
                  'previous_rth_close':str(r['previous_rth_close']),'m1_record_id':r['record_id'],'source_m1':source}
            proxy=float_evidence(base,current,floats);se=sec.get(r['security_id'])
            frame.append({**base,'float_proxy':proxy,'stratum':'PROXY_FLOAT_IN_RANGE' if proxy['status']=='ELIGIBLE' else 'OTHER_EXCHANGE_PRICE_ELIGIBLE',
                'cohorts':['EXCHANGE_PRICE_ONLY']+(['MASSIVE_CURRENT_FLOAT_PROXY'] if proxy['status']=='ELIGIBLE' else []),
                'sec_evidence':{'classification':se['status'],'source':context['sec_source'],'carry_forward':False} if se else None})
    selected,strata=sample_frame(frame,config);date_index={c['cycle_id']:c for c in chosen}
    for row in selected:
        c=date_index[row['cycle_id']]
        row.update(month=c['month'],date_inclusion_probability=c['date_inclusion_probability'],
                   date_plan_probability=c['date_plan_probability'],date_batch_conditional_probability=c['date_batch_conditional_probability'],
                   joint_inclusion_probability=row['selection_probability']*c['date_inclusion_probability'],
                   joint_sampling_weight=row['sampling_weight']/c['date_inclusion_probability'],
                   execute_in_initial_batch=c['execute_in_initial_batch'])
    if len(selected)!=720 or any(s['sample_n']!=12 for s in strata):raise ValueError('Every planned cycle needs 12 members per stratum')
    event_table(root/'population/frame.parquet',frame)
    write_json(root/'context.json',context)
    plan={'config':config,'calendar':chosen,'date_strata':date_strata,'selected':selected,'security_strata':strata,
        'frame_counts':frame_counts,'historical_sources':fingerprints,'development_dates':sorted(dates),
        'reference_context_sha256':file_hash(old/'context.json'),'frame_sha256':file_hash(root/'population/frame.parquet'),
        'selection_code_sha256':file_hash(__file__),'tick_outcomes_examined_before_selection':False}
    write_json(target,plan);write_json(root/'selection.sha256.json',{'sha256':file_hash(target)})
    write_json(root/'protected.json',protected_hashes(config['run_id']))
    return root,plan
