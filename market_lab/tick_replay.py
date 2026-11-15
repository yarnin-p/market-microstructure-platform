"""Deterministic SIP replay; gross observations, never execution assumptions."""
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from functools import lru_cache

import pandas as pd

from .storage import digest

SECOND = 1_000_000_000


def ns(value):
    t = pd.Timestamp(value)
    if t.tzinfo is None:
        raise ValueError("timestamp must be timezone aware")
    return t.value


@lru_cache(maxsize=1000)
def _bounds(anchor, ah_end, pre, opened, end):
    return tuple(ns(x) for x in [anchor, ah_end, pre, opened, end])


def bounds(cycle):
    return _bounds(*(cycle[k] for k in ["anchor_at", "afterhours_end", "premarket_start", "rth_open", "end_at"]))


def session_label(cycle, t):
    anchor, ah_end, pre, opened, end = bounds(cycle)
    if not isinstance(t, int) or not anchor < t <= end:
        return "OUTSIDE_CYCLE"
    if t < ah_end:
        return "AH"
    if pre <= t < opened:
        return "PRE"
    if opened <= t <= end:
        return "RTH"
    return "UNOBSERVED_OVERNIGHT"


def number(value):
    try:
        d = Decimal(str(value))
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def correction_key(r):
    return (r.get("trade_id"), r.get("sequence_number"), r.get("exchange"), r.get("trf_id"), r.get("participant_timestamp"))


def restore_observed_records(rows):
    """Reconstruct original observed fields, not eligibility from future cancel tags.

    REST original correction=1 contains corrected data. Matching 12 retains the
    originally reported fields. Missing/ambiguous pairs cannot be reconstructed.
    Original 7/8 is observable at its own SIP time; later 11/10 invalidates it only
    when that notice arrives. Pair references remain auditable.
    """
    pairs = defaultdict(list)
    for row in rows:
        if row.get("correction") == 12:
            pairs[correction_key(row)].append(row)
    for row in rows:
        r = dict(row)
        r["restoration_status"] = "AS_RECORDED"
        if r.get("correction") == 1:
            match = [x for x in pairs[correction_key(r)] if (x["sip_timestamp"] or 0) > (r["sip_timestamp"] or 0)]
            if len(match) == 1:
                for key in ["price", "size", "conditions_json"]:
                    r[key] = match[0][key]
                r["restoration_status"] = "ORIGINAL_FIELDS_FROM_MATCHING_12"
                r["restoration_source"] = match[0]["source_json"]
            else:
                r["restoration_status"] = "CORRECTION_RECONSTRUCTION_UNRESOLVED"
        yield r


def eligible_trade(r, cycle, conditions, config):
    t = r.get("sip_timestamp")
    if r.get("normalization_status") != "OK":
        return False, "INVALID_TIMESTAMP"
    if r.get("restoration_status") == "CORRECTION_RECONSTRUCTION_UNRESOLVED":
        return False, "CORRECTION_RECONSTRUCTION_UNRESOLVED"
    correction = r.get("correction") or 0
    if correction not in {0, 1, 7, 8}:
        return False, "CORRECTION_OR_CANCEL_NOTICE"
    price, size = number(r.get("price")), number(r.get("size"))
    if price is None or price <= 0 or size is None or size <= 0:
        return False, "INVALID_PRICE_OR_SIZE"
    session = session_label(cycle, t)
    if session not in {"AH", "PRE", "RTH"}:
        return False, "OUTSIDE_OBSERVED_SESSION"
    participant = r.get("participant_timestamp")
    if participant is not None:
        if participant <= bounds(cycle)[0]:
            return False, "PRIOR_CYCLE_EXECUTION"
        if participant > t:
            return False, "PARTICIPANT_AFTER_SIP"
        if t - participant > config["max_participant_lag_seconds"] * SECOND:
            return False, "DELAYED_PRINT"
    codes = json.loads(r.get("conditions_json", "[]"))
    for code in codes:
        if code == 0:
            continue
        if code in {5, 10, 13, 22, 30, 31, 32, 33, 38}:
            return False, "OUT_OF_SEQUENCE_OR_REFERENCE_PRICE"
        if code == 12:
            if session not in {"AH", "PRE"}:
                return False, "FORM_T_OUTSIDE_EXTENDED_SESSION"
            continue
        condition = conditions.get(code)
        if condition is None:
            return False, "UNKNOWN_TRADE_CONDITION"
        if condition.get("type") in {"short_sale_restriction_indicator", "financial_status_indicator"}:
            continue
        rules = condition.get("update_rules", {}).get("consolidated", {})
        if not (rules.get("updates_high_low") is True and rules.get("updates_open_close") is True):
            return False, "NON_PRICE_FORMING_CONDITION"
    return True, "ELIGIBLE_OBSERVED_TRADE"


