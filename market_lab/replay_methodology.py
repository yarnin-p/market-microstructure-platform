"""TASK 002.1 policies; the original replay module and outputs stay immutable."""
import json
from collections import Counter, defaultdict
from decimal import Decimal

from .storage import digest
from .tick_replay import (SECOND, bounds, correction_key, eligible_trade, number,
                          outcomes as legacy_outcomes, session_label)

VERSION = "task-002-1-observed-sessions-v2"
POLICIES = ["LEGACY_BOTH", "HIGH_LOW_ONLY", "ODD_LOT_OBSERVATION_SENSITIVITY"]
UNKNOWN = {"UNKNOWN_TRADE_CONDITION", "CORRECTION_RECONSTRUCTION_UNRESOLVED", "INVALID_TIMESTAMP"}


def condition_maps(conditions):
    # Change the conjunctive rule only. The explicit late/reference-price vetoes
    # remain fixed, so high/low-only need not admit more prints in this pilot.
    relaxed = {}
    for code, condition in conditions.items():
        value = {**condition, "update_rules": dict(condition.get("update_rules", {}))}
        rules = dict(value["update_rules"].get("consolidated", {}))
        if rules.get("updates_high_low") is True:
            rules["updates_open_close"] = True
        value["update_rules"]["consolidated"] = rules
        relaxed[code] = value
    odd = {**relaxed, 37: {"type": "sale_condition", "update_rules": {
        "consolidated": {"updates_high_low": True, "updates_open_close": True}}}}
    return {"LEGACY_BOTH": conditions, "HIGH_LOW_ONLY": relaxed, "ODD_LOT_OBSERVATION_SENSITIVITY": odd}


def ordering(row):
    return (row.get("sip_timestamp") or 0, row.get("sequence_number") or 0,
            row.get("exchange") or 0, row.get("trade_id") or "", row["record_id"])


def first_touch_scope(event, cycle, complete, unknown_prior, observed_end, overnight_evidence=False):
    observed = complete and not unknown_prior
    # A prefix proof does not certify future portions of this cycle. An AH
    # touch can be located before the overnight blind interval.
    prefix = not unknown_prior and event["session"] == "AH" and (
        complete or event["event_timestamp"] < observed_end)
    strict_opportunity = complete and overnight_evidence
    strict = strict_opportunity and not unknown_prior
    return {"observed_sessions_first_verified": observed, "prefix_first_verified": prefix,
            "strict_full_cycle_first_verified": strict,
            "strict_full_cycle_opportunity_eligible": strict_opportunity,
            "first_touch_definition": "OBSERVED_SESSIONS_FIRST",
            "first_touch_status": "OBSERVED_SESSIONS_FIRST_VERIFIED" if observed else "UNVERIFIED_TOUCH",
            "prior_evidence_unknown": unknown_prior,
            "overnight_coverage": "VERIFIED" if overnight_evidence else "UNOBSERVED_NOT_PROOF_OF_CLOSURE",
            "overnight_interval_ns": [bounds(cycle)[1], bounds(cycle)[2]]}


