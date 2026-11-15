"""Causal confirmation signals on a fixed first-touch event risk set."""
import bisect
import json
from copy import copy
from decimal import Decimal

from .replay_methodology import outcome_sensitivity
from .storage import digest
from .tick_replay import SECOND, bounds, correction_key, number, session_label


def causal_quote(rows, timestamp, config, complete=True):
    """Never consult later quotes, even to set a halt/quality flag."""
    prior = [q for q in rows if isinstance(q.get('sip_timestamp'), int) and q['sip_timestamp'] <= timestamp]
    if not prior:
        return {'status': 'MISSING', 'flags': ['NO_PRECEDING_NBBO'], 'complete': complete}
    q = prior[-1]
    flags = []
    bid, ask = number(q.get('bid_price')), number(q.get('ask_price'))
    if q.get('normalization_status') != 'OK':
        flags.append('INVALID_TIMESTAMP')
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        flags.append('INVALID_OR_CROSSED_NBBO')
    if any(number(q.get(k)) is None or number(q[k]) <= 0 for k in ['bid_size', 'ask_size']):
        flags.append('INVALID_OR_EMPTY_DISPLAYED_SIZE')
    if timestamp - q['sip_timestamp'] > config['max_quote_age_seconds'] * SECOND:
        flags.append('STALE_NBBO')
    if any(c not in {0, 1} for c in json.loads(q.get('conditions_json', '[]'))):
        flags.append('NON_REGULAR_QUOTE_CONDITION')
    if not complete:
        flags.append('INCOMPLETE_QUOTE_WINDOW')
    return {'status': 'OK' if not flags else 'FLAGGED', 'flags': flags, 'complete': complete,
            'bid': str(bid) if bid is not None else None, 'ask': str(ask) if ask is not None else None,
            'timestamp': q['sip_timestamp'], 'age_ns': timestamp - q['sip_timestamp'],
            'record_id': q['record_id'], 'source_json': q['source_json']}


def signal_result(policy, status, reason, timestamp=None, price=None, evidence=None, **extra):
    return {'signal_policy': policy, 'status': status, 'reason': reason,
            'signal_timestamp': timestamp, 'market_observation_price': str(price) if price is not None else None,
            'evidence': evidence or [], **extra}


def trade_confirmation(state, initial, cycle, config, notices):
    threshold = number(initial['threshold_price'])
    start = initial['event_timestamp']
    eligible = state.eligible
    anchor_index = next(i for i, r in enumerate(eligible) if r['record_id'] == initial['record_id'])
    candidates = {}
    seen = set()
    last_session = None
    notice_index = 0
    by_key = {}
    subthreshold = 0
    for row in eligible[anchor_index:]:
        if row['record_id'] in seen:
            continue
        seen.add(row['record_id'])
        t = row['sip_timestamp']
        # AH -> PRE/RTH crosses the unobserved interval; its elapsed clock
        # cannot establish a persistence span. PRE -> RTH is contiguous.
        if last_session == 'AH' and row['session'] != 'AH':
            candidates.clear()
            by_key.clear()
        last_session = row['session']
        while notice_index < len(notices) and notices[notice_index]['sip_timestamp'] <= t:
            notice = notices[notice_index]
            for rid in by_key.get(correction_key(notice), []):
                candidates.pop(rid, None)
            notice_index += 1
        if number(row['price']) < threshold:
            subthreshold += 1
            continue
        candidates[row['record_id']] = row
        by_key.setdefault(correction_key(row), []).append(row['record_id'])
        if len(candidates) >= config['c1_min_observations']:
            first = next(iter(candidates.values()))
            if t - first['sip_timestamp'] >= config['c1_min_span_seconds'] * SECOND:
                # Minimal sufficient source-linked proof, plus complete count.
                proof = list(candidates.values())[:config['c1_min_observations'] - 1] + [row]
                return signal_result('C1', 'CONFIRMED', 'THREE_TRADES_WITH_MINIMUM_SPAN', t, row['price'],
                    [{'record_id': r['record_id'], 'timestamp': r['sip_timestamp'], 'source_json': r['source_json'],
                      'restoration_source': r.get('restoration_source')} for r in proof],
                    qualifying_count=len(candidates), qualifying_span_ns=t - first['sip_timestamp'],
                    intervening_subthreshold_trades=subthreshold, trade_record_id=row['record_id'],
                    market_price_timestamp=t, market_price_source=row['source_json'])
    status = 'UNCONFIRMED' if state.complete and not any(t is None or t >= start for t in state.unknown_times) else 'INSUFFICIENT_DATA'
    return signal_result('C1', status, 'INSUFFICIENT_QUALIFYING_TRADES_OR_SPAN_BY_CYCLE_END',
                         qualifying_count=len(candidates), intervening_subthreshold_trades=subthreshold)


