"""Independent proof checks, Thai QA findings and the consolidated bundle."""
import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from market_lab.confirmation import causal_quote
from market_lab.confirmation_pilot import read
from market_lab.confirmation_qa_run import package
from market_lab.m2_report import records
from market_lab.replay_methodology import condition_maps
from market_lab.storage import digest, file_hash, write_json
from market_lab.tick_replay import SECOND, eligible_trade, number, session_label


def independent_checks(config,root,dest):
    rows=read(dest/'event-level-results.json')['records']
    assert rows==records(root/'events/event_results.parquet')
    baseline=read(Path('reports',config['baseline_run'],'event-level-results.json'))['records']
    old={(r['initial_event_id'],r['condition_policy'],r['signal']['signal_policy']):r for r in baseline}
    selection=read(Path('data/runs',config['source_run'],'selection.json'))
    cycles={c['cycle_id']:c for c in selection['calendar']}
    context=read(Path('data/runs',config['source_run'],'context.json'))
    maps=condition_maps({r['id']:r for r in context['conditions']})
    trade_config=read('configs/task-002-2-systematic-v1.json')
    raw_cache={};proofs=0;common_c0=0
    def raw(ref):
        if isinstance(ref,str):ref=json.loads(ref)
        p=ref['path']
        if p not in raw_cache:
            assert file_hash(p)==ref['sha256'];raw_cache[p]=read(p)
        return raw_cache[p]['results'][ref['row']]
    expected={r['initial_event_id'] for r in baseline}
    for condition in config['condition_policies']:
        for policy in {r['policy'] for r in rows}:
            rr=[r for r in rows if r['condition_policy']==condition and r['policy']==policy]
            assert len(rr)==40 and {r['initial_event_id'] for r in rr}==expected
    for r in rows:
        b=old[r['initial_event_id'],r['condition_policy'],'C0']
        assert all(r[k]==b[k] for k in ['sampling_weight','selection_probability','population_N','sample_n','initial_event_timestamp','original_threshold_price','stratum','float_proxy'])
        signal=r['signal'];cycle=cycles[r['cycle_id']]
        if r['policy'] in {'C0_FROZEN','C2_FROZEN','C1_COUNTED_ORIGINAL'}:
            policy={'C0_FROZEN':'C0','C2_FROZEN':'C2','C1_COUNTED_ORIGINAL':'C1'}[r['policy']]
            assert signal==old[r['initial_event_id'],r['condition_policy'],policy]['signal']
            assert r['own_signal_outcomes']==old[r['initial_event_id'],r['condition_policy'],policy]['outcomes']
        if signal['status']=='CONFIRMED' and r['policy'].startswith('C1'):
            evidence=signal['evidence']
            assert len({e['record_id'] for e in evidence})>=3
            assert max(e['timestamp'] for e in evidence)-min(e['timestamp'] for e in evidence)>=30*SECOND
            assert max(e['timestamp'] for e in evidence)==signal['signal_timestamp']
            for e in evidence:
                body=raw(e['source_json'])
                assert digest(body)==e['record_id'] and body['sip_timestamp']==e['timestamp']
                fields=raw(e['restoration_source']) if e.get('restoration_source') else body
                normalized={'normalization_status':'OK','sip_timestamp':body['sip_timestamp'],'participant_timestamp':body.get('participant_timestamp'),
                    'correction':body.get('correction',0),'price':fields['price'],'size':fields['size'],
                    'conditions_json':json.dumps(fields.get('conditions',[]))}
                assert eligible_trade(normalized,cycle,maps[r['condition_policy']],trade_config)[0]
                assert number(fields['price'])>=number(r['original_threshold_price'])
                if r['definition']=='C1_SESSION_BOUND':assert session_label(cycle,e['timestamp'])==r['initial_session']
                proofs+=1
        if r['policy']=='C0_FROZEN':
            primary=next(o for o in r['own_signal_outcomes'] if o['gap_policy']=='NO_MECHANICAL_GAP')
            for m in r['common_landmarks']:
                own=next(v for v in primary['forward'] if v['horizon']==str(m['landmark_minutes'])+'m')
                assert m['target_ns']==own['target_ns'] and m['return']==own['return']
                assert m['exit_observation_ns']==own['mark_ns']
                common_c0+=1
    pairs=read(dest/'common-landmark-pairs.json')
    assert len(pairs)==2240
    for p in pairs:
        assert p['c0']['target_ns']==p['policy_mark']['target_ns']==p['common_target_ns']
        assert p['c0']['exit_observation_ns']==p['policy_mark']['exit_observation_ns']
        assert (p['paired_return_difference'] is not None)==p['matched_observable_pair']
    groups=read(dest/'cohort_metrics.json')
    for g in groups:
        assert sum(g['statuses'].values())==g['initial_events']
        for m in g['common_landmarks'].values():assert sum(m['buckets'].values())==g['initial_events']
    result={'status':'PASS','full_json_equals_parquet':True,'all_policy_risk_sets':40,'paired_landmarks_checked':len(pairs),
        'c0_common_marks_equal_original_own_marks':common_c0,'c1_qualifying_raw_evidence_checked':proofs,
        'original_weights_and_frozen_signals_unchanged':True,'checker_sha256':file_hash(__file__)}
    write_json(dest/'independent-validation.json',result)
    return result


