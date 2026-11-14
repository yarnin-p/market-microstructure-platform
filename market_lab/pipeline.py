import json
import fcntl
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from . import POLICY_VERSION
from .api import APIError, Massive
from .calendar import cycles
from .eligibility import (identity, exchange, price_gate, float_gate, type_gate, combine, validate_evidence,
                          evidence_at, decimal_value, ELIGIBLE, INELIGIBLE, UNRESOLVED)
from .corporate_actions import load_actions, action_index, action_gate
from .results import result_package
from .storage import digest, file_hash, parquet, write_json, json_default

STRING_FIELDS = ["run_id", "cycle_id", "anchor_at", "end_at", "ticker", "security_id", "security_type",
                 "primary_exchange_raw", "canonical_exchange", "exchange_status", "exchange_reason", "price_status",
                 "price_reason", "float_status", "float_reason", "status", "change_status", "reference_date",
                 "reference_precision", "provenance_json", "policy_version", "mapping_version"]
STRING_FIELDS += ["type_status", "type_reason"]
STRING_FIELDS += ["record_id", "identity_status", "identity_reason", "currency_status", "currency_reason",
                  "action_status", "action_reason", "float_cohort", "split_group", "reference_close_method",
                  "reference_available_at", "reference_availability_status", "schema_version"]
GATES = ["exchange", "price", "float", "type", "identity", "currency", "action"]
SCHEMA = pa.schema([(s, pa.string()) for s in STRING_FIELDS] +
                   [(s, pa.decimal128(38, 12)) for s in ["previous_rth_close", "shares_float"]] +
                   [("trigger_price", pa.decimal128(38, 14))])
CHANGE_SCHEMA = pa.schema([(s, pa.string()) for s in ["cycle_id", "ticker", "security_id", "anchor_code", "observed_code", "change_status", "observed_date"]])


def index_tickers(rows):
    index = {}
    for row in rows:
        ticker = row.get("ticker")
        if not ticker or ticker in index:
            raise APIError("MISSING_OR_DUPLICATE_TICKER")
        index[ticker] = row
    return index


def source_locators(sources):
    """Exact source row locations for historical reference and daily close joins."""
    locations = {}
    for source in sources:
        if Path(source["path"]).suffix != ".parquet":
            continue
        envelope = pq.ParquetFile(source["path"]).read().to_pylist()[0]
        request, response = json.loads(envelope["request"]), json.loads(envelope["response"])
        for index, record in enumerate(response.get("results", [])):
            if not isinstance(record, dict):
                continue
            field = "ticker" if "ticker" in record else "T"
            key = (field, record.get(field), digest(record))
            locations[key] = {**source, "row_index": index, "request_hash": envelope["request_hash"],
                              "retrieved_at": envelope["retrieved_at"], "endpoint": request["url"],
                              "provider_request_id": response.get("request_id")}
    return locations