def chronological(rows):
    return sorted(rows, key=lambda r: (r.get("sip_timestamp") or 0, r.get("sequence_number") or 0,
                                      r.get("exchange") or 0, r.get("trade_id") or "", r["record_id"]))


def first_touch(rows, cycle, opportunity, config, conditions, complete, run_id, halt_intervals=None):
    threshold = Decimal(str(opportunity["previous_rth_close"])) * Decimal(config["trigger_multiplier"])
    restored = list(restore_observed_records(chronological(rows)))
    raw_crossing = None
    primary = None
    candidates, eligible, reject_counts = [], [], Counter()
    unknown_prior = False
    above = False
    invalidations = []
    first_key = None
    for r in restored:
        t, p = r.get("sip_timestamp"), number(r.get("price"))
        if p is not None and p >= threshold and raw_crossing is None:
            raw_crossing = r
        passed, reason = eligible_trade(r, cycle, conditions, config)
        if any(a <= (t or 0) <= b for a, b in (halt_intervals or [])):
            passed, reason = False, "KNOWN_HALT_INTERVAL"
        if not passed:
            reject_counts[reason] += 1
            if reason in {"UNKNOWN_TRADE_CONDITION", "CORRECTION_RECONSTRUCTION_UNRESOLVED", "INVALID_TIMESTAMP"} and primary is None:
                unknown_prior = True
            if p is not None and p >= threshold:
                candidates.append({"record_id": r["record_id"], "sip_timestamp": t, "candidate_status": "REJECTED", "reason": reason,
                                   "source_json": r["source_json"]})
        else:
            eligible.append(r)
            if p >= threshold and not above:
                if primary is None:
                    first_key = correction_key(r)
                    event_id = digest([opportunity["security_id"], cycle["cycle_id"], "first-touch-v1"])
                    flags = ["UNOBSERVED_OVERNIGHT", "RETROSPECTIVE_P0", "HALT_HISTORY_NOT_CERTIFIED"]
                    if not complete:
                        flags.append("INCOMPLETE_TRADE_PAGINATION")
                    if unknown_prior:
                        flags.append("UNKNOWN_PRIOR_PRICE_EVIDENCE")
                    # PRE/RTH observations cannot establish a first touch during
                    # the unobserved overnight interval. Preserve a narrower proof.
                    observed_verified = complete and not unknown_prior
                    full_cycle_verified = observed_verified and r["session"] == "AH"
                    primary = {"event_id": event_id, "run_id": run_id, "cycle_id": cycle["cycle_id"], "ticker": opportunity["ticker"],
                               "security_id": opportunity["security_id"], "sample": opportunity["sample"], "session": r["session"],
                               "event_timestamp": t, "previous_rth_close": str(opportunity["previous_rth_close"]),
                               "threshold_price": str(threshold), "touch_price": str(p), "record_id": r["record_id"],
                               "trade_size": r["size"], "trade_exchange": r["exchange"], "conditions_json": r["conditions_json"],
                               "correction": r.get("correction"), "source_json": r["source_json"],
                               "restoration_status": r["restoration_status"], "restoration_source": r.get("restoration_source"),
                               "first_touch_status": "VERIFIED_FIRST_TOUCH" if full_cycle_verified else "FIRST_TOUCH_UNVERIFIED",
                               "observed_window_first_verified": observed_verified, "quality_flags": flags,
                               "cohorts": opportunity["cohorts"], "float_proxy": opportunity.get("float_proxy"),
                               "sec_evidence": opportunity.get("sec_evidence", []), "later_invalidated": False}
                else:
                    candidates.append({"record_id": r["record_id"], "sip_timestamp": t, "candidate_status": "SUBSEQUENT_CROSSING",
                                       "reason": "NOT_AN_INDEPENDENT_FIRST_TOUCH", "source_json": r["source_json"]})
            above = p >= threshold
        if primary and r.get("correction") in {10, 11, 12} and correction_key(r) == first_key:
            invalidations.append(t)
            primary["later_invalidated"] = True
            primary["quality_flags"].append("LATER_CANCELLED_OR_CORRECTED")
    if primary:
        primary["raw_first_crossing"] = {k: raw_crossing.get(k) for k in ["record_id", "sip_timestamp", "price", "source_json"]} if raw_crossing else None
    return {"event": primary, "raw_first_crossing": raw_crossing, "candidates": candidates, "eligible": eligible,
            "reject_counts": dict(reject_counts), "invalidations": invalidations,
            "zero_event_status": None if primary else "ZERO_EVENT_OBSERVED" if complete and not unknown_prior else "UNKNOWN_INCOMPLETE"}


