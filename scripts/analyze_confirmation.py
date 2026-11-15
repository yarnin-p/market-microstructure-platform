"""Risk-set, weight, waiting-risk and gap sensitivity checks for TASK 003."""
import json
from collections import Counter
from pathlib import Path

from market_lab.confirmation_pilot import read, stats, quotes_for
from market_lab.confirmation import causal_quote
from market_lab.storage import file_hash, write_json


def weighted_mean(pairs):
    pairs = [(float(v), float(w)) for v, w in pairs if v is not None]
    total = sum(w for _, w in pairs)
    return sum(v*w for v, w in pairs)/total if total else None


def gap_panel(rows, gap):
    result = {'initial_denominator': len(rows), 'gap_policy': gap, 'forward': {}, 'barriers': {}}
    for horizon in ['5m','15m','30m','60m']:
        values = []
        buckets = Counter()
        for r in rows:
            outcome = next((o for o in r['outcomes'] if o['gap_policy'] == gap), None)
            mark = next((m for m in outcome['forward'] if m['horizon'] == horizon), None) if outcome else None
            status = r['signal']['status']
            bucket = ('UNCONFIRMED' if status == 'UNCONFIRMED' else 'INSUFFICIENT_DATA' if status == 'INSUFFICIENT_DATA'
                      else 'NO_TRADE_MARK' if not mark else 'CENSORED' if mark['censored'] else 'OBSERVED')
            buckets[bucket] += 1
            if mark and not mark['censored']:
                values.append((mark['return'], r['sampling_weight']))
        assert sum(buckets.values()) == len(rows)
        result['forward'][horizon] = {'initial_population_buckets': dict(buckets), 'observed_distribution': stats(v for v,_ in values),
            'observed_weighted_mean': weighted_mean(values), 'weighted_mean_scope': 'Conditional uncensored selected events, not unconditional strategy return'}
    for up, down in [('0.03','0.03'),('0.05','0.03'),('0.10','0.05')]:
        buckets = Counter()
        for r in rows:
            outcome = next((o for o in r['outcomes'] if o['gap_policy'] == gap), None)
            barrier = next((b for b in outcome['barriers'] if (b['up'],b['down']) == (up,down)), None) if outcome else None
            buckets[barrier['outcome'] if barrier else r['signal']['status']] += 1
        assert sum(buckets.values()) == len(rows)
        result['barriers'][up+'/'+down] = dict(buckets)
    return result


def comparisons(rows):
    by_key = {(r['initial_event_id'],r['condition_policy'],r['signal']['signal_policy']):r for r in rows}
    pairs = []
    for condition in ['HIGH_LOW_ONLY','ODD_LOT_OBSERVATION_SENSITIVITY']:
        for policy in ['C1','C2']:
            chosen = [r for r in rows if r['condition_policy'] == condition and r['signal']['signal_policy'] == policy]
            waiting = Counter()
            for r in chosen:
                if r['signal']['status'] != 'CONFIRMED':
                    waiting[r['signal']['status']] += 1
                    continue
                barrier = next(b for b in r['initial_c0_barriers'] if b['up'] == '0.03' and b['down'] == '0.03')
                category = barrier['observed_direction'] if barrier['occurred_before_signal'] else 'NO_REPORTED_BARRIER_BEFORE_SIGNAL'
                if barrier['outcome'] == 'CENSORED' and barrier['occurred_before_signal']:
                    category = 'CENSORED_PRE_SIGNAL_PATH'
                waiting[category] += 1
            assert sum(waiting.values()) == 40
            pairs.append({'condition_policy':condition,'signal_policy':policy,'initial_denominator':40,
                'c0_3pct_barrier_before_signal_population_buckets':dict(waiting),
                'note':'A prior C0 barrier is waiting-risk context, not a trade loss/profit, and own-signal windows differ.'})
    odd = []
    for policy in ['C0','C1','C2']:
        base = [r for r in rows if r['condition_policy']=='HIGH_LOW_ONLY' and r['signal']['signal_policy']==policy]
        pairs_of_rows = [(r,by_key[r['initial_event_id'],'ODD_LOT_OBSERVATION_SENSITIVITY',policy]) for r in base]
        odd.append({'signal_policy':policy,'same_initial_events':len(base),
            'primary_confirmed':sum(a['signal']['status']=='CONFIRMED' for a,b in pairs_of_rows),
            'odd_confirmed':sum(b['signal']['status']=='CONFIRMED' for a,b in pairs_of_rows),
            'status_changes':sum(a['signal']['status']!=b['signal']['status'] for a,b in pairs_of_rows),
            'signal_time_changes':sum(a['signal']['signal_timestamp']!=b['signal']['signal_timestamp'] for a,b in pairs_of_rows),
            'market_price_changes':sum(a['signal']['market_observation_price']!=b['signal']['market_observation_price'] for a,b in pairs_of_rows)})
    return pairs,odd


