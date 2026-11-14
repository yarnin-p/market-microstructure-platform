import json
import fcntl
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import pyarrow.parquet as pq
import requests

from .storage import digest, parquet, raw_schema, file_hash, write_json


class APIError(RuntimeError):
    pass


def load_key(env_file=None):
    key = os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY")
    if key:
        return key
    if env_file:
        for line in Path(env_file).read_text().splitlines():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() in {"MASSIVE_API_KEY", "POLYGON_API_KEY"}:
                return value.strip().strip("\"'")
    return None


def safe_url(value):
    p = urlparse(value)
    if p.scheme != "https" or p.hostname != "api.massive.com" or p.port not in (None, 443) or p.username:
        raise APIError("UNSAFE_PAGINATION_URL")
    q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in {"apikey", "api_key"}]
    return urlunparse((p.scheme, p.netloc, p.path, "", urlencode(sorted(q)), ""))


def scrub(value, key):
    if isinstance(value, dict):
        return {k: scrub(v, key) for k, v in value.items() if k.lower() not in {"apikey", "api_key", "authorization"}}
    if isinstance(value, list):
        return [scrub(v, key) for v in value]
    if isinstance(value, str):
        if key:
            value = value.replace(key, "[REDACTED]")
        if value.startswith("https://api.massive.com"):
            return safe_url(value)
    return value


class Massive:
    def __init__(self, root, key=None, session=None, retries=3, offline=False, max_requests=None, evidence_index=None):
        self.root = Path(root)
        self.key = key
        self.session = session or requests.Session()
        self.retries = retries
        self.errors = []
        self.requests = 0
        self.cache_hits = 0
        self.evidence = []
        self.offline = offline
        self.max_requests = max_requests
        self.pinned_hashes = {}
        if evidence_index:
            self.pinned_hashes = {str(Path(r["path"]).resolve()): r["sha256"]
                                  for r in json.loads(Path(evidence_index).read_text())}

    def get(self, path, params=None):
        url = safe_url(path if path.startswith("https:") else "https://api.massive.com" + path)
        query = dict(parse_qsl(urlparse(url).query))
        query.update({k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in (params or {}).items()})
        if any(k.lower() in {"apikey", "api_key"} for k in query):
            raise APIError("CREDENTIALS_MUST_USE_AUTH_HEADER")
        base = url.split("?", 1)[0]
        if base.endswith("/float"):
            raise APIError("CURRENT_FLOAT_DISABLED_FOR_HISTORICAL_RESEARCH")
        request = {"url": base, "params": query}
        ident = digest(request)
        endpoint = "float" if "/float" in base else "reference" if "/reference/" in base else "prices"
        cache = self.root / "raw" / f"endpoint={endpoint}" / f"{ident}.parquet"
        lock = self.root / "locks" / (ident + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            return self._fetch(cache, request, ident, base, query)

    def _fetch(self, cache, request, ident, base, query):
        if cache.exists():
            sidecar = cache.with_suffix(".sha256.json")
            expected = self.pinned_hashes.get(str(cache.resolve()))
            if expected is None and sidecar.exists():
                expected = json.loads(sidecar.read_text())["sha256"]
            if expected is None:
                raise APIError("LEGACY_CACHE_REQUIRES_PINNED_EVIDENCE_INDEX")
            if file_hash(cache) != expected:
                raise APIError("CACHE_HASH_MISMATCH")
            row = pq.ParquetFile(cache).read().to_pylist()[0]
            if row["request_hash"] != ident or json.loads(row["request"]) != request:
                raise APIError("CACHE_REQUEST_MISMATCH")
            self.cache_hits += 1
            self.evidence.append({"path": str(cache), "sha256": file_hash(cache)})
            return json.loads(row["response"])
        if self.offline:
            raise APIError("OFFLINE_CACHE_MISS")
        if not self.key:
            raise APIError("MISSING_API_KEY")
        error = "UNKNOWN_API_ERROR"
        for attempt in range(self.retries):
            if self.max_requests is not None and self.requests >= self.max_requests:
                raise APIError("REQUEST_BUDGET_EXHAUSTED")
            self.requests += 1
            try:
                response = self.session.get(base, params=query, headers={"Authorization": f"Bearer {self.key}"}, timeout=45, allow_redirects=False)
                code = response.status_code
                if code == 429 or code >= 500:
                    error = f"HTTP_{code}"
                    self.errors.append({"request_hash": ident, "error": error, "attempt": attempt + 1})
                    if attempt + 1 < self.retries:
                        delay = min(2 ** attempt, 4)
                        retry_after = getattr(response, "headers", {}).get("Retry-After")
                        if retry_after:
                            from email.utils import parsedate_to_datetime
                            try:
                                delay = max(delay, float(retry_after))
                            except ValueError:
                                delay = max(delay, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                        if delay > 60:
                            raise APIError("RETRY_AFTER_DEFERRED")
                        time.sleep(delay)
                    continue
                if code != 200:
                    error = f"HTTP_{code}"
                    self.errors.append({"request_hash": ident, "error": error, "attempt": attempt + 1})
                    break
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("response is not an object")
                if body.get("status") in {"ERROR", "NOT_AUTHORIZED", "NOT_FOUND"}:
                    error = "API_" + body["status"]
                    self.errors.append({"request_hash": ident, "error": error, "attempt": attempt + 1})
                    break
                body = scrub(body, self.key)
                if "results" not in body and "close" not in body:
                    raise ValueError("missing response data")
                parquet(cache, [{"request_hash": ident, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                                 "request": json.dumps(request, sort_keys=True), "response": json.dumps(body, sort_keys=True)}], raw_schema())
                write_json(cache.with_suffix(".sha256.json"), {"sha256": file_hash(cache), "request_hash": ident})
                self.evidence.append({"path": str(cache), "sha256": file_hash(cache)})
                return body
            except (requests.RequestException, ValueError):
                error = "NETWORK_OR_INVALID_JSON"
                self.errors.append({"request_hash": ident, "error": error, "attempt": attempt + 1})
                if attempt + 1 < self.retries:
                    time.sleep(min(2 ** attempt, 4))
        raise APIError(error)

    def pages(self, path, params):
        seen = set()
        while path:
            marker = digest([path, params])
            if marker in seen:
                raise APIError("PAGINATION_LOOP")
            seen.add(marker)
            body = self.get(path, params)
            rows = body.get("results")
            if not isinstance(rows, list):
                raise APIError("MISSING_RESULTS_ARRAY")
            yield from rows
            path = body.get("next_url")
            params = None

    def tickers(self, day):
        # Date-qualified discovery includes securities delisted since that date.
        # No type/exchange server filters: retain blank fields for unresolved audit.
        return list(self.pages("/v3/reference/tickers", {"market": "stocks", "locale": "us", "date": day,
                                                       "active": True, "limit": 1000, "sort": "ticker", "order": "asc"}))

    def exchanges(self):
        return list(self.pages("/v3/reference/exchanges", {"asset_class": "stocks", "locale": "us"}))

    def prices(self, day):
        body = self.get(f"/v2/aggs/grouped/locale/us/market/stocks/{day}", {"adjusted": False, "include_otc": True})
        if not isinstance(body.get("results"), list) or not body["results"]:
            raise APIError("MISSING_DAILY_PRICES")
        if body.get("adjusted") is True:
            raise APIError("ADJUSTED_PRICE_RESPONSE")
        return body["results"]