def bid_confirmation(state, initial, cycle, config, quotes, coverage):
    start = initial['event_timestamp']
    deadline = min(start + config['c2_window_seconds'] * SECOND, bounds(cycle)[-1])
    req = coverage.get('request', {})
    complete = bool(coverage.get('complete') and req.get('start_ns', start) < start
                    and req.get('end_ns', 0) >= deadline)
    if not complete:
        return signal_result('C2', 'INSUFFICIENT_DATA', 'MISSING_OR_INCOMPLETE_60_SECOND_NBBO_COVERAGE',
                             quote_coverage_complete=False, evaluation_deadline=deadline)
    threshold = number(initial['threshold_price'])
    samples = [(start, causal_quote(quotes, start, config, complete))]
    samples += [(q['sip_timestamp'], causal_quote([q], q['sip_timestamp'], config, complete))
                for q in quotes if start < q['sip_timestamp'] <= deadline]
    first, previous = None, None
    fresh = 0
    below = 0
    resets = 0
    for t, quote in samples:
        if session_label(cycle, t) not in {'AH', 'PRE', 'RTH'}:
            first, previous = None, None
            continue
        valid = quote['status'] == 'OK'
        if valid:
            fresh += 1
        if not valid or number(quote.get('bid')) < threshold:
            below += valid
            resets += first is not None
            first, previous = None, None
            continue
        if previous and (t - previous[0] > config['max_quote_age_seconds'] * SECOND
                         or previous[1]['timestamp'] + config['max_quote_age_seconds'] * SECOND < t):
            resets += 1
            first = None
        if first is None:
            first = (t, quote)
        previous = (t, quote)
        if (t - first[0] >= config['c2_min_span_seconds'] * SECOND
                and quote['record_id'] != first[1]['record_id']):
            rows = state.eligible
            times = [r['sip_timestamp'] for r in rows]
            index = bisect.bisect_right(times, t) - 1
            mark = rows[index] if index >= 0 else None
            good_mark = mark is not None and t - mark['sip_timestamp'] <= config['max_mark_age_seconds'] * SECOND
            return signal_result('C2', 'CONFIRMED', 'FRESH_BID_OBSERVATIONS_SUSTAIN_THRESHOLD', t,
                mark['price'] if good_mark else None,
                [{'record_id': q['record_id'], 'timestamp': q['timestamp'], 'observed_at': when,
                  'source_json': q['source_json']} for when, q in [first, (t, quote)]],
                entry_nbbo=quote, qualifying_span_ns=t - first[0], fresh_quote_observations=fresh,
                quote_coverage_complete=True, evaluation_deadline=deadline, stale_or_below_resets=resets,
                market_price_timestamp=mark['sip_timestamp'] if good_mark else None,
                market_price_source=mark['source_json'] if good_mark else None,
                trade_record_id=mark['record_id'] if good_mark else None,
                market_price_status='FRESH_ASOF_TRADE_MARK' if good_mark else 'MISSING_OR_STALE_TRADE_MARK')
    reason = 'NO_SUSTAINED_BID_CONFIRMATION' if fresh else 'NO_FRESH_VALID_NBBO_OBSERVATIONS'
    return signal_result('C2', 'UNCONFIRMED' if fresh else 'INSUFFICIENT_DATA', reason,
                         quote_coverage_complete=True, fresh_quote_observations=fresh, below_threshold_observations=below,
                         evaluation_deadline=deadline, stale_or_below_resets=resets)


def confirmation_outcomes(state, initial, signal, cycle, config, notices, gap_seconds=None):
    if signal['status'] != 'CONFIRMED' or signal['market_observation_price'] is None:
        return None
    t = signal['signal_timestamp']
    s = copy(state)
    event = {**initial, 'event_timestamp': t, 'touch_price': signal['market_observation_price'],
             'session': session_label(cycle, t)}
    if signal['signal_policy'] == 'C2':
        # Explicit synthetic as-of marker; never represented as an actual trade.
        anchor = {'record_id': digest(['ASOF_MARK', t, signal['trade_record_id']]), 'sip_timestamp': t,
                  'price': signal['market_observation_price'], 'session': event['session'],
                  'source_json': signal['market_price_source'], 'synthetic_asof_marker': True}
        event['record_id'] = anchor['record_id']
        s.eligible = [anchor] + [r for r in state.eligible if r['sip_timestamp'] > t]
    else:
        event['record_id'] = signal['trade_record_id']
    s.event = event
    keys = {correction_key(r) for r in state.eligible if r['record_id'] in {v['record_id'] for v in signal['evidence']}}
    s.invalidations = sorted(set(state.invalidations + [n['sip_timestamp'] for n in notices if correction_key(n) in keys]))
    result = outcome_sensitivity(s, cycle, config, gap_seconds)
    result.update(signal_policy=signal['signal_policy'], price_basis='GROSS_ELIGIBLE_TRADE_MARK_NOT_EXECUTION',
                  signal_price_observation_timestamp=signal.get('market_price_timestamp'))
    return result


def execution_mark_estimates(signal, outcome, quotes, coverage, config):
    """Sparse ask-to-bid mark estimates, with no simulated fills or order sizes."""
    if signal['status'] != 'CONFIRMED':
        return {'status': 'NO_SIGNAL', 'marks': [], 'executable_pnl': None}
    entry = causal_quote(quotes, signal['signal_timestamp'], config, coverage.get('complete', False))
    marks = []
    for mark in outcome['forward'] if outcome else []:
        if mark['horizon'] not in {'5m', '15m', '30m', '60m'}:
            continue
        target = mark['target_ns']
        inside = coverage.get('request', {}).get('end_ns', 0) >= target
        exit_quote = causal_quote(quotes, target, config, coverage.get('complete', False)) if inside else {'status': 'OUTSIDE_QUOTE_COVERAGE'}
        good = entry['status'] == exit_quote['status'] == 'OK' and not mark['censored']
        marks.append({'horizon': mark['horizon'], 'target_ns': target, 'entry': entry, 'exit': exit_quote,
                      'ask_to_bid_mark_return': str(number(exit_quote['bid']) / number(entry['ask']) - 1) if good else None,
                      'status': 'QUOTE_MARK_ESTIMATE_NOT_FILL' if good else 'INSUFFICIENT_QUOTE_OR_PRICE_PATH_EVIDENCE'})
    return {'status': 'MARK_ESTIMATES_ONLY', 'entry': entry, 'marks': marks, 'executable_pnl': None}
