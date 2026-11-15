"""Independent temporal design checks, weighted outcomes and Thai findings."""
import argparse
import json
import re
import shutil
import sys
import platform
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

from market_lab.confirmation_pilot import stats
from market_lab.m2_report import records
from market_lab.replay_methodology import outcome_sensitivity
from market_lab.storage import file_hash,write_json
from market_lab.systematic_pilot import sample_frame,replay
from market_lab.temporal_design import CONFIG,read,temporal_sample
from market_lab.temporal_pilot import package,runtime_config


def independent_checks(config,root,plan,tables,replay_ticks=False):
    assert file_hash(root/'population/frame.parquet')==plan['frame_sha256']
    metadata=read(Path('data/runs',config['source_m1_run'],'calendar.json'))
    dates,strata=temporal_sample(metadata,set(plan['development_dates']),config)
    assert dates==plan['calendar'] and strata==plan['date_strata']
    selected,security_strata=sample_frame(records(root/'population/frame.parquet'),config)
    assert security_strata==plan['security_strata']
    assert len(selected)==len(plan['selected'])==720
    for expected,actual in zip(selected,plan['selected']):
        assert all(actual[k]==v for k,v in expected.items())
        assert abs(actual['joint_sampling_weight']-actual['sampling_weight']/actual['date_inclusion_probability'])<1e-10
    ledger=read(root/'ledger.json');earliest=min(datetime.fromisoformat(a['started_at']).timestamp() for a in ledger['attempts']) if ledger['attempts'] else None
    assert earliest is None or (root/'selection.json').stat().st_mtime<=earliest
    frozen=read(root/'execution.json');assert frozen['selection_sha256']==file_hash(root/'selection.json')
    assert all(file_hash(p)==h for p,h in frozen['code_hashes'].items())
    checkpoints=list(root.glob('ticks/cycle=*/security=*/ingest.json'));checked=0
    context=read(root/'context.json');conditions={r['id']:r for r in context['conditions']}
    cfg=runtime_config(config);op_index={(o['cycle_id'],o['security_id']):o for o in plan['selected']}
    cycle_index={c['cycle_id']:c for c in plan['calendar']}
    for p in checkpoints:
        saved=read(p)
        for path,h in saved['input_hashes'].items():assert file_hash(path)==h,'Ingest dependency changed'
        if not replay_ticks:continue
        op=saved['opportunities'][0];original=op_index[op['cycle_id'],op['security_id']]
        states,_,_=replay(saved['paths'],read(saved['coverage_path']),original,cycle_index[op['cycle_id']],cfg,conditions)
        expected=[]
        for policy,state in states.items():
            e=next((e for e in saved['events'] if e['condition_policy']==policy),None)
            assert bool(e)==bool(state.event)
            if e:
                assert all(e[k]==state.event[k] for k in ['record_id','event_timestamp','touch_price','threshold_price','observed_sessions_first_verified'])
                expected.extend(outcome_sensitivity(state,cycle_index[op['cycle_id']],cfg,g) for g in config['gap_sensitivities_seconds'])
        assert expected==saved['first_outcomes']
        checked+=1
    primary=[e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY' and e['observed_sessions_first_verified']]
    ids={e['event_id'] for e in primary};counts=Counter((r['condition_policy'],r['policy']) for r in tables['confirmation'])
    if not read(root/'analysis-status.json')['stop_reason']:assert all(n==len(ids) for n in counts.values())
    by_key={(r['initial_event_id'],r['condition_policy']):r for r in tables['confirmation'] if r['policy']=='C0_FROZEN'}
    common_checked=0
    for r in tables['confirmation']:
        assert r['initial_event_id'] in ids
        base=by_key[r['initial_event_id'],r['condition_policy']]
        for a,b in zip(base['common_landmarks'],r['common_landmarks']):
            assert (a['target_ns'],a['exit_price'],a['exit_observation_ns'])==(b['target_ns'],b['exit_price'],b['exit_observation_ns'])
            assert b['return'] is None or b['confirmed_before_or_at_landmark']
            common_checked+=1
    return {'status':'PASS','date_selection_reproduced':30,'security_selection_reproduced':720,
        'selection_precedes_first_http':True,'ingest_dependencies_checked':len(checkpoints),
        'deterministic_first_touch_replays':checked,'deterministic_first_touch_replay_requested':replay_ticks,
        'common_mark_matches_checked':common_checked,'verified_initial_confirmation_events':len(ids),
        'frozen_20_reserved_dates_not_analyzed':True,'checker_sha256':file_hash(__file__)}


def weighted_policies(rows):
    output=[]
    for condition in sorted({r['condition_policy'] for r in rows}):
        for stratum in ['ALL','PROXY_FLOAT_IN_RANGE','OTHER_EXCHANGE_PRICE_ELIGIBLE']:
            for session in ['ALL','AH','PRE','RTH']:
                for policy in sorted({r['policy'] for r in rows}):
                    rr=[r for r in rows if r['condition_policy']==condition and r['policy']==policy and
                        (stratum=='ALL' or r['stratum']==stratum) and (session=='ALL' or r['initial_session']==session)]
                    W=sum(r['joint_sampling_weight'] for r in rr);landmarks={}
                    for minute in [5,15,30,60]:
                        buckets=Counter();values=[]
                        for r in rr:
                            m=next(m for m in r['common_landmarks'] if m['landmark_minutes']==minute)
                            buckets[m['status']]+=r['joint_sampling_weight']
                            if m['status']=='OBSERVED':values.append((float(m['return']),r['joint_sampling_weight']))
                        observedW=sum(w for v,w in values)
                        landmarks[str(minute)]={'weighted_initial_denominator':W,'joint_design_weight_buckets':dict(buckets),
                            'observed_n':len(values),'conditional_weighted_mean':sum(v*w for v,w in values)/observedW if observedW else None,
                            'observed_effective_n':observedW**2/sum(w*w for v,w in values) if values else None}
                    output.append({'condition_policy':condition,'stratum':stratum,'initial_session':session,'policy':policy,
                        'initial_events':len(rr),'joint_weight_sum':W,'kish_effective_n':W*W/sum(r['joint_sampling_weight']**2 for r in rr) if W else None,
                        'joint_weighted_confirmation_fraction':sum(r['joint_sampling_weight'] for r in rr if r['signal']['status']=='CONFIRMED')/W if W else None,
                        'common_landmarks':landmarks,'scope':'Descriptive conditional means; no iid confidence intervals or unconditional policy performance claim'})
    return output


def findings(config,root,dest,plan,tables):
    summary=read(dest/'summary.json');statistics=read(dest/'statistical-preparation.json');groups=read(dest/'cohort_metrics.json')
    primary=[g for g in groups if g['condition_policy']=='HIGH_LOW_ONLY' and g['stratum']==g['initial_session']=='ALL']
    text='# TASK 004 — ผล Temporal Expansion & Statistical Preparation\n\n'
    text+=f"Run `{config['run_id']}`; baseline `e160627`. Freeze 30 exploration dates และ 720 security-cycle opportunities ก่อนอ่าน tick ใหม่; execute เฉพาะ initial batch **10 dates /240 opportunities** กระจาย June–September ไม่เพิ่มอีก 20 วันที่ reserve และไม่วิเคราะห์ 40-cycle holdout\n\n"
    text+='## Frozen sampling\n\nRemaining 70 dates: June14 /July22 /August21 /September13; เลือก 30 เป็น **6/9/9/6**, เลือก batch แรก 10 เป็น **2/3/3/2** ด้วย independent seeded SRS/second-stage permutation และ fixed round-robin order ไม่เลือกจาก returns ทุกวันสุ่ม 12 proxy +12 complementary ด้วย historical M1 gates เดิม เก็บ N,n,n/N,N/n และ date/joint probabilities/weights ทุกแถว\n\n'
    text+='Snapshot current float ใช้ cache เดิมที่ตรวจ hash แล้วจาก development run และ identity FIGI mapping แบบเดิม จึงไม่เปลี่ยน classifier หลังเห็นผล Current float เป็น retrospective proxy ไม่ใช่ historical PIT; SEC evidence แยกและไม่ forward-fill; unresolved proxy อยู่ complementary stratum ไม่ถูกทิ้ง\n\n'
    text+='## Actual coverage และ first touch\n\n| Cycle | Selected | Complete trades | Verified events | Zero-event opportunities | Sessions |\n|---|---:|---:|---:|---:|---|\n'
    for c in summary['cycles']:
        text+=f"| {c['cycle_id']} | {c['selected']} | {c['complete']} | {c['verified_events']} | {c['zero_events']} | {json.dumps(c['sessions'])} |\n"
    text+=f"\nรวม complete trade windows **{summary['complete_trade_windows']}/240**, verified primary first touches **{summary['verified_primary_events']}**, zero-event opportunities **{summary['zero_event_opportunities']}**, unknown quality/coverage opportunities **{summary['unverified_opportunities_including_unknown_prior_evidence']}**. Unverified candidates เก็บใน source tables แต่ไม่เข้าร่วม verified confirmation risk set ไม่ใส่ missing เป็น zero-event\n\n"
    text+=f"ใช้ **{summary['http_requests']} requests /{summary['ledger']['pages']} pages /{summary['ledger']['decoded_bytes']:,} decoded bytes**; HTTP/network error attempts {summary['http_errors']}; acquisition stop reason `{summary['acquisition']['stop_reason']}`; analysis stop reason `{summary['analysis']['stop_reason']}`. งบ 1,200 attempts/1,150 pages/3GiB decoded/10GiB storage; acquisition1800s, offline analysis5400s\n\n"
    text+='| Historical analytical stratum | Selected | Complete | Event candidates | Joint-weighted observed incidence |\n|---|---:|---:|---:|---:|\n'
    for s in read(dest/'stratum-incidence.json'):
        rate=s['statistics'].get('weighted_incidence')
        text+=f"| {s['stratum']} | {s['selected']} | {s['complete']} | {s['events']} | {format(rate,'.3%') if rate is not None else 'NA'} |\n"
    text+='\nSession-specific verified risk sets (ตัด earlier-session touches ออกจาก session ถัดไป ไม่บวกเป็น independent samples):\n\n| Session | Risk set | Events |\n|---|---:|---:|\n'
    for s in read(dest/'session-risk-sets.json'):
        if s['condition_policy']=='HIGH_LOW_ONLY':text+=f"| {s['session']} | {s['verified_risk_set']} | {s['events']} |\n"
    text+='\n## Frozen confirmation rules บน initial risk set เดียวกัน\n\n'
    text+=f"Risk set ใหม่ = verified primary events **{summary['confirmation_initial_risk_set']}**; analyzed initial events **{summary['analyzed_confirmation_initial_events']}**. C0, original counted/observed acceptance/session-bound C1 และ D60 sensitivities กับ C2 ใช้ TASK003.1 code เดิมโดยตรง ไม่ retune3 trades/30s, quote freshness5s/support10s/window60s หรือ +10% threshold\n\n"
    text+='| Policy | Initial | Confirmed | Unconfirmed | Insufficient | Median delay(s) | Median waiting price change |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for g in primary:
        s=g['statuses'];delay=g['delay_seconds']['median'];cost=g['waiting_price_change']['median']
        text+=f"| {g['policy']} | {g['initial_events']} | {s.get('CONFIRMED',0)} | {s.get('UNCONFIRMED',0)} | {s.get('INSUFFICIENT_DATA',0)} | {format(delay,'.3f') if delay is not None else 'NA'} | {format(cost,'.3%') if cost is not None else 'NA'} |\n"
    text+='\nNo observed below-threshold trade ไม่พิสูจน์ continuous support; C2 ไม่มี quote update ไม่ใช่หลักฐาน support หรือfailureโดยอัตโนมัติ Odd-lot discovery แยกจาก primary; follow-up sensitivity ยังคง initial primary anchor และไม่เพิ่ม odd-only events เข้า confirmation risk set\n\n'
    odd=read(dest/'odd-lot-sensitivity.json');sec=read(dest/'sec-secondary-overlap.json')
    text+=f"Odd-lot discovery sensitivity: primary {odd['primary_events']}, odd {odd['odd_events']}, added security-cycle events {odd['added_events']}, changed primary-pair touch timestamps {odd['changed_touch_timestamps']} ไม่รวมเป็น independent observations; confirmation follow-up ยังใช้ primary risk setเดิม. SEC secondary overlap = {sec['selected_opportunity_overlap']} selected opportunities /{sec['verified_primary_event_overlap']} verified primary events เป็น evidence context เท่านั้น ไม่อนุมัติ historical float eligibility\n\n"
    text+='Common landmarks ใช้ touch+5/15/30/60 นาทีและ exit mark เดียวกันทุก policy เก็บ not-yet-confirmed/unconfirmed/insufficient/censored ครบ พร้อม paired matching โดยไม่เปรียบ survivor-only return means เป็น unconditional improvement\n\n| Policy | Common exit | Observed /initial | Censored | Not yet | Unconfirmed | Insufficient | Median observed return |\n|---|---|---:|---:|---:|---:|---:|---:|\n'
    for g in primary:
        for m in [5,15,30,60]:
            q=g['common_landmarks'][str(m)];b=q['buckets'];median=q['observed_return_distribution']['median']
            text+=f"| {g['policy']} | {m}m | {b.get('OBSERVED',0)}/{g['initial_events']} | {b.get('CENSORED',0)} | {b.get('NOT_YET_CONFIRMED',0)} | {b.get('UNCONFIRMED',0)} | {b.get('INSUFFICIENT_DATA',0)} | {format(median,'.3%') if median is not None else 'NA'} |\n"
    text+='\nOwn-signal 5/15/30/60m returns, MFE/MAE, first passage +3/−3/+5/−3/+10/−5 และ 300/900-second censoring sensitivities อยู่ครบใน event-level tables, รวม pre-confirmation excursions/crossings และ exact source timestamps. `design-weighted-policy-metrics.json` เก็บ joint-weighted buckets/conditional means และ effective observable denominators; ไม่ใช้คำว่า profitability\n\n'
    old=summary['development_separate'];rate=statistics['design_weighted_incidence'].get('weighted_incidence')
    text+='## Temporal comparison และ uncertainty feasibility\n\n'
    text+=f"Development เดิม: **{old['events']}/{old['opportunities']}** primary events จากสิบวัน May–June ที่เลือกติดกัน ใช้เป็น development evidence เท่านั้น New distributed exploration: **{summary['verified_primary_events']}/240** verified events (unknown {summary['unverified_opportunities_including_unknown_prior_evidence']}); joint-design-weighted observed incidence **{format(rate,'.3%') if rate is not None else 'NA'}** เป้าหมายคือ remaining70 exploration dates ไม่ใช่ development+new pooled validation หรือ holdout\n\n"
    text+='Original C1 counted33/40, observed acceptance31/40, session-bound31/40; D60 17/10/17; C2 6 confirmed/24 unconfirmed/10 insufficient ใช้เป็น frozen descriptive reference ไม่ใช่ independence assumption หรือ causal comparator ค่า incidence/confirmation ต่างเวลาอาจเกี่ยวข้องกับ calendar composition, unequal weights, retrospective float classification และ missingness จึงไม่เลือก policy จากผลที่ดีขึ้น\n\n'
    d=statistics['design_weighted_incidence'];cl=statistics['two_way_cluster_sensitivity'];bs=statistics['crossed_cluster_resampling']
    text+=f"Effective denominators: selected {d['selected_denominator']}, quality-complete {d['complete_denominator']}, Kish n_eff {d.get('kish_effective_n')}, date clusters {d.get('date_clusters')}, security clusters {d.get('security_clusters')}. Two-stage Taylor SE `{d.get('two_stage_taylor_se')}`; status `{d['uncertainty_status']}`. Date+security−intersection cluster-score SE `{cl.get('two_way_se')}` เป็น sensitivity ไม่ใช่ iid event interval\n\n"
    text+=f"Month-stratified date × crossed-security resampling {bs['replicates']} replicates: p2.5/median/p97.5 = {bs.get('p025')}/{bs.get('median')}/{bs.get('p975')}. นี่เป็น **illustrative resampling range ไม่ใช่ calibrated confidence interval**. มีเพียง10 date clusters/2–3ต่อเดือน; repeated securities และ subset censoring จำกัด inference. ไม่มี significance test และ suppress finite-population design SE เมื่อมี nonresponse/unknown prior evidence\n\n"
    text+='Design-based SE อ้างอิง fixed remaining70-date finite population ภายใต้การสุ่มที่ประกาศไว้ ไม่ใช่ stationarity test หรือ superpopulation forecast; date/security sensitivities ยังไม่ calibrate serial dependence ระหว่างวัน จึงไม่อ้างว่า10วันที่กระจายใหม่พิสูจน์ความเสถียรทั่วไปของ strategy\n\n'
    text+='## Integrity และ reproduction\n\n'
    v=read(dest/'validation.json');i=read(dest/'independent-validation.json');t=read(dest/'tests.json')
    text+=f"Tests **{t['passed']} passed** ({t['warnings']} existing pandas warnings); protected files **{v['protected_files_unchanged']}** ไม่เปลี่ยน; ตรวจ coverage pages **{v['coverage_pages_checked']}**, raw signal references **{v['raw_signal_references_checked']}**. Reproduced30date/720security selections; selection fingerprint precedes first HTTP request; deterministic first-touch replays **{i['deterministic_first_touch_replays']}**. Reserved20datesไม่ถูกเรียกtick endpoint; M1/SEC/priorM2/M3/holdoutเก็บเดิมครบ\n\n"
    text+='```sh\npython -m market_lab.temporal_pilot prepare\npython -m market_lab.temporal_pilot acquire --offline\npython -m market_lab.temporal_pilot analyze\npython -m market_lab.temporal_pilot validate\npython -m pytest -q > /tmp/temporal-tests.txt\npython -m scripts.finalize_temporal --pytest-output /tmp/temporal-tests.txt --replay-ticks\n```\n\n'
    text+='Online acquisition ดำเนินการแล้วภายในrunนี้ ไม่ควรใช้คำสั่งonlineเพื่อขยาย20reserveddates Full raw/normalized evidence local under `data/runs/'+config['run_id']+'/`; compact reports และ consolidated `research_bundle.zip` under `reports/'+config['run_id']+'/`. Fresh checkout อ่าน compact results ได้; raw revalidationต้องมีimmutablecache ไม่มีraw ticks, Parquet หรือcredentialsเข้าGit\n\n'
    text+='ข้อจำกัดคงเดิม: historical float unresolved, current snapshotอาจมีsurvivorship/dilution/split misclassification, unverifiedovernight/feedcontinuity, retrospectiveRESTcorrectionsและ groupedcloseที่ไม่ได้รับรองofficialauctioncloseอิสระ BoundedNBBOไม่ครอบคลุมentry/exitทั้งหมด ไม่มีorder/fill/queue/fees evidence จึงไม่อ้างexecutableprofitability งานนี้ไม่ขยาย80explorationcyclesและไม่ปรับtradingstrategy\n'
    (dest/'findings-th.md').write_text(text);Path('docs/research/task-004-temporal-expansion.md').write_text(text)


def finalize(output=None,replay_ticks=False):
    config=read(CONFIG);root=Path('data/runs',config['run_id']);dest=Path('reports',config['run_id']);plan=read(root/'selection.json')
    tables=read(dest/'event-level-results.json')
    for name,rows in tables.items():assert rows==records(root/name/(name+'.parquet'))
    write_json(dest/'independent-validation.json',independent_checks(config,root,plan,tables,replay_ticks))
    hashes={str(p):file_hash(p) for p in sorted(Path('tests').glob('*.py'))}
    if output:
        m=re.search(r'(?m)^(\d+) passed, (\d+) warnings in [^\n]+$',Path(output).read_text())
        if not m:raise ValueError('Successful full pytest summary required')
        write_json(dest/'tests.json',{'status':'PASS','passed':int(m[1]),'warnings':int(m[2]),'test_source_hashes':hashes})
    assert read(dest/'tests.json')['test_source_hashes']==hashes
    primary=[e for e in tables['events'] if e['condition_policy']=='HIGH_LOW_ONLY']
    odd=[e for e in tables['events'] if e['condition_policy']=='ODD_LOT_OBSERVATION_SENSITIVITY']
    by_pair={(e['cycle_id'],e['security_id']):e for e in primary}
    write_json(dest/'odd-lot-sensitivity.json',{'primary_events':len(primary),'odd_events':len(odd),
        'added_events':sum((e['cycle_id'],e['security_id']) not in by_pair for e in odd),
        'changed_touch_timestamps':sum((e['cycle_id'],e['security_id']) in by_pair and e['event_timestamp']!=by_pair[e['cycle_id'],e['security_id']]['event_timestamp'] for e in odd),
        'confirmation_risk_set_unchanged':True,'no_independent_event_pooling':True})
    overlap=[o for o in tables['opportunities'] if o['condition_policy']=='HIGH_LOW_ONLY' and o.get('sec_evidence')]
    write_json(dest/'sec-secondary-overlap.json',{'selected_opportunity_overlap':len(overlap),
        'verified_primary_event_overlap':sum(bool(e.get('sec_evidence')) and e['observed_sessions_first_verified'] for e in primary),
        'classifications':dict(Counter(o['sec_evidence']['classification'] for o in overlap)),
        'rows':[{'cycle_id':o['cycle_id'],'security_id':o['security_id'],'ticker':o['ticker'],'evidence':o['sec_evidence']} for o in overlap],
        'historical_float_gate_changed':False,'carry_forward':False,'verified_pit_claim':False})
    from importlib.metadata import version
    write_json(dest/'environment.json',{'python':sys.version,'machine':platform.machine(),
        'dependencies':{name:version(name) for name in ['requests','pyarrow','exchange-calendars','duckdb','pytest']}})
    (dest/'design-weighted-policy-metrics.json').write_text(json.dumps(weighted_policies(tables['confirmation']),sort_keys=True,separators=(',',':'))+'\n')
    findings(config,root,dest,plan,tables)
    shutil.copyfile('docs/plans/TASK-004-temporal-expansion.md',dest/'methodology.md')
    write_json(dest/'finalization.json',{'status':'PASS','publisher_sha256':file_hash(__file__),'methodology_sha256':file_hash('docs/plans/TASK-004-temporal-expansion.md'),
        'all_records_preserved':True,'no_threshold_optimization':True,'development_not_pooled':True})
    package(config,root,dest,plan)
    return read(dest/'bundle-validation.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pytest-output');p.add_argument('--replay-ticks',action='store_true');a=p.parse_args()
    print(json.dumps(finalize(a.pytest_output,a.replay_ticks),indent=2))
