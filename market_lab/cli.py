import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from .api import Massive, load_key, APIError
from .pipeline import build, validate
from .results import query
from .eligibility import event_eligibility, validate_evidence
from .storage import write_json, json_default
from .bundle import export_bundle, validate_bundle
from .audit import audit_captures
from .corporate_actions import import_connector_actions


def main():
    parser = argparse.ArgumentParser(description="Historical universe research; never downloads bulk ticks.")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--env-file", help="Credential file path; contents never printed or copied")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit-captures")
    audit.add_argument("--folder", required=True)
    audit.add_argument("--output", required=True)
    actions = sub.add_parser("import-actions")
    actions.add_argument("--folder", required=True)
    actions.add_argument("--output", required=True)
    actions.add_argument("--start", required=True)
    actions.add_argument("--end", required=True)
    b = sub.add_parser("build", aliases=["run"])
    b.add_argument("--run-id", required=True)
    b.add_argument("--end", required=True, help="Last completed cycle date (YYYY-MM-DD)")
    b.add_argument("--cycles", type=int, default=120)
    b.add_argument("--workers", type=int, default=1, help="Bounded reference/price prefetch workers (1..16)")
    b.add_argument("--evidence", help="JSON array of externally verified effective-dated float/exchange evidence")
    b.add_argument("--corporate-actions", help="Versioned corporate action dataset with complete source evidence")
    b.add_argument("--offline", action="store_true", help="Read pinned cache only; no network calls")
    b.add_argument("--source-index", help="Pinned raw evidence index for legacy cache verification")
    b.add_argument("--max-requests", type=int, help="Hard HTTP request budget including retries")
    b.add_argument("--export-bundle", action="store_true", help="Optional consolidated ZIP export")
    b.add_argument("--bundle-budget-mb", type=float, default=50)
    for command in ["report", "export"]:
        p = sub.add_parser(command)
        p.add_argument("--run-id", required=True)
        p.add_argument("--format", choices=["bundle"], default="bundle")
        p.add_argument("--bundle-budget-mb", type=float, default=50)
    vb = sub.add_parser("validate-bundle")
    vb.add_argument("path")
    v = sub.add_parser("validate")
    v.add_argument("--run-id", required=True)
    q = sub.add_parser("query")
    q.add_argument("--run-id", required=True)
    q.add_argument("--dataset", choices=["universe", "events", "ticks"], default="universe")
    for f in ["cycle", "ticker", "event-id", "session", "status"]:
        q.add_argument("--" + f)
    q.add_argument("--limit", type=int, default=100)
    q.add_argument("--output")
    q.add_argument("--count", action="store_true")
    s = sub.add_parser("smoke")
    s.add_argument("--date", required=True)
    s.add_argument("--ticker", default="AAPL")
    e = sub.add_parser("event-check")
    e.add_argument("--run-id", required=True)
    e.add_argument("--cycle", required=True)
    e.add_argument("--ticker", required=True)
    e.add_argument("--at", required=True)
    e.add_argument("--evidence", help="Additional point-in-time exchange evidence; initial snapshot remains frozen")
    args = parser.parse_args()
    root, reports = Path(args.data_root).resolve(), Path(args.reports_root).resolve()
    try:
        if args.command == "audit-captures":
            result = audit_captures(args.folder, args.output)
            print(json.dumps({k: v for k, v in result.items() if k != "checks"}, indent=2))
            return 0
        if args.command == "import-actions":
            print(json.dumps(import_connector_actions(args.folder, args.output, args.start, args.end), indent=2))
            return 0
        if args.command in {"build", "run"}:
            evidence = json.loads(Path(args.evidence).read_text()) if args.evidence else []
            api = Massive(root / "cache", load_key(args.env_file), offline=args.offline,
                          max_requests=args.max_requests, evidence_index=args.source_index)
            m = build(api, root, reports, args.run_id, args.end, args.cycles, evidence, args.workers, args.corporate_actions)
            print(json.dumps({k: m[k] for k in ["run_id", "status", "completed_cycles", "processed_cycles"]}, indent=2))
            checks = validate(reports / args.run_id)
            write_json(reports / args.run_id / "acceptance.json", checks)
            if args.export_bundle:
                print(json.dumps(export_bundle(reports / args.run_id, Path("research/runs") / args.run_id / "research_bundle.zip",
                                               int(args.bundle_budget_mb * 1024 * 1024)), indent=2))
            return 0 if m["status"] == "COMPLETE" else 2
        if args.command in {"report", "export"}:
            print(json.dumps(export_bundle(reports / args.run_id, Path("research/runs") / args.run_id / "research_bundle.zip",
                                           int(args.bundle_budget_mb * 1024 * 1024)), indent=2))
        elif args.command == "validate-bundle":
            print(json.dumps(validate_bundle(args.path), indent=2))
        elif args.command == "validate":
            print(json.dumps(validate(reports / args.run_id), indent=2))
        elif args.command == "query":
            filters = {k: v for k, v in {"cycle_id": args.cycle, "ticker": args.ticker, "event_id": args.event_id,
                                       "session": args.session, "status": args.status}.items() if v is not None}
            print(json.dumps(query(root, args.run_id, args.dataset, filters, args.limit, args.output, args.count), indent=2, default=json_default))
        elif args.command == "event-check":
            run = root / "runs" / args.run_id
            rows = pq.ParquetFile(run / "universe" / f"cycle={args.cycle}" / "snapshot.parquet").read().to_pylist()
            matches = [r for r in rows if r["ticker"] == args.ticker]
            if len(matches) != 1:
                raise ValueError("ticker not uniquely present in frozen universe")
            evidence = json.loads((run / "evidence.json").read_text())
            if args.evidence:
                evidence += json.loads(Path(args.evidence).read_text())
            validate_evidence(evidence)
            result = event_eligibility(matches[0], args.at, evidence, json.loads((run / "exchange_directory.json").read_text()))
            print(json.dumps(result, indent=2))
        elif args.command == "smoke":
            api = Massive(root / "cache", load_key(args.env_file))
            checks = {}
            for name, path, params in [
                ("exchanges", "/v3/reference/exchanges", {"asset_class": "stocks", "locale": "us"}),
                ("historical_ticker", "/v3/reference/tickers", {"ticker": args.ticker, "date": args.date, "market": "stocks", "limit": 1}),
                ("previous_close", f"/v1/open-close/{args.ticker}/{args.date}", {"adjusted": False})]:
                try:
                    body = api.get(path, params)
                    checks[name] = {"status": "OK", "response": body}
                except APIError as error:
                    checks[name] = {"status": "ERROR", "error": str(error)}
            result = {"checks": checks, "api_errors": api.errors, "evidence": api.evidence,
                      "historical_float_supported": False, "historical_float_reason": "Provider documents latest-only endpoint; date filters are not supported."}
            write_json(reports / "live-smoke" / "smoke.json", result)
            print(json.dumps({k: {x: y for x, y in v.items() if x != "response"} for k, v in checks.items()}, indent=2))
            return 0 if all(v["status"] == "OK" for v in checks.values()) else 2
    except (ValueError, APIError, OSError) as error:
        parser.exit(1, f"{type(error).__name__}: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
