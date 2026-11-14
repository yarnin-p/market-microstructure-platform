"""Validate bounded, saved Massive connector probes without fetching more data."""
import csv
import io
import json
from pathlib import Path

from .corporate_actions import connector_text
from .storage import file_hash, write_json


def audit_captures(folder, output):
    folder = Path(folder)
    checks = []
    for path in sorted(folder.glob("*-connector.json")):
        capture = json.loads(path.read_text())
        text = connector_text(capture)
        table = text.split("\n\n\nNext page available.", 1)[0]
        rows = list(csv.DictReader(io.StringIO(table)))
        if not rows:
            raise ValueError("probe has no records: " + path.name)
        endpoint, params = capture["path"], capture["params"]
        if "/float" in endpoint:
            raise ValueError("current float is forbidden in M1 audit")
        bounded_tick = "/v3/trades/" in endpoint or "/v3/quotes/" in endpoint
        if bounded_tick:
            lo, hi = int(params["timestamp.gte"]), int(params["timestamp.lt"])
            if hi - lo > 60_000_000_000 or params["limit"] > 100 or len(rows) > params["limit"]:
                raise ValueError("tick probe exceeds approved budget")
            stamps = [int(r["sip_timestamp"]) for r in rows]
            if stamps != sorted(stamps) or not all(lo <= t < hi for t in stamps):
                raise ValueError("tick timestamps violate requested range/order")
        if endpoint == "/v3/reference/exchanges":
            mapped = {r["mic"]: r for r in rows}
            for mic in ["XNAS", "XASE", "XNYS"]:
                if mapped.get(mic, {}).get("type") != "exchange":
                    raise ValueError("missing approved MIC in live dictionary")
        checks.append({"capture": path.name, "path": str(path.resolve()), "sha256": file_hash(path),
                       "endpoint": endpoint, "params": params, "rows": len(rows), "status": "PASS",
                       "retrieved_at": capture["retrieved_at"], "transport": "AUTHENTICATED_MASSIVE_CONNECTOR",
                       "has_more": "Next page available." in text,
                       "coverage_claim": "BOUNDED_SCHEMA_PROBE_ONLY" if bounded_tick else "CAPTURED_PAGE_ONLY"})
    if not checks:
        raise ValueError("no connector captures")
    tick_checks = [c for c in checks if c["coverage_claim"] == "BOUNDED_SCHEMA_PROBE_ONLY"]
    windows = {(c["params"]["timestamp.gte"], c["params"]["timestamp.lt"]) for c in tick_checks}
    if len(windows) > 2 or len(checks) > 30:
        raise ValueError("audit exceeds approved call/window budget")
    result = {"schema_version": "m1-capability-audit-v1", "status": "PASS", "checks": checks,
              "connector_calls_recorded": len(checks), "http_retries_inside_connector": "NOT_EXPOSED",
              "local_http_entitlement": "NOT_TESTED_NO_LOCAL_KEY", "tick_rows": sum(c["rows"] for c in tick_checks),
              "tick_windows": len(windows), "bulk_ticks_downloaded": False,
              "historical_float": "UNAVAILABLE_UNRESOLVED", "current_float_requested": False,
              "event_outcomes_computed": False,
              "limitations": ["Connector exposes normalized tables, not original wire HTTP bodies or retry counts.",
                              "Tick probes validate access/schema only; their pagination is intentionally not followed.",
                              "No full-session/overnight/halt completeness or historical float verification is implied."]}
    write_json(output, result)
    return result
