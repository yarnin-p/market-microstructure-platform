"""Causal quote-state replay, kept distinct from freshness and execution.

Invalid/latest observations invalidate state rather than resurrecting an older
valid quote. No carry across session boundaries or incomplete source intervals.
"""
import bisect
import json
from collections import defaultdict

from .confirmation import signal_result
from .tick_replay import SECOND, bounds, number, session_label


def valid_quote(q):
    flags=[]
    bid,ask=number(q.get('bid_price')),number(q.get('ask_price'))
    if q.get('normalization_status')!='OK':flags.append('INVALID_TIMESTAMP')
    if bid is None or ask is None or not 0<bid<=ask:flags.append('INVALID_OR_CROSSED_NBBO')
    if any(number(q.get(k)) is None or number(q[k])<=0 for k in ['bid_size','ask_size']):flags.append('INVALID_OR_EMPTY_DISPLAYED_SIZE')
    if any(c not in [0,1] for c in json.loads(q.get('conditions_json','[]'))):flags.append('NON_REGULAR_OR_CORRECTED_QUOTE')
    return not flags,flags


def quote_fingerprint(q):
    return tuple(str(q.get(k)) for k in ['bid_price','ask_price','bid_size','ask_size','bid_exchange','ask_exchange','conditions_json','indicators_json'])


class QuoteState:
    def __init__(self, quotes, intervals, cycle, fresh_seconds=5, state_seconds=60):
        self.quotes=sorted(quotes,key=lambda q:(q['sip_timestamp'],q.get('sequence_number') or 0,q['record_id']))
        self.times=[q['sip_timestamp'] for q in self.quotes]
        self.intervals=intervals;self.cycle=cycle;self.fresh=fresh_seconds*SECOND;self.max_state=state_seconds*SECOND
        groups=defaultdict(list)
        for q in self.quotes:groups[q['sip_timestamp']].append(q)
        # Deterministic last sequence wins when sequences distinguish observations.
        # Ambiguous unequal observations at the same SIP+sequence invalidate state.
        self.groups=dict(groups)
        self.ambiguous=set()
        for t,rows in groups.items():
            seq=defaultdict(set)
            for q in rows:seq[q.get('sequence_number')].add(quote_fingerprint(q))
            if any(len(v)>1 for v in seq.values()):self.ambiguous.add(t)
    def covered(self,start,end):
        merged=[]
        for a,b in sorted((i['start_ns'],i['end_ns']) for i in self.intervals if i['complete']):
            if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
            else:merged.append([a,b])
        return any(a<start and b>=end for a,b in merged)
    def asof(self,t):
        if not self.covered(t,t):return {'status':'SOURCE_COVERAGE_UNKNOWN','valid':False,'fresh':False,'evaluation_ns':t}
        label=session_label(self.cycle,t)
        if label not in ['AH','PRE','RTH']:return {'status':'OUTSIDE_OBSERVED_SESSION','valid':False,'fresh':False,'evaluation_ns':t}
        i=bisect.bisect_right(self.times,t)-1
        if i<0:return {'status':'NO_QUOTE_UPDATE_OBSERVED','valid':False,'fresh':False,'evaluation_ns':t}
        q=self.quotes[i];age=t-q['sip_timestamp'];ok,flags=valid_quote(q)
        if not self.covered(q['sip_timestamp'],t):flags.append('UNKNOWN_COVERAGE_SINCE_UPDATE')
        if session_label(self.cycle,q['sip_timestamp'])!=label:flags.append('SESSION_RESET')
        if q['sip_timestamp'] in self.ambiguous:flags.append('AMBIGUOUS_SAME_SIP_SEQUENCE')
        if age>self.max_state:flags.append('STATE_AGE_LIMIT_EXCEEDED')
        valid=ok and not flags
        return {'status':'QUOTE_STATE_AVAILABLE' if valid else 'QUOTE_STATE_INVALID_OR_STALE','valid':valid,
            'fresh':valid and age<=self.fresh,'evaluation_ns':t,'quote_timestamp':q['sip_timestamp'],'age_ns':age,
            'bid':q.get('bid_price'),'ask':q.get('ask_price'),'bid_size':q.get('bid_size'),'ask_size':q.get('ask_size'),
            'locked':number(q.get('bid_price')) is not None and number(q.get('bid_price'))==number(q.get('ask_price')),
            'flags':flags,'record_id':q['record_id'],'source_json':q['source_json'],
            'state_persistence_not_executable_liquidity':True}


