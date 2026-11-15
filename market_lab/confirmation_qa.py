"""TASK 003.1 policies. The TASK 003 implementation remains unchanged."""
import json
from collections import Counter, defaultdict
from copy import copy

from .confirmation import causal_quote, signal_result, trade_confirmation
from .tick_replay import SECOND, bounds, correction_key, gaps_for, number, session_label


def c1_signal(state, initial, cycle, config, notices, definition, deadline_seconds=None):
    end = bounds(cycle)[-1]
    if deadline_seconds is not None:
        end = min(end, initial['event_timestamp'] + deadline_seconds * SECOND)
    if definition == 'C1_SESSION_BOUND':
        end = min(end, {'AH': bounds(cycle)[1], 'PRE': bounds(cycle)[3], 'RTH': bounds(cycle)[4]}[initial['session']])
    limited = copy(state)
    limited.eligible = [r for r in state.eligible if r['sip_timestamp'] <= end and
                        (definition != 'C1_SESSION_BOUND' or r['session'] == initial['session'])]
    limited.unknown_times = [t for t in state.unknown_times if t is None or t <= end]
    if definition != 'C1_OBSERVED_ACCEPTANCE':
        result = trade_confirmation(limited, initial, cycle, config, notices)
    else:
        candidates, seen = {}, set()
        by_key = defaultdict(list)
        notice_index, resets = 0, 0
        last_session = None
        result = None
        start_index = next(i for i,r in enumerate(limited.eligible) if r['record_id'] == initial['record_id'])
        for row in limited.eligible[start_index:]:
            if row['record_id'] in seen:
                continue
            seen.add(row['record_id'])
            t = row['sip_timestamp']
            if last_session == 'AH' and row['session'] != 'AH':
                candidates.clear(); by_key.clear()
            last_session = row['session']
            while notice_index < len(notices) and notices[notice_index]['sip_timestamp'] <= t:
                notice = notices[notice_index]
                for rid in by_key.get(correction_key(notice), []):
                    candidates.pop(rid, None)
                notice_index += 1
            if number(row['price']) < number(initial['threshold_price']):
                resets += bool(candidates)
                candidates.clear(); by_key.clear()
                continue
            candidates[row['record_id']] = row
            by_key[correction_key(row)].append(row['record_id'])
            first = next(iter(candidates.values()))
            if len(candidates) >= config['c1_min_observations'] and t-first['sip_timestamp'] >= config['c1_min_span_seconds']*SECOND:
                proof = list(candidates.values())[:config['c1_min_observations']-1]+[row]
                result = signal_result('C1','CONFIRMED','OBSERVED_ACCEPTANCE_SPAN',t,row['price'],
                    [{'record_id':r['record_id'],'timestamp':r['sip_timestamp'],'source_json':r['source_json'],
                      'restoration_source':r.get('restoration_source')} for r in proof],
                    qualifying_count=len(candidates),qualifying_span_ns=t-first['sip_timestamp'],
                    below_threshold_resets=resets,trade_record_id=row['record_id'],market_price_timestamp=t,
                    market_price_source=row['source_json'])
                break
        if result is None:
            result = signal_result('C1','UNCONFIRMED','OBSERVED_ACCEPTANCE_NOT_MET',below_threshold_resets=resets)
    start = initial['event_timestamp']
    candidate = result['signal_timestamp']
    until = candidate if candidate is not None else end
    if not state.complete or any(t is None or start <= t <= until for t in limited.unknown_times):
        result.update(status='INSUFFICIENT_DATA',reason='UNKNOWN_OR_INCOMPLETE_CONFIRMATION_EVIDENCE')
    if result['status'] == 'UNCONFIRMED' and deadline_seconds is not None:
        result['reason'] = 'NOT_CONFIRMED_BY_PREDECLARED_60_SECOND_DEADLINE'
    return result, end