def quote_detail(config,dest):
    original=read(dest/'c2-quote-audit.json')
    thresholds={r['initial_event_id']:r['original_threshold_price'] for r in read(dest/'event-level-results.json')['records']}
    details=[];cache={}
    for case in original['all_40']:
        conditions=Counter(); refs=[];invalid_quotes=0;corrected_quotes=0
        for point in case['timeline']:
            q=point['quote']
            if 'source_json' not in q:continue
            ref=json.loads(q['source_json']);p=ref['path']
            if p not in cache:
                assert file_hash(p)==ref['sha256'];cache[p]=read(p)
            raw=cache[p]['results'][ref['row']]
            conditions[json.dumps(raw.get('conditions',[]))]+=1
            invalid_quotes+=bool(set(q.get('flags',[])) & {'NON_REGULAR_QUOTE_CONDITION','INVALID_OR_CROSSED_NBBO','INVALID_OR_EMPTY_DISPLAYED_SIZE','INVALID_TIMESTAMP'})
            corrected_quotes+=81 in raw.get('conditions',[])
            refs.append({'observed_at':point['observed_at'],'quote_sip_timestamp':raw['sip_timestamp'],
                'conditions':raw.get('conditions',[]),'bid':raw.get('bid_price'),'ask':raw.get('ask_price'),'source':ref,
                'valid_under_frozen_policy':q['status']=='OK','flags':q.get('flags',[])})
        prior=case['initial_quote'];prior_support=False
        if 'source_json' in prior:
            ref=json.loads(prior['source_json']);body=cache[ref['path']]['results'][ref['row']]
            normalized={**body,'record_id':digest(body),'normalization_status':'OK','source_json':prior['source_json'],
                        'conditions_json':json.dumps(body.get('conditions',[]))}
            when_published=causal_quote([normalized],body['sip_timestamp'],read('configs/task-003-confirmation-v1.json'))
            prior_support=when_published['status']=='OK' and number(when_published['bid'])>=number(thresholds[case['initial_event_id']])
        details.append({k:v for k,v in case.items() if k not in {'timeline','invalid_or_corrected_observations'}} | {
            'non_valid_observation_checks_including_missing_or_stale':case['invalid_or_corrected_observations'],
            'invalid_or_corrected_quote_observations':invalid_quotes,'corrected_quote_observation_checks':corrected_quotes,
            'missing_preceding_observation_checks':case['rejection_flags_overlapping'].get('NO_PRECEDING_NBBO',0),
            'stale_quote_observation_checks':case['rejection_flags_overlapping'].get('STALE_NBBO',0),
            'raw_condition_counts_overlapping':dict(conditions),'raw_observations':refs,
            'preceding_quote_was_valid_support_when_published':prior_support,
            'no_updates_after_prior_support_including_now_stale_quotes':case['no_updates_after_touch'] and prior_support,
            'prior_support_is_not_proof_of_support_after_expiry':True})
    write_json(dest/'c2-evidence-detail.json',{'all_40':details,'original_10_insufficient':[d for d in details if d['frozen_status']=='INSUFFICIENT_DATA'],
        'counter_scope':'Replay audit non-valid checks include missing/stale. This derived audit separately counts actual invalid/corrected quotes, stale checks and missing predecessors; never sum overlapping flags as independent cases.',
        'condition_mapping_source':'Frozen TASK 003 mapping: quote 81 Corrected_Price; no new reinterpretation or threshold change',
        'observations_are_not_independent_cases':True})
    detail_path=dest/'c2-evidence-detail.json'
    complete=read(detail_path)
    detail_path.write_text(json.dumps(complete,sort_keys=True,separators=(',',':'))+'\n')
    assert read(detail_path)==complete
    return details


