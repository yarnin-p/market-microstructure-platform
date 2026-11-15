"""Public TEST-key feasibility probe. Never imports or writes M1 datasets.

At most five HTTP calls across a persisted output ledger, no automatic retries,
redirects, pagination or paid credentials. Explicit --resume can retry a failed
comparison inside the same five-call budget.
Use a fresh output directory for each explicitly authorized experiment.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://api.ortex.com/api/v11/stock/NYSE/AMC/reference/free_float/"
MAX_BYTES = 2 * 1024 * 1024


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def run(output, resume=False):
    if not resume:
        output.mkdir(parents=True, exist_ok=False)
    requests_plan = [
        ("documented_pit", {"from_date": "2017-06-01", "point_in_time": "true", "split_adjusted": "false"}),
        ("documented_non_pit", {"from_date": "2017-06-01", "point_in_time": "false", "split_adjusted": "false"}),
        ("documented_adjusted", {"from_date": "2017-06-01", "point_in_time": "true", "split_adjusted": "true"}),
        ("m1_window_pit", {"from_date": "2026-05-27", "to_date": "2026-11-13", "point_in_time": "true", "split_adjusted": "false"}),
    ]
    # The documentation supplies from_date only; omitted to_date uses server today.
    ledger = json.loads((output / "manifest.json").read_text()) if resume else {
        "schema_version": "ortex-demo-probe-v1", "auth": "PUBLIC_DEMO_TEST_ONLY",
        "attempts": [], "m1_status": "BLOCKED_DATA"}
    ledger["max_api_calls"] = 5
    if ledger.get("auth") != "PUBLIC_DEMO_TEST_ONLY" or len(ledger["attempts"]) > 5:
        raise ValueError("invalid probe ledger")
    successful = {r["name"] for r in ledger["attempts"] if r.get("http_status") == 200}
    session = requests.Session()
    session.trust_env = False  # Do not load netrc credentials or ambient proxies.
    try:
        for name, params in requests_plan:
            if name in successful:
                continue
            if len(ledger["attempts"]) >= 5:
                break
            if ledger["attempts"]:
                time.sleep(2)  # Observed demo allowance: one request per second.
            record = {"name": name, "url": URL, "params": params,
                      "started_at": datetime.now(timezone.utc).isoformat(), "status": "ATTEMPT_STARTED"}
            ledger["attempts"].append(record)
            save(output / "manifest.json", ledger)  # Count attempts before network I/O.
            start = time.monotonic()
            try:
                with session.get(URL, params=params, headers={"Ortex-Api-Key": "TEST", "Accept": "application/json"},
                                 timeout=(10, 25), allow_redirects=False, stream=True) as response:
                    record["http_status"] = response.status_code
                    record["headers"] = {k: v for k, v in response.headers.items()
                                         if k.lower().startswith(("ortex-", "x-", "ratelimit"))
                                         or k.lower() in {"date", "content-type", "etag", "retry-after"}}
                    chunks, size = [], 0
                    for chunk in response.iter_content(16384):
                        size += len(chunk)
                        if size > MAX_BYTES or time.monotonic() - start > 40:
                            raise ValueError("response size/time budget exceeded")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    # No request headers, cookies or credentials are persisted.
                    record["body_sha256"] = hashlib.sha256(body).hexdigest()
                    record["body_bytes"] = len(body)
                    try:
                        parsed = json.loads(body)
                        filename = f"{len(ledger['attempts']):02d}-{name}.json"
                        save(output / filename, parsed)
                        record["response_file"] = filename
                        record["top_level_keys"] = list(parsed) if isinstance(parsed, dict) else None
                        record["rows"] = len(parsed.get("data", [])) if isinstance(parsed, dict) else None
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        (output / f"{name}.txt").write_bytes(body)
                        record["response_file"] = f"{name}.txt"
                    record["status"] = "RESPONSE_CAPTURED"
            except (requests.RequestException, ValueError) as error:
                record["status"] = "TRANSPORT_OR_BUDGET_ERROR"
                record["error_type"] = type(error).__name__
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            save(output / "manifest.json", ledger)
            print(json.dumps(record), flush=True)
            # Authentication, transport, rate or server failures need no further calls.
            if record.get("http_status") in {401, 402, 429} or record.get("http_status", 0) >= 500 or record["status"] != "RESPONSE_CAPTURED":
                break
            if record.get("http_status") != 200:
                break  # Do not search for an unrestricted ticker or date.
    finally:
        session.close()
    return ledger


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Continue the same persisted five-call budget")
    args = parser.parse_args()
    run(args.output, args.resume)