def analyze(config):
    dest = Path('reports',config['run_id'])
    rows = read(dest/'event-level-results.json')['records']
    panels = []
    for condition in config['condition_policies']:
        for stratum in ['ALL','PROXY_FLOAT_IN_RANGE','OTHER_EXCHANGE_PRICE_ELIGIBLE']:
            for signal in config['signal_policies']:
                chosen = [r for r in rows if r['condition_policy']==condition and r['signal']['signal_policy']==signal
                          and (stratum=='ALL' or r['stratum']==stratum)]
                panels.append({'condition_policy':condition,'stratum':stratum,'signal_policy':signal,
                    'gaps':[gap_panel(chosen,g) for g in ['NO_MECHANICAL_GAP','GAP_300_SECONDS','GAP_900_SECONDS']]})
    pairs,odd = comparisons(rows)
    primary = [r for r in rows if r['condition_policy']=='HIGH_LOW_ONLY']
    quote_missingness = []
    for r in primary:
        if r['signal']['signal_policy'] != 'C2' or r['signal']['status'] != 'INSUFFICIENT_DATA':
            continue
        source = Path('data/runs',config['source_run'],'ticks','cycle='+r['cycle_id'],'security='+r['security_id'])
        quotes,_ = quotes_for(source)
        t = r['initial_event_timestamp']
        after = [q for q in quotes if t < q['sip_timestamp'] <= t+60_000_000_000]
        observations = [causal_quote(quotes,t,config)] + [causal_quote([q],q['sip_timestamp'],config) for q in after]
        flags = Counter(f for q in observations for f in q.get('flags',[]))
        quote_missingness.append({'initial_event_id':r['initial_event_id'],'ticker':r['ticker'],'cycle_id':r['cycle_id'],
            'returned_updates_within_60s':len(after),'asof_and_update_rejection_flags':dict(flags),
            'raw_update_condition_combinations':dict(Counter(q['conditions_json'] for q in after)),
            'provider_window_complete':r['signal']['quote_coverage_complete']})
    result = {'analysis_code_sha256':file_hash(__file__),'panels':panels,'waiting_risk':pairs,'odd_lot_sensitivity':odd,
        'c2_insufficient_observation_audit':quote_missingness,
        'quote_condition_source':{'url':'https://massive.com/glossary/conditions-indicators',
            'reviewed_at':'2026-11-15','code_81':'Corrected_Price',
            'policy':'Keep conservative regular 0/1 rule; do not treat corrected quote fields as original PIT NBBO'},
        'quote_estimates':{'primary_mark_statuses':dict(Counter(m['status'] for r in primary for m in r['quote_mark_estimates']['marks'])),
                          'executable_pnl_available':False},
        'c1_long_delays':[{'ticker':r['ticker'],'cycle_id':r['cycle_id'],'initial_session':r['initial_session'],
                          'signal_session':r['signal_session'],'delay_seconds':r['confirmation_delay_seconds'],
                          'qualifying_span_ns':r['signal'].get('qualifying_span_ns')}
                         for r in primary if r['signal']['signal_policy']=='C1' and r['confirmation_delay_seconds'] is not None
                         and r['confirmation_delay_seconds']>3600],
        'weight_scope':'Original cycle/stratum N/n; descriptive ratios on selected initial events, not universe or profitability inference'}
    write_json(dest/'sensitivity-analysis.json',result)
    # Independent reconciliations against the compact export and cohort totals.
    assert len(rows)==240 and len({r['initial_event_id'] for r in rows})==40
    groups=read(dest/'cohort_metrics.json')
    for group in groups:
        assert sum(group['signal_status_counts'].values())==group['initial_events']
        for f in group['forward'].values():
            assert sum(f['population_buckets'].values())==group['initial_events']
        for b in group['barriers'].values():
            assert sum(b['buckets'].values())==group['initial_events']
    write_json(dest/'analysis-validation.json',{'status':'PASS','initial_risk_set':40,'event_rows':240,
        'cohort_session_policy_groups':len(groups),'gap_stratum_policy_panels':len(panels),
        'all_initial_denominators_reconcile':True,'analysis_code_sha256':file_hash(__file__)})
    return result


if __name__=='__main__':
    result=analyze(read('configs/task-003-confirmation-v1.json'))
    print(json.dumps({'odd_lots':result['odd_lot_sensitivity'],'quote_estimates':result['quote_estimates'],
                      'c1_long_delays':result['c1_long_delays']},indent=2))