def state_confirmation(replay, trade_state, initial, cycle, config):
    start=initial['event_timestamp'];deadline=min(start+config['c2_deadline_seconds']*SECOND,bounds(cycle)[-1])
    policy='C2_S3_STATE_BASED';threshold=number(initial['threshold_price'])
    if not replay.covered(start,deadline):return signal_result(policy,'INSUFFICIENT_DATA','SOURCE_COVERAGE_UNKNOWN',evaluation_deadline=deadline)
    times=sorted(set([start,deadline]+[t for t in replay.times if start<t<=deadline]+[b for b in bounds(cycle) if start<b<=deadline]))
    index=0;support=None;proof=None;previous=None;resets=0;seen_valid=False;seen_unknown=False;t=start
    while t<=deadline:
        state=replay.asof(t);seen_valid|=state['valid'];seen_unknown|=state['status'] in ['SOURCE_COVERAGE_UNKNOWN','NO_QUOTE_UPDATE_OBSERVED']
        supported=state['valid'] and number(state['bid'])>=threshold
        continuity=previous and (session_label(cycle,t)!=session_label(cycle,previous['evaluation_ns']) or
            (previous.get('quote_timestamp') is not None and t-previous['quote_timestamp']>config['max_state_age_seconds']*SECOND))
        group_break=any(not valid_quote(q)[0] or number(q.get('bid_price'))<threshold for q in replay.groups.get(t,[]))
        if group_break and support is not None and t>start:
            resets+=1;support=None;proof=None
        if not supported:
            resets+=support is not None;support=None;proof=None
        elif support is None or continuity:
            resets+=bool(continuity and support is not None);support=t;proof=state
        if supported and support is not None and t-support>=config['c2_min_span_seconds']*SECOND:
            trade_times=[r['sip_timestamp'] for r in trade_state.eligible]
            j=bisect.bisect_right(trade_times,t)-1;mark=trade_state.eligible[j] if j>=0 else None
            good=mark is not None and t-mark['sip_timestamp']<=60*SECOND
            return signal_result(policy,'CONFIRMED','CAUSAL_STATE_TIMER_REACHED',t,mark['price'] if good else None,
                [{'record_id':q['record_id'],'timestamp':q['quote_timestamp'],'observed_at':q['evaluation_ns'],'source_json':q['source_json']} for q in [proof,state]],
                state_age_ns=state['age_ns'],fresh_at_confirmation=state['fresh'],state_support_start=support,
                timer_not_second_quote_update=proof['record_id']==state['record_id'],entry_nbbo=state,
                trade_record_id=mark['record_id'] if good else None,market_price_timestamp=mark['sip_timestamp'] if good else None,
                market_price_source=mark['source_json'] if good else None,evaluation_deadline=deadline,resets=resets)
        previous=state
        while index<len(times) and times[index]<=t:index+=1
        next_observation=times[index] if index<len(times) else deadline+1
        timer=support+config['c2_min_span_seconds']*SECOND if support is not None else deadline+1
        next_t=min(next_observation,timer if timer>t else deadline+1)
        if next_t<=t:raise AssertionError('Non-advancing quote-state clock')
        t=next_t
    return signal_result(policy,'UNCONFIRMED' if seen_valid else 'INSUFFICIENT_DATA',
        'NO_STATE_SUPPORT_WITHIN_FROZEN_DEADLINE',evaluation_deadline=deadline,resets=resets,
        valid_state_seen=seen_valid,missing_or_unknown_state_seen=seen_unknown,
        unconfirmed_is_not_proof_of_market_support_failure=True)
