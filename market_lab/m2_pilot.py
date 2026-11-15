"""TASK 002 selection, cohort evidence, bounded execution, and audit orchestration."""
import argparse
import fcntl
import json
import random
import subprocess
from collections import Counter
from pathlib import Path
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from .api import load_key, APIError
from .eligibility import identity
from .storage import digest, file_hash, write_json, parquet
from .tick_ingest import TickClient, normalize
from .tick_replay import ns, first_touch, outcomes, quote_at_event, SECOND

NON_FLOAT_GATES = ["exchange", "price", "type", "identity", "currency", "action"]
DOCS = ["configs/m2-pilot-v1.json", "configs/float-proxy-v0.2.json", "configs/sip-first-touch-v1.json"]


def fingerprint(m1):
    files = list(Path("data/runs", m1).rglob("*")) + list(Path("reports", m1).rglob("*"))
    return {str(p): file_hash(p) for p in sorted(files) if p.is_file() and p.name != ".writer.lock"}


def source_rows(m1, cycle):
    p = Path("data/runs", m1, "universe", "cycle=" + cycle, "snapshot.parquet")
    checkpoint = json.loads(p.with_name("checkpoint.json").read_text())
    if file_hash(p) != checkpoint["snapshot_hash"]:
        raise ValueError("M1 snapshot hash mismatch")
    return pq.ParquetFile(p).read().to_pylist(), {"path": str(p.resolve()), "sha256": file_hash(p)}


def control_eligible(row):
    return all(row[g + "_status"] == "ELIGIBLE" for g in NON_FLOAT_GATES) and row["change_status"] == "NO_CHANGE_OBSERVED"


def freeze(config, root):
    path = root / "selection.json"
    version = digest({p: file_hash(p) for p in DOCS})
    if path.exists():
        selection = json.loads(path.read_text())
        if selection["policy_hash"] != version:
            raise ValueError("immutable selection policy mismatch")
        return selection
    calendar = json.loads(Path("data/runs", config["source_m1_run"], "calendar.json").read_text())
    chosen_cycles = calendar[:3]
    if [c["cycle_id"] for c in chosen_cycles] != config["cycles"] or any(c["split_group"] != "EXPLORATION" for c in chosen_cycles):
        raise ValueError("pilot must use first three exploration cycles only")
    rows, source = source_rows(config["source_m1_run"], config["cycles"][0])
    candidates = sorted([r for r in rows if control_eligible(r)], key=lambda r: (r["security_id"], r["ticker"]))
    systematic = random.Random(config["seed"]).sample(candidates, config["systematic_securities"])
    occupied = {r["security_id"] for r in systematic}
    next_rows, daily_source = source_rows(config["source_m1_run"], config["cycles"][1])
    day_high = {r["security_id"]: json.loads(r["provenance_json"])["price_record"].get("h") for r in next_rows}
    diagnostic = sorted([r for r in candidates if r["security_id"] not in occupied and day_high.get(r["security_id"]) is not None],
                        key=lambda r: (-Decimal(str(day_high[r["security_id"]])) / r["previous_rth_close"], r["ticker"]))[:config["diagnostic_securities"]]
    selected = []
    for label, sample in [("SYSTEMATIC", systematic), ("DIAGNOSTIC", diagnostic)]:
        for r in sample:
            selected.append({"security_id": r["security_id"], "ticker": r["ticker"], "sample": label,
                             "selection_p0": str(r["previous_rth_close"]), "m1_record_id": r["record_id"],
                             "selection_score": str(Decimal(str(day_high[r["security_id"]])) / r["previous_rth_close"]) if label == "DIAGNOSTIC" else None})
    selection = {"policy_hash": version, "config": config, "calendar": chosen_cycles, "selected": selected,
                 "eligible_selection_frame": len(candidates), "source": source, "diagnostic_daily_source": daily_source,
                 "selection_scope": "FIRST_CYCLE_FRAME; later cycle non-float eligibility checked separately",
                 "diagnostic_bias": "Selected on first pilot day's daily high; not a population sample; no continuation outcomes used",
                 "m1_before": fingerprint(config["source_m1_run"])}
    write_json(path, selection)
    return selection