def path_flags(state, initial, signal, cycle, config, notices, until):
    start = signal['signal_timestamp']
    flags = []
    if not state.complete:
        flags.append('INCOMPLETE_TRADE_WINDOW')
    if until > bounds(cycle)[-1]:
        flags.append('BEYOND_CYCLE_END')
    for a,b,kind in gaps_for(state.eligible,cycle,{**config,'intertrade_gap_seconds':10**12}):
        if a < until and b > start:
            flags.append(kind)
    if any(t is None or start < t <= until for t in state.unknown_times):
        flags.append('UNKNOWN_PATH_PRICE_EVIDENCE')
    ids = {initial['record_id']} | {e['record_id'] for e in signal.get('evidence',[])}
    keys = {correction_key(r) for r in state.eligible if r['record_id'] in ids}
    if any(n['sip_timestamp'] <= until and correction_key(n) in keys for n in notices):
        flags.append('INITIAL_OR_CONFIRMATION_EVIDENCE_INVALIDATED')
    return sorted(set(flags))


def common_marks(state, initial, signal, cycle, config, notices):
    marks = []
    for minute in config['landmarks_minutes']:
        target = initial['event_timestamp'] + minute*60*SECOND
        candidates = [r for r in state.eligible if initial['event_timestamp'] <= r['sip_timestamp'] <= min(target,bounds(cycle)[-1])]
        mark = candidates[-1] if candidates else None
        age = target-mark['sip_timestamp'] if mark else None
        confirmed = signal['status']=='CONFIRMED'
        before = confirmed and signal['signal_timestamp'] <= target
        flags = []
        if not before:
            status = 'NOT_YET_CONFIRMED' if confirmed else signal['status']
        else:
            flags = path_flags(state,initial,signal,cycle,config,notices,target)
            if not mark or age > config['max_mark_age_seconds']*SECOND or mark['sip_timestamp'] < signal['signal_timestamp']:
                flags.append('MISSING_OR_STALE_POST_SIGNAL_EXIT_MARK')
            if signal['market_observation_price'] is None:
                flags.append('MISSING_SIGNAL_TRADE_MARK')
            status = 'CENSORED' if flags else 'OBSERVED'
        value = (number(mark['price'])/number(signal['market_observation_price'])-1) if status=='OBSERVED' else None
        marks.append({'landmark_minutes':minute,'target_ns':target,'confirmed_before_or_at_landmark':before,
            'status':status,'flags':sorted(set(flags)),'return':str(value) if value is not None else None,
            'exit_price':mark['price'] if mark else None,'exit_observation_ns':mark['sip_timestamp'] if mark else None,
            'exit_age_ns':age,'exit_source_json':mark['source_json'] if mark else None,
            'entry_price':signal['market_observation_price'] if before else None,
            'entry_timestamp':signal['signal_timestamp'] if before else None})
    return marks


def waiting_path(state, initial, signal, cycle, config, notices, operational_end):
    end = signal['signal_timestamp'] if signal['status']=='CONFIRMED' else operational_end
    t0 = initial['event_timestamp']
    anchor = next(r for r in state.eligible if r['record_id']==initial['record_id'])
    rows = [anchor]+[r for r in state.eligible if t0 < r['sip_timestamp'] < end]
    high=max(rows,key=lambda r:number(r['price'])); low=min(rows,key=lambda r:number(r['price']))
    reference={**signal,'signal_timestamp':t0,'evidence':[]}
    flags=path_flags(state,initial,reference,cycle,config,notices,end)
    if end-rows[-1]['sip_timestamp'] > config['max_mark_age_seconds']*SECOND:
        flags.append('STALE_END_OF_WAITING_PATH')
    entry=number(initial['touch_price'])
    barriers=[]
    groups=defaultdict(list)
    for r in rows[1:]:groups[r['sip_timestamp']].append(r)
    for up,down in config['barriers']:
        first=None
        for stamp,group in sorted(groups.items()):
            upper=any(number(r['price']) >= entry*(1+number(up)) for r in group)
            lower=any(number(r['price']) <= entry*(1-number(down)) for r in group)
            if upper or lower:
                first={'timestamp':stamp,'direction':'AMBIGUOUS_SAME_SIP' if upper and lower else 'UPSIDE_FIRST' if upper else 'DOWNSIDE_FIRST',
                       'sources':[r['source_json'] for r in group if number(r['price']) >= entry*(1+number(up)) or number(r['price']) <= entry*(1-number(down))],
                       'flags':path_flags(state,initial,reference,cycle,config,notices,stamp)}
                break
        barriers.append({'up':up,'down':down,'first_observed_crossing':first})
    return {'start_ns':t0,'end_exclusive_ns':end,'end_reason':'SIGNAL' if signal['status']=='CONFIRMED' else 'OPERATIONAL_CUTOFF_WITHOUT_SIGNAL',
        'mfe':str(number(high['price'])/entry-1),'mae':str(number(low['price'])/entry-1),
        'mfe_ns':high['sip_timestamp'],'mae_ns':low['sip_timestamp'],'mfe_source':high['source_json'],'mae_source':low['source_json'],
        'flags':sorted(set(flags)),'censored':bool(flags),'observed_trade_count':len(rows),'barriers':barriers}