def thai_report(config,dest,details):
    summary=read(dest/'summary.json');groups=summary['primary_policies'];plan=read(dest/'quote-top-up-plan.json')
    text='# TASK 003.1 — ผล Confirmation Methodology QA\n\n'
    text+=f"Run `{config['run_id']}`; baseline `423dead` ไม่เปลี่ยน ใช้ 40 initial events เดิมและ 10 exploration cycles เท่านั้น ไม่มี HTTP requests เพิ่ม ไม่มีการวิเคราะห์ holdout\n\n"
    text+='## C1 sensitivities และ frozen baselines\n\nทุกแถวมี initial denominator **40**; deadline 60 วินาทีเป็น sensitivity ที่กำหนดก่อนคำนวณ ไม่ใช่การเลือก threshold จากผลกำไร\n\n'
    text+='| Policy | Confirmed | Unconfirmed | Insufficient | Median delay (s) | Median waiting price change |\n|---|---:|---:|---:|---:|---:|\n'
    for g in groups:
        s=g['statuses'];delay=g['delay_seconds']['median'];price=g['waiting_price_change']['median']
        text+=f"| {g['policy']} | {s.get('CONFIRMED',0)} | {s.get('UNCONFIRMED',0)} | {s.get('INSUFFICIENT_DATA',0)} | {format(delay,'.3f') if delay is not None else 'NA'} | {format(price,'.4%') if price is not None else 'NA'} |\n"
    text+='\nCOUNTED_ORIGINAL คงกฎเดิม; OBSERVED_ACCEPTANCE เริ่มสะสมใหม่เมื่อพบ eligible trade ต่ำกว่า threshold; SESSION_BOUND ใช้ counted rule แต่ยืนยันได้เฉพาะ initial AH/PRE/RTH session ไม่ใช่กฎรวม observed acceptance โดยอัตโนมัติ `_D60` จำกัด receipt time <=touch+60 วินาที ทุกแบบใช้สาม distinct trades/span >=30 วินาที และ threshold เดิม\n\n'
    text+='การไม่พบ observed below-threshold trade **ไม่พิสูจน์ continuous market support** งานนี้ไม่เปลี่ยนนิยามเดิมหรือเขียนผล C1/C2 ทับ ความต่างของ count/delay เป็น sensitivity ไม่ใช่เกณฑ์เลือกวิธีเพื่อ maximize positive returns\n\n'
    text+='## C2: ตรวจ 10 insufficient cases รายตัว\n\nFrozen C2 ยังคง confirmed 6 / unconfirmed 24 / insufficient 10 แต่แยก **ลักษณะหลักฐาน** ออกจาก formal signal status ไม่มี quote update ไม่ถูกแปลว่า bid ยืนหรือ support ล้มเหลวโดยอัตโนมัติ\n\n'
    text+='| Security | Cycle | Evidence assessment | Updates | Stale preceding | Invalid/corrected observations |\n|---|---|---|---:|---|---:|\n'
    for a in details:
        if a['frozen_status']!='INSUFFICIENT_DATA':continue
        text+=f"| {a['ticker']} | {a['cycle_id']} | {a['assessment']} | {a['returned_updates']} | {a['stale_preceding_quote']} | {a['invalid_or_corrected_quote_observations']} |\n"
    text+='\nAssessment counts ของทั้ง 40: '+json.dumps(read(dest/'c2-quote-audit.json')['assessments'],ensure_ascii=False)+'\n\n'
    text+='Explicit valid below-threshold bid กับ observed support break เป็นหลักฐานราคาเชิงลบที่สังเกตจริง ส่วน freshness gap/ช่วงไม่มี update คือ support ที่ยังพิสูจน์ไม่ได้ ไม่ใช่ genuine observed break; timelines และหลาย flags อาจซ้อนกัน กฎ quote conditions/freshness/10-second support เดิมไม่เปลี่ยน ไม่ใช้ corrected quote fields เป็น original PIT NBBO และไม่อ้างว่า provider มี data outage จากการไม่มี update\n\n'
    text+='## Common wall-clock exits\n\nExit = **original first touch+5/15/30/60 นาที** ทุก policy ใช้ target และ observed exit mark เดียวกันใน event/condition เดียวกัน Entry ต้องเกิดแล้วก่อนหรือเท่ากับ landmark จึงมี return ได้ `NOT_YET_CONFIRMED` แยกจาก final unconfirmed/insufficient; ไม่มีการใส่ zero return ให้กลุ่มเหล่านี้\n\n'
    text+='แต่ละช่องแสดง **observable / censored / not-yet-confirmed / unconfirmed / insufficient** รวมครบ 40; median return เป็น conditional เฉพาะ observable subset ซึ่งเปลี่ยนตาม policy จึงไม่ใช่ unconditional performance\n\n'
    text+='| Policy | Landmark | Population buckets | Median observed return |\n|---|---|---|---:|\n'
    for g in groups:
        for minute in [5,15,30,60]:
            m=g['common_landmarks'][str(minute)];b=m['buckets'];median=m['observed_return_distribution']['median']
            buckets=' / '.join(str(b.get(k,0)) for k in ['OBSERVED','CENSORED','NOT_YET_CONFIRMED','UNCONFIRMED','INSUFFICIENT_DATA'])
            text+=f"| {g['policy']} | {minute}m | {buckets} | {format(median,'.3%') if median is not None else 'NA'} |\n"
    text+='\n`common-landmark-pairs.json` เก็บคู่ครบ **2,240 rows** รวม missing/censored พร้อม matching keys, timestamps และ source locators; `paired_summary.json` เก็บจำนวน matched pairs และ conditional differences ไม่ตีความ survivor-only paired means ว่าเป็นผลของกลยุทธ์บนทั้งประชากร Own-signal horizon distributions/barriers เดิมยังอยู่ในทุก event และ cohort summary แยกจาก common-clock\n\n'
    text+='Common 5-minute matched pairs เทียบ C0 (initial denominator 40 ทุกแถว):\n\n| Policy | Matched observable pairs | Median return difference (percentage points) |\n|---|---:|---:|\n'
    for pair in read(dest/'paired_summary.json'):
        if pair['condition_policy']=='HIGH_LOW_ONLY' and pair['landmark_minutes']==5:
            delta=pair['conditional_return_difference']['median']
            text+=f"| {pair['policy']} | {pair['matched_pairs']}/40 | {format(delta*100,'+.3f') if delta is not None else 'NA'} |\n"
    text+='\nนี่เป็น conditional difference ในคู่ที่ทั้งสองฝั่งมี mark เท่านั้น ช่วง exit เดียวกันทำให้เห็นผลของ entry-price difference ชัดขึ้น แต่ไม่แก้ missingness ให้กลายเป็น unconditional performance และไม่ใช่ executable returns\n\n'
    text+='## Pre-confirmation path, weights และ cohorts\n\nทุก event-policy เก็บ MFE/MAE ก่อนสัญญาณ อ้างอิงราคา original touch พร้อม exact sources และ +3/−3, +5/−3, +10/−5 first-passage ก่อน signal ไม่รวม signal trade ในช่วงรอ สำหรับ no-signal cases ใช้ operational deadline/session/cycle end ที่ประกาศไว้แทนและติด flags จึงไม่เงียบตัดเหตุการณ์เหล่านี้ออก Overnight/unknown/corrections/stale-tail flags ยังคงอยู่ ไม่มีการย้ายข้อมูล extrema ย้อนเข้า trigger\n\n'
    text+='| Policy | Pre-confirmation MFE median | MAE median | Censored waiting paths /40 |\n|---|---:|---:|---:|\n'
    for g in groups:
        mfe=g['pre_confirmation_mfe']['median'];mae=g['pre_confirmation_mae']['median']
        text+=f"| {g['policy']} | {format(mfe,'.3%') if mfe is not None else 'NA'} | {format(mae,'.3%') if mae is not None else 'NA'} | {g['pre_confirmation_censored']}/40 |\n"
    text+='\nตาราง pre-path รวม no-signal cases ด้วย cutoff ที่ต่างกันตามนิยาม และเก็บ observed extrema แม้ path ถูก censor จึงไม่ใช่การเปรียบเทียบ opportunity/fill ที่เท่ากันโดยอัตโนมัติ\n\n'
    text+='ทุก policy คง risk set proxy 25 events กับ complementary 15 events และ original cycle/stratum N/n, n/N ไม่ reweight เฉพาะ confirmed survivors ค่า weighted buckets/conditional means เป็น descriptive ratios เท่านั้น ไม่มี population/significance/profitability inference ตารางตาม AH/PRE/RTH, float strata และ odd-lot follow-up sensitivity อยู่ใน `cohort_metrics.json` ทั้ง 192 กลุ่ม Current float ไม่ใช่ historical PIT; SEC/M1 ไม่เปลี่ยน\n\n'
    text+='## Execution-data coverage และ proposed quote budget\n\n'
    text+=f"นับ unique primary-policy entry/exit targets ได้ **{plan['unique_entry_exit_targets']}**: cached fresh-valid **{plan['cached_valid_targets']}**, มี complete time coverage แต่ invalid/stale **{plan['cached_complete_but_invalid_or_stale_targets']}**, ขาด time coverage **{plan['missing_coverage_target_windows']}** snapshot windows แต่ละ missing window ขอช่วงย้อนหลัง 5 วินาที+1ns ถึง target เพื่อรับ preceding mark การขอหนึ่งหน้าต่อทุก unmerged missing window ต้องอย่างน้อย {plan['minimum_calls_for_all_unmerged_missing_windows']} calls โดยยังไม่รู้จำนวน pages จริงหรือว่าจะมี valid quotes หรือไม่\n\n"
    text+='แผน probe ที่เสนอ: **10 windows / 40 requests / 40 pages / 4 pages ต่อ window / 64 MiB decoded / 8 MiB ต่อ page / 256 MiB storage**, connect/read timeout 5/20s, รวมไม่เกิน 600s และ spacing >=250ms เลือก queue แบบ cycle round-robin ตาม identity/time ไม่ดู returns ใช้ subscription เดิมเท่านั้น แผนนี้ **ยังไม่อนุมัติให้ fetch และไม่ได้ execute**; full queue กับ pilot queue อยู่ใน `quote-top-up-plan.json`\n\n'
    text+='Snapshot ask-entry/bid-exit marks ไม่พิสูจน์ fills, queue, size, latency/costs หรือ bid-path barriers การ top-up อาจได้ empty/partial response และไม่แก้ historical corrected quote fields โดยอัตโนมัติ ไม่อ้าง executable P&L และไม่ขยาย 80 exploration cycles\n\n'
    text+='## Validation และ reproduction\n\n'
    validation=read(dest/'validation.json');independent=read(dest/'independent-validation.json');tests=read(dest/'tests.json')
    text+=f"Tests **{tests['passed']} passed** ({tests['warnings']} existing pandas warnings); baseline **240 signal/condition records พร้อม outcomes** ตรงเดิม, protected artifacts **{validation['protected_files_unchanged']} files** ไม่เปลี่ยน, ตรวจ raw source **{validation['source_pages_checked']} pages / {validation['source_references_checked']} references**; independent checker ตรวจ qualifying C1 proof {independent['c1_qualifying_raw_evidence_checked']} records และ C0 common marks 320 จุดตรง own-clock C0 เดิม ไม่มี HTTP request และไม่ parse holdout outcomes\n\n"
    text+='```sh\npython -m market_lab.confirmation_qa_run run\npython -m market_lab.confirmation_qa_run validate\npython -m pytest -q > /tmp/confirmation-qa-tests.txt\npython -m scripts.finalize_confirmation_qa --pytest-output /tmp/confirmation-qa-tests.txt\n```\n\n'
    text+='Full new local run/checkpoints อยู่ใน `data/runs/'+config['run_id']+'/`; compact reports และ single `research_bundle.zip` อยู่ใน `reports/'+config['run_id']+'/` ZIP/Parquet/raw data ไม่เข้า Git ตาม convention เดิม ทุก 640 event-policy-condition rows และ own/common outcomes รวมครบสิบ cycles ไม่มี truncation Fresh checkout อ่าน compact results ได้ แต่ raw source revalidation ต้องมี immutable existing cache\n\n'
    text+='ข้อจำกัดยังเป็น small dependent stratified sample, conditioning ที่ +10% first touch, retrospective float/REST evidence, unverified overnight/feed continuity และ M1 grouped close ที่ไม่ได้รับรอง official auction close อิสระ งานนี้ประเมินความหมายและความเป็นธรรมของ comparison ไม่เลือก thresholds หรืออ้างผลกำไร\n'
    (dest/'findings-th.md').write_text(text)
    Path('docs/research/task-003-1-confirmation-qa.md').write_text(text)