class ReplayState:
    def __init__(self, policy, cycle, opportunity, config, conditions, complete, run_id, observed_end):
        self.policy, self.cycle, self.opportunity = policy, cycle, opportunity
        self.config, self.conditions, self.complete = config, conditions, complete
        self.run_id, self.observed_end = run_id, observed_end
        self.threshold = Decimal(str(opportunity["previous_rth_close"])) * Decimal(config["trigger_multiplier"])
        self.eligible, self.reject_counts, self.invalidations = [], Counter(), []
        self.event, self.raw_first_crossing, self.first_key = None, None, None
        self.unknown_prior, self.above = False, False
        self.unknown_times, self.rejected_crossings, self.recrosses = [], 0, 0

    def feed(self, row):
        passed, reason = eligible_trade(row, self.cycle, self.conditions, self.config)
        p, t = number(row.get("price")), row.get("sip_timestamp")
        if p is not None and p >= self.threshold and self.raw_first_crossing is None:
            self.raw_first_crossing = {k: row.get(k) for k in ["record_id", "sip_timestamp", "price", "source_json"]}
        if not passed:
            self.reject_counts[reason] += 1
            if reason in UNKNOWN:
                self.unknown_times.append(t)
                if self.event is None:
                    self.unknown_prior = True
            if p is not None and p >= self.threshold:
                self.rejected_crossings += 1
        else:
            self.eligible.append(row)
            if p >= self.threshold and not self.above:
                if self.event is None:
                    self.first_key = correction_key(row)
                    self.event = {"event_id": digest([VERSION, self.policy, self.opportunity["security_id"],
                                                      self.cycle["cycle_id"], row["record_id"]]),
                        "run_id": self.run_id, "methodology_version": VERSION, "condition_policy": self.policy,
                        "cycle_id": self.cycle["cycle_id"], "ticker": self.opportunity["ticker"],
                        "security_id": self.opportunity["security_id"], "sample": self.opportunity["sample"],
                        "session": row["session"], "event_timestamp": t,
                        "previous_rth_close": str(self.opportunity["previous_rth_close"]),
                        "threshold_price": str(self.threshold), "touch_price": str(p),
                        "record_id": row["record_id"], "trade_size": row["size"], "trade_exchange": row["exchange"],
                        "conditions_json": row["conditions_json"], "source_json": row["source_json"],
                        "restoration_status": row.get("restoration_status", "AS_RECORDED"),
                        "restoration_source": row.get("restoration_source"), "later_invalidated": False,
                        "cohorts": self.opportunity["cohorts"], "sec_evidence": self.opportunity.get("sec_evidence", []),
                        "float_proxy": self.opportunity.get("float_proxy"),
                        **first_touch_scope({"session": row["session"], "event_timestamp": t}, self.cycle,
                                            self.complete, self.unknown_prior, self.observed_end)}
                else:
                    self.recrosses += 1
            self.above = p >= self.threshold
        if self.event and row.get("correction") in {10, 11, 12} and correction_key(row) == self.first_key:
            self.invalidations.append(t)
            self.event["later_invalidated"] = True
        return passed, reason

    def replay(self):
        return {"event": self.event, "eligible": self.eligible, "invalidations": self.invalidations}


def outcome_sensitivity(state, cycle, config, gap_seconds):
    if not state.event:
        return None
    cfg = {**config, "intertrade_gap_seconds": gap_seconds if gap_seconds is not None else 10**12}
    result = legacy_outcomes(state.replay(), cycle, cfg, state.complete)
    start = state.event["event_timestamp"]
    for mark in result["forward"]:
        if any(t is None or start < t <= mark["target_ns"] for t in state.unknown_times):
            mark["flags"] = sorted(set(mark["flags"] + ["UNKNOWN_PATH_PRICE_EVIDENCE"]))
            mark.update(censored=True, **{"return": None, "relative_to_p0": None})
    for barrier in result["barriers"]:
        end = barrier["first_passage_ns"] or bounds(cycle)[-1]
        if any(t is None or start < t <= end for t in state.unknown_times):
            barrier["flags"] = sorted(set(barrier["flags"] + ["UNKNOWN_PATH_PRICE_EVIDENCE"]))
            barrier["outcome"] = "CENSORED"
    if any(t is None or t > start for t in state.unknown_times):
        result["excursion_censored"] = True
        result["flags"] = sorted(set(result["flags"] + ["UNKNOWN_PATH_PRICE_EVIDENCE"]))
    result.update(methodology_version=VERSION, condition_policy=state.policy,
                  gap_policy="NO_MECHANICAL_GAP" if gap_seconds is None else f"GAP_{gap_seconds}_SECONDS",
                  gap_seconds=gap_seconds, price_path_basis="ELIGIBLE_OBSERVED_TRADES_ONLY",
                  first_touch_evidence_status=state.event["first_touch_status"])
    return result


def gap_diagnostics(rows, cycle, complete):
    counts = Counter()
    examples = []
    for a, b in zip(rows, rows[1:]):
        if a["session"] != b["session"] or a["session"] not in {"AH", "PRE", "RTH"}:
            continue
        seconds = (b["sip_timestamp"] - a["sip_timestamp"]) / SECOND
        for threshold in [300, 900]:
            counts[f"over_{threshold}_seconds"] += seconds > threshold
        if seconds > 300:
            examples.append({"session": a["session"], "start_ns": a["sip_timestamp"], "end_ns": b["sip_timestamp"],
                "seconds": seconds, "classification": "NO_REPORTED_ELIGIBLE_TRADES_IN_COMPLETE_PROVIDER_WINDOW" if complete
                else "PARTIAL_PROVIDER_WINDOW_NO_COMPLETENESS_CLAIM",
                "independent_feed_loss_or_halt_proof": False})
    return {"counts": dict(counts), "intervals": examples,
            "limitation": "Eligible-trade gaps may contain rejected prints; never infer a halt or a missing API page from elapsed time alone."}
