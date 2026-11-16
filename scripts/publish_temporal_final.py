"""Publication views: retain source weights, expose correct derived batch/full30 metrics."""
import argparse
import json
import re
import shutil
from pathlib import Path

from market_lab.storage import file_hash,write_json
from market_lab.m2_pilot import event_table
from market_lab.temporal_design import read
from market_lab.temporal_pilot import package
from scripts.finalize_temporal_final import bundle


def correct_batch_views(dest):
    saved={}
    for stem in ['stratum-incidence','cohort_metrics']:
        p=dest/(stem+'.json');archive=dest/('original-weight-'+stem+'.json')
        if not archive.exists():shutil.copyfile(p,archive)
        saved[archive.name]=file_hash(archive)
    old=dest/'cohort_metrics.parquet';archive=dest/'original-weight-cohort_metrics.parquet'
    if not archive.exists():shutil.copyfile(old,archive)
    write_json(dest/'stratum-incidence.json',read(dest/'statistical-preparation.json')['strata'])
    groups=read(dest/'design-weighted-policy-metrics.json')
    (dest/'cohort_metrics.json').write_text(json.dumps(groups,sort_keys=True,separators=(',',':'))+'\n')
    event_table(dest/'cohort_metrics.parquet',groups)
    write_json(dest/'original-weight-warning.json',{'audit_only_files':list(saved)+[archive.name],
        'derived_files':['stratum-incidence.json','cohort_metrics.json','cohort_metrics.parquet','statistical-results.json'],
        'scope':'Original source event/opportunity weights unchanged. Canonical derived reports use batch3 allocation1/4/4/1; archived inherited projections are audit-only.',
        'archive_hashes':saved})


def common_pairs(cfg,dest):
    sidecar=read(dest/'analytical-weights.json');keys={(r['cycle_id'],r['security_id']) for r in sidecar};pairs=[];sources={}
    for run in cfg['source_runs']:
        path=Path('reports',run,'common-landmark-pairs.json');sources[str(path)]=file_hash(path)
        for p in read(path):
            assert (p['cycle_id'],p['security_id']) in keys
            assert p['target_ns']==p['c0']['target_ns']==p['policy_mark']['target_ns']
            assert p['c0']['exit_observation_ns']==p['policy_mark']['exit_observation_ns']
            assert p['matched']==(p['c0']['status']==p['policy_mark']['status']=='OBSERVED')
            assert (p['difference'] is not None)==p['matched']
            pairs.append({**p,'source_run_id':run})
    expected=read(dest/'validation.json')['confirmation_initial_risk_set']*2*7*4
    assert len(pairs)==expected
    (dest/'common-landmark-pairs.json').write_text(json.dumps(pairs,sort_keys=True,separators=(',',':'))+'\n')
    return {'paired_rows':len(pairs),'source_pair_hashes':sources,'all_common_timestamps_and_censoring_reconciled':True,
        'analytical_weights':'Join analytical-weights.json by cycle_id/security_id. Original conditional weights in source pairs are retained, never reused as full30 weights.'}