def quote_audit(quotes, initial, cycle, config, baseline_signal):
    start=initial['event_timestamp']; end=min(start+60*SECOND,bounds(cycle)[-1])
    initial_quote=causal_quote(quotes,start,config)
    updates=[q for q in quotes if start < q['sip_timestamp'] <= end]
    observations=[(start,initial_quote)]+[(q['sip_timestamp'],causal_quote([q],q['sip_timestamp'],config)) for q in updates]
    above,below,invalid,gaps,breaks=0,0,0,0,0
    support=None; previous=None; previous_quote_timestamp=None; max_span=0
    timeline=[]
    for t,q in observations:
        valid=q['status']=='OK'
        is_above=valid and number(q['bid']) >= number(initial['threshold_price'])
        is_below=valid and not is_above
        if support is not None and previous and (t-previous > config['max_quote_age_seconds']*SECOND or
                previous_quote_timestamp+config['max_quote_age_seconds']*SECOND < t):
            gaps+=1; support=None
        if valid:
            above+=is_above; below+=is_below
            if is_below:
                breaks+=support is not None; support=None
            elif support is None:
                support=t
            else:max_span=max(max_span,t-support)
        else:
            invalid+=1; support=None
        if support is not None:previous=t;previous_quote_timestamp=q['timestamp']
        timeline.append({'observed_at':t,'quote':q,'bid_at_or_above_threshold':is_above,'explicit_below_threshold':is_below})
    if support is not None and previous is not None and end-previous > config['max_quote_age_seconds']*SECOND:
        gaps+=1
    flags=Counter(f for _,q in observations for f in q.get('flags',[]))
    no_returned=not any(start-60*SECOND <= q['sip_timestamp'] <= end for q in quotes)
    prior_support=initial_quote['status']=='OK' and number(initial_quote['bid'])>=number(initial['threshold_price'])
    if baseline_signal['status']=='CONFIRMED':assessment='FROZEN_SUPPORT_CONFIRMED'
    elif no_returned:assessment='NO_QUOTE_RETURNED'
    elif above==below==0:
        assessment='INVALID_OR_CORRECTED_QUOTES' if flags['NON_REGULAR_QUOTE_CONDITION'] or flags['INVALID_OR_CROSSED_NBBO'] else 'STALE_OR_NO_FRESH_UPDATES'
    elif breaks:assessment='EXPLICIT_OBSERVED_SUPPORT_BREAK'
    elif below and not above:assessment='EXPLICIT_BELOW_THRESHOLD_BID'
    elif gaps:assessment='SUPPORT_UNPROVEN_FRESHNESS_GAPS_NOT_FAILURE'
    else:assessment='INSUFFICIENT_OBSERVED_SUPPORT_DURATION'
    return {'initial_event_id':initial['event_id'],'ticker':initial['ticker'],'cycle_id':initial['cycle_id'],
        'frozen_status':baseline_signal['status'],'frozen_reason':baseline_signal['reason'],'assessment':assessment,
        'no_quote_returned':no_returned,'returned_updates':len(updates),'initial_quote':initial_quote,
        'invalid_or_corrected_observations':invalid,'rejection_flags_overlapping':dict(flags),
        'stale_preceding_quote':'STALE_NBBO' in initial_quote.get('flags',[]),
        'no_updates_despite_prior_fresh_valid_support':not updates and prior_support,
        'no_updates_after_touch':not updates,'explicit_below_threshold_observations':below,
        'above_threshold_observations':above,'observed_support_breaks':breaks,'freshness_gaps_after_support':gaps,
        'longest_observed_support_span_seconds':max_span/SECOND,'timeline':timeline,
        'continuous_support_independently_verified':False,'missing_update_implies_failure':False}
