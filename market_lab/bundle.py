"""Consolidated export foundation. Does not pretend to implement tick research."""
import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .storage import file_hash, parquet, write_json

BUNDLE_VERSION = "research-bundle-v1"
REQUIRED = {"manifest.json", "summary.json", "event_results.parquet", "cycle_metrics.parquet",
            "cohort_metrics.parquet", "distributions.parquet", "statistical_tests.json",
            "data_quality.json", "anomalies.json", "report.md"}
EVENT_SCHEMA = pa.schema(
    [(k, pa.string()) for k in ["event_id", "cycle_id", "ticker", "security_id", "session", "event_timestamp",
                              "confirmation_classification", "pullback_classification", "continuation_outcome", "outcome_horizon",
                              "data_validity", "censoring_reason", "source_dataset_id"]]
    + [(k, pa.float64()) for k in ["previous_rth_close", "event_price", "bid", "ask", "shares_float", "mfe", "mae"]]
    + [("censored", pa.bool_()), ("event_order", pa.int64())])
CYCLE_SCHEMA = pa.schema(
    [(k, pa.string()) for k in ["cycle_id", "universe_status", "replay_status"]]
    + [(k, pa.int64()) for k in ["candidates", "qualified", "excluded", "unresolved", "excluded_type", "excluded_exchange",
                               "excluded_price", "excluded_float", "detected_events", "ah_events", "pre_events", "rth_events"]]
    + [("continuation_rate", pa.float64())])
COHORT_SCHEMA = pa.schema([("dimension", pa.string()), ("cohort", pa.string()), ("event_count", pa.int64()), ("continuation_rate", pa.float64())])
DISTRIBUTION_SCHEMA = pa.schema([("metric", pa.string()), ("population", pa.string()), ("sample_size", pa.int64()), ("quantile", pa.float64()), ("value", pa.float64())])
TABLE_SCHEMAS = {"event_results.parquet": EVENT_SCHEMA, "cycle_metrics.parquet": CYCLE_SCHEMA,
                 "cohort_metrics.parquet": COHORT_SCHEMA, "distributions.parquet": DISTRIBUTION_SCHEMA}


