"""Bounded immutable M2 REST storage, deliberately separate from strict M1 client."""
import fcntl
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, quote

import pyarrow as pa
import pyarrow.parquet as pq
import requests

from .api import APIError, safe_url, scrub
from .storage import digest, file_hash, write_json, parquet, durable_replace


class TickClient:
    def __init__(self, root, config, key=None, offline=False, session=None):
        self.root, self.config, self.key = Path(root), config, key
        self.offline = offline
        self.session = session or requests.Session()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "request-ledger.json"
        self.ledger = json.loads(self.ledger_path.read_text()) if self.ledger_path.exists() else {"attempts": [], "pages": 0, "decoded_bytes": 0}
        self.hits = 0

    def get(self, path, params=None):
        url = safe_url(path if path.startswith("https:") else "https://api.massive.com" + path)
        base = url.split("?", 1)[0]
        if not any(urlparse(base).path.startswith(p) for p in ["/v3/trades/", "/v3/quotes/", "/v3/reference/", "/stocks/vX/float"]):
            raise APIError("M2_ENDPOINT_NOT_ALLOWED")
        query = dict(parse_qsl(urlparse(url).query)); query.update(params or {})
        request = {"url": base, "params": query}
        key = digest(request)
        raw = self.root / "pages" / (key + ".json")
        meta = raw.with_suffix(".meta.json")
        if meta.exists():
            source = json.loads(meta.read_text())
            if source["request"] != request or file_hash(raw) != source["sha256"]:
                raise APIError("M2_RAW_HASH_OR_REQUEST_MISMATCH")
            self.hits += 1
            return json.loads(raw.read_text()), source
        if self.offline:
            raise APIError("M2_OFFLINE_CACHE_MISS")
        if not self.key:
            raise APIError("MISSING_API_KEY")
        if len(self.ledger["attempts"]) >= self.config["max_requests"] or self.ledger["pages"] >= self.config["max_pages"]:
            raise APIError("M2_REQUEST_OR_PAGE_BUDGET")
        if self.ledger["decoded_bytes"] >= self.config["max_decoded_bytes"]:
            raise APIError("M2_BYTE_BUDGET")
        attempt = {"request_hash": key, "path": urlparse(base).path, "started_at": datetime.now(timezone.utc).isoformat(), "status": "STARTED", "bytes": 0}
        self.ledger["attempts"].append(attempt)
        write_json(self.ledger_path, self.ledger)
        raw.parent.mkdir(parents=True, exist_ok=True)
        temp = raw.with_suffix(".tmp")
        try:
            time.sleep(0.1)
            started = time.monotonic()
            with self.session.get(base, params=query, headers={"Authorization": "Bearer " + self.key},
                                  timeout=(10, 45), stream=True, allow_redirects=False) as response:
                attempt["http_status"] = response.status_code
                if response.status_code != 200:
                    raise APIError(f"HTTP_{response.status_code}")
                with temp.open("wb") as f:
                    for block in response.iter_content(65536):
                        if time.monotonic() - started > 120:
                            raise APIError("M2_RESPONSE_TIME_BUDGET")
                        attempt["bytes"] += len(block)
                        self.ledger["decoded_bytes"] += len(block)
                        # Durable accounting survives interruption during a large response.
                        write_json(self.ledger_path, self.ledger)
                        if attempt["bytes"] > self.config["max_page_bytes"] or self.ledger["decoded_bytes"] > self.config["max_decoded_bytes"]:
                            raise APIError("M2_BYTE_BUDGET")
                        f.write(block)
            body = json.loads(temp.read_text())
            if not isinstance(body, dict) or body.get("status") in {"ERROR", "NOT_AUTHORIZED"} or "results" not in body:
                raise APIError("M2_INVALID_RESPONSE")
            # Persist original response bytes unless an access-bearing URL is present.
            sanitized = scrub(body, self.key)
            if sanitized != body:
                temp.write_text(json.dumps(sanitized, separators=(",", ":")))
            durable_replace(temp, raw)
            source = {"path": str(raw.resolve()), "sha256": file_hash(raw), "request": request,
                      "retrieved_at": datetime.now(timezone.utc).isoformat(), "provider_request_id": body.get("request_id"),
                      "transport": "REST", "sanitized_access_tokens": sanitized != body, "bytes": raw.stat().st_size}
            write_json(meta, source)
            attempt["status"] = "OK"
            self.ledger["pages"] += 1
            return sanitized, source
        except requests.RequestException as exc:
            attempt["status"] = type(exc).__name__
            raise APIError("M2_NETWORK_" + type(exc).__name__) from None
        except (APIError, ValueError) as exc:
            attempt["status"] = str(exc) if isinstance(exc, APIError) else "INVALID_JSON"
            raise APIError(attempt["status"]) from None
        finally:
            if temp.exists():
                temp.unlink()
            write_json(self.ledger_path, self.ledger)

    def window(self, kind, ticker, start_ns, end_ns, output):
        """Fetch a complete (start,end] SIP window, retaining page-level lineage."""
        if kind not in {"trades", "quotes"} or start_ns >= end_ns:
            raise ValueError("invalid tick window")
        output = Path(output)
        manifest_path = output / "coverage.json"
        request_spec = {"kind": kind, "ticker": ticker, "start_ns": start_ns, "end_ns": end_ns}
        if manifest_path.exists():
            prior = json.loads(manifest_path.read_text())
            if prior["request"] != request_spec:
                raise APIError("WINDOW_CONFIG_MISMATCH")
            for p in prior["pages"]:
                if file_hash(p["path"]) != p["sha256"]:
                    raise APIError("WINDOW_HASH_MISMATCH")
            if prior["complete"]:
                return prior
        path = f"/v3/{kind}/{quote(ticker, safe='')}"
        params = {"timestamp.gt": str(start_ns), "timestamp.lte": str(end_ns), "order": "asc", "sort": "timestamp",
                  "limit": self.config["trade_page_limit" if kind == "trades" else "quote_page_limit"]}
        coverage = {"request": request_spec, "pages": [], "complete": False, "error": None, "raw_rows": 0,
                    "coverage_claim": "PROVIDER_SIP_WINDOW_PAGINATION_ONLY", "unobserved_overnight": True}
        seen = set()
        try:
            for _ in range(self.config["max_window_pages"]):
                marker = digest([path, params])
                if marker in seen:
                    raise APIError("PAGINATION_LOOP")
                seen.add(marker)
                body, source = self.get(path, params)
                if not isinstance(body["results"], list):
                    raise APIError("MISSING_RESULTS_ARRAY")
                coverage["pages"].append({**source, "rows": len(body["results"])})
                coverage["raw_rows"] += len(body["results"])
                write_json(manifest_path, coverage)
                path = body.get("next_url")
                params = None
                if not path:
                    coverage["complete"] = True
                    break
            if path:
                coverage["error"] = "WINDOW_PAGE_BUDGET"
        except APIError as error:
            coverage["error"] = str(error)
        write_json(manifest_path, coverage)
        return coverage