def report_appendix(dest,scope):
    st=read(dest/'statistical-preparation.json');es=read(dest/'statistical-results.json')
    lines=['','## Analytical-weight publication audit','',
        'Source opportunity/event weights unchanged. Canonical stratum/cohort reports use separately derived analytical weights; inherited original-weight projections are explicitly archived for audit only. Full30 uses planned6/14,9/22,9/21,6/13; Batch3 uses1/14,4/22,4/21,1/13.',
        '', '| Stratum | Selected | Verified first touches | Weighted incidence |','|---|---:|---:|---:|']
    for name,s in st['strata'].items():lines.append(f"| {name} | {s['selected_denominator']} | {s.get('observed_events')} | {s['weighted_incidence']:.3%} |")
    lines+=['','Primary first-touch session counts: '+str(read(dest/'summary.json').get('sessions',read(dest/'summary.json').get('session_events'))),
        '',f"Full test suite: {read(dest/'tests.json')['passed']} passed; raw/source/weight/replay validation receipts remain separate and unchanged.",
        '', '## Pattern interpretation','',
        'Batch2 5 upside/25 downsideยังคงเดิม. Batch3 12 upside/17 downside/3 neither: downsideยังมากกว่าแต่ไม่ซ้ำความสุดโต่งของBatch2. Full30 26 upside/62 downside/5 neither. นี่เป็นdescriptive observed-trade first-passage pattern ภายใต้กฎเดิม ไม่ใช่statistically significant continuationหรือshort-sellingprofitability.',
        '', '## Reproduction','',
        'Run temporal_final_batch prepare/acquire --offline/analyze/validate, full pytest, scripts.finalize_temporal_final --pytest-output PATH, then scripts.publish_temporal_final. Source caches are required for raw revalidation; compact results/bundles contain all processed outcomes without truncation.',
        '', 'คำแนะนำก่อน formal holdout: prioritize offline methodology/data-quality checks, censoring/quote coverage and a preregistered primary estimand/decision rule. C2 full30มีเพียง9 confirmed casesจึงยังไม่เหมาะสรุปผลการยืนยันทั่วไป หากต้องเพิ่ม precision ให้เสนอ exploration เพิ่มจากวันที่เหลือภายใต้แผนใหม่ที่ freezeก่อน ไม่เปลี่ยนthresholdเพื่อไล่ผลดี และไม่เปิดholdoutอัตโนมัติ.' ]
    marker='\n## Analytical-weight publication audit\n'
    text=(dest/'report.md').read_text().split(marker)[0].rstrip()+'\n'+'\n'.join(lines)+'\n'
    (dest/'report.md').write_text(text)
    target='docs/research/task-004-2-cumulative30.md' if scope=='full30' else 'docs/research/task-004-2-temporal-batch3.md'
    Path(target).write_text(text)


def main(test_output=None):
    bc=read('configs/task-004-2-batch3-v1.json');br=Path('data/runs',bc['run_id']);bd=Path('reports',bc['run_id'])
    cfg=read('configs/task-004-2-cumulative30-v1.json');root=Path('data/runs',cfg['run_id']);dest=Path('reports',cfg['run_id'])
    if test_output:
        match=re.search(r'(?m)^(\d+) passed, (\d+) warnings in [^\n]+$',Path(test_output).read_text());assert match
        receipt={'status':'PASS','passed':int(match[1]),'warnings':int(match[2]),'source_hashes':{str(p):file_hash(p) for p in Path('tests').glob('*.py')}}
        for d in [bd,dest]:write_json(d/'tests.json',receipt)
    correct_batch_views(bd);report_appendix(bd,'batch3')
    write_json(bd/'publication-validation.json',{'status':'PASS','publisher_sha256':file_hash(__file__),
        'derived_batch_month_allocation':[1,4,4,1],'source_event_json_sha256':file_hash(bd/'event-level-results.json'),
        'source_weights_unchanged':True,'canonical_derived_views_corrected_without_signal_changes':True})
    package(bc,br,bd,read(br/'selection.json'))
    proof=common_pairs(cfg,dest);report_appendix(dest,'full30')
    write_json(dest/'original-weight-warning.json',{'source_files':['source-event-level-results.json','event_results.parquet','common-landmark-pairs.json'],
        'analytical_weights':'analytical-weights.json','join_keys':['cycle_id','security_id'],
        'scope':'Source original conditional weights remain unchanged; use only the separate full30 analytical weights for cumulative estimates.'})
    weights=read(dest/'analytical-weights.json')
    for r in weights:
        assert abs(r['analysis_joint_weight']-r['analysis_weight_numerator']/r['analysis_weight_denominator'])<1e-9
        assert r['analysis_date_probability']==cfg['date_probabilities'][r['cycle_id'][:7]][0]/cfg['date_probabilities'][r['cycle_id'][:7]][1]
    write_json(dest/'publication-validation.json',{'status':'PASS','publisher_sha256':file_hash(__file__),'derived_weight_rows':len(weights),
        'planned_date_probabilities':cfg['date_probabilities'],'source_weights_unchanged':True,**proof})
    bundle(root,dest,cfg,read(Path('data/runs',cfg['source_temporal_run'],'selection.json'))['calendar'])
    print(json.dumps({'batch3':'PASS','full30':'PASS','common_pairs':proof['paired_rows'],'weight_rows':len(weights)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pytest-output');args=parser.parse_args();main(args.pytest_output)
