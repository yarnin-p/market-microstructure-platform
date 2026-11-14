import json
import platform
import subprocess
from datetime import datetime, timezone
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import duckdb

from .storage import write_json, file_hash, digest

CONTRACT_VERSION = "research-results-v1"


def result_package(report_dir, manifest, entries, api):
    report_dir = Path(report_dir)
    completed = [e for e in entries if e["status"] == "COMPLETE"]
    totals = Counter()
    for e in entries:
        totals.update(e.get("counts", {}))
    artifacts = []
    for e in entries:
        for name in ("snapshot", "changes"):
            if e.get(name):
                p = Path(e[name])
                artifacts.append({"path": str(p), "bytes": p.stat().st_size, "sha256": file_hash(p)})
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except subprocess.CalledProcessError:
        commit = None
    evidence_registry = Path(manifest["artifact_root"]) / "evidence-index.json" if manifest.get("artifact_root") else report_dir / "evidence-index.json"
    sources = list({e["path"]: e for e in api.evidence}.values())
    write_json(evidence_registry, sources)
    compact_entries = [{k: v for k, v in e.items() if k not in {"sources", "config_hash"}} for e in entries]
    manifest.update({"contract_version": CONTRACT_VERSION, "cycles": compact_entries,
                     "completed_cycles": len(completed), "processed_cycles": sum(e["status"] in {"COMPLETE", "UNRESOLVED"} for e in entries),
                     "artifacts": artifacts, "git_commit": commit, "python": platform.python_version(),
                     "dependencies": {p: version(p) for p in ["pyarrow", "exchange-calendars", "duckdb", "requests"]},
                     "code_hashes": {str(p): file_hash(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
                     "raw_evidence_index": {"path": str(evidence_registry), "sha256": file_hash(evidence_registry), "records": len(sources)},
                     "api_errors": api.errors, "network_requests_this_invocation": api.requests, "cache_hits_this_invocation": api.cache_hits})
    manifest.update({"ended_at": datetime.now(timezone.utc).isoformat(),
                     "schema_version": "universe-snapshot-v2", "technical_validation": "PENDING_VALIDATOR",
                     "research_ready": manifest["status"] == "COMPLETE" and manifest["requested_cycles"] == 120 and totals.get("qualified", 0) > 0,
                     "dataset_id": digest(sorted((s["path"], s["sha256"]) for s in sources)),
                     "research_fingerprint": digest([manifest["config_hash"], sorted((s["path"], s["sha256"]) for s in sources)]),
                     "git_dirty": None})
    git_state = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if git_state.returncode == 0:
        manifest["git_dirty"] = bool(git_state.stdout.strip())
    write_json(report_dir / "manifest.json", manifest)
    summary = {"run_id": manifest["run_id"], "research_stage": "HISTORICAL_UNIVERSE", "population": "discovered security-cycle records; not unique tickers",
               "statistics_basis": "FULL_DISCOVERED_POPULATION", "sampling": False,
               "requested_cycles": manifest["requested_cycles"], "completed_cycles": len(completed), "counts": dict(totals),
               "metric_definitions": {"qualified": "all anchor common-stock type, exchange, price, float gates ELIGIBLE",
                    "unresolved": "no known exclusion and at least one unresolved gate",
                    "excluded_exchange/price/float": "independent gate counts; may overlap",
                    "unresolved_fields": "records with any unresolved field, including already excluded records",
                    "completed_cycle": "discovery and prices available, no unresolved candidate fields, and change observation available"}}
    paths = [e["snapshot"] for e in entries if e.get("snapshot")]
    if paths:
        with duckdb.connect() as con:
            con.read_parquet(paths, hive_partitioning=False).create_view("universe")
            unique = con.execute("SELECT count(DISTINCT ticker), count(DISTINCT security_id) FROM universe").fetchone()
            summary["unique_tickers"] = unique[0]
            summary["unique_security_ids"] = unique[1]
            summary["outcome_distributions"] = dict(con.execute("SELECT status, count(*) FROM universe GROUP BY status").fetchall())
    write_json(report_dir / "summary.json", summary)
    write_json(report_dir / "coverage.json", {"requested_cycles": manifest["requested_cycles"],
        "processed_cycles": manifest["processed_cycles"], "cycles": [
            {"cycle_id": c["cycle_id"], "split_group": c["split_group"], "status": e["status"],
             "anchor_at": c["anchor_at"], "end_at": c["end_at"],
             "reference_coverage": "PROCESSED" if e.get("snapshot") else "MISSING",
             "tick_session_coverage": {s: "NOT_REQUESTED_M1" for s in ["AH", "PRE", "RTH", "OVERNIGHT"]},
             "halt_coverage": "NOT_VERIFIED", "counts": e.get("counts", {})}
            for c, e in zip(manifest["config"]["calendar"], entries)]})
    quality = {"api_errors": api.errors, "missing_cycles": [e["cycle_id"] for e in entries if e["status"] == "ERROR"],
               "unresolved_cycles": [e["cycle_id"] for e in entries if e["status"] == "UNRESOLVED"],
               "limitations": ["Massive float is latest-only; no historical float substitution is permitted.",
                   "Historical ticker reference is effective-dated reconstruction, not a contemporaneously archived publication-time view.",
                   "Daily exchange observations do not supply exact intraday change times or detect same-day round-trip changes.",
                   "Previous close uses unadjusted provider regular-session daily aggregate close, not guaranteed official auction price.",
                   "Default market=stocks discovery does not enumerate the full OTC market; transitions to OTC become unresolved if absent from stocks reference.",
                   "Universe freezes at prior RTH close; newly listed securities during the cycle cannot enter that cycle."]}
    write_json(report_dir / "data_quality.json", quality)
    write_json(report_dir / "statistical_results.json", {"stage": "HISTORICAL_UNIVERSE", "status": "NOT_ESTIMATED",
                "sample_size": totals.get("candidates", 0), "event_sample_size": None,
                "outcome_distributions": None, "confidence_intervals": None,
                "reason": "No event detector, tick replay or continuation study has run. Universe counts are descriptive full-population counts, not predictive statistics."})
    anomaly_items = []
    if totals.get("unresolved_float", 0):
        anomaly_items.append({"kind": "HISTORICAL_FLOAT_UNAVAILABLE", "severity": "blocking_for_qualification", "records": totals["unresolved_float"]})
    if api.errors:
        anomaly_items.append({"kind": "API_ERRORS", "count": len(api.errors)})
    write_json(report_dir / "anomalies.json", {"items": anomaly_items,
                "drilldown": "Use market-lab query --run-id RUN --status UNRESOLVED and --cycle / --ticker filters. All records remain in Parquet."})
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.md").write_text(f"# Universe run {manifest['run_id']}\n\n"
        f"Processed cycles: {manifest['processed_cycles']} / {manifest['requested_cycles']}. Fully verified cycles: {len(completed)}.\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in sorted(totals.items()))
        + "\n\nThese are full discovered-population counts, not sampled estimates. No continuation outcomes or confidence intervals were estimated.\n\n"
        + "\n".join(f"- {x}" for x in quality["limitations"])
        + "\n\nSee manifest.json for configuration, calendar, code hashes, evidence hashes and artifact paths. Use query for focused extracts; raw evidence is never truncated.\n")


def query(root, run_id, dataset="universe", filters=None, limit=100, output=None, aggregate=False):
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id) or dataset not in {"universe", "events", "ticks"}:
        raise ValueError("invalid run or dataset")
    if not 1 <= limit <= 10000:
        raise ValueError("extract limit must be 1..10000")
    base = Path(root) / "runs" / run_id / dataset
    reference = base / "dataset-reference.json"
    if dataset == "ticks" and reference.exists():
        dataset_id = json.loads(reference.read_text())["dataset_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id):
            raise ValueError("invalid shared dataset ID")
        base = Path(root) / "datasets" / "ticks" / dataset_id
    paths = sorted(base.rglob("*.parquet"))
    if not paths:
        raise ValueError("dataset has no artifacts")
    con = duckdb.connect()
    try:
        con.read_parquet([str(p) for p in paths], hive_partitioning=False).create_view("evidence")
        columns = {r[0] for r in con.execute("DESCRIBE evidence").fetchall()}
        clauses, values = [], []
        for key, value in (filters or {}).items():
            if key not in {"cycle_id", "ticker", "event_id", "session", "status"} or key not in columns:
                raise ValueError(f"unsupported filter: {key}")
            clauses.append(f'"{key}" = ?')
            values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        count = con.execute("SELECT count(*) FROM evidence" + where, values).fetchone()[0]
        if aggregate:
            return {"matching_rows": count, "statistics_basis": "FULL_MATCHING_POPULATION", "sampling": False}
        cursor = con.execute("SELECT * FROM evidence" + where + " LIMIT ?", values + [limit])
        names = [d[0] for d in cursor.description]
        rows = [dict(zip(names, r)) for r in cursor.fetchall()]
        extract = {"run_id": run_id, "filters": filters, "matching_rows": count, "returned_rows": len(rows),
                   "truncated_extract": len(rows) < count, "statistics_basis": "FOCUSED_EXTRACT_NOT_POPULATION_STATISTICS", "rows": rows}
        if output:
            write_json(output, extract)
        return extract
    finally:
        con.close()