def source_rows(coverage):
    for page in coverage["pages"]:
        if file_hash(page["path"]) != page["sha256"]:
            raise APIError("RAW_EVIDENCE_HASH_MISMATCH")
        rows = json.loads(Path(page["path"]).read_text())["results"]
        for i, row in enumerate(rows):
            yield row, {"path": page["path"], "sha256": page["sha256"], "row": i}


TICK_SCHEMA = pa.schema([(k, pa.string()) for k in ["record_id", "security_id", "ticker", "cycle_id", "session", "kind",
    "trade_id", "price", "size", "bid_price", "ask_price", "bid_size", "ask_size", "conditions_json", "indicators_json",
    "source_json", "raw_json", "normalization_status"]] + [(k, pa.int64()) for k in ["sip_timestamp", "participant_timestamp",
    "sequence_number", "exchange", "bid_exchange", "ask_exchange", "correction", "trf_id", "trf_timestamp"]])


def normalize(coverage, security_id, cycle, output):
    from .tick_replay import session_label
    rows, seen, duplicates, invalid = [], set(), [], 0
    start, end = coverage["request"]["start_ns"], coverage["request"]["end_ns"]
    for raw, source in source_rows(coverage):
        ident = digest(raw)
        if ident in seen:
            duplicates.append({"raw_record_hash": ident, "source": source})
            continue
        seen.add(ident)
        t = raw.get("sip_timestamp")
        valid = isinstance(t, int) and not isinstance(t, bool) and start < t <= end
        invalid += not valid
        row = {"record_id": ident, "security_id": security_id, "ticker": coverage["request"]["ticker"],
               "cycle_id": cycle["cycle_id"], "kind": coverage["request"]["kind"],
               "session": session_label(cycle, t) if valid else "INVALID", "trade_id": str(raw["id"]) if raw.get("id") is not None else None,
               "conditions_json": json.dumps(raw.get("conditions", [])), "indicators_json": json.dumps(raw.get("indicators", [])),
               "raw_json": json.dumps(raw, sort_keys=True), "source_json": json.dumps(source),
               "normalization_status": "OK" if valid else "INVALID_OR_OUT_OF_WINDOW_TIMESTAMP"}
        for key in ["price", "size", "bid_price", "ask_price", "bid_size", "ask_size"]:
            value = raw.get("decimal_size", raw.get(key)) if key == "size" else raw.get(key)
            row[key] = str(value) if value is not None else None
        for field in [f.name for f in TICK_SCHEMA if pa.types.is_int64(f.type)]:
            v = raw.get(field)
            row[field] = v if isinstance(v, int) and not isinstance(v, bool) and -(2**63) <= v < 2**63 else None
        rows.append(row)
    rows.sort(key=lambda r: (r["sip_timestamp"] or 0, r["sequence_number"] or 0, r["exchange"] or 0, r["trade_id"] or "", r["record_id"]))
    parquet(output, rows, TICK_SCHEMA)
    audit = {"raw_rows": coverage["raw_rows"], "normalized_rows": len(rows), "exact_duplicates": len(duplicates),
             "invalid_timestamp_rows": invalid, "duplicates": duplicates, "deduplication": "exact full raw record equality; corrections with different SIP/code are preserved",
             "path": str(Path(output).resolve()), "sha256": file_hash(output)}
    write_json(Path(output).with_suffix(".audit.json"), audit)
    return rows, audit
