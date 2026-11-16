"""Frozen TASK003.2 audit cases, comparing only demonstrated source overlap."""
import argparse
import json
from collections import Counter
from pathlib import Path

from .flatfile_cache import CONFIG, atomic_json
from .flatfile_revalidation import source_quotes
from .nbbo_probe import normalized as rest_quotes
from .quote_state import QuoteState
from .replay_qa import iter_normalized
from .storage import file_hash
from .temporal_design import read
from .tick_replay import SECOND, number

CASES=['BIVI','ATNM','EVTV','FFAI','QRHC']


def canonical_quote(q):
    raw=json.loads(q.get('raw_json','{}'))
    def numeric(k):
        v=number(q.get(k));return str(v.normalize()) if v is not None else None
    return tuple(q.get(k) for k in ['sip_timestamp','participant_timestamp','sequence_number','bid_exchange','ask_exchange'])+tuple(numeric(k) for k in ['bid_price','ask_price','bid_size','ask_size'])+(
        tuple(json.loads(q.get('conditions_json','[]'))),tuple(json.loads(q.get('indicators_json','[]'))),
        int(raw['tape']) if raw.get('tape') not in ['',None] else None,
        int(raw['trf_timestamp']) if raw.get('trf_timestamp') not in ['',None] else None)


def witness(q):
    return {k:q.get(k) for k in ['record_id','sip_timestamp','sequence_number','bid_price','ask_price','bid_size','ask_size','bid_exchange','ask_exchange','conditions_json','indicators_json','source_json']} if q else None