def collect_context(client, selected, root):
    path = root / "context.json"
    if path.exists():
        return json.loads(path.read_text())
    context = {"float": {}, "conditions": [], "sources": [], "errors": [], "SEC": {}}
    conditions_path, params = "/v3/reference/conditions", {"asset_class": "stocks", "data_type": "trade", "limit": 1000}
    try:
        for _ in range(5):
            body, source = client.get(conditions_path, params)
            context["sources"].append(source)
            context["conditions"].extend(body["results"])
            conditions_path, params = body.get("next_url"), None
            if not conditions_path:
                break
        if conditions_path:
            raise APIError("CONDITIONS_PAGINATION_INCOMPLETE")
    except APIError as e:
        context["errors"].append({"stage": "conditions", "error": str(e)})
        context["conditions"] = []
    for r in selected:
        evidence = {"original_ticker": r["ticker"], "historical_security_id": r["security_id"], "cohort": "MASSIVE_CURRENT_FLOAT_PROXY",
                    "status": "UNRESOLVED", "field": "free_float", "endpoint": "/stocks/vX/float", "value": None, "is_verified_pit": False}
        try:
            current, identity_source = client.get("/v3/reference/tickers/" + r["ticker"])
            current_ref = current["results"]
            evidence["resolved_security_id"] = identity(current_ref)
            evidence["identity_source"] = identity_source
            if evidence["resolved_security_id"] != r["security_id"]:
                evidence["reason"] = "CURRENT_TICKER_IDENTITY_MISMATCH"
            else:
                body, float_source = client.get("/stocks/vX/float", {"ticker": r["ticker"], "limit": 10})
                matches = [x for x in body["results"] if x.get("ticker") == r["ticker"]]
                evidence["source"] = float_source
                evidence["retrieved_at"] = float_source["retrieved_at"]
                if len(matches) == 1 and isinstance(matches[0].get("free_float"), (int, float)) and not isinstance(matches[0]["free_float"], bool):
                    evidence["value"] = matches[0]["free_float"]
                    evidence["effective_date"] = matches[0].get("effective_date")
                    evidence["status"] = "ELIGIBLE" if client.config["float_min"] <= evidence["value"] <= client.config["float_max"] else "INELIGIBLE"
                    evidence["reason"] = "LATEST_FREE_FLOAT_RETROSPECTIVE_PROXY"
                else:
                    evidence["reason"] = "MISSING_OR_AMBIGUOUS_FREE_FLOAT"
        except APIError as e:
            evidence["reason"] = str(e)
            context["errors"].append({"stage": "float", "ticker": r["ticker"], "error": str(e)})
        context["float"][r["security_id"]] = evidence
    sec_path = Path("data/sec-pilot-20261115-v2/results-reviewed-v1.json")
    context["sec_source"] = {"path": str(sec_path.resolve()), "sha256": file_hash(sec_path)}
    for r in json.loads(sec_path.read_text())["results"]:
        sid = r["security"]["security_id"]
        context["SEC"][sid] = r
    # Immutable context: missing proxy stays unresolved within this run. New data
    # requires a new run rather than changing eligibility after outcomes are seen.
    write_json(path, context)
    return context


def event_table(path, records):
    schema = pa.schema([(k, pa.string()) for k in ["run_id", "event_id", "cycle_id", "ticker", "security_id", "sample", "session", "payload_json"]])
    parquet(path, [{**{k: r.get(k) for k in schema.names if k != "payload_json"}, "payload_json": json.dumps(r, sort_keys=True)} for r in records], schema)


