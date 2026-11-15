"""Publish complete comparison results and audit the explicitly named examples."""
import bisect
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from market_lab.m2_report import records
from market_lab.replay_qa import roots, raw_at
from market_lab.storage import write_json, file_hash
from market_lab.tick_replay import SECOND, number, quote_at_event


def requested_examples(original_examples, revised):
    """Match the immutable audit's security-cycle/record, not first ticker match."""
    selected=[]
    for original in original_examples:
        event=next(e for e in revised if e['ticker']==original['ticker'] and e['cycle_id']==original['cycle_id']
                   and e['variant']=='QA_REPAIRED' and e['condition_policy']=='HIGH_LOW_ONLY')
        selected.append((original,event))
    return selected


def audit_requested(config, events):
    base,_,dest=roots(config)
    originals=json.loads((Path('reports')/config['baseline_run']/'verified-audit-examples.json').read_text())
    opportunities=records(base/'opportunities/opportunities.parquet')
    result=[]
    for old,event in requested_examples(originals,events):
        raw,ref=raw_at(event['source_json'])
        assert raw['sip_timestamp']==event['event_timestamp'] and number(raw['price'])==number(event['touch_price'])
        opportunity=next(o for o in opportunities if o['security_id']==event['security_id'] and o['cycle_id']==event['cycle_id'])
        quotes=pq.ParquetFile(Path(opportunity['normalization']['path']).with_name('quotes.parquet')).read().to_pylist()
        coverage=opportunity['quote_coverage']
        assert coverage['request']['start_ns'] < event['event_timestamp'] <= coverage['request']['end_ns']
        quote=quote_at_event(quotes,event,{'max_quote_age_seconds':5},coverage['complete'])
        raw_quote,qref=raw_at(quote['source_json'])
        assert number(raw_quote['bid_price'])==number(quote['bid']) and number(raw_quote['ask_price'])==number(quote['ask'])
        price,bid,ask=number(event['touch_price']),number(quote['bid']),number(quote['ask'])
        relation='WITHIN_PRECEDING_NBBO' if bid<=price<=ask else 'ABOVE_PRECEDING_ASK' if price>ask else 'BELOW_PRECEDING_BID'
        after=[r for r in quotes if event['event_timestamp'] < (r.get('sip_timestamp') or 0) <= event['event_timestamp']+5*SECOND
               and number(r.get('bid_price')) is not None and number(r.get('ask_price')) is not None]
        support=next((r for r in after if number(r['bid_price'])<=price<=number(r['ask_price'])),None)
        subsequent=None
        if support:
            support_raw,sref=raw_at(support['source_json'])
            assert support_raw['sip_timestamp']==support['sip_timestamp']
            subsequent={'delay_ns':support['sip_timestamp']-event['event_timestamp'],'bid':support['bid_price'],
                        'ask':support['ask_price'],'source':sref,'quote_conditions':support['conditions_json']}
        result.append({'ticker':event['ticker'],'cycle_id':event['cycle_id'],'event_timestamp':event['event_timestamp'],
            'baseline_event_id':old['event_id'],'event_id':event['event_id'],'touch_price':event['touch_price'],
            'threshold':event['threshold_price'],'raw_trade':raw,'trade_source':ref,'preceding_nbbo':quote,
            'raw_quote':raw_quote,'quote_source':qref,'relation':relation,'subsequent_support_within_5s':subsequent,
            'same_as_original_audit_record':old['record_id']==event['record_id'],
            'future_quotes_used_for_trigger':False,'executable_fill_claim':False,'status':'RAW_TRADE_AND_NBBO_HASH_VERIFIED'})
    write_json(dest/'requested-raw-nbbo-audit.json',result)
    return result