def reconcile(config,root):
    integrity=read(root/'gzip-integrity.json')
    assert integrity['complete'] and len(integrity['sources'])==len(config['objects']),'Mandatory gzip proof incomplete'
    target=root/'reconciliation.json'
    if target.exists():return read(target)
    manifests=read(root/'ingested-sources.json');selection=read(Path('data/runs',config['source_run'],'selection.json'))
    original=read(Path('reports',config['nbbo_probe_run'],'coverage-quality.json'))
    results=[]
    for ticker in CASES:
        old=next(r for r in original if r['ticker']==ticker)
        cycle=next(c for c in selection['calendar'] if c['cycle_id']==old['cycle_id'])
        covpath=Path('data/runs',config['nbbo_probe_run'],'windows',str(old['index']).zfill(2),'coverage.json')
        cov=read(covpath);window=cov['window'];rest,ra=rest_quotes(cov,cycle)
        quotes,intervals,dups=source_quotes(manifests,ticker,cycle,old['security_id'])
        stream=QuoteState(quotes,intervals,cycle,5,60)
        covered=stream.covered(window['start_ns']+1,window['end_ns'])
        if not covered:
            results.append({'ticker':ticker,'cycle_id':old['cycle_id'],'classification':'SOURCE_COVERAGE_UNKNOWN',
                'rest_unique_rows':len(rest),'s3_rows':None,'rest_empty':len(rest)==0,
                'reason':'DAILY_SOURCE_OUTSIDE_FROZEN_TWO_DAY_PILOT','rest_coverage_sha256':file_hash(covpath),
                'target_ns':window['target_ns'],'source_coverage':False})
            continue
        overlap=[q for q in quotes if window['start_ns']<q['sip_timestamp']<=window['end_ns']]
        rc,sc=Counter(map(canonical_quote,rest)),Counter(map(canonical_quote,overlap))
        equal=rc==sc;before=[q for q in quotes if q['sip_timestamp']<=window['start_ns']];after=[q for q in quotes if q['sip_timestamp']>window['end_ns']]
        asof=stream.asof(window['target_ns'])
        field_names=['sip_timestamp','participant_timestamp','sequence_number','bid_exchange','ask_exchange',
                     'bid_price','ask_price','bid_size','ask_size','conditions','indicators','tape','trf_timestamp']
        differences=[];counts=Counter()
        rest_by_clock={(q['sip_timestamp'],q.get('sequence_number')):q for q in rest}
        for q in overlap:
            matched=rest_by_clock.get((q['sip_timestamp'],q.get('sequence_number')))
            if matched is None:continue
            for name,a,b in zip(field_names,canonical_quote(matched),canonical_quote(q)):
                if a!=b:
                    counts[name]+=1
                    differences.append({'sip_timestamp':q['sip_timestamp'],'sequence_number':q.get('sequence_number'),
                        'field':name,'rest':a,'s3':b,'rest_source':matched['source_json'],'s3_source':q['source_json']})
        results.append({'ticker':ticker,'cycle_id':old['cycle_id'],'classification':'REST_AND_S3_RECONCILED' if equal else 'SOURCE_DISAGREEMENT',
            'update_classification':'NO_QUOTE_UPDATE_OBSERVED' if not overlap else 'QUOTE_UPDATES_OBSERVED',
            'state_classification':asof['status'],'state_fresh':asof['fresh'],'rest_unique_rows':len(rest),'s3_rows':len(overlap),
            'rest_raw_rows':cov['raw_rows'],'rest_audit':ra,'s3_cycle_audit':dups,
            'rest_order_equal':list(map(canonical_quote,rest))==list(map(canonical_quote,overlap)),
            'clock_keys_reconciled':Counter((q['sip_timestamp'],q.get('sequence_number')) for q in rest)==Counter((q['sip_timestamp'],q.get('sequence_number')) for q in overlap),
            'core_fields_reconciled_excluding_optional_trf_diagnostic':Counter(k[:-1] for k in map(canonical_quote,rest))==Counter(k[:-1] for k in map(canonical_quote,overlap)),
            'differing_fields':dict(counts),'difference_examples':differences,
            'strict_classification_not_waived_for_diagnostic':True,
            'rest_only_record_count':sum((rc-sc).values()),'s3_only_record_count':sum((sc-rc).values()),
            'rest_records':[witness(q) for q in rest],'s3_records':[witness(q) for q in overlap],
            'preceding_s3_quote':witness(before[-1] if before else None),'following_s3_quote':witness(after[0] if after else None),
            'following_quote_not_used_for_past_state':True,'state_at_target':asof,'window':window,
            'rest_coverage_sha256':file_hash(covpath),'source_coverage':True,
            'compared_fields':['SIP/participant/sequence','bid/ask price/size','exchange','conditions','indicators','tape','trf_timestamp'],
            'rest_empty_is_not_independent_feed_loss_evidence':True})
    # One predeclared, bounded raw-trade reconciliation: BIVI on first pilot day.
    case=next(r for r in original if r['ticker']=='BIVI');cycle=next(c for c in selection['calendar'] if c['cycle_id']==case['cycle_id'])
    s3,intervals,dup=source_quotes(manifests,'BIVI',cycle,case['security_id'],'trades')
    pair=Path('data/runs',config['source_run'],'ticks','cycle='+case['cycle_id'],'security='+case['security_id'])
    coverage=read(pair/'trades/coverage.json')
    relevant=next((i for i in intervals if i['complete']),None)
    trade={'ticker':'BIVI','status':'SOURCE_COVERAGE_UNKNOWN'}
    if relevant:
        a=max(relevant['start_ns'],coverage['request']['start_ns']);b=min(relevant['end_ns'],coverage['request']['end_ns'])
        rest=list(iter_normalized(sorted((pair/'trades/normalized').glob('*.parquet'))))
        rest=[r for r in rest if a<r['sip_timestamp']<=b];s3=[r for r in s3 if a<r['sip_timestamp']<=b]
        def key(q):
            return (q['sip_timestamp'],q.get('participant_timestamp'),q.get('sequence_number'),q.get('exchange'),
                    str(number(q.get('price')).normalize()) if number(q.get('price')) is not None else None,str(number(q.get('size')).normalize()) if number(q.get('size')) is not None else None,tuple(json.loads(q.get('conditions_json','[]'))))
        r,s=Counter(map(key,rest)),Counter(map(key,s3))
        trade={'ticker':'BIVI','status':'REST_AND_S3_RECONCILED' if r==s else 'SOURCE_DISAGREEMENT',
            'overlap_start_ns':a,'overlap_end_ns':b,'rest_records':len(rest),'s3_records':len(s3),
            'rest_only_count':sum((r-s).values()),'s3_only_count':sum((s-r).values()),'source_audit':dup,
            'shared_fields':['sip_timestamp','participant_timestamp','sequence_number','exchange','price','size','conditions'],
            'correction_metadata_comparison':dict(Counter(str(q.get('correction')) for q in s3)),
            'limitation':'Shared-field reconciliation only; no replacement of original REST correction reconstruction or trade outcomes.'}
    result={'cases':results,'trade_reconciliation':trade,'source_independence':False,
        'interpretation':'S3 and REST are deliveries of the same provider, not independent feed evidence.',
        'all_five_frozen_cases_retained':True,'rest_requests':0,'holdout_access':False}
    atomic_json(target,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);a=p.parse_args();cfg=read(a.config)
    r=reconcile(cfg,Path('data/runs',cfg['run_id']));print(json.dumps(r,indent=2))