def run_pilot(run_id, config_path="configs/m2-pilot-v1.json", env_file=None, offline=False):
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id) or run_id.startswith("m1-"):
        raise ValueError("invalid/new M2 run ID required")
    config = json.loads(Path(config_path).read_text())
    root = Path("data/runs", run_id)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        selection = freeze(config, root)
        code_hashes = {str(p): file_hash(p) for p in Path("market_lab").glob("*.py")}
        execution_path = root / "execution.json"
        if execution_path.exists() and json.loads(execution_path.read_text())["code_hashes"] != code_hashes:
            raise ValueError("code changed; use a new run ID")
        write_json(execution_path, {"run_id": run_id, "code_hashes": code_hashes, "policy_hash": selection["policy_hash"],
                                    "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()})
        client = TickClient(root / "raw", config, load_key(env_file), offline)
        context = collect_context(client, selection["selected"], root)
        conditions = {r["id"]: r for r in context["conditions"]}
        opportunities, events, all_outcomes, all_candidates, memberships = [], [], [], [], []
        quote_windows = 0
        for cycle in selection["calendar"]:
            rows, source = source_rows(config["source_m1_run"], cycle["cycle_id"])
            by_id = {r["security_id"]: r for r in rows if r.get("security_id")}
            for selected in selection["selected"]:
                sid = selected["security_id"]
                row = by_id.get(sid)
                opportunity = {"run_id": run_id, "cycle_id": cycle["cycle_id"], "ticker": selected["ticker"], "security_id": sid,
                               "sample": selected["sample"], "cohorts": [], "status": "HISTORICAL_QUALITY_EXCLUDED",
                               "float_proxy": context["float"][sid], "source_m1": source}
                if not row or not control_eligible(row):
                    opportunity["reason"] = "MISSING_OR_FAILED_HISTORICAL_NON_FLOAT_GATES"
                    opportunities.append(opportunity)
                    continue
                opportunity.update({"ticker": row["ticker"], "previous_rth_close": str(row["previous_rth_close"]),
                                    "cohorts": ["EXCHANGE_PRICE_ONLY"], "sec_evidence": [], "m1_record_id": row["record_id"]})
                if context["float"][sid]["status"] == "ELIGIBLE":
                    opportunity["cohorts"].append("MASSIVE_CURRENT_FLOAT_PROXY")
                if sid in context["SEC"]:
                    sec = context["SEC"][sid]
                    opportunity["sec_evidence"] = [{"classification": sec["status"], "source": context["sec_source"],
                                                    "derived_estimates": sec.get("derived_estimates", []), "carry_forward": False,
                                                    "corporate_actions": json.loads(row["provenance_json"])["corporate_actions"]}]
                pair = root / "ticks" / ("cycle=" + cycle["cycle_id"]) / ("security=" + sid)
                coverage = client.window("trades", row["ticker"], ns(cycle["anchor_at"]), ns(cycle["end_at"]), pair / "trades")
                normalized, audit = normalize(coverage, sid, cycle, pair / "trades.parquet")
                technical_complete = coverage["complete"] and audit["invalid_timestamp_rows"] == 0 and bool(conditions)
                replay = first_touch(normalized, cycle, opportunity, config, conditions, technical_complete, run_id)
                result = outcomes(replay, cycle, config, technical_complete)
                opportunity.update({"status": "PROCESSED" if technical_complete else "INCOMPLETE", "trade_coverage": coverage,
                                    "normalization": audit, "eligible_trades": len(replay["eligible"]), "reject_counts": replay["reject_counts"],
                                    "raw_crossing": {k: replay["raw_first_crossing"].get(k) for k in ["record_id", "sip_timestamp", "price", "source_json"]} if replay["raw_first_crossing"] else None,
                                    "zero_event_status": replay["zero_event_status"], "event_id": replay["event"]["event_id"] if replay["event"] else None})
                for c in replay["candidates"]:
                    all_candidates.append({**c, "run_id": run_id, "cycle_id": cycle["cycle_id"], "ticker": row["ticker"], "security_id": sid,
                                           "sample": selected["sample"], "event_id": opportunity["event_id"]})
                event = replay["event"]
                if event:
                    if quote_windows < config["max_quote_windows"]:
                        quote_windows += 1
                        start = max(ns(cycle["anchor_at"]), event["event_timestamp"] - config["quote_radius_seconds"] * SECOND)
                        end = min(ns(cycle["end_at"]), event["event_timestamp"] + config["quote_radius_seconds"] * SECOND)
                        quote_coverage = client.window("quotes", row["ticker"], start, end, pair / "quotes")
                        quotes, q_audit = normalize(quote_coverage, sid, cycle, pair / "quotes.parquet")
                        event["quote"] = quote_at_event(quotes, event, config, quote_coverage["complete"] and q_audit["invalid_timestamp_rows"] == 0)
                        opportunity["quote_coverage"] = quote_coverage
                    else:
                        event["quote"] = {"status": "NOT_DOWNLOADED_QUOTE_WINDOW_BUDGET"}
                    events.append(event)
                    all_outcomes.append({**result, "run_id": run_id})
                    for cohort in event["cohorts"]:
                        memberships.append({"run_id": run_id, "event_id": event["event_id"], "security_id": sid,
                                            "cycle_id": cycle["cycle_id"], "ticker": row["ticker"], "cohort": cohort})
                opportunities.append(opportunity)
                write_json(root / "progress.json", {"processed_pairs": len(opportunities), "events": len(events),
                                                   "requests": len(client.ledger["attempts"]), "decoded_bytes": client.ledger["decoded_bytes"]})
                print(json.dumps({"cycle": cycle["cycle_id"], "ticker": row["ticker"], "sample": selected["sample"],
                                  "trade_rows": len(normalized), "complete": technical_complete, "event": bool(event)}), flush=True)
        event_table(root / "events/events.parquet", events)
        event_table(root / "outcomes/outcomes.parquet", all_outcomes)
        event_table(root / "candidates/candidates.parquet", all_candidates)
        event_table(root / "opportunities/opportunities.parquet", opportunities)
        parquet(root / "cohort_memberships.parquet", memberships, pa.schema([(k, pa.string()) for k in ["run_id", "event_id", "security_id", "cycle_id", "ticker", "cohort"]]))
        integrity = {"m1_unchanged": fingerprint(config["source_m1_run"]) == selection["m1_before"], "holdout_accessed": False}
        if not integrity["m1_unchanged"]:
            raise ValueError("M1 integrity changed")
        write_json(root / "integrity.json", integrity)
        from .m2_report import report
        summary = report(run_id, selection, context, opportunities, events, all_outcomes, client.ledger, integrity)
        return summary


def main():
    p = argparse.ArgumentParser(description="Bounded M2 pilot; no full-universe tick downloads")
    p.add_argument("command", choices=["select", "run", "validate", "query"])
    p.add_argument("--run-id", required=True)
    p.add_argument("--config", default="configs/m2-pilot-v1.json")
    p.add_argument("--env-file")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--event-id")
    p.add_argument("--ticker")
    p.add_argument("--cycle")
    args = p.parse_args()
    if args.command == "select":
        root = Path("data/runs", args.run_id); root.mkdir(parents=True, exist_ok=True)
        result = freeze(json.loads(Path(args.config).read_text()), root)
        print(json.dumps({"selected": result["selected"], "cycles": result["config"]["cycles"]}, indent=2))
    elif args.command == "run":
        print(json.dumps(run_pilot(args.run_id, args.config, args.env_file, args.offline), indent=2))
    else:
        from .m2_report import validate_pilot, query_pilot
        print(json.dumps(validate_pilot(args.run_id) if args.command == "validate" else query_pilot(args.run_id, args.event_id, args.ticker, args.cycle), indent=2))


if __name__ == "__main__":
    main()
