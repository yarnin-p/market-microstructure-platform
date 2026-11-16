"""Explain every covered signal comparison without changing signals/outcomes."""
import argparse
from collections import Counter
from pathlib import Path

from market_lab.confirmation_pilot import quotes_for, coverage_for
from market_lab.flatfile_cache import CONFIG, atomic_json
from market_lab.flatfile_ingest import selected_mapping
from market_lab.flatfile_reconcile import canonical_quote
from market_lab.flatfile_revalidation import source_quotes
from market_lab.storage import file_hash
from market_lab.temporal_design import read
from market_lab.tick_replay import SECOND,bounds


def audit(cfg,root):
    target=root/'change-explanations.json'
    if target.exists():raise ValueError('Immutable change audit exists')
    data=read(root/'confirmation-comparison.json');manifests=read(root/'ingested-sources.json')
    selection=read(Path('data/runs',cfg['source_run'],'selection.json'));events,_=selected_mapping(cfg)
    rows=[]
    for event in events:
        rr=[r for r in data['rows'] if r['initial_event_id']==event['event_id'] and r['comparable_source_coverage']]
        if not rr:continue
        cycle=next(c for c in selection['calendar'] if c['cycle_id']==event['cycle_id'])
        s3,_,_=source_quotes(manifests,event['ticker'],cycle,event['security_id'])
        pair=Path('data/runs',cfg['source_run'],'ticks','cycle='+event['cycle_id'],'security='+event['security_id'])
        rest,intervals=quotes_for(pair);start=event['event_timestamp'];end=min(start+60*SECOND,bounds(cycle)[-1])
        low=start-5*SECOND
        a=[q for q in rest if low<=q['sip_timestamp']<=end];b=[q for q in s3 if low<=q['sip_timestamp']<=end]
        strict_a,strict_b=Counter(map(canonical_quote,a)),Counter(map(canonical_quote,b))
        core_a=Counter(k[:-1] for k in map(canonical_quote,a));core_b=Counter(k[:-1] for k in map(canonical_quote,b))
        coverage=coverage_for(intervals,start,end)
        for row in rr:
            reasons=[]
            changed=row.get('changed_signal_clock_or_price',False)
            if not changed:reasons.append('SAME_STATUS_SIGNAL_CLOCK_AND_PRICE;OUTCOMES_REUSED')
            if row['policy']=='C2_S3_STATE_BASED':reasons.append('SEPARATELY_FROZEN_STATE_PERSISTENCE_TIMER_AND_AGE_POLICY')
            if not coverage['complete']:reasons.append('BOUNDED_REST_COVERAGE_REPLACED_BY_COMPLETE_PROVIDER_SESSION_OBJECT')
            if core_a!=core_b:reasons.append('DIFFERENT_CORE_QUOTE_EVENT_CONTEXT;NOT_INDEPENDENT_PROOF_OF_FEED_LOSS')
            elif strict_a!=strict_b:reasons.append('OPTIONAL_TRF_FIELD_REPRESENTATION_DIFFERS;CORE_QUOTES_MATCH')
            if changed and row['policy']=='C2_S3_FROZEN_RULE' and coverage['complete'] and core_a==core_b:
                reasons.append('REQUIRES_REVIEW_OF_LOOKBACK_BOUNDARY_OR_SOURCE_ORDER;DO_NOT_ASSUME_EXPLAINED')
            rows.append({'initial_event_id':event['event_id'],'ticker':event['ticker'],'cycle_id':event['cycle_id'],
                'condition_policy':row['condition_policy'],'policy':row['policy'],
                'old_status':row['baseline_signal']['status'],'new_status':row['signal']['status'],
                'old_signal_ns':row['baseline_signal']['signal_timestamp'],'new_signal_ns':row['signal']['signal_timestamp'],
                'changed_status_clock_or_price':changed,'reason_codes':reasons,
                'rest_source_window_complete':coverage['complete'],'rest_context_records':len(a),'s3_context_records':len(b),
                'strict_context_equal':strict_a==strict_b,'core_context_equal_excluding_optional_trf_diagnostic':core_a==core_b,
                'rest_only_core_count':sum((core_a-core_b).values()),'s3_only_core_count':sum((core_b-core_a).values()),
                'state_timer_without_new_update':row['signal'].get('timer_not_second_quote_update'),
                'new_state_age_ns':row['signal'].get('state_age_ns'),'new_state_fresh':row['signal'].get('fresh_at_confirmation'),
                'new_signal_evidence':row['signal']['evidence'],
                'requires_manual_review':any('REQUIRES_REVIEW' in r for r in reasons)})
    result={'rows':rows,'covered_comparisons':len(rows),'requires_review':sum(r['requires_manual_review'] for r in rows),
        'reason_counts':dict(Counter(reason for r in rows for reason in r['reason_codes'])),
        'scope':'Diagnostic explanation only; no signal/outcome/threshold changes',
        'code_sha256':file_hash(__file__),'rest_requests':0,'holdout_access':False}
    atomic_json(target,result);print({k:v for k,v in result.items() if k!='rows'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);a=p.parse_args();cfg=read(a.config);audit(cfg,Path('data/runs',cfg['run_id']))
