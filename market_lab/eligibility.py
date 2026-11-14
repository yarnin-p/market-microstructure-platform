import math
from datetime import datetime
from decimal import Decimal, InvalidOperation

ALLOW = {"XNAS": "NASDAQ", "XASE": "NYSE American (AMEX)", "XNYS": "NYSE"}
ELIGIBLE, INELIGIBLE, UNRESOLVED = "ELIGIBLE", "INELIGIBLE", "UNRESOLVED"


def instant(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("evidence timestamps must include timezone")
    return t


def identity(row):
    # CIK identifies an issuer, not a security: never use CIK alone to join histories.
    return row.get("share_class_figi") or row.get("composite_figi")


def exchange(raw, market, directory):
    if market == "otc":
        return INELIGIBLE, "OTC", "OTC_PRIMARY_LISTING"
    if not raw:
        return UNRESOLVED, None, "MISSING_HISTORICAL_EXCHANGE"
    matches = [r for r in directory if r.get("mic") == raw and r.get("asset_class") == "stocks"
               and r.get("locale") == "us"]
    if not matches:
        return UNRESOLVED, None, "UNMAPPED_EXCHANGE_CODE"
    if raw in ALLOW and all(r.get("type") == "exchange" for r in matches):
        return ELIGIBLE, ALLOW[raw], "ALLOWED_PRIMARY_LISTING"
    return INELIGIBLE, matches[0]["name"], "DISALLOWED_PRIMARY_LISTING"


def decimal_value(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result != result.quantize(Decimal("0.000000000001")):
            return None
        return result
    except (InvalidOperation, ValueError):
        return None


def price_gate(value):
    value = decimal_value(value)
    if value is None:
        return UNRESOLVED, "MISSING_PREVIOUS_RTH_CLOSE"
    return (ELIGIBLE, "PRICE_IN_RANGE") if 0 < value <= 3 else (INELIGIBLE, "PRICE_OUT_OF_RANGE")


def type_gate(value):
    if not value:
        return UNRESOLVED, "MISSING_HISTORICAL_SECURITY_TYPE"
    return (ELIGIBLE, "COMMON_STOCK") if value == "CS" else (INELIGIBLE, "NOT_COMMON_STOCK")


def validate_evidence(rows):
    for r in rows:
        for field in ("kind", "security_id", "effective_from", "effective_to", "available_at", "source", "source_sha256"):
            if not r.get(field):
                raise ValueError(f"evidence missing {field}")
        if r["kind"] not in {"float", "exchange"}:
            raise ValueError("unknown evidence kind")
        if instant(r["effective_from"]) >= instant(r["effective_to"]):
            raise ValueError("invalid evidence interval")
        instant(r["available_at"])
        if len(r["source_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in r["source_sha256"]):
            raise ValueError("invalid source_sha256")
        if r["kind"] == "float":
            value = decimal_value(r.get("shares_float"))
            if value is None or value < 0:
                raise ValueError("invalid shares_float")
            if r.get("cohort") not in {"VERIFIED_PIT", "HISTORICAL_PROXY", "CURRENT_PROXY", "UNRESOLVED"}:
                raise ValueError("float evidence requires explicit cohort")
            if r["cohort"] == "VERIFIED_PIT":
                if not r.get("measurement_at") or not r.get("validity_policy"):
                    raise ValueError("PIT evidence requires measurement_at and validity_policy")
                if instant(r["measurement_at"]) > instant(r["available_at"]):
                    raise ValueError("measurement is after availability")
                if "/stocks/vX/float" in r["source"] or r.get("source_kind") != "AUDITED_HISTORICAL_RECORD":
                    raise ValueError("current/provider latest float cannot be PIT evidence")
        elif not r.get("primary_exchange"):
            raise ValueError("missing evidence primary_exchange")


def evidence_at(evidence, kind, security_id, at):
    if not security_id:
        return []
    t = instant(at)
    return [r for r in evidence if r["kind"] == kind and r["security_id"] == security_id
            and instant(r["effective_from"]) <= t < instant(r["effective_to"])
            and instant(r["available_at"]) <= t]


def float_gate(evidence, security_id, at):
    rows = [r for r in evidence_at(evidence, "float", security_id, at)
            if r.get("cohort") == "VERIFIED_PIT"
            and r.get("source_kind") == "AUDITED_HISTORICAL_RECORD"
            and r.get("measurement_at") and instant(r["measurement_at"]) <= instant(at)
            and r.get("validity_policy") and "/stocks/vX/float" not in r.get("source", "")]
    values = {decimal_value(r["shares_float"]) for r in rows}
    if None in values:
        return UNRESOLVED, None, "INVALID_FLOAT_EVIDENCE", rows
    if not values:
        return UNRESOLVED, None, "HISTORICAL_FLOAT_UNAVAILABLE", []
    if len(values) != 1:
        return UNRESOLVED, None, "CONFLICTING_FLOAT_EVIDENCE", rows
    value = next(iter(values))
    return (ELIGIBLE if 100_000 <= value <= 15_000_000 else INELIGIBLE), value, "FLOAT_IN_RANGE" if 100_000 <= value <= 15_000_000 else "FLOAT_OUT_OF_RANGE", rows


def combine(*statuses):
    # A known exclusion is sufficient even if another independent field is unknown.
    if INELIGIBLE in statuses:
        return INELIGIBLE
    if UNRESOLVED in statuses:
        return UNRESOLVED
    return ELIGIBLE


def event_eligibility(snapshot, event_at, evidence, directory):
    t = instant(event_at)
    if not instant(snapshot["anchor_at"]) < t <= instant(snapshot["end_at"]):
        return {"status": INELIGIBLE, "reason": "EVENT_OUTSIDE_CYCLE"}
    if snapshot["status"] != ELIGIBLE:
        return {"status": snapshot["status"], "reason": "NOT_IN_FROZEN_ELIGIBLE_UNIVERSE"}
    rows = evidence_at(evidence, "exchange", snapshot["security_id"], event_at)
    codes = {r["primary_exchange"] for r in rows}
    if len(codes) > 1:
        return {"status": UNRESOLVED, "reason": "CONFLICTING_EXCHANGE_EVIDENCE"}
    if rows:
        status, canonical, reason = exchange(rows[0]["primary_exchange"], "stocks", directory)
        return {"status": status, "reason": reason, "canonical_exchange": canonical, "evidence": rows}
    if snapshot["change_status"] != "NO_CHANGE_OBSERVED":
        return {"status": UNRESOLVED, "reason": "INTRACYCLE_EXCHANGE_UNVERIFIED"}
    return {"status": ELIGIBLE, "reason": "FROZEN_ANCHOR_NO_IDENTIFIED_CHANGE",
            "limitation": "Daily reference observations cannot rule out same-day round-trip changes."}