def gaps_for(eligible, cycle, config, halt_intervals=None):
    _, ah_end, pre, _, _ = bounds(cycle)
    gaps = [(ah_end, pre, "UNOBSERVED_OVERNIGHT")]
    for a, b in zip(eligible, eligible[1:]):
        if a["session"] == b["session"] and b["sip_timestamp"] - a["sip_timestamp"] > config["intertrade_gap_seconds"] * SECOND:
            gaps.append((a["sip_timestamp"], b["sip_timestamp"], "LONG_INTERTRADE_GAP_NOT_PROOF_OF_HALT"))
    gaps.extend((a, b, "KNOWN_HALT_INTERVAL") for a, b in (halt_intervals or []))
    return gaps


def outcomes(replay, cycle, config, complete, halt_intervals=None):
    event = replay["event"]
    if not event:
        return None
    all_rows = replay["eligible"]
    index = next(i for i, r in enumerate(all_rows) if r["record_id"] == event["record_id"])
    path = all_rows[index:]
    start = event["event_timestamp"]
    entry, p0 = Decimal(event["touch_price"]), Decimal(event["previous_rth_close"])
    _, ah_end, _, opened, end = bounds(cycle)
    session_end = ah_end if event["session"] == "AH" else opened if event["session"] == "PRE" else end
    gaps = gaps_for(all_rows, cycle, config, halt_intervals)

    def reasons(until):
        result = []
        if not complete:
            result.append("INCOMPLETE_TRADE_WINDOW")
        if any(a < until and b > start for a, b, _ in gaps):
            result.append("UNOBSERVED_INTERVAL_OR_TRADE_GAP")
        if any(t <= until for t in replay["invalidations"]):
            result.append("TOUCH_LATER_INVALIDATED")
        return result

    marks = []
    targets = [(f"{m}m", start + m * 60 * SECOND) for m in config["forward_minutes"]] + [("session_end", session_end), ("cycle_end", end)]
    for label, target in targets:
        flags = reasons(min(target, end))
        if target > end:
            flags.append("BEYOND_CYCLE_END")
        candidates = [r for r in path if r["sip_timestamp"] <= target and r["sip_timestamp"] <= end]
        mark = candidates[-1] if candidates else None
        age = target - mark["sip_timestamp"] if mark else None
        if mark is None or age > config["max_mark_age_seconds"] * SECOND:
            flags.append("MISSING_OR_STALE_MARK")
        # PRE end is the opening boundary: use the last PRE mark for session-end.
        if label == "session_end":
            candidates = [r for r in candidates if r["session"] == event["session"]]
            mark = candidates[-1] if candidates else None
            age = target - mark["sip_timestamp"] if mark else None
            if mark is None or age > config["max_mark_age_seconds"] * SECOND:
                flags.append("MISSING_OR_STALE_MARK")
        price = number(mark["price"]) if mark else None
        marks.append({"horizon": label, "clock": "WALL_CLOCK", "target_ns": target,
                      "mark_ns": mark["sip_timestamp"] if mark else None, "mark_age_ns": age,
                      "observed_mark_price": str(price) if price is not None else None,
                      "return": str(price / entry - 1) if price is not None and not flags else None,
                      "relative_to_p0": str(price / p0 - 1) if price is not None and not flags else None,
                      "censored": bool(flags), "flags": sorted(set(flags)), "source_json": mark["source_json"] if mark else None})
    hi = max(path, key=lambda r: Decimal(r["price"]))
    lo = min(path, key=lambda r: Decimal(r["price"]))
    barriers = []
    grouped = defaultdict(list)
    for r in path[1:]:
        grouped[r["sip_timestamp"]].append(r)
    for up, down in config["barriers"]:
        u, d = entry * (1 + Decimal(up)), entry * (1 - Decimal(down))
        result, hit, direction = None, None, None
        for t, group in sorted(grouped.items()):
            upper = any(Decimal(r["price"]) >= u for r in group)
            lower = any(Decimal(r["price"]) <= d for r in group)
            if upper or lower:
                direction = "AMBIGUOUS_SAME_SIP" if upper and lower else "UPSIDE_FIRST" if upper else "DOWNSIDE_FIRST"
                hit = t
                result = "CENSORED" if reasons(t) else direction
                break
        if result is None:
            result = "CENSORED" if reasons(end) or not path or end - path[-1]["sip_timestamp"] > config["max_mark_age_seconds"] * SECOND else "NEITHER"
        barriers.append({"up": up, "down": down, "up_price": str(u), "down_price": str(d), "outcome": result,
                         "observed_direction": direction, "first_passage_ns": hit, "elapsed_ns": hit - start if hit else None,
                         "flags": reasons(hit or end)})
    return {"event_id": event["event_id"], "cycle_id": cycle["cycle_id"], "security_id": event["security_id"],
            "ticker": event["ticker"], "sample": event["sample"], "session": event["session"],
            "forward": marks, "barriers": barriers, "window_start_ns": start, "window_end_ns": end,
            "observed_mfe": str(Decimal(hi["price"]) / entry - 1), "mfe_ns": hi["sip_timestamp"],
            "observed_mae": str(Decimal(lo["price"]) / entry - 1), "mae_ns": lo["sip_timestamp"],
            "excursion_censored": bool(reasons(end)) or end - path[-1]["sip_timestamp"] > config["max_mark_age_seconds"] * SECOND,
            "flags": reasons(end), "observed_price_count": len(path), "performance_basis": "GROSS_OBSERVED_PRICE_NOT_EXECUTION"}