def raw_gap_audit(config):
    base,root,dest=roots(config)
    eligible_gaps=json.loads((dest/'gap-diagnostics.json').read_text())
    gaps=[];outside=[]
    for opportunity in records(base/'opportunities/opportunities.parquet'):
        if 'normalization' not in opportunity:
            continue
        repair=root/'repairs'/opportunity['cycle_id']/opportunity['ticker']
        paths=[opportunity['normalization']['path']]+[str(p) for p in sorted((repair/'normalized').glob('*.parquet'))]
        with duckdb.connect() as db:
            db.read_parquet(paths,hive_partitioning=False).create_view('ticks')
            # Message counts distinguish filtered-trade gaps from no returned
            # messages; neither proves that an exchange was open or halted.
            stamps=[r[0] for r in db.execute('SELECT DISTINCT sip_timestamp FROM ticks ORDER BY sip_timestamp').fetchall()]
            raw_gaps=db.execute("""SELECT session,previous_ns,sip_timestamp,(sip_timestamp-previous_ns)/1e9 AS gap_seconds
                FROM (SELECT session,sip_timestamp,lag(sip_timestamp) OVER(PARTITION BY session ORDER BY sip_timestamp) previous_ns
                      FROM ticks WHERE session IN ('AH','PRE','RTH')) WHERE sip_timestamp-previous_ns>300000000000""").fetchall()
            unusual=db.execute("SELECT sip_timestamp,price,source_json FROM ticks WHERE session='UNOBSERVED_OVERNIGHT'").fetchall()
        source=next((g for g in eligible_gaps if g['ticker']==opportunity['ticker'] and g['cycle_id']==opportunity['cycle_id']
                     and g['variant']=='QA_REPAIRED'),None)
        source=source or next(g for g in eligible_gaps if g['ticker']==opportunity['ticker'] and g['cycle_id']==opportunity['cycle_id'])
        intervals=[]
        for gap in source['intervals']:
            count=bisect.bisect_left(stamps,gap['end_ns'])-bisect.bisect_right(stamps,gap['start_ns'])
            intervals.append({**gap,'returned_message_timestamps_inside':count,
                'kind':'FILTERED_PRINT_GAP' if count else 'NO_RETURNED_MESSAGES_BETWEEN_ELIGIBLE_TRADES'})
        gaps.append({'ticker':opportunity['ticker'],'cycle_id':opportunity['cycle_id'],
            'eligible_gaps_over_300':len(intervals),'eligible_gaps_containing_rejected_messages':sum(x['returned_message_timestamps_inside']>0 for x in intervals),
            'raw_message_gaps_over_300':len(raw_gaps),'raw_message_gaps':[dict(zip(['session','start_ns','end_ns','seconds'],r)) for r in raw_gaps],
            'eligible_gap_details':intervals,'halt_or_feed_loss_verified':False})
        outside.extend({'ticker':opportunity['ticker'],'cycle_id':opportunity['cycle_id'],'sip_timestamp':t,
                        'price':p,'source_json':source} for t,p,source in unusual)
    result={'scope':'REPAIRED_45_PROVIDER_WINDOWS','windows':gaps,'raw_records_outside_defined_sessions':outside,
        'eligible_gaps_over_300':sum(g['eligible_gaps_over_300'] for g in gaps),
        'eligible_gaps_containing_rejected_messages':sum(g['eligible_gaps_containing_rejected_messages'] for g in gaps),
        'raw_message_gaps_over_300':sum(g['raw_message_gaps_over_300'] for g in gaps),
        'interpretation':'Cursor-complete provider messages distinguish API truncation from returned-stream quiet periods. Neither an illiquidity diagnosis nor an authoritative halt/feed-loss determination.'}
    write_json(dest/'raw-versus-filtered-gaps.json',result)
    return result


