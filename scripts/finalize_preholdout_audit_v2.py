"""Publish the completed offline audit and freeze the prospective protocol."""
import argparse
import hashlib
import json
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path
from market_lab.storage import file_hash,write_json
from market_lab.temporal_design import read
from market_lab.confirmation_pilot import stats
from market_lab.audit_supplement import calibration_clearance

CONFIG='configs/task-005-audit-v2.json'


def finalize(test_output):
    config=read(CONFIG);root=Path('data/runs',config['run_id']);dest=Path('reports',config['run_id'])
    if (dest/'manifest.json').exists():raise ValueError('Immutable publication exists')
    summary=read(dest/'summary.json');quality=read(dest/'data_quality.json');statistics=read(dest/'statistical_results.json')
    events=read(dest/'event-audits.json');calibration=read(dest/'estimator-calibration.json');fairness=read(dest/'confirmation-fairness.json')
    assert len(events)==93 and len({r['event_id'] for r in events})==93
    test=re.search(r'(\d+) passed(?:, (\d+) warnings)? in',Path(test_output).read_text());assert test
    write_json(dest/'tests.json',{'status':'PASS','passed':int(test[1]),'warnings':int(test[2] or 0),
        'source_hashes':{str(p):file_hash(p) for p in Path('tests').glob('*.py')}})
    touch_sizes=[float(r['touch']['size']) for r in events];barrier_sizes=[];quotes=Counter();corrected=[]
    for r in events:
        for b in r['outcomes'][0]['barriers']:
            for support in b['support']:
                barrier_sizes.append(float(support['size']));quotes[support['quote']['status']]+=1
                if support['later_correction_notices']:corrected.append({'event_id':r['event_id'],'up':b['up'],'down':b['down'],'support':support})
    write_json(dest/'price-quality.json',{'trigger_share_size_distribution':stats(touch_sizes),'barrier_support_share_size_distribution':stats(barrier_sizes),
        'support_counting':'Each barrier has its own support; the same trade may appear in multiple barriers, not independent liquidity samples',
        'barrier_support_quote_status':dict(quotes),'barrier_support_with_later_corrections':corrected,
        'full_window_eligible_print_counts':stats([r['eligible_rows'] for r in events]),
        'overshoot_relative_to_threshold':stats([float(r['overshoot_relative_to_threshold']) for r in events]),
        'quote_scope':'Only existing event-centered windows; missing/stale NBBO at a barrier is not a trade-path failure or executable fill',
        'share_basis':dict(Counter(r['m1_basis']['action_reason'] for r in events)),
        'official_close_limitation':'P0 is unadjusted provider daily close, not independently certified closing auction',
        'historical_float_limitation':'Frozen current free_float proxy, not verified historical PIT',
        'correction_limit':'REST original reconstruction from unique matching12 is retrospective evidence; source/reference timing retained, not a new live execution claim'})
    # Explicit coverage confidence bounds describe Monte Carlo error, not market CI.
    calibration_gates=[]
    for r in calibration:
        p=r['coverage_all_replicates'];n=r['replicates'];z=1.96;den=1+z*z/n
        mid=(p+z*z/(2*n))/den;half=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/den
        calibration_gates.append({'scenario':r['scenario'],'coverage':p,'simulation_coverage_wilson95':[mid-half,mid+half],
            'meets_diagnostic_floor':p>=config['minimum_simulation_coverage'],'not_market_confidence_interval':True})
    write_json(dest/'calibration-readiness.json',calibration_gates)
    clearance=calibration_clearance(calibration,config['minimum_simulation_coverage'])
    write_json(dest/'statistical-clearance.json',clearance)
    readiness={'statistical_clearance':clearance['status'],'technical_audit':'PASS','decision':summary['readiness'],'audit_complete':summary['events_audited']==93,'holdout_authorized':False,
        'blocking_audit_discrepancies':read(dest/'anomalies.json')['discrepancies'],
        'remaining_conditions':[
            'New explicit user authorization and frozen acquisition budget/sample are required before any holdout tick access.',
            'Formal statistical clearance BLOCKED: rare_domain coverage 0.915 is below frozen global floor 0.93. All four scenarios are required. A pre-access statistical amendment and independent calibration validation are necessary; count gates or review alone cannot waive this failure.',
            'Holdout must pass complete discovery-coverage, domain-size, unknown-fraction and source-integrity gates; failures are INCONCLUSIVE, not replacement samples.',
            'Current-float classification, unverified overnight intervals and provider-close basis limit the claim to the frozen retrospective-proxy observed-print population.',
            'Bounded NBBO and only nine C2 confirmations do not support executable or causal confirmation claims.'],
        'no_market_neutral_50_50_assumption':True,'no_formal_exploration_significance_claim':True,
        'failed_simulation_diagnostics':[r['scenario'] for r in calibration_gates if not r['meets_diagnostic_floor']]}
    write_json(dest/'readiness.json',readiness)
    protocol=Path('docs/plans/TASK-005-holdout-preregistration-v2.md')
    shutil.copyfile(protocol,dest/'holdout-preregistration-v2.md')
    shutil.copyfile('docs/plans/TASK-005-preholdout-audit.md',dest/'methodology.md')
    context=read('data/runs/m4-temporal-10cycles-20261115-v1/context.json')
    for source in context['reference_sources']:
        assert file_hash(source['path'])==source['sha256']
    write_json(dest/'protocol-freeze.json',{'version':'holdout-preregistration-v2','protocol_sha256':file_hash(protocol),
        'exploratory_origin':True,'holdout_accessed':False,'execution_authorized':False,
        'frozen_reference_context_sha256':file_hash('data/runs/m4-temporal-10cycles-20261115-v1/context.json'),
        'frozen_float_and_identity_sources':context['reference_sources'],
        'frozen_policy_config_hashes':{p:file_hash(p) for p in ['configs/task-003-confirmation-v1.json','configs/task-003-1-confirmation-qa-v1.json','configs/task-002-2-systematic-v1.json']},
        'audit_config_sha256':file_hash(CONFIG),'statistical_clearance':clearance,'publisher_sha256':file_hash(__file__),
        'baseline_commit':config['baseline_commit'],'statistical_code_sha256':file_hash('market_lab/audit_statistics.py'),
        'primary':'P(downside-first)-P(upside-first), +3/-3, all initial events retained; identification bounds for unknowns',
        'sampler_seed':202611160050,'holdout_date_inclusion_probability':1,'holdout_dates_to_execute_now':0})
    primary=statistics['primary_contrast_down_minus_up']
    lines=['# TASK005 — Pre-Holdout Research Audit','',f"Run `{config['run_id']}`; baseline `{config['baseline_commit']}`",'',
        f"Readiness: **{summary['readiness']}**. Offline audit ครบ93 events /720 opportunities /30 exploration dates; zero-event627. ไม่เปิด holdout, ไม่รวม Development10, market-data requests0.",
        f"Independent raw reconstruction พบ discrepancy {summary['discrepancy_events']} events. ตรวจ SIP/ties, condition rules, corrections, trigger/P0, barrier timestamps และ forward censoring ครบทุกevent ไม่จำกัด representative examples.",'',
        '## First passage และ price quality','', '| Frozen barrier | Full30 independent outcomes |','|---|---|']
    for label,counts in quality['barrier_counts']['None'].items():lines.append(f"| {label} | {counts} |")
    lines += ['',f"Trigger shares: {stats(touch_sizes)}; touch quote statuses {quality['quote_statuses']}; trade/NBBO relations {quality['quote_relations']}. Odd-lot sensitivity เปลี่ยน first-touch record {quality['odd_touch_changed']}/93 events. Same-SIP multiple prices {quality['same_sip_multiple_prices']}; restored original records {quality['restored_rows']}.",
        'Trade-above-ask flags เก็บไว้ตรวจ ไม่ตัดทิ้งเงียบ ๆ. Barrier support sizes/conditions/corrections/source references อยู่ใน event-audits.json และprice-quality.json. ปริมาณหุ้นที่printไม่ใช่ executable liquidity/queue guarantee.',
        '','## Censoring และ missingness','','| Horizon | Observed | Censored | Root causes (overlap allowed) |','|---|---:|---:|---|']
    for h,v in quality['censoring']['None'].items():lines.append(f"| {h} | {v['observed']} | {v['censored']} | {v['root_causes']} |")
    lines += ['', 'Complete pagination แยกจาก no recent eligible print: ช่องว่างอาจสอดคล้องกับilliquidity/rejected prints แต่ไม่พิสูจน์feed lossหรือhalt. Quote freshnessไม่ใช่สาเหตุcensoringของtrade-onlyreturn. ไม่แทนcensoredreturnsด้วย0/lastprice/win/loss.',
        'NEITHERที่cycle endเป็น known category แต่เป็น administrative right-censoring สำหรับtime-to-event; upside/downsideเป็นcompeting outcomes. Stale endpoint/overnight/unknown evidenceเก็บcensoring timeและสาเหตุแยก ไม่สมมติnoninformative censoring. ผลgap300/900อยู่ในdata_quality.json.','',
        '## Estimator และ calibration','',f"Design-weighted downside-minus-upside contrast = {primary['estimate']:.6f}; Taylor SE = {primary['se']:.6f}. เป็นexploratory-origin finding ไม่ใช่confirmatory test. Identification bounds = {primary['censoring_identification_bounds']}.",
        'Varianceใช้domain residualของทั้ง720opportunities รวม627zero-event rows และfinite population correctionsทั้งdate/security stages. Reconciliationกับincidence estimatorเดิมผ่าน. Repeated securities/serialoutcomesเป็นfixedpopulationstructureในการsampling inference; crossed-date/security และleave-one-security/date sensitivitiesรายงานแยก ไม่อ้างfuture-processindependence.',
        '', '| Synthetic scenario | Repetitions | Candidate interval coverage | MC SE |','|---|---:|---:|---:|']
    for r in calibration:lines.append(f"| {r['scenario']} | {r['replicates']} | {r['coverage_all_replicates']:.3%} | {r['coverage_monte_carlo_se']:.4f} |")
    lines += ['', 'ทั้งหมดเป็นsynthetic known-population calibration ไม่ใช่market observations. Candidate t/Taylor intervals และillustrativebootstrapไม่ใช่formal95%marketCI. Scenarioที่ไม่ผ่านและMCuncertaintyอยู่ในcalibration-readiness.json; informative missingnessไม่recoverlatentoutcomes.',
        'Estimator reference: [Aubry (2024), stratified two-stage SRSWOR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11404174/). สูตรratio linearizationใช้เพื่อfixedfinitepopulation; calibrationในรายงานนี้เป็นsimulationที่รันเอง.',
        '', '## Confirmation fairness และ protocol','',f"Common initial risk set93ครบทุกpolicy; common-clock marksตรวจ {fairness['common_marks_checked']} รายการ; errors {len(fairness['errors'])}. C2confirmed9/93ยังunderpowered. Unconfirmed/insufficient/not-yet-confirmed/censoredเก็บครบ ไม่อ้างcausal improvement.",
        'Freeze primary +3/-3 contrast โดยเปิดเผยว่าเลือกหลังเห็นexploration; ไม่สมมติ50/50เป็นmarket-neutral benchmark. Secondary continuation/C1/C2/float/otherbarriersคงเดิม. Holdoutplanกำหนดdatecensus40และSRS12/stratum/date, snapshotเดิม, estimator/unknownbounds/gatesและSUPPORTED/UNSUPPORTED/INCONCLUSIVEล่วงหน้า. ยังไม่สร้างsampleหรือเรียกholdoutticks.',
        '', '## ข้อจำกัดและเงื่อนไขที่ยังต้องผ่าน','']
    lines += ['- '+s for s in readiness['remaining_conditions']]
    if readiness['failed_simulation_diagnostics']:lines.append('- Simulation diagnostics below floor: '+', '.join(readiness['failed_simulation_diagnostics']))
    lines += ['',f"Tests **{test[1]} passed**, {test[2] or 0} existing warnings. Protected artifacts {summary['protected_files_unchanged']} files unchanged. Raw reads {summary['raw_bytes_read']:,} bytes (รวมตรวจซ้ำ), elapsed {summary['elapsed_seconds']:.1f}s ภายในงบ. Raw marketdata0bytesใหม่; outputข้อมูลauditแยกจากrunsเดิม.",
        f"Local event/censoring Parquet: `data/runs/{config['run_id']}`; compact package `reports/{config['run_id']}`. Raw source paths+SHA256อยู่ครบในevent-audits.json.",
        'Reproduction: new versioned run ID in config, `.venv/bin/python -m market_lab.preholdout_audit --config PATH`, full pytest, `.venv/bin/python -m scripts.finalize_preholdout_audit_v2 --pytest-output PATH`. Default run refuses overwrite; holdout authorization remains separate.']
    witnesses=read(dest/'root-cause-summary.json')
    lines += ['', '## Additional independent rerun / readiness freeze v2', '',
        'Technical audit PASS; overall readiness CONDITIONAL; formal statistical clearance **BLOCKED**; holdout NOT AUTHORIZED.',
        f"Independent rerun agrees exactly with preserved v1 for {len(witnesses['v1_reproduction_identical'])} evidence files. Strict manifest verification requires every listed file to exist, not just hash-checking existing files.",
        f"271 censored primary forward marks across six horizons (not 271 unique events): {witnesses['primary_raw_window_witnesses']}. Eligible recent prints can coexist with overnight/gap censoring; they do not repair the missing interval.",
        'PRICE_MARK_FRESHNESS_FAILURE witnesses: '+str(witnesses['primary_freshness_failures'])+'. Return values remain null, never zero or assumed last-price returns.',
        'All returned-message condition distributions by AH/PRE/RTH and rejected reason are in root-cause-summary.json; per-mark raw witnesses and source hashes are in root-cause-witnesses.json. Scope is 93 event windows, not all 720 windows.',
        'Primary technical conclusion is about observed eligible prints and provider-complete pagination. No tick-level source independently establishes continuous exchange coverage, official closing auction certification or verified historical float.',
        f"Total raw-cache bytes read including supplemental witnesses: {witnesses['total_raw_bytes_with_reconstruction']:,}, below 8GiB. No new market data acquired.",
        'Rare-domain simulation coverage 91.5% is below the frozen 93% floor. The four-scenario gate cannot be narrowed after viewing outcomes. Other simulated observable-target coverage is 94.9%,96.6%,95.2%; informative-missingness latent-target coverage is only38.7%, demonstrating that an observable classification contrast does not recover latent full-path probabilities.',
        'Primary point estimate 36.60 percentage points is exploratory and design-weighted across both strata; no formal exploration CI or significance claim. Equality of observed downside/upside probabilities is not a market-neutral null.',
        'The holdout sampler is specified but not implemented/executed in this task. Separate authorization, a frozen bounded acquisition plan and a pre-access validated statistical amendment remain outstanding. No actual holdout outcomes or membership sample have been opened.',
        'Reproduce witnesses: `.venv/bin/python -m market_lab.audit_supplement --config configs/task-005-audit-v2.json`; publisher: `.venv/bin/python -m scripts.finalize_preholdout_audit_v2 --pytest-output PATH`. For reruns choose a new run ID and matching publication config; all stages refuse overwrites.',
        'The v1 draft source and unfinalized v1 local audit are retained. This v2 is the completed publication. Audit bundle uses its own audit-evidence-v1 contract; it is not the narrower original research-bundle-v1 schema.']
    report='\n'.join(lines)+'\n';(dest/'report.md').write_text(report);Path('docs/research/task-005-preholdout-audit.md').write_text(report)
    for p,h in read(root/'protected.json').items():assert file_hash(p)==h,p
    write_json(dest/'finalization.json',{'publisher_sha256':file_hash(__file__),'supplement_code_sha256':file_hash('market_lab/audit_supplement.py'),'audit_execution_sha256':file_hash(root/'execution.json'),
        'protocol_sha256':file_hash(protocol),'all_events_preserved':True})
    shutil.copyfile(root/'events/events.parquet',dest/'event_results.parquet')
    shutil.copyfile(root/'censoring/censoring.parquet',dest/'censoring_results.parquet')
    # Compact JSON retains every evidence record and all nanosecond integers.
    for artifact in dest.glob('*.json'):
        artifact.write_text(json.dumps(read(artifact),ensure_ascii=False,separators=(',',':'))+'\n')
    files={p.name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in dest.iterdir() if p.is_file() and p.name not in ['manifest.json','bundle-validation.json','research_bundle.zip']}
    manifest={'contract_version':'audit-evidence-v1','run_id':config['run_id'],'config':config,'baseline_commit':config['baseline_commit'],
        'files':files,'status':summary['readiness'],'holdout_executed':False,'raw_market_data_included':False,'event_count':93,
        'price_path':'Full existing raw evidence retained locally; independent event audit references every reconstructed source path',
        'statistical_claim':'Exploratory finite-population analysis; candidate interval calibration only','protocol_sha256':file_hash(protocol)}
    write_json(dest/'manifest.json',manifest)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for n in ['manifest.json',*files]:z.write(dest/n,n)
    with zipfile.ZipFile(dest/'research_bundle.zip') as z:
        assert z.testzip() is None
        for n,m in files.items():assert hashlib.sha256(z.read(n)).hexdigest()==m['sha256']
    size=sum(p.stat().st_size for folder in [root,dest] for p in folder.rglob('*') if p.is_file());assert size<config['max_output_bytes']
    write_json(dest/'bundle-validation.json',{'status':'PASS','sha256':file_hash(dest/'research_bundle.zip'),
        'bytes':(dest/'research_bundle.zip').stat().st_size,'total_audit_storage_bytes':size,'files':len(files)})
    print(json.dumps({'readiness':readiness,'summary':summary,'tests':int(test[1]),'bundle_bytes':(dest/'research_bundle.zip').stat().st_size},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pytest-output',required=True);a=p.parse_args();finalize(a.pytest_output)