def classify(run_id, cycle, tickers, prices, observed, directory, evidence, provenance, actions=None, locators=None):
    actions = actions or {"complete": False}
    actions_by_ticker = action_index(actions)
    locators = locators or {}
    identities = Counter(identity(r) for r in tickers if identity(r))
    by_id = {}
    for r in observed or []:
        if identity(r):
            by_id.setdefault(identity(r), []).append(r)
    price_index = {}
    for r in prices:
        if r.get("T") in price_index:
            raise APIError("DUPLICATE_PRICE_TICKER")
        price_index[r.get("T")] = r
    snapshots, changes = [], []
    for ticker, ref in index_tickers(tickers).items():
        security_id = identity(ref)
        raw = ref.get("primary_exchange")
        status, canonical, reason = exchange(raw, ref.get("market"), directory)
        anchor_evidence = evidence_at(evidence, "exchange", security_id, cycle["anchor_at"])
        if anchor_evidence:
            codes = {r["primary_exchange"] for r in anchor_evidence}
            if len(codes) == 1:
                raw = next(iter(codes))
                status, canonical, reason = exchange(raw, "stocks", directory)
            else:
                status, canonical, reason = UNRESOLVED, None, "CONFLICTING_EXCHANGE_EVIDENCE"
        price_record = price_index.get(ticker, {})
        price = decimal_value(price_record.get("c"))
        p_status, p_reason = price_gate(price)
        t_status, t_reason = type_gate(ref.get("type"))
        f_status, value, f_reason, f_evidence = float_gate(evidence, security_id, cycle["anchor_at"])
        i_status = ELIGIBLE if security_id and identities[security_id] == 1 else UNRESOLVED
        i_reason = "UNIQUE_OBSERVED_SECURITY_ID" if i_status == ELIGIBLE else "MISSING_OR_AMBIGUOUS_SECURITY_ID"
        currency = ref.get("currency_name") or ref.get("currency_symbol")
        c_status = UNRESOLVED if not currency else ELIGIBLE if currency.lower() == "usd" else INELIGIBLE
        c_reason = "MISSING_CURRENCY" if not currency else "USD" if c_status == ELIGIBLE else "NON_USD"
        later = by_id.get(security_id, []) if security_id else []
        aliases = [r["ticker"] for r in later if r.get("ticker")]
        a_status, a_reason, a_rows = action_gate(cycle, ticker, actions_by_ticker, actions.get("complete", False), aliases)
        if len(later) != 1 and a_status == ELIGIBLE:
            a_status, a_reason = UNRESOLVED, "ACTION_SYMBOL_CONTINUITY_UNVERIFIED"
        change = "UNVERIFIED"
        observed_code = None
        if observed is not None and len(later) == 1:
            observed_code = later[0].get("primary_exchange")
            if observed_code and raw:
                change = "NO_CHANGE_OBSERVED" if observed_code == raw else "CHANGE_IDENTIFIED"
        # Exact evidence can identify a change missed by daily endpoint observations.
        from .eligibility import instant
        if any(r["kind"] == "exchange" and r["security_id"] == security_id
               and instant(cycle["anchor_at"]) < instant(r["effective_from"]) <= instant(cycle["end_at"])
               and r["primary_exchange"] != raw for r in evidence):
            change = "CHANGE_IDENTIFIED"
        snapshots.append({"run_id": run_id, "cycle_id": cycle["cycle_id"], "anchor_at": cycle["anchor_at"], "end_at": cycle["end_at"],
                          "ticker": ticker, "security_id": security_id, "security_type": ref.get("type"),
                          "primary_exchange_raw": ref.get("primary_exchange"), "canonical_exchange": canonical,
                          "exchange_status": status, "exchange_reason": reason, "previous_rth_close": price,
                          "price_status": p_status, "price_reason": p_reason, "shares_float": value,
                          "float_status": f_status, "float_reason": f_reason, "type_status": t_status, "type_reason": t_reason,
                          "identity_status": i_status, "identity_reason": i_reason,
                          "currency_status": c_status, "currency_reason": c_reason,
                          "action_status": a_status, "action_reason": a_reason,
                          "record_id": digest([cycle["cycle_id"], ticker, security_id]),
                          "float_cohort": "VERIFIED_PIT" if value is not None else "UNRESOLVED",
                          "split_group": cycle["split_group"], "schema_version": "universe-snapshot-v2",
                          "reference_close_method": "UNADJUSTED_PROVIDER_DAILY_CLOSE",
                          "reference_available_at": None, "reference_availability_status": "RETROSPECTIVE_NOT_EXECUTABLE",
                          "trigger_price": price * Decimal("1.10") if price is not None else None,
                          "status": combine(status, p_status, f_status, t_status, i_status, c_status, a_status),
                          "change_status": change, "reference_date": cycle["anchor_date"],
                          "reference_precision": "TIMESTAMP_EVIDENCE" if anchor_evidence else "EFFECTIVE_DATE_RECONSTRUCTION",
                          "provenance_json": json.dumps({"sources": provenance, "anchor_exchange_evidence": anchor_evidence, "float_evidence": f_evidence,
                              "ticker_reference": ref, "price_record": price_record,
                              "source_reference": locators.get(("ticker", ticker, digest(ref))),
                              "source_price": locators.get(("T", ticker, digest(price_record))),
                              "observed_references": later, "corporate_actions": a_rows}, sort_keys=True, default=json_default),
                          "policy_version": POLICY_VERSION, "mapping_version": digest(directory)})
        if change != "NO_CHANGE_OBSERVED":
            changes.append({"cycle_id": cycle["cycle_id"], "ticker": ticker, "security_id": security_id,
                            "anchor_code": raw, "observed_code": observed_code, "change_status": change, "observed_date": cycle["cycle_id"]})
    return snapshots, changes


