"""Publish compact source-linked S3 pilot evidence; raw daily files stay local."""
import argparse
import hashlib
import json
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from market_lab.flatfile_cache import CONFIG, atomic_json
from market_lab.confirmation_pilot import stats
from market_lab.m2_pilot import event_table
from market_lab.m2_report import records
from market_lab.storage import file_hash, digest
from market_lab.temporal_design import read


def publish(config_path,tests_path):
    cfg=read(config_path);root=Path('data/runs',cfg['run_id']);dest=Path('reports',cfg['run_id'])
    if dest.exists():raise ValueError('Immutable research publication exists')
    validation=read(root/'pilot-validation.json');assert validation['status']=='PASS'
    change_audit=read(root/'change-explanations.json');assert change_audit['requires_review']==0
    compare=read(root/'confirmation-comparison.json');recon=read(root/'reconciliation.json')
    baseline=read(root/'baseline-reproduction.json');sources=read(root/'downloaded-sources.json');ingested=read(root/'ingested-sources.json')
    test=re.search(r'(\d+) passed(?:, (\d+) warnings)? in',Path(tests_path).read_text());assert test
    prior=read(root/'protected.json')
    for path,sha in prior.items():assert file_hash(path)==sha,path
    dest.mkdir()
    qa=read(Path('reports',cfg['qa_run'],'event-level-results.json'))['records']
    qaindex={(r['initial_event_id'],r['condition_policy']):r for r in qa if r['policy']=='C2_FROZEN'}
    initial={r['event_id']:r for r in records(Path('data/runs',cfg['source_run'],'events/events.parquet')) if r['condition_policy']=='HIGH_LOW_ONLY'}
    enriched=[]
    for row in compare['rows']:
        old=qaindex[row['initial_event_id'],row['condition_policy']]
        enriched.append({**row,'event_id':digest([cfg['run_id'],row['initial_event_id'],row['condition_policy'],row['policy']]),
            'run_id':cfg['run_id'],'security_id':old['security_id'],'session':old['initial_session'],
            'sample':initial[row['initial_event_id']].get('sample'),
            'stratum':old['stratum'],'cohorts':old['cohorts'],'float_proxy':old['float_proxy'],'sec_evidence':old['sec_evidence'],
            'frozen_risk_metadata':{k:old[k] for k in ['security_id','stratum','cohorts','sampling_weight','selection_probability','population_N','sample_n','float_proxy','sec_evidence','initial_session']}})
    primary=[r for r in enriched if r['condition_policy']=='HIGH_LOW_ONLY']
    covered=[r for r in primary if r['comparable_source_coverage']]
    groups={}
    for policy in ['C2_S3_FROZEN_RULE','C2_S3_STATE_BASED']:
        rr=[r for r in primary if r['policy']==policy];cc=[r for r in covered if r['policy']==policy]
        old=[r['baseline_signal'] for r in rr]
        groups[policy]={'initial_denominator':40,'source_covered_denominator':len(cc),'outside_pilot_denominator':40-len(cc),
            'statuses_all40':dict(Counter(r['signal']['status'] for r in rr)),
            'statuses_covered_only':dict(Counter(r['signal']['status'] for r in cc)),
            'baseline_statuses_same_covered_population':dict(Counter(r['baseline_signal']['status'] for r in cc)),
            'changed_classifications_covered_only':sum(r['changed_classification'] for r in cc),
            'changed_signal_clock_or_price_covered_only':sum(r.get('changed_signal_clock_or_price',False) for r in cc),
            'delay_seconds':stats(r.get('delay_seconds') for r in cc),
            'waiting_price_change':stats(r.get('waiting_price_change') for r in cc),
            'common_landmarks':{str(m):{'initial_denominator':40,'statuses':dict(Counter(next(x for x in r['common_landmarks'] if x['landmark_minutes']==m)['status'] for r in rr)),
                'observed_return_distribution_conditional_only':stats(next(x for x in r['common_landmarks'] if x['landmark_minutes']==m).get('return') for r in rr)} for m in [5,15,30,60]},
            'fresh_quote_mark_pairs':sum(p['status']=='QUOTE_MARK_NOT_FILL' for r in rr for p in r['quote_marks']['pairs']),
            'cohorts':{stratum:{'initial':sum(r['frozen_risk_metadata']['stratum']==stratum for r in rr),
                'covered':sum(r['frozen_risk_metadata']['stratum']==stratum for r in cc),
                'statuses':dict(Counter(r['signal']['status'] for r in rr if r['frozen_risk_metadata']['stratum']==stratum))}
                for stratum in sorted({r['frozen_risk_metadata']['stratum'] for r in rr})},
            'executable_pnl':None}
    disagreements=[r['ticker'] for r in recon['cases'] if r['classification']=='SOURCE_DISAGREEMENT']
    unknown=[r['ticker'] for r in recon['cases'] if r['classification']=='SOURCE_COVERAGE_UNKNOWN']
    readiness={'technical_validation':'PASS','overall':'CONDITIONAL','broad_expansion_authorized':False,
        'source_disagreement_cases':disagreements,'audit_cases_outside_pilot':unknown,
        'reasons':['Only two provider days and a subset of original40 signal windows have S3 evidence; missing dates remain unknown.',
                   'REST and S3 share a provider; corrected observations and historical snapshot vintage do not independently certify original PIT market state.',
                   'State persistence is a separate sensitivity from5s quote freshness and executable liquidity.',
                   'Whole-run combined memory peak was not persisted for an interrupted quote-extraction process; memory audit remains conditional, not falsely certified from last-resume peak.',
                   'Full original development-sample expansion requires separately frozen metadata/budgets and explicit authorization.'],
        'holdout_access':False,'task0051_unchanged':True,'task0051_statistical_clearance':'BLOCKED'}
    summary={'run_id':cfg['run_id'],'source_objects':len(sources),'source_dates':cfg['pilot_dates'],
        'compressed_source_bytes':sum(s['size'] for s in sources),'raw_csv_rows':sum(s['raw_rows'] for s in ingested),
        'selected_rows':sum(s['selected_rows'] for s in ingested),'original_risk_set':40,'policies':groups,
        'baseline_reproduction':{k:v for k,v in baseline.items() if k!='row_hashes'},'readiness':readiness,
        'change_explanations':{k:v for k,v in change_audit.items() if k!='rows'},
        'rest_requests':0,'holdout_access':False,'tests_passed':int(test[1])}
    atomic_json(dest/'summary.json',summary);atomic_json(dest/'readiness.json',readiness)
    atomic_json(dest/'event-level-results.json',{'records':enriched,'timelines':compare['timelines']})
    import platform,sys,boto3,duckdb,pyarrow
    atomic_json(dest/'runtime.json',{'python':sys.version,'platform':platform.platform(),'boto3':boto3.__version__,'duckdb':duckdb.__version__,'pyarrow':pyarrow.__version__})
    atomic_json(dest/'tests.json',{'passed':int(test[1]),'warnings':int(test[2] or 0),'test_source_sha256':file_hash('tests/test_flatfiles.py')})
    for name in ['metadata-probe.json','plan-freeze.json','throughput-probe.json','resource-ledger.json','downloaded-sources.json',
                 'ingested-sources.json','ingest-resources.json','baseline-reproduction.json','reconciliation.json',
                 'pilot-validation.json','acquisition-code.json','acquisition-code-v2.json','analysis-code-freeze.json',
                 'acquisition-stop.json','acquisition-attempt-state.json','analysis-code-v3.json','analysis-code-v4.json','analysis-code-v5.json','analysis-code-v6.json','analysis-code-v7.json','analysis-code-v8.json','analysis-code-v9.json','analysis-code-v10.json','gzip-integrity.json','resource-audit-notes.json','resume-attempt-3.json','change-explanations.json']:
        if (root/name).exists():shutil.copyfile(root/name,dest/name)
    for p in root.glob('acquisition-stop-attempt-*.json'):shutil.copyfile(p,dest/p.name)
    for p in (root/'code-snapshots').glob('*.py'):shutil.copyfile(p,dest/p.name)
    shutil.copyfile('docs/plans/TASK-003-S3-parser-amendment-v1.md',dest/'parser-amendment.md')
    shutil.copyfile('docs/plans/TASK-003-S3-session-alignment-amendment-v1.md',dest/'session-alignment-amendment.md')
    event_table(dest/'event_results.parquet',enriched)
    shutil.copyfile('docs/plans/TASK-003-S3-flatfiles-v1.md',dest/'methodology.md')
    shutil.copyfile('docs/plans/TASK-003-S3-development-expansion-proposal.md',dest/'migration-proposal.md')
    lines=['# TASK 003-S3 — Massive Flat Files & Confirmation Revalidation', '',
        f"Run `{cfg['run_id']}` · baseline `{cfg['baseline_commit']}` · branch `feat/task-003-s3-flatfiles`", '',
        '**Overall: CONDITIONAL; technical validation PASS.** ทดลองจริงเฉพาะ2 source dates โดยเก็บ risk set40ไว้ครบ ไม่เปิด holdout ไม่แก้ TASK005.1 และไม่ซื้อ subscription เพิ่ม', '',
        '## การเข้าถึงและ daily cache', '',
        'ใช้ S3 clientโดยตรงเนื่องจากconnectorเดิมรองรับREST สำหรับS3 endpoint `https://files.massive.com`, bucket `flatfiles` ด้วย credentials ที่ runtime ไม่บันทึกใน Git ตรวจ HEAD7 objects ก่อนตรึง pilot เลือก May28/29 จากลำดับ audit cases เดิม ไม่เลือกตามผลตอบแทน ใช้ quote2ไฟล์และtrade1ไฟล์ รวม16,890,044,044 compressed bytes', '',
        '| Dataset/date | Compressed bytes | SHA256 | LastModified |', '|---|---:|---|---|']
    for s in sources:lines.append(f"| {s['dataset']} / {s['date']} | {s['size']:,} | `{s['sha256']}` | {s['last_modified']} |")
    lines+=['', 'Source identity เก็บ key,size,ETag,LastModified,download timestamp,SHA256,local path และpost-download HEAD verification โดยไม่ใช้ multipart ETag เป็น MD5 ชุดใหม่ที่sourceเปลี่ยนจะได้snapshotใหม่ ไม่เขียนทับชุดเก่า', '',
        'พบ IncompleteReadError ในหนึ่ง byte range: หยุดเป็น INCOMPLETE เก็บ checkpoint และ error เดิม แล้วresumeส่วนที่ขาดภายในงบเดิม มีconservative8MiB chargeสำหรับข้อมูลที่อาจเข้ามาก่อน read exception ไม่ถือว่าครบจน assembled length,identity และSHAผ่าน Operational revisionv2เพิ่มattempt-state markersเพื่อให้resume ingestionได้ ไม่เปลี่ยน quote-state/confirmation semantics', '',
        '## Streaming ingestion / date alignment', '',
        '| Source | Raw CSV rows | Selected rows | Decoded upper bound | Min SIP | Max SIP | Outside UTC date |', '|---|---:|---:|---:|---:|---:|---:|']
    for m in ingested:lines.append(f"| {m['source']['dataset']}/{m['source']['date']} | {m['raw_rows']:,} | {m['selected_rows']:,} | {m['decoded_bytes']:,} | {m['min_sip_timestamp']} | {m['max_sip_timestamp']} | {m['rows_outside_object_utc_date']} |")
    lines+=['', 'หลังเก็บ initial Arrow partial attemptไว้ ใช้DuckDB relationอ่านgzipแบบstreamingArrowbatches65,536rows กรอง original historical tickers เก็บทุก raw field เป็นstringและtimestamp19digitsเป็นint64 ไม่แปลงผ่านfloat แบ่งParquetตามdate/tickerพร้อมzero-row partitions ใช้DuckDBอ่านโดยไม่ materialize market-wide CSV Completed sources/extractionsใช้ซ้ำ; incomplete gzip attemptsเก็บแยกและเริ่มscanเฉพาะไฟล์ที่ยังไม่ครบ ไม่อ้างว่าgzipseekได้โดยไม่replayprefix', '',
        'Source filename/time alignment ตรวจจากทุกrecordและเทียบกับclock/sessionเดิม พบclosingSIPspillข้ามUTC date จึงแก้unsupportedUTC-onlyadmissionเป็นprovider04–20ETโดยมีversionedaddendumก่อนS3signals ไม่ขยายcoverageไปยังspill/admininterval และไม่เลื่อนหรือลบtimestamp Stocks sourceครอบคลุมPRE/RTH/AHตามผู้ให้บริการ ไม่ใช่หลักฐาน24-hour continuous coverage AHอาจเป็นวันก่อนcycleและFriday AHอาจอยู่ในMonday cycle ดังนั้นsource-day denominatorไม่เท่ากับcycle-date denominator', '',
        '## REST/S3 frozen cases', '', '| Case | Record reconciliation | REST / S3 rows | State at target |', '|---|---|---:|---|']
    for case in recon['cases']:lines.append(f"| {case['ticker']} | {case['classification']} | {case['rest_unique_rows']} / {case.get('s3_rows')} | {case.get('state_classification','SOURCE_COVERAGE_UNKNOWN')} |")
    lines+=['', 'ครบทั้ง5caseในรายงาน แต่EVTV/FFAI/QRHCอยู่นอก2วันpilotจึงUNKNOWN ไม่ใช่no-updateหรือfailure ส่วนoverlapเปรียบเทียบinteger SIP/PT/sequence,bid/ask price,size,exchange,conditions,indicators,tape,TRF พร้อมลำดับและduplicates พยานbefore/inside/afterwindowอยู่ในreconciliation.json โดยfollowingquoteไม่ถูกใช้ย้อนตัดสินอดีต', '',
        'Integrity regressionพบว่าDuckDBยอมรับgzipที่CRCผิด จึงบังคับindependent gzip CRC/length passก่อนadmitข้อมูล มีunit testsครอบคลุมCRC-mismatchและtruncation Exactdecodedbytesยืนยันโดยcounterในgzip-integrity.json ไม่ใช้conservativeCSVupperเป็นexactsize', '',
        'Empty REST ไม่พิสูจน์provider loss และS3/RESTเป็นช่องทางของผู้ให้บริการเดียวกัน ไม่ใช่independent market-data sources ข้อมูลผิดเงื่อนไข/correctedถูกเก็บและinvalidate current state ไม่ย้อนเลือกearlier valid quote', '',
        'ATNM strictdisagreementแจกแจงรายfieldในreconciliation.json: ถ้าcore_fields_reconciled_excluding_optional_trf_diagnostic=true หมายถึงcorequotesตรงกัน โดยTRFmissing/zeroยังเก็บเป็นstrictdifference ไม่ตัดfieldออกเพื่อทำให้ผ่าน ทั้งสองdeliveryยังมีcorrectedconditionsเดียวกันจึงไม่กลายเป็นvalidNBBOโดยอัตโนมัติ', '',
        'Bounded BIVI trade reconciliation: `'+json.dumps(recon['trade_reconciliation'],ensure_ascii=False)+'` ไม่เปลี่ยนtrade/correction evidenceเดิม', '',
        '## C0/C1 reproduction และ C2 comparison', '',
        f"ตรวจ original C0/C1/C2 signal/outcomes {baseline['frozen_baseline_signal_outcome_checks']} checks และQA rows **{baseline['qa_rows_recomputed_exactly']}** แถวตรงเดิมทุกแถว ทั้ง40 initial eventsและ2condition policies รวมC1 counted/observed/session-boundและD60sensitivities", '',
        'Original primary C2 baselineทั้ง40คือconfirmed6,unconfirmed24,insufficient10 ตารางต่อไปไม่ใช้เฉพาะผู้รอดจนconfirmเป็นdenominator และแยกsubsetที่sourceครบออกจากnonpilotที่ไม่มีข้อมูล', '',
        '| Policy | Initial | S3 source-covered | Status all40 | Baseline on covered subset | S3 on covered subset |', '|---|---:|---:|---|---|---|']
    for p,g in groups.items():lines.append(f"| {p} | 40 | {g['source_covered_denominator']} | {g['statuses_all40']} | {g['baseline_statuses_same_covered_population']} | {g['statuses_covered_only']} |")
    lines+=['', '`C2_S3_FROZEN_RULE` เรียก original C2 unchanged:bid>=originalthreshold,span>=10s,5sfreshness/gap,60sdeadline ส่วน `C2_S3_STATE_BASED_V1` เป็นsensitivityที่ตรึงก่อนoutcomes:causal timer10s,currentvalidstate age<=60s,<=60sdeadline,resetเมื่อinvalid/below/sessionเปลี่ยน ค่า5sfreshnessยังรายงานแยก ไม่ใช่การเปลี่ยนruleเดิมเพื่อให้confirmมากขึ้น', '',
        'No-forward-fill across invalidation/session/unknown coverage; same-SIP eventsมาก่อนtimerและsame-SIP+sequenceที่ขัดกันเป็นambiguous Testยืนยันว่าfuture invalidationไม่ย้อนเปลี่ยนsignalอดีต Timeline40eventsอยู่ในevent-level-results.json ส่วนnonpilotทั้งหมดยังINSUFFICIENT_DATAอย่างชัดเจน', '',
        '| Policy | Covered classification changes | Changed signal clock/price | Delay median s | Fresh ask/bid mark pairs |', '|---|---:|---:|---:|---:|']
    for p,g in groups.items():lines.append(f"| {p} | {g['changed_classifications_covered_only']} | {g['changed_signal_clock_or_price_covered_only']} | {g['delay_seconds']['median']} | {g['fresh_quote_mark_pairs']} |")
    lines+=['', 'Change-explanations.jsonตรวจ48coveredcomparisons ไม่พบunexplainedfrozen-rulechange; frozen-ruleตรงRESTทั้ง12events ในขณะที่state-policyให้2additionalconfirmationsและ1earlier/differentclockจากนิยามที่แยกไว้ ไม่ใช่การแก้ผลoriginalC2', '',
        'Per-event evidenceเก็บold/new signals,timestamps,delays,state age/freshness,source rows,waiting price change,own-clock/common-clock5/15/30/60m,MFE/MAE,barriers/censoring และquote marksครบ Recompute trade outcomesเฉพาะsignal status/time/priceเปลี่ยน ที่เหมือนเดิมreuse frozen outcomesพร้อมprovenance Cohorts/weights/SECmetadataทั้ง40joinกลับจากbaselineไว้ในfrozen_risk_metadata ไม่มีcurrent-float refresh', '',
        'Quote entry ask/exit bidใช้เฉพาะcausal fresh-valid endpointsและรายงานtrade-pathstatusแยก ตัวเลขmarkไม่ใช่fills,realizedP&Lหรือprofitability State supportที่age>5sอาจconfirmstate-sensitivityได้แต่ไม่ผ่านfresh execution-mark gate ไม่มีการเพิ่มliquidityหรือqueueevidenceขึ้นเอง', '',
        '## Resource / integrity results', '',
        f"S3 attempts **{validation['resources']['requests']} / {cfg['max_requests']}**, charged received bytes **{validation['resources']['downloaded_bytes']:,} / {cfg['max_download_bytes']:,}**, active acquisition seconds **{validation['resources']['active_seconds']:.1f} / {cfg['max_active_seconds']}**.",
        f"CSV decoded upper **{validation['ingest_resources']['decoded_bytes']:,}**, total decoded-work upper including CRC/recovery/benchmarks **{validation['decoded_work_upper_bytes']:,}**, last-resume conservative transfer/ingest peak RSS **{validation['conservative_concurrent_transfer_ingest_peak_rss_bytes']:,} bytes**, current local storage **{validation['current_storage_bytes']:,} bytes**, conservative staging upper **{validation['conservative_staging_storage_upper_bytes']:,} bytes** ต่ำกว่าdisk ceiling; RSSตัวเลขนี้ครอบคลุมlastresumeเท่านั้น Earlierquote-extractioncombinedRSSไม่ถูกpersistจึงยังไม่certifywhole-runmemorybudget แม้per-processguardsผ่าน Implementstricter1.5GiBparsercapและpersistentmetricsแล้ว ไม่โหลดmarket-wideCSVเข้าRAM.",
        f"Tests **{test[1]} passed** ({test[2] or 0} existing warnings); covered signal reruns **{validation['covered_signal_checks']}** และstate prefix-causality checks **{validation['state_prefix_causality_checks']}** ผ่าน Prior artifacts **{validation['prior_artifacts_unchanged']:,}** hashes unchanged.", '',
        '## Readiness / migration', '',
        '**CONDITIONAL** สำหรับการขยาย:เทคนิคcache/parser/replayผ่าน แต่2source datesไม่validatecomplete40-eventdevelopment sampleหรือทั้ง5auditdates ต้องอธิบายsource discrepanciesและcoverageก่อนใช้สัญญาณเป็นผลวิจัยต่อ S3snapshotอาจเป็นrevised historical content; replayพิสูจน์SIP-causalityภายในsnapshot ไม่รับรองpublication-vintage PITหรือindependent exchange-feed truth', '',
        'เตรียมproposalแยกสำหรับ11source datesที่จำเป็นต่อoriginal10cycles รวมpreceding AH, reuse2pilotfilesและไม่เกิน9additional quote dates แต่ยังไม่อนุมัติหรือดาวน์โหลดเพิ่ม เอกสาร `docs/plans/TASK-003-S3-development-expansion-proposal.md` ระบุงบและgatesแยก ไม่แตะ120cyclesหรือholdout TASK005.1 statistical clearanceยังBLOCKEDและไม่ถูกแก้ในงานนี้', '',
        '## Reproduction', '',
        'ติดตั้ง optional dependency `pip install -e ".[flatfiles]"`; กำหนดMASSIVE_S3_ACCESS_KEY_ID/MASSIVE_S3_SECRET_ACCESS_KEYหรือprivate runtime credentials file ห้ามใส่keysในconfig', '',
        'ใช้new run IDแล้วfreeze metadata/selection/budgetsก่อน `market_lab.flatfile_cache probe`, `market_lab.flatfile_transfer`, `market_lab.flatfile_integrity`, `market_lab.flatfile_ingest_duckdb --watch`, `market_lab.flatfile_revalidation baseline`, `market_lab.flatfile_revalidation revalidate`, `market_lab.flatfile_reconcile`, `scripts.validate_flatfile_pilot`, pytest และpublisherนี้ Existing completeddaily cachesใช้ซ้ำได้โดยตรวจhashก่อน ไม่เขียนทับรายงานที่ตีพิมพ์แล้ว', '',
        'Official references: [S3 quickstart](https://massive.com/docs/flat-files/quickstart), [Stocks sessions](https://massive.com/docs/flat-files/stocks/overview), [Quotes](https://massive.com/docs/flat-files/stocks/quotes), [Trades](https://massive.com/docs/flat-files/stocks/trades), [timestamp units](https://massive.com/knowledge-base/article/what-timezone-are-massives-timestamps-in). ตัวเลขผลจริงอ้างจากlocal immutable evidence ไม่ได้อนุมานcoverageจากคำโฆษณาของผู้ให้บริการ']
    text='\n'.join(lines)+'\n';(dest/'report.md').write_text(text)
    doc=Path('docs/research/task-003-s3-flatfiles-pilot.md');assert not doc.exists();doc.write_text(text)
    for p in dest.glob('*.json'):
        p.write_text(json.dumps(read(p),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    source_paths=[config_path,'pyproject.toml',*map(str,Path('market_lab').glob('flatfile*.py')),
                  'market_lab/quote_state.py','scripts/audit_flatfile_changes.py','scripts/prepare_flatfile_pilot.py','scripts/validate_flatfile_pilot.py',__file__,'tests/test_flatfiles.py',
                  'schemas/massive-flatfile-evidence-v1.json','schemas/quote-state-v1.json',str(doc)]
    files={p.name:{'bytes':p.stat().st_size,'sha256':file_hash(p)} for p in dest.iterdir() if p.is_file()}
    manifest={'contract':'s3-pilot-research-evidence-v1','run_id':cfg['run_id'],'files':files,
              'source_hashes':{p:file_hash(p) for p in source_paths},'baseline_commit':cfg['baseline_commit'],
              'raw_marketwide_data_included':False,'holdout_access':False,'readiness':readiness}
    atomic_json(dest/'manifest.json',manifest)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['manifest.json',*files]:z.write(dest/name,name)
    with zipfile.ZipFile(dest/'research_bundle.zip') as z:
        assert z.testzip() is None
        for name,meta in files.items():assert hashlib.sha256(z.read(name)).hexdigest()==meta['sha256']
    atomic_json(dest/'bundle-validation.json',{'status':'PASS','sha256':file_hash(dest/'research_bundle.zip'),'bytes':(dest/'research_bundle.zip').stat().st_size})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);p.add_argument('--pytest-output',required=True);a=p.parse_args();publish(a.config,a.pytest_output)
