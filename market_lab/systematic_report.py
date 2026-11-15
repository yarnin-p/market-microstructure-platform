"""Full selected-sample reporting, source auditing and reproducible replay validation."""
import json
import zipfile
from collections import Counter
from pathlib import Path
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from .m2_pilot import event_table
from .m2_report import records
from .storage import write_json,file_hash,digest,parquet


def read(path):return json.loads(Path(path).read_text())


def metrics(outcomes):
    result={}
    for horizon in ['5m','15m','30m','60m','session_end','cycle_end']:
        marks=[m for r in outcomes for m in r['forward'] if m['horizon']==horizon]
        values=sorted(float(m['return']) for m in marks if m['return'] is not None)
        n=len(values)
        result[horizon]={'events':len(marks),'uncensored':n,'censored':sum(m['censored'] for m in marks),
                         'mean':sum(values)/n if n else None,'median':(values[(n-1)//2]+values[n//2])/2 if n else None,
                         'min':min(values) if n else None,'max':max(values) if n else None}
    return {'forward':result,'barriers':{u+'/'+d:dict(Counter(b['outcome'] for r in outcomes for b in r['barriers'] if b['up']==u and b['down']==d))
                                      for u,d in [('0.03','0.03'),('0.05','0.03'),('0.10','0.05')]},
            'excursion_events':len(outcomes),'excursion_censored':sum(r['excursion_censored'] for r in outcomes)}


def report(config,root,selection,events,outcomes,opportunities,ledger):
    dest=Path('reports',config['run_id']);dest.mkdir(parents=True,exist_ok=True)
    primary=[r for r in events if r['condition_policy']=='HIGH_LOW_ONLY']
    primary_opp=[r for r in opportunities if r['condition_policy']=='HIGH_LOW_ONLY']
    cycles=[]
    for c in selection['calendar']:
        oo=[o for o in primary_opp if o['cycle_id']==c['cycle_id']];ee=[e for e in primary if e['cycle_id']==c['cycle_id']]
        cycles.append({'cycle_id':c['cycle_id'],'selected':len(oo),'complete':sum(o['complete_observed_sessions'] for o in oo),
                       'observed_first_denominator':sum(o['observed_opportunity_eligible'] for o in oo),
                       'events':len(ee),'verified_events':sum(e['observed_sessions_first_verified'] for e in ee),
                       'zero_event':sum(o['zero_event_observed'] for o in oo),'sessions':dict(Counter(e['session'] for e in ee)),
                       'primary_outcomes':metrics([r for r in outcomes if r['cycle_id']==c['cycle_id'] and r['condition_policy']=='HIGH_LOW_ONLY' and r['gap_policy']=='NO_MECHANICAL_GAP'])})
    groups=[]
    for policy in config['condition_policies']:
        for cohort in ['EXCHANGE_PRICE_ONLY','MASSIVE_CURRENT_FLOAT_PROXY','SEC_HISTORICAL_EVIDENCE_OVERLAP']:
            def member(r): return bool(r.get('sec_evidence')) if cohort=='SEC_HISTORICAL_EVIDENCE_OVERLAP' else cohort in r['cohorts']
            oo=[o for o in opportunities if o['condition_policy']==policy and member(o)]
            ee=[e for e in events if e['condition_policy']==policy and member(e)]
            ids={e['event_id'] for e in ee}
            for session in ['ALL','AH','PRE','RTH']:
                chosen=[e for e in ee if session=='ALL' or e['session']==session];chosen_ids={e['event_id'] for e in chosen}
                # Session risk set excludes earlier-session primary touches of the same policy.
                rank={'AH':0,'PRE':1,'RTH':2}
                earlier={(e['cycle_id'],e['security_id']) for e in ee if session!='ALL' and rank[e['session']]<rank[session]}
                eligible=[o for o in oo if o['observed_opportunity_eligible'] and (o['cycle_id'],o['security_id']) not in earlier]
                groups.append({'sample':'SYSTEMATIC','condition_policy':policy,'cohort':cohort,'session':session,
                               'selected_opportunities':len(oo),'verified_risk_set':len(eligible),'events':len(chosen),
                               'verified_events':sum(e['observed_sessions_first_verified'] for e in chosen),
                               'strict_denominator':0,'strict_events':None,
                               'outcomes':{g:metrics([r for r in outcomes if r['event_id'] in chosen_ids and r['gap_policy']==g])
                                           for g in ['NO_MECHANICAL_GAP','GAP_300_SECONDS','GAP_900_SECONDS']}})
    securities=[]
    for sid in sorted({o['security_id'] for o in primary_opp}):
        oo=[o for o in primary_opp if o['security_id']==sid];ee=[e for e in primary if e['security_id']==sid]
        securities.append({'security_id':sid,'tickers':sorted({o['ticker'] for o in oo}),'cycles':len(oo),'complete':sum(o['complete_observed_sessions'] for o in oo),
                           'events':len(ee),'verified_events':sum(e['observed_sessions_first_verified'] for e in ee),
                           'primary_outcomes':metrics([r for r in outcomes if r['security_id']==sid and r['condition_policy']=='HIGH_LOW_ONLY' and r['gap_policy']=='NO_MECHANICAL_GAP'])})
    odd=[e for e in events if e['condition_policy']!='HIGH_LOW_ONLY'];by_pair={(e['cycle_id'],e['security_id']):e for e in primary}
    sensitivity={'odd_events':len(odd),'primary_events':len(primary),
                 'odd_added_events':sum((e['cycle_id'],e['security_id']) not in by_pair for e in odd),
                 'changed_touch_timestamps':sum((e['cycle_id'],e['security_id']) in by_pair and e['event_timestamp']!=by_pair[e['cycle_id'],e['security_id']]['event_timestamp'] for e in odd)}
    summary={'run_id':config['run_id'],'primary_definition':config['methodology'],'selected_opportunities':len(primary_opp),
             'cycles_processed':len(cycles),'complete_cycles':sum(c['complete']==c['selected'] for c in cycles),'complete_trade_windows':sum(o['complete_observed_sessions'] for o in primary_opp),
             'primary_events':len(primary),'verified_observed_first_events':sum(e['observed_sessions_first_verified'] for e in primary),
             'zero_event_opportunities':sum(o['zero_event_observed'] for o in primary_opp),
             'strict_full_cycle_status':'UNAVAILABLE_NO_INDEPENDENT_OVERNIGHT_VERIFICATION','strict_denominator':0,
             'session_events':dict(Counter(e['session'] for e in primary)),'unique_securities':len(securities),
             'repeated_securities':sum(s['cycles']>1 for s in securities),'sampling':'24 per cycle, daily stratified SRS; full selected sample only',
             'requests':len(ledger['attempts']),'pages':ledger['pages'],'decoded_bytes':ledger['decoded_bytes'],
             'api_errors':sum(a['status']!='OK' for a in ledger['attempts']),'sensitivities':sensitivity,
             'statuses':{'ENGINEERING_VALIDATED':False,'DATA_COVERAGE_VALIDATED':all(o['complete_observed_sessions'] for o in primary_opp),
                         'PILOT_RESULTS_AVAILABLE':True,'RESEARCH_STATISTICALLY_VALIDATED':False}}
    quality={'coverage_scope':'TERMINAL_PROVIDER_PAGINATION_IN_AH_PRE_RTH; not independent consolidated-feed or overnight certification',
             'incomplete_opportunities':[{'cycle_id':o['cycle_id'],'ticker':o['ticker'],'error':o['coverage_error']} for o in primary_opp if not o['complete_observed_sessions']],
             'float_status_counts':dict(Counter(o['float_proxy']['status'] for o in primary_opp)),
             'sec_overlap_opportunities':sum(bool(o['sec_evidence']) for o in primary_opp),
             'api_errors':[a for a in ledger['attempts'] if a['status']!='OK'],
             'context_errors':read(root/'context.json')['errors'],
             'primary_nbbo_relations':dict(Counter(e['quote']['trade_relation'] for e in primary)),
             'quote_scope':'BOUNDED_EVENT_WINDOWS_ONLY',
             'raw_trade_rows':sum(o['raw_rows'] for o in primary_opp),'normalized_trade_rows':sum(o['normalized_rows'] for o in primary_opp),
             'reject_counts':dict(sum((Counter(o['reject_counts']) for o in primary_opp),Counter()))}
    anomalies={'events':[{'event_id':e['event_id'],'ticker':e['ticker'],'cycle_id':e['cycle_id'],'condition_policy':e['condition_policy'],
                         'quote':e['quote'],'source_json':e['source_json']} for e in events if e['quote']['trade_relation'] not in ['WITHIN_NBBO']],
               'policy':'Retained, never discarded for trade-above-ask; quotes are context not trigger inputs'}
    for name,value in [('summary',summary),('data_quality',quality),('anomalies',anomalies),('cycle_metrics',cycles),('security_variation',securities),
                       ('statistical_results',{'groups':groups,'confidence_intervals':{'status':'NOT_ESTIMATED','reason':'Descriptive dependent pilot; no population inference'},
                                               'weights':'n/N inclusion probability and N/n design weight stored on every selected opportunity; no iid or pooled profitability claims'}),
                       ('sampling',{'strata':selection['strata'],'frame_counts':selection['frame_counts'],'selection_sha256':file_hash(root/'selection.json')}),
                       ('event-level-results',{'events':events,'outcomes':outcomes,'opportunities':opportunities})]:
        write_json(dest/(name+'.json'),value)
    event_table(dest/'event_results.parquet',[{**e,'outcomes':[r for r in outcomes if r['event_id']==e['event_id']]} for e in events])
    event_table(dest/'cycle_metrics.parquet',cycles);event_table(dest/'cohort_metrics.parquet',groups)
    event_table(dest/'distributions.parquet',outcomes)
    body='# TASK 002.2 — Systematic expansion\n\n'+json.dumps(summary,indent=2)+'\n\n## Coverage by cycle\n\n'+json.dumps(cycles,indent=2)
    body+='\n\n## Research limits\n\nAll statistics cover the complete selected pilot sample, not the full historical universe. Sampling uses each cycle\'s M1 population, current identity-matched free-float proxy and complementary strata. Current float is not historical PIT: survivorship, dilution, reverse splits and later changes may misclassify past float. Missing current identity/float stays unresolved in the complementary control stratum. SEC evidence is independent, never forward-filled. No diagnostic securities were selected using future movement. Cohorts overlap; repeated securities, policy sensitivities and session risk sets must not be summed as independent observations. No population confidence intervals, threshold optimization or profitability inference is attempted. Weights and frame denominators are preserved for future design-aware analysis.\n\nPrimary returns use HIGH_LOW_ONLY eligible observed trades, wall-clock horizons, 60-second mark freshness and no automatic elapsed-gap censoring. Overnight, missing pages, unknown path evidence and corrections still censor. The 300/900-second rules and odd lots are separately labeled sensitivities. Observed MFE/MAE are not executable fills. Strict full-cycle findings remain unavailable. NBBO is bounded context; trade-above-ask flags remain in event data. P0 inherits M1 grouped daily close, not independently certified official auction close. No holdout observations were analyzed.\n\n## Reproduction\n\n`python -m market_lab.systematic_pilot run --offline` resumes immutable checkpoints. `validate --offline` independently checks page chains, raw events, NBBO and deterministic outcomes. `python scripts/query_systematic_pilot.py --kind events --ticker SYMBOL` provides bounded extracts; complete Parquet remains local. Code/config/source hashes and selection freeze are under data/runs/'+config['run_id']+'.\n'
    (dest/'report.md').write_text(body)
    package(config,root,dest)
    return summary


def package(config,root,dest):
    manifest={'run_id':config['run_id'],'config':config,'selection_sha256':file_hash(root/'selection.json'),
              'execution_sha256':file_hash(root/'execution.json'),
              'artifacts':{p.name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in sorted(dest.iterdir()) if p.is_file() and p.name not in ['manifest.json','research_bundle.zip']},
              'raw_evidence_root':str(root.resolve()),'statistics_scope':'FULL_SELECTED_SAMPLE_NOT_FULL_UNIVERSE'}
    write_json(dest/'manifest.json',manifest)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.iterdir()):
            if p.is_file() and p.name!='research_bundle.zip':z.write(p,p.name)


def validate(config,root,execution):
    from .systematic_pilot import replay,nbbo_context,sample_frame,size
    from .replay_methodology import outcome_sensitivity
    selection=read(root/'selection.json');assert file_hash(root/'selection.json')==read(root/'selection.sha256.json')['sha256']
    for p,h in execution['protected_files'].items():assert file_hash(p)==h,'previous artifact changed: '+p
    for p,h in execution['code_hashes'].items():assert file_hash(p)==h,'execution code changed'
    assert all(c['split_group']=='EXPLORATION' for c in selection['calendar'])
    assert file_hash(root/'context.json')==selection['context_sha256']
    assert file_hash(root/'population/frame.parquet')==selection['frame_sha256']
    selected,strata=sample_frame(records(root/'population/frame.parquet'),config)
    assert selected==selection['selected'] and strata==selection['strata']
    assert size(root)<=config['max_storage_bytes']
    for meta_path in (root/'raw/pages').glob('*.meta.json'):
        meta=read(meta_path);assert file_hash(meta['path'])==meta['sha256']
    contexts=read(root/'context.json');conditions={r['id']:r for r in contexts['conditions']}
    cycles={c['cycle_id']:c for c in selection['calendar']};events=records(root/'events/events.parquet');outcomes=records(root/'outcomes/outcomes.parquet')
    saved_events={e['event_id']:e for e in events};checks=Counter();checked=set()
    for coverage_path in root.glob('ticks/cycle=*/security=*/**/coverage.json'):
        cov=read(coverage_path);previous=0;last=None
        for page in cov['pages']:
            assert file_hash(page['path'])==page['sha256']
            body=read(page['path']);checked.add(page['path'])
            if last is not None:
                from .api import safe_url
                from urllib.parse import urlparse,parse_qsl
                next_url=safe_url(last['next_url'])
                assert page['request']=={'url':next_url.split('?',1)[0],'params':dict(parse_qsl(urlparse(next_url).query))},'cursor chain mismatch'
            stamps=[r['sip_timestamp'] for r in body['results']]
            assert stamps==sorted(stamps)
            assert all(cov['request']['start_ns']<t<=cov['request']['end_ns'] for t in stamps)
            if stamps:assert stamps[0]>=previous;previous=stamps[-1]
            last=body
        if cov['complete']:assert last is not None and not last.get('next_url')
        checks['complete_windows' if cov['complete'] else 'incomplete_windows']+=1
    for op in selection['selected']:
        pair=root/'ticks'/('cycle='+op['cycle_id'])/('security='+op['security_id'])
        result=read(pair/'result.json')
        for p,h in result['input_hashes'].items():assert file_hash(p)==h
        cov=read(pair/'trades/coverage.json');paths=sorted(map(str,(pair/'trades/normalized').glob('*.parquet')))
        invalid=sum(read(Path(p).with_suffix('.audit.json'))['invalid_timestamp_rows'] for p in paths)
        states,_,_=replay(paths,cov,op,cycles[op['cycle_id']],config,conditions,invalid)
        for policy,state in states.items():
            if not state.event:continue
            event=saved_events[state.event['event_id']]
            assert all(event[k]==v for k,v in state.event.items()),'deterministic event mismatch'
            source=read_source(event['source_json']);assert digest(source)==event['record_id']
            assert source['sip_timestamp']==event['event_timestamp']
            price_raw=read_source(event['restoration_source']) if event.get('restoration_source') else source
            assert Decimal(str(price_raw['price']))==Decimal(event['touch_price'])>=Decimal(event['threshold_price'])
            if event['quote'].get('source_json'):
                qr=read_source(event['quote']['source_json'])
                assert qr['sip_timestamp']==event['quote']['sip_timestamp']<=event['event_timestamp']
                for side in ['bid','ask']:
                    if event['quote'][side] is not None:assert Decimal(str(qr[side+'_price']))==Decimal(event['quote'][side])
            qdir=pair/'quotes'/str(event['event_timestamp'])
            if qdir.exists():
                qc=read(qdir/'coverage.json');qpaths=sorted((qdir/'normalized').glob('*.parquet'));quotes=[]
                for p in qpaths:quotes.extend(pq.ParquetFile(p).read().to_pylist())
                qi=sum(read(p.with_suffix('.audit.json'))['invalid_timestamp_rows'] for p in qpaths)
                assert nbbo_context(quotes,event,config,qc['complete'] and not qi)==event['quote']
            for gap in config['gap_sensitivities_seconds']:
                actual=outcome_sensitivity(state,cycles[op['cycle_id']],config,gap)
                found=next(r for r in outcomes if r['event_id']==event['event_id'] and r['gap_seconds']==gap)
                assert all(found[k]==v for k,v in actual.items()),'deterministic outcome mismatch'
                checks['outcomes_replayed']+=1
            checks['events_replayed']+=1
        checks['opportunities_replayed']+=1
    assert checks['events_replayed']==len(events)
    validation={'status':'PASS','checks':dict(checks),'raw_tick_pages_checked':len(checked),'protected_files_unchanged':len(execution['protected_files']),
                'holdout_analyzed':False,'source_code_hashes_match':True}
    dest=Path('reports',config['run_id']);write_json(dest/'validation.json',validation)
    summary=read(dest/'summary.json');summary['statuses']['ENGINEERING_VALIDATED']=True;write_json(dest/'summary.json',summary)
    p=dest/'report.md'
    p.write_text(p.read_text().replace('"ENGINEERING_VALIDATED": false','"ENGINEERING_VALIDATED": true').split('\n## Executed validation')[0]+'\n## Executed validation\n\n'+json.dumps(validation,indent=2)+'\n')
    package(config,root,dest)
    return validation


def read_source(encoded):
    source=json.loads(encoded);assert file_hash(source['path'])==source['sha256']
    return read(source['path'])['results'][source['row']]