def counts(rows):
    c = Counter(candidates=len(rows))
    c.update(qualified=sum(r["status"] == ELIGIBLE for r in rows), unresolved=sum(r["status"] == UNRESOLVED for r in rows),
             excluded=sum(r["status"] == INELIGIBLE for r in rows),
             unresolved_fields=sum(any(r[g + "_status"] == UNRESOLVED for g in GATES) for r in rows))
    for gate in GATES:
        c["excluded_" + gate] = sum(r[gate + "_status"] == INELIGIBLE for r in rows)
        c["unresolved_" + gate] = sum(r[gate + "_status"] == UNRESOLVED for r in rows)
    return dict(c)


def build(api, root, reports, run_id, end, count=120, evidence=None, workers=1, actions_path=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("invalid run ID")
    lock = Path(root) / "runs" / run_id / ".writer.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another writer is active for this run") from None
        return _build(api, root, reports, run_id, end, count, evidence, workers, actions_path)


def _build(api, root, reports, run_id, end, count=120, evidence=None, workers=1, actions_path=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("invalid run ID")
    evidence = evidence or []
    validate_evidence(evidence)
    schedule = cycles(end, count)
    actions = load_actions(actions_path, schedule)
    if datetime.fromisoformat(schedule[-1]["end_at"]) > datetime.now(timezone.utc):
        raise ValueError("end cycle has not closed")
    root, reports = Path(root).resolve(), Path(reports).resolve()
    run = root / "runs" / run_id
    report = reports / run_id
    policy_path = Path(__file__).resolve().parents[1] / "configs/m1-v1.json"
    lock_path = Path(__file__).resolve().parents[1] / "requirements.lock"
    config = {"policy_version": POLICY_VERSION, "approved_policy": json.loads(policy_path.read_text()),
              "policy_hash": file_hash(policy_path), "dependency_lock_hash": file_hash(lock_path),
              "actions_hash": digest(actions), "schema_version": "universe-snapshot-v2",
              "source_index_hash": digest(getattr(api, "pinned_hashes", {})),
              "end": end, "cycles": count, "float_min": 100000, "float_max": 15000000,
              "eligible_security_types": ["CS"],
              "price_min_exclusive": 0, "price_max_inclusive": 3, "evidence_hash": digest(evidence), "calendar": schedule,
              "code_hashes": {p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")}}
    manifest = {"run_id": run_id, "artifact_root": str(run), "requested_cycles": count, "config": config, "config_hash": digest(config),
                "started_at": datetime.now(timezone.utc).isoformat(), "status": "RUNNING"}
    manifest_path = report / "manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if previous["config_hash"] != manifest["config_hash"]:
            raise ValueError("run configuration/code changed; use a new run ID to preserve frozen snapshots")
        manifest["started_at"] = previous["started_at"]
    run.mkdir(parents=True, exist_ok=True)
    write_json(run / "calendar.json", schedule)
    write_json(run / "evidence.json", evidence)
    write_json(run / "corporate_actions.json", actions)
    api.evidence.extend(actions.get("sources", []))
    manifest["input_actions"] = {"path": str(run / "corporate_actions.json"), "sha256": file_hash(run / "corporate_actions.json")}
    entries = []
    try:
        directory = api.exchanges()
    except APIError as error:
        entries = [{"cycle_id": c["cycle_id"], "status": "ERROR", "error": str(error)} for c in schedule]
        manifest["status"] = "BLOCKED"
        result_package(report, manifest, entries, api)
        return manifest
    directory_path = run / "exchange_directory.json"
    if directory_path.exists() and json.loads(directory_path.read_text()) != directory:
        raise ValueError("exchange directory changed; use a new run ID")
    write_json(directory_path, directory)
    if not 1 <= workers <= 16:
        raise ValueError("workers must be 1..16")
    if workers > 1:
        if getattr(api, "max_requests", None) is not None or getattr(api, "offline", False):
            raise ValueError("budgeted/offline runs require workers=1")
        # Each date belongs to exactly one worker. Page responses remain bounded;
        # no shared requests.Session and no duplicate date writes across workers.
        days = sorted({c["anchor_date"] for c in schedule} | {c["cycle_id"] for c in schedule})
        price_days = {c["anchor_date"] for c in schedule}
        def fetch_day(day):
            client = Massive(api.root, api.key)
            client.pinned_hashes = getattr(api, "pinned_hashes", {})
            error = None
            try:
                client.tickers(day)
                if day in price_days:
                    client.prices(day)
            except APIError as exc:
                error = str(exc)
            finally:
                client.session.close()
            return day, client, error
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fetch_day, day) for day in days]
            for i, future in enumerate(as_completed(futures), 1):
                day, client, error = future.result()
                api.evidence.extend(client.evidence)
                api.errors.extend(client.errors)
                api.requests += client.requests
                api.cache_hits += client.cache_hits
                print(json.dumps({"prefetched_date": day, "dates_done": i, "dates_total": len(days), "error": error}), flush=True)
    for cycle in schedule:
        ident = cycle["cycle_id"]
        partition = run / "universe" / f"cycle={ident}"
        checkpoint = partition / "checkpoint.json"
        if checkpoint.exists():
            entry = json.loads(checkpoint.read_text())
            if entry["config_hash"] != manifest["config_hash"]:
                raise ValueError("checkpoint configuration mismatch")
            for artifact in ["snapshot", "changes"]:
                if file_hash(entry[artifact]) != entry[artifact + "_hash"]:
                    raise ValueError("checkpoint artifact hash mismatch")
            if not entry.get("price_error") and not entry.get("observation_error"):
                entries.append(entry)
                continue
        evidence_start = len(api.evidence)
        try:
            tickers = api.tickers(cycle["anchor_date"])
            if not tickers:
                raise APIError("EMPTY_HISTORICAL_DISCOVERY")
            price_error = None
            try:
                prices = api.prices(cycle["anchor_date"])
            except APIError as error:
                prices = []
                price_error = str(error)
            anchor_sources = list(api.evidence[evidence_start:])
            observation_error = None
            try:
                observed = api.tickers(ident)
            except APIError as error:
                observed = None
                observation_error = str(error)
            sources = api.evidence[evidence_start:]
            rows, changes = classify(run_id, cycle, tickers, prices, observed, directory, evidence, sources,
                                     actions, source_locators(anchor_sources))
            snapshot = partition / "snapshot.parquet"
            change_path = run / "exchange_changes" / f"cycle={ident}" / "changes.parquet"
            parquet(snapshot, rows, SCHEMA)
            parquet(change_path, changes, CHANGE_SCHEMA)
            tally = counts(rows)
            entry = {"cycle_id": ident, "config_hash": manifest["config_hash"], "counts": tally,
                     "status": "UNRESOLVED" if tally["unresolved_fields"] or changes or observation_error else "COMPLETE",
                     "snapshot": str(snapshot), "snapshot_hash": file_hash(snapshot), "changes": str(change_path),
                     "changes_hash": file_hash(change_path), "observation_error": observation_error, "price_error": price_error,
                     "sources": api.evidence[evidence_start:]}
            write_json(checkpoint, entry)
            print(json.dumps({"cycle": ident, "status": entry["status"], "counts": tally}), flush=True)
        except APIError as error:
            entry = {"cycle_id": ident, "status": "ERROR", "error": str(error)}
            print(json.dumps(entry), flush=True)
        entries.append(entry)
        # Atomic progress report enables inspection/restart after interruption.
        write_json(manifest_path, {**manifest, "cycles": entries})
        if entry.get("error") in {"MISSING_API_KEY", "HTTP_401", "HTTP_403"}:
            entries.extend({"cycle_id": c["cycle_id"], "status": "ERROR", "error": "BLOCKED_AFTER_AUTH_FAILURE"}
                           for c in schedule[len(entries):])
            break
    manifest["status"] = "COMPLETE" if len(entries) == count and all(e["status"] == "COMPLETE" for e in entries) else "PARTIAL_UNRESOLVED"
    # Include evidence from skipped checkpoints too, not only this process's API calls.
    api.evidence.extend(s for e in entries for s in e.get("sources", []))
    result_package(report, manifest, entries, api)
    return manifest


def validate(report_dir):
    report_dir = Path(report_dir)
    files = ["manifest.json", "summary.json", "data_quality.json", "statistical_results.json", "anomalies.json", "report.md"]
    for name in files:
        if not (report_dir / name).exists():
            raise ValueError("missing result package file: " + name)
    m = json.loads((report_dir / "manifest.json").read_text())
    if digest(m["config"]) != m["config_hash"]:
        raise ValueError("configuration hash mismatch")
    if len(m["cycles"]) != m["requested_cycles"]:
        raise ValueError("incomplete manifest cycle coverage")
    schedule = {c["cycle_id"]: c for c in m["config"]["calendar"]}
    if [e["cycle_id"] for e in m["cycles"]] != list(schedule):
        raise ValueError("manifest cycle ordering/identity mismatch")
    processed = sum(e["status"] in {"COMPLETE", "UNRESOLVED"} for e in m["cycles"])
    completed = sum(e["status"] == "COMPLETE" for e in m["cycles"])
    if processed != m["processed_cycles"] or completed != m["completed_cycles"]:
        raise ValueError("manifest completion counts mismatch")
    if m["status"] == "COMPLETE" and completed != m["requested_cycles"]:
        raise ValueError("incomplete research cannot be marked complete")
    directory = json.loads((Path(m["artifact_root"]) / "exchange_directory.json").read_text()) if processed else []
    run = Path(m["artifact_root"])
    evidence = json.loads((run / "evidence.json").read_text())
    validate_evidence(evidence)
    if digest(evidence) != m["config"]["evidence_hash"]:
        raise ValueError("float/exchange evidence hash mismatch")
    actions = json.loads((run / "corporate_actions.json").read_text())
    if digest(actions) != m["config"]["actions_hash"] or file_hash(run / "corporate_actions.json") != m["input_actions"]["sha256"]:
        raise ValueError("corporate actions hash mismatch")
    action_lookup = action_index(actions)
    if json.loads((run / "calendar.json").read_text()) != m["config"]["calendar"]:
        raise ValueError("calendar artifact mismatch")
    groups = [c["split_group"] for c in schedule.values()]
    if m["requested_cycles"] == 120 and groups != ["EXPLORATION"] * 80 + ["HOLDOUT"] * 40:
        raise ValueError("holdout split mismatch")
    from functools import lru_cache
    @lru_cache(maxsize=32)
    def source_rows(path):
        envelope = pq.ParquetFile(path).read().to_pylist()[0]
        return json.loads(envelope["response"])["results"]
    total = Counter()
    for e in m["cycles"]:
        if e["status"] == "ERROR":
            continue
        if file_hash(e["snapshot"]) != e["snapshot_hash"] or file_hash(e["changes"]) != e["changes_hash"]:
            raise ValueError("artifact hash mismatch")
        table = pq.ParquetFile(e["snapshot"]).read()
        if table.schema != SCHEMA:
            raise ValueError("snapshot schema mismatch")
        rows = table.to_pylist()
        identities = Counter(r["security_id"] for r in rows if r["security_id"])
        if len({r["ticker"] for r in rows}) != len(rows):
            raise ValueError("duplicate security-cycle")
        for r in rows:
            if any(r[g + "_status"] not in {ELIGIBLE, INELIGIBLE, UNRESOLVED} for g in GATES):
                raise ValueError("invalid gate classification")
            if r["cycle_id"] != e["cycle_id"] or r["run_id"] != m["run_id"]:
                raise ValueError("partition identity mismatch")
            cycle = schedule[r["cycle_id"]]
            if r["anchor_at"] != cycle["anchor_at"] or r["reference_date"] != cycle["anchor_date"] or r["end_at"] != cycle["end_at"]:
                raise ValueError("snapshot anchor/boundary mismatch")
            if r["mapping_version"] != digest(directory):
                raise ValueError("exchange mapping version mismatch")
            if (r["type_status"], r["type_reason"]) != type_gate(r["security_type"]):
                raise ValueError("security type classification mismatch")
            if (r["price_status"], r["price_reason"]) != price_gate(r["previous_rth_close"]):
                raise ValueError("price classification mismatch")
            f_status, f_value, f_reason, _ = float_gate(evidence, r["security_id"], r["anchor_at"])
            if (r["float_status"], r["shares_float"], r["float_reason"]) != (f_status, f_value, f_reason):
                raise ValueError("historical float classification/evidence mismatch")
            if r["float_cohort"] != ("VERIFIED_PIT" if f_value is not None else "UNRESOLVED"):
                raise ValueError("float cohort mismatch")
            expected_identity = ELIGIBLE if r["security_id"] and identities[r["security_id"]] == 1 else UNRESOLVED
            if r["identity_status"] != expected_identity:
                raise ValueError("identity classification mismatch")
            prov = json.loads(r["provenance_json"])
            later = prov["observed_references"]
            if any(identity(item) != r["security_id"] for item in later):
                raise ValueError("corporate action alias identity mismatch")
            aliases = [item["ticker"] for item in later if item.get("ticker")]
            a_status, a_reason, a_rows = action_gate(cycle, r["ticker"], action_lookup, actions.get("complete", False), aliases)
            if len(later) != 1 and a_status == ELIGIBLE:
                a_status, a_reason = UNRESOLVED, "ACTION_SYMBOL_CONTINUITY_UNVERIFIED"
            if (r["action_status"], r["action_reason"]) != (a_status, a_reason):
                raise ValueError("corporate action classification mismatch")
            if prov["corporate_actions"] != a_rows:
                raise ValueError("corporate action evidence mismatch")
            reference = prov["ticker_reference"]
            if identity(reference) != r["security_id"] or reference.get("primary_exchange") != r["primary_exchange_raw"]:
                raise ValueError("reference identity/listing mismatch")
            ex = exchange(reference.get("primary_exchange"), reference.get("market"), directory)
            precise = evidence_at(evidence, "exchange", r["security_id"], r["anchor_at"])
            if precise:
                codes = {p["primary_exchange"] for p in precise}
                ex = exchange(next(iter(codes)), "stocks", directory) if len(codes) == 1 else (UNRESOLVED, None, "CONFLICTING_EXCHANGE_EVIDENCE")
            if (r["exchange_status"], r["canonical_exchange"], r["exchange_reason"]) != ex:
                raise ValueError("exchange classification mismatch")
            currency = reference.get("currency_name") or reference.get("currency_symbol")
            expected_currency = UNRESOLVED if not currency else ELIGIBLE if currency.lower() == "usd" else INELIGIBLE
            if r["currency_status"] != expected_currency:
                raise ValueError("currency classification mismatch")
            if r["previous_rth_close"] != decimal_value(prov["price_record"].get("c")):
                raise ValueError("reference close source mismatch")
            if r["trigger_price"] != (r["previous_rth_close"] * Decimal("1.10") if r["previous_rth_close"] is not None else None):
                raise ValueError("trigger price mismatch")
            if r["split_group"] != cycle["split_group"] or r["record_id"] != digest([r["cycle_id"], r["ticker"], r["security_id"]]):
                raise ValueError("split/record identity mismatch")
            for field, raw in [("source_reference", reference), ("source_price", prov["price_record"])]:
                locator = prov.get(field)
                if prov["sources"] and raw and not locator:
                    raise ValueError("missing source row locator")
                if locator and source_rows(locator["path"])[locator["row_index"]] != raw:
                    raise ValueError("source row locator mismatch")
            if r["status"] != combine(*(r[g + "_status"] for g in GATES)):
                raise ValueError("classification inconsistent")
            if r["status"] == ELIGIBLE and not (0 < r["previous_rth_close"] <= 3 and 100000 <= r["shares_float"] <= 15000000):
                raise ValueError("qualified row violates thresholds")
        tally = counts(rows)
        if e["status"] == "COMPLETE" and tally["unresolved_fields"]:
            raise ValueError("unresolved cycle marked complete")
        if tally != e["counts"]:
            raise ValueError("snapshot counts mismatch")
        total.update(tally)
    s = json.loads((report_dir / "summary.json").read_text())
    if dict(total) != s["counts"]:
        raise ValueError("summary counts mismatch")
    registry = m["raw_evidence_index"]
    if file_hash(registry["path"]) != registry["sha256"]:
        raise ValueError("evidence index hash mismatch")
    for source in json.loads(Path(registry["path"]).read_text()):
        if file_hash(source["path"]) != source["sha256"]:
            raise ValueError("raw evidence hash mismatch")
    ready = m["status"] == "COMPLETE" and m["requested_cycles"] == 120 and total.get("qualified", 0) > 0
    return {"validation": "PASSED", "technical_validation": "PASSED",
            "m1_status": "READY_FOR_REVIEW" if ready else "BLOCKED_DATA",
            "requested_cycles": m["requested_cycles"], "processed_cycles": m["processed_cycles"],
            "completed_cycles": m["completed_cycles"], "research_ready": ready, "counts": dict(total)}