def export_bundle(report_dir, output, budget_bytes=50 * 1024 * 1024):
    """Package all processed universe cycles. Research-only fields remain null.

    Full-event aggregation is deliberately gated until detector/outcome contracts
    exist. This prevents silently accepting arbitrary events as valid research.
    """
    from .pipeline import validate
    validate(report_dir)
    report_dir, output = Path(report_dir), Path(output)
    m = json.loads((report_dir / "manifest.json").read_text())
    run_root = Path(m["artifact_root"])
    if any((run_root / "events").rglob("*.parquet")):
        raise ValueError("event aggregation is not implemented; event evidence remains local and must not be silently omitted")
    if budget_bytes < 1:
        raise ValueError("bundle size budget must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="research-bundle-", dir=output.parent) as temp:
        stage = Path(temp)
        cycle_rows = []
        for e in m["cycles"]:
            c = e.get("counts", {})
            cycle_rows.append({"cycle_id": e["cycle_id"], "universe_status": e["status"], "replay_status": "NOT_IMPLEMENTED",
                               **{k: c.get(k) for k in ["candidates", "qualified", "excluded", "unresolved", "excluded_type",
                                                       "excluded_exchange", "excluded_price", "excluded_float"]},
                               **{k: None for k in ["detected_events", "ah_events", "pre_events", "rth_events", "continuation_rate"]}})
        parquet(stage / "cycle_metrics.parquet", cycle_rows, CYCLE_SCHEMA)
        for name in ["event_results.parquet", "cohort_metrics.parquet", "distributions.parquet"]:
            parquet(stage / name, [], TABLE_SCHEMAS[name])
        summary = json.loads((report_dir / "summary.json").read_text())
        summary.update({"event_research_status": "NOT_IMPLEMENTED", "total_detected_events": None,
                        "price_confirmation_events": None, "pullback_events": None, "continuation_outcomes": None,
                        "false_spike_outcomes": None, "false_pullback_outcomes": None, "mfe_mae": None,
                        "time_to_target": None, "time_to_invalidation": None,
                        "event_results_rows": 0, "event_rows_explanation": "No detector/replay executed; zero stored event rows does not estimate zero market events."})
        write_json(stage / "summary.json", summary)
        quality = json.loads((report_dir / "data_quality.json").read_text())
        quality.update({"missing_tick_intervals": None, "invalid_timestamps": None, "missing_quotes": None,
                        "duplicate_or_invalid_events": None, "replay_failures": None,
                        "tick_quality_status": "NOT_ASSESSED_NO_REPLAY", "coverage_table": "cycle_metrics.parquet"})
        write_json(stage / "data_quality.json", quality)
        write_json(stage / "anomalies.json", json.loads((report_dir / "anomalies.json").read_text()))
        write_json(stage / "statistical_tests.json", {
            "status": "NOT_IMPLEMENTED", "sample_size": None, "confidence_intervals": None, "tests": [],
            "uncertainty_estimates": None, "independent_opportunities": None,
            "required_future_method": "Account for dependence within security and cycle, overlapping events, censoring and multiple testing. Method must be specified before reporting significance.",
            "performance_basis": "No gross event or execution-adjusted trading performance has been estimated.",
            "population_counts": "Universe counts use the full discovered population; no sampling."})
        text = (report_dir / "report.md").read_text()
        text += "\n## Consolidated bundle scope\n\nExecution status: **INCOMPLETE** as an event-research experiment. TASK 001 universe outputs are consolidated across all requested cycles in cycle_metrics.parquet; failed/unresolved cycles remain visible.\n\n"
        text += "event_results.parquet, cohort_metrics.parquet and distributions.parquet are typed empty tables because tick replay and event classification are not implemented. Their emptiness is not a finding about the market. No event sampling, truncation, probabilities or significance claims were produced.\n\n"
        text += "Raw tick data is not included. Universe source snapshots stay at the local artifact paths recorded in manifest.json. Additional inspection uses the local query CLI by run, cycle or ticker; event-ID/session drilldowns apply when those datasets exist.\n"
        (stage / "report.md").write_text(text)
        files = {}
        for p in sorted(stage.iterdir()):
            metadata = {"sha256": file_hash(p), "bytes": p.stat().st_size}
            if p.suffix == ".parquet":
                table = pq.ParquetFile(p)
                metadata.update({"records": table.metadata.num_rows, "schema": str(table.schema_arrow)})
            files[p.name] = metadata
        manifest = {"contract_version": BUNDLE_VERSION, "experiment_id": m["run_id"], "code_version": "0.1.0",
                    "git_commit": m["git_commit"], "code_hashes": m["code_hashes"], "dependencies": m["dependencies"],
                    "research_configuration": m["config"], "configuration_hash": m["config_hash"],
                    "input_dataset_identifiers": [m["raw_evidence_index"]], "local_artifact_root": str(run_root),
                    "requested_trading_cycles": [c["cycle_id"] for c in m["config"]["calendar"]],
                    "processed_trading_cycles": [c["cycle_id"] for c in m["cycles"] if c["status"] != "ERROR"],
                    "universe_completed_cycles": m["completed_cycles"], "universe_status": m["status"],
                    "event_definitions": {"status": "NOT_IMPLEMENTED", "plus_ten_percent_reference": "previous RTH close; detector contract pending"},
                    "outcome_definitions": {"status": "NOT_IMPLEMENTED"},
                    "timezone": "America/New_York", "cycle_interval": "(previous RTH close, current RTH close]",
                    "sessions": ["AH", "PRE", "RTH"], "internal_session_aliases": {"AFTER_HOURS": "AH", "PREMARKET": "PRE", "RTH": "RTH"},
                    "schema_versions": {name: BUNDLE_VERSION for name in TABLE_SCHEMAS},
                    "files": files, "execution_status": "INCOMPLETE", "packaged_at": datetime.now(timezone.utc).isoformat(),
                    "research_completion_timestamp": None, "raw_ticks_included": False,
                    "event_population": {"stored": 0, "included": 0, "sampled": False, "externally_retained": 0,
                                         "status": "NOT_GENERATED"},
                    "size_policy": {"budget_bytes": budget_bytes, "mode": "FULL_AVAILABLE_RESULTS",
                                    "future_oversize_events": "Retain full events locally and disclose omitted/included counts in a compact analysis bundle; never sample silently."}}
        write_json(stage / "manifest.json", manifest)
        temp_zip = stage / "research_bundle.zip"
        def pack():
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name in sorted(REQUIRED):
                    archive.write(stage / name, name)
        pack()
        if temp_zip.stat().st_size > budget_bytes:
            # With no events to externalize, even the compact metadata exceeds the
            # budget. Preserve everything and disclose the unavoidable overage.
            manifest["size_policy"].update({"mode": "COMPACT_ANALYSIS", "budget_exceeded": True,
                                            "reason": "Metadata/minimal empty schemas exceed budget; no evidence was omitted. Increase budget."})
            write_json(stage / "manifest.json", manifest)
            pack()
        validate_bundle(temp_zip)
        os.replace(temp_zip, output)
    return {"path": str(output.resolve()), "bytes": output.stat().st_size, "sha256": file_hash(output),
            "execution_status": "INCOMPLETE", "processed_cycles": m["processed_cycles"], "stored_event_rows": 0}


def validate_bundle(path):
    with zipfile.ZipFile(path) as archive:
        if set(archive.namelist()) != REQUIRED or len(archive.namelist()) != len(REQUIRED):
            raise ValueError("bundle members do not match contract")
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity error")
        manifest = json.loads(archive.read("manifest.json"))
        tables = {}
        with tempfile.TemporaryDirectory(prefix="validate-research-") as temp:
            for name, meta in manifest["files"].items():
                if name not in REQUIRED - {"manifest.json"}:
                    raise ValueError("unexpected bundle member")
                # Stream table contents to local temporary storage, not RAM.
                p = Path(temp) / name
                h = hashlib.sha256()
                size = 0
                with archive.open(name) as source, p.open("wb") as dest:
                    while block := source.read(1024 * 1024):
                        h.update(block); dest.write(block); size += len(block)
                if h.hexdigest() != meta["sha256"] or size != meta["bytes"]:
                    raise ValueError("bundle checksum/size mismatch")
                if name in TABLE_SCHEMAS:
                    pf = pq.ParquetFile(p)
                    if pf.metadata.num_rows != meta["records"] or pf.schema_arrow != TABLE_SCHEMAS[name]:
                        raise ValueError("bundle schema/record-count mismatch")
                    tables[name] = pf.read() if name == "cycle_metrics.parquet" else pf.metadata.num_rows
            if set(manifest["files"]) != REQUIRED - {"manifest.json"}:
                raise ValueError("missing file checksum")
            cycles = tables["cycle_metrics.parquet"].to_pylist()
            expected = manifest["requested_trading_cycles"]
            if len(cycles) != len(expected) or [c["cycle_id"] for c in cycles] != expected or len(set(expected)) != len(expected):
                raise ValueError("cycle coverage mismatch")
            summary = json.loads(archive.read("summary.json"))
            for metric in ["candidates", "qualified", "excluded", "unresolved", "excluded_exchange", "excluded_price", "excluded_float", "excluded_type"]:
                if sum(c[metric] or 0 for c in cycles) != summary["counts"].get(metric, 0):
                    raise ValueError("bundle aggregation mismatch")
            if tables["event_results.parquet"] != summary["event_results_rows"]:
                raise ValueError("event row count mismatch")
            if manifest["event_definitions"]["status"] == "NOT_IMPLEMENTED" and manifest["execution_status"] != "INCOMPLETE":
                raise ValueError("unimplemented research cannot be complete")
    return {"validation": "PASSED", "bytes": Path(path).stat().st_size, "members": len(REQUIRED),
            "cycle_records": len(cycles), "event_records": tables["event_results.parquet"]}