def finalize(pytest_output=None):
    config=read('configs/task-003-1-confirmation-qa-v1.json');root=Path('data/runs',config['run_id']);dest=Path('reports',config['run_id'])
    assert read(dest/'validation.json')['status']=='PASS'
    hashes={str(p):file_hash(p) for p in sorted(Path('tests').glob('*.py'))}
    if pytest_output:
        match=re.search(r'(?m)^(\d+) passed, (\d+) warnings in [^\n]+$',Path(pytest_output).read_text())
        if not match:raise ValueError('Expected successful full pytest output')
        write_json(dest/'tests.json',{'status':'PASS','passed':int(match[1]),'warnings':int(match[2]),'test_source_hashes':hashes})
    assert read(dest/'tests.json')['test_source_hashes']==hashes
    independent_checks(config,root,dest)
    details=quote_detail(config,dest)
    thai_report(config,dest,details)
    shutil.copyfile('docs/plans/TASK-003-1-confirmation-qa.md',dest/'methodology.md')
    shutil.copyfile('docs/plans/TASK-003-1-quote-top-up-plan.md',dest/'quote-top-up-plan.md')
    write_json(dest/'finalization.json',{'status':'PASS','publisher_sha256':file_hash(__file__),
        'methodology_sha256':file_hash('docs/plans/TASK-003-1-confirmation-qa.md'),
        'quote_plan_document_sha256':file_hash('docs/plans/TASK-003-1-quote-top-up-plan.md'),
        'event_schema_sha256':file_hash('schemas/confirmation-qa-v1.json'),
        'all_640_event_records_exported':True,'threshold_optimization':False,'additional_quote_requests':0})
    selection=read(Path('data/runs',config['source_run'],'selection.json'))
    package(config,root,dest,selection)
    return read(dest/'bundle-validation.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pytest-output');args=parser.parse_args()
    print(json.dumps(finalize(args.pytest_output),indent=2))