def condition_summary(config):
    _,_,dest=roots(config)
    full=json.loads((dest/'condition-distributions.json').read_text())
    rows=full['rows'];panels=[];per_code=Counter()
    for variant in ['QA_UNREPAIRED','QA_REPAIRED']:
        for session in ['AH','PRE','RTH','UNOBSERVED_OVERNIGHT']:
            data=[r for r in rows if r['variant']==variant and r['session']==session]
            panel={'variant':variant,'session':session,'policy_counts':{}}
            for policy in ['LEGACY_BOTH','HIGH_LOW_ONLY','ODD_LOT_OBSERVATION_SENSITIVITY']:
                selected=[r for r in data if r['policy']==policy]
                panel['policy_counts'][policy]={'accepted':sum(r['trades'] for r in selected if r['accepted']),
                    'rejected':sum(r['trades'] for r in selected if not r['accepted'])}
            panel['high_low_minus_both_accepted']=panel['policy_counts']['HIGH_LOW_ONLY']['accepted']-panel['policy_counts']['LEGACY_BOTH']['accepted']
            panels.append(panel)
    for r in rows:
        for code in r['codes'] or [0]:
            per_code[(r['variant'],r['session'],r['policy'],code,r['accepted'],r['reason'])]+=r['trades']
    result={'session_panels':panels,'per_code_overlapping_counts':[{'variant':v,'session':s,'policy':p,'code':c,'accepted':a,'reason':reason,'trades':n}
        for (v,s,p,c,a,reason),n in sorted(per_code.items())],
        'rule_notes':['High/low-only retains the explicit vetoes for 5/10/22/32 and other stale/reference conditions.',
                      'Form T is accepted only in AH/PRE; a second rejecting condition still rejects the whole print.',
                      'Odd lots are separate raw-observation sensitivity, not declared official last/high-low forming trades.']}
    write_json(dest/'condition-audit-summary.json',result)
    return result


def publish(config):
    base,root,dest=roots(config)
    events=records(root/'events/events.parquet');outcomes=records(root/'outcomes/outcomes.parquet')
    opportunities=records(root/'opportunities/opportunities.parquet')
    write_json(dest/'event-level-results.json',{'run_id':config['run_id'],'composite_event_key':['variant','condition_policy','event_id'],
        'events':events,'outcomes':outcomes,'opportunities':opportunities,
        'counts':{'event_policy_variant_records':len(events),'outcome_gap_policy_records':len(outcomes),'opportunity_policy_variant_records':len(opportunities)},
        'sampling':False,'scope':'ALL_FIRST_TOUCH_RESULTS_AND_SENSITIVITY_VARIANTS_OF_THE_FROZEN_PILOT; not independent event counts'})
    requested=audit_requested(config,events)
    gaps=raw_gap_audit(config)
    condition_summary(config)
    selection=json.loads((base/'selection.json').read_text())
    summary=json.loads((dest/'summary.json').read_text())
    main=[g for g in summary['groups'] if g['variant']=='QA_REPAIRED' and g['condition_policy']=='HIGH_LOW_ONLY']
    write_json(dest/'primary-cohort-results.json',{'groups':main,'sample_frame':dict(Counter(r['sample'] for r in selection['selected'])),
        'opportunity_exclusions':[r for r in opportunities if r['variant']=='HISTORICAL_EXCLUDED_UNCHANGED'],
        'cohort_definitions':{'EXCHANGE_PRICE_ONLY':'Frozen M1 non-float gates; original name is shorthand, not a change to those gates.',
            'MASSIVE_CURRENT_FLOAT_PROXY':'Original frozen latest-float evidence/mapping; retrospective proxy, never PIT.',
            'SEC_HISTORICAL_EVIDENCE_OVERLAP':'Security appears in original SEC pilot context, regardless of estimate usability; no carry-forward or historical float qualification.'}})
    manifest={'run_id':config['run_id'],'baseline_commit':config['baseline_commit'],'methodology_version':config['methodology_version'],
        'config':config,'full_evidence_root':str(root.resolve()),'publisher_sha256':file_hash(__file__),
        'artifacts':{p.name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in dest.iterdir() if p.is_file() and p.name!='manifest.json'}}
    write_json(dest/'manifest.json',manifest)
    print(json.dumps({'event_records':len(events),'outcome_records':len(outcomes),'gap_intervals':gaps['eligible_gaps_over_300'],
                      'requested_audit_examples':[(a['ticker'],a['cycle_id'],a['relation']) for a in requested]},indent=2))


if __name__=='__main__':
    publish(json.loads(Path('configs/task-002-1-qa-v1.json').read_text()))