def quote_at_event(rows, event, config, complete):
    t = event["event_timestamp"]
    previous = [r for r in rows if r["normalization_status"] == "OK" and r["sip_timestamp"] <= t]
    chosen = previous[-1] if previous else None
    if chosen is None:
        return {"status": "MISSING", "coverage_complete": complete}
    bid, ask = number(chosen["bid_price"]), number(chosen["ask_price"])
    flags = []
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        flags.append("INVALID_OR_CROSSED_NBBO")
    if t - chosen["sip_timestamp"] > config["max_quote_age_seconds"] * SECOND:
        flags.append("STALE_NBBO")
    codes = json.loads(chosen["conditions_json"])
    if codes and any(c not in {0, 1} for c in codes):
        flags.append("NON_REGULAR_QUOTE_CONDITION")
    if any(43 in json.loads(r["conditions_json"]) for r in rows):
        flags.append("LULD_HALT_INDICATION_IN_BOUNDED_WINDOW")
    if not complete:
        flags.append("INCOMPLETE_QUOTE_WINDOW")
    return {"status": "OK" if not flags else "FLAGGED", "flags": flags, "bid": str(bid) if bid is not None else None,
            "ask": str(ask) if ask is not None else None, "sip_timestamp": chosen["sip_timestamp"],
            "age_ns": t - chosen["sip_timestamp"], "source_json": chosen["source_json"], "coverage_complete": complete,
            "coverage_scope": "BOUNDED_EVENT_WINDOW_ONLY"}
