"""Bounded SEC historical-float pilot, independent of the M1 eligibility gate."""
import argparse
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

STATUSES = {"SEC_DERIVED_HISTORICAL_ESTIMATE", "SEC_REPORTED_SHARE_COUNT_ONLY",
            "INSUFFICIENT_PRICE_BASIS", "AMBIGUOUS_SHARE_CLASS", "UNRESOLVED"}
UA = "yarnin-p MarketMicrostructurePlatform SEC research (https://github.com/yarnin-p/market-microstructure-platform)"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n")
    temp.replace(path)


class SECClient:
    """Single-worker 1 request/sec; persistent attempt budget; no automatic retries."""

    def __init__(self, root, user_agent=UA, budget=110, offline=False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "http-ledger.json"
        self.ledger = json.loads(self.ledger_path.read_text()) if self.ledger_path.exists() else []
        self.budget, self.offline, self.ua = budget, offline, user_agent
        self.session = requests.Session()
        self.session.trust_env = False
        self.blocked_hosts = {r["host"] for r in self.ledger if r.get("status") in {403, 429}}
        self.last_request = 0.0

    def get(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"data.sec.gov", "www.sec.gov"} or parsed.username:
            raise ValueError("unapproved SEC URL")
        key = sha(url.encode())
        meta_path, body_path = self.root / f"{key}.json", self.root / f"{key}.body"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            body = body_path.read_bytes()
            if sha(body) != meta["sha256"]:
                raise ValueError("SEC cache checksum mismatch")
            return body, meta
        if self.offline:
            raise RuntimeError("OFFLINE_CACHE_MISS")
        if parsed.hostname in self.blocked_hosts:
            raise RuntimeError("SEC_HOST_BLOCKED_AFTER_403_OR_429")
        if len(self.ledger) >= self.budget:
            raise RuntimeError("SEC_REQUEST_BUDGET_EXHAUSTED")
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last_request)))
        row = {"url": url, "host": parsed.hostname, "started_at": datetime.now(timezone.utc).isoformat(),
               "status": "STARTED", "user_agent_identity": "PROJECT_CONTACT"}
        self.ledger.append(row)
        save(self.ledger_path, self.ledger)
        self.last_request = time.monotonic()
        try:
            with self.session.get(url, headers={"User-Agent": self.ua, "Accept-Encoding": "gzip, deflate"},
                                  timeout=(10, 30), allow_redirects=False, stream=True) as response:
                chunks, size, started = [], 0, time.monotonic()
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 30 * 1024 * 1024 or time.monotonic() - started > 60:
                        raise ValueError("SEC_RESPONSE_BUDGET_EXCEEDED")
                    chunks.append(chunk)
                body = b"".join(chunks)
                row.update(status=response.status_code, bytes=len(body), sha256=sha(body),
                           retrieved_at=datetime.now(timezone.utc).isoformat(),
                           headers={k: v for k, v in response.headers.items()
                                    if k.lower() in {"date", "last-modified", "content-type", "retry-after", "etag"}})
                body_path.write_bytes(body)
                save(meta_path, row)
                if response.status_code in {403, 429}:
                    self.blocked_hosts.add(parsed.hostname)
        except (requests.RequestException, ValueError) as exc:
            row.update(status="TRANSPORT_ERROR", error_type=type(exc).__name__)
            raise RuntimeError("SEC_TRANSPORT_ERROR") from None
        finally:
            save(self.ledger_path, self.ledger)
        return body, row

    def json(self, url):
        body, meta = self.get(url)
        if meta["status"] != 200:
            raise RuntimeError(f"SEC_HTTP_{meta['status']}")
        return json.loads(body), meta


def select_sample(manifest_path, output):
    import duckdb
    import pyarrow.parquet as pq
    manifest = json.loads(Path(manifest_path).read_text())
    con = duckdb.connect()
    con.read_parquet([e["snapshot"] for e in manifest["cycles"]], hive_partitioning=False).create_view("u")
    query = """SELECT ticker,security_id,canonical_exchange,count(*) n,
        max(CASE WHEN action_reason='SPLIT_CYCLE_PRICE_BASIS_UNRESOLVED' THEN 1 ELSE 0 END) split,
        max(CASE WHEN change_status<>'NO_CHANGE_OBSERVED' THEN 1 ELSE 0 END) change
        FROM u WHERE split_group='EXPLORATION' AND exchange_status='ELIGIBLE'
        AND price_status='ELIGIBLE' AND type_status='ELIGIBLE' AND identity_status='ELIGIBLE'
        GROUP BY ALL"""
    columns = ["ticker", "security_id", "exchange", "low_price_exploration_cycles", "has_split", "change_flag"]
    candidates = [dict(zip(columns, row)) for row in con.execute(query).fetchall()]
    selected, seen = [], set()
    for exchange in ["NASDAQ", "NYSE American (AMEX)", "NYSE"]:
        group = [r for r in candidates if r["exchange"] == exchange]
        ranked = sorted(group, key=lambda r: (-r["has_split"], -r["change_flag"], r["ticker"], r["security_id"]))
        stable = sorted([r for r in group if not r["has_split"] and not r["change_flag"]], key=lambda r: (r["ticker"], r["security_id"]))
        for record in ranked[:4] + stable[:4]:
            if record["security_id"] in seen:
                raise ValueError("duplicate sampled identity")
            seen.add(record["security_id"])
            match = con.execute("""SELECT cycle_id FROM u WHERE security_id=? AND ticker=?
                AND split_group='EXPLORATION' AND price_status='ELIGIBLE' ORDER BY cycle_id LIMIT 1""",
                [record["security_id"], record["ticker"]]).fetchone()[0]
            entry = next(e for e in manifest["cycles"] if e["cycle_id"] == match)
            rows = pq.ParquetFile(entry["snapshot"]).read().to_pylist()
            row = next(r for r in rows if r["security_id"] == record["security_id"] and r["ticker"] == record["ticker"])
            provenance = json.loads(row["provenance_json"])
            ref = provenance["ticker_reference"]
            history = con.execute("""SELECT DISTINCT ticker,primary_exchange_raw FROM u
                WHERE security_id=? AND split_group='EXPLORATION' ORDER BY ticker,primary_exchange_raw""",
                [record["security_id"]]).fetchall()
            record.update(cik=ref.get("cik"), name=ref.get("name"), historical_symbols=history,
                          selection_cycle=match, previous_rth_close=str(row["previous_rth_close"]),
                          source_snapshot=entry["snapshot"], source_snapshot_sha256=entry["snapshot_hash"],
                          source_reference=provenance.get("source_reference"),
                          mapping_status="MASSIVE_REPORTED_CIK_ISSUER_ONLY" if ref.get("cik") else "MISSING_CIK")
            selected.append(record)
    con.close()
    if len(selected) != 24:
        raise ValueError("pilot must contain exactly 24 historical securities")
    result = {"schema_version": "sec-pilot-sample-v1", "m1_run_id": manifest["run_id"],
              "selection": "Per exchange: 4 ranked split/change cases + 4 alphabetically first stable cases; exploration only; no SEC outcomes used",
              "sampling": "PURPOSIVE_FEASIBILITY_NOT_STATISTICALLY_REPRESENTATIVE",
              "securities": selected, "calendar": manifest["config"]["calendar"]}
    save(output, result)
    return result


class FilingParser(HTMLParser):
    """Preserve iXBRL fact attributes and context dimensions alongside plain text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.facts, self.stack = [], [], []
        self.contexts, self.context_id, self.context_depth = {}, None, 0
        self.text_length = 0
        self.units, self.unit_id, self.unit_depth = {}, None, 0

    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): v for k, v in attrs}
        if tag.lower().endswith(":context") or tag.lower() == "context":
            self.context_id = attrs.get("id")
            self.context_depth = len(self.stack) + 1
            self.contexts[self.context_id] = {"text": [], "dimensions": []}
        if tag.lower() in {"xbrli:unit", "unit"}:
            self.unit_id = attrs.get("id")
            self.unit_depth = len(self.stack) + 1
            self.units[self.unit_id] = []
        if self.context_id and tag.lower().endswith((":explicitmember", ":typedmember")):
            self.contexts[self.context_id]["dimensions"].append(attrs.get("dimension"))
        fact = None
        if tag.lower() in {"ix:nonfraction", "ix:nonnumeric"}:
            fact = {"name": attrs.get("name"), "context_ref": attrs.get("contextref"),
                    "unit_ref": attrs.get("unitref"), "scale": attrs.get("scale", "0"),
                    "sign": attrs.get("sign"), "nil": attrs.get("xsi:nil"),
                    "decimals": attrs.get("decimals"), "format": attrs.get("format"),
                    "text": [], "text_offset": self.text_length}
        self.stack.append((tag, fact))
        if tag in {"p", "div", "tr", "br", "td"}:
            self.text.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        self.text.append(data)
        self.text_length += len(data) + 1
        for _, fact in self.stack:
            if fact is not None:
                fact["text"].append(data)
        if self.context_id:
            self.contexts[self.context_id]["text"].append(data)
        if self.unit_id:
            self.units[self.unit_id].append(data)

    def handle_endtag(self, tag):
        # HTML void tags need not receive an end tag; unwind only matched tags.
        matches = [i for i, (start, _) in enumerate(self.stack) if start == tag]
        if not matches:
            return
        index = matches[-1]
        for _, fact in self.stack[index:]:
            if fact is not None:
                fact["text"] = "".join(fact["text"]).strip()
                self.facts.append(fact)
        del self.stack[index:]
        if self.context_id and len(self.stack) < self.context_depth:
            self.context_id = None
        if self.unit_id and len(self.stack) < self.unit_depth:
            self.unit_id = None

    def result(self):
        return {"text": re.sub(r"\s+", " ", " ".join(self.text)), "facts": self.facts,
                "units": {k: " ".join(v).strip() for k, v in self.units.items()},
                "contexts": {k: {**v, "text": " ".join(v["text"])} for k, v in self.contexts.items()}}


def parse_filing(body):
    parser = FilingParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    result = parser.result()
    # Only cover-page public-float passages; snippets are candidates for review.
    result["float_passages"] = []
    for match in re.finditer(r"non[\s-]*affiliates", result["text"], re.I):
        start, end = max(0, match.start() - 650), min(len(result["text"]), match.end() + 1100)
        passage = result["text"][start:end]
        if re.search(r"aggregate market value|public float", passage, re.I):
            result["float_passages"].append({"start": start, "end": end, "text": passage})
        if len(result["float_passages"]) == 8:
            break
    result["facts"] = [r for r in result["facts"] if r["name"] and
                       (r["name"].split(":")[-1] in {"EntityPublicFloat", "EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding", "CommonStockSharesIssued"})]
    return result


def recent_filings(submissions):
    rows = submissions.get("filings", {}).get("recent", {})
    return [{k: v[index] for k, v in rows.items() if isinstance(v, list) and index < len(v)}
            for index in range(len(rows.get("accessionNumber", [])))]


def accepted_at(value):
    if not value:
        return None
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Never guess timezone for a naive acceptanceDateTime.
    return stamp.astimezone(timezone.utc).isoformat() if stamp.tzinfo else None


def inline_value(fact):
    if fact.get("nil") == "true":
        return None
    text = fact["text"].replace(",", "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    value = Decimal(text) * Decimal(10) ** int(fact.get("scale", "0"))
    return str(-value if fact.get("sign") == "-" else value)


def availability(anchor_at, acceptance_at, observation_date):
    anchor = datetime.fromisoformat(anchor_at.replace("Z", "+00:00"))
    if anchor.tzinfo is None:
        raise ValueError("anchor timezone required")
    age = (anchor.date() - date.fromisoformat(observation_date)).days if observation_date else None
    accepted = accepted_at(acceptance_at)
    if accepted is None:
        return {"acceptance_at_or_before_anchor": None, "measurement_age_days": age,
                "available_at": None, "status": "UNKNOWN_ACCEPTANCE_OR_PUBLICATION_TIME"}
    before = datetime.fromisoformat(accepted) <= anchor
    return {"acceptance_at_or_before_anchor": before, "measurement_age_days": age,
            "available_at": None, "status": "ACCEPTED_BEFORE_ANCHOR_PUBLICATION_UNVERIFIED" if before else "NOT_YET_ACCEPTED_AT_ANCHOR"}


def extract_facts(companyfacts, filings, cutoff="2026-11-13"):
    by_accession = {r["accessionNumber"]: r for r in filings}
    output = []
    for taxonomy, concept, unit in [("dei", "EntityPublicFloat", "USD"),
                                    ("dei", "EntityCommonStockSharesOutstanding", "shares"),
                                    ("us-gaap", "CommonStockSharesOutstanding", "shares"),
                                    ("us-gaap", "CommonStockSharesIssued", "shares")]:
        for row in companyfacts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {}).get(unit, []):
            if not row.get("filed") or row["filed"] > cutoff or row.get("end", "9999") > cutoff:
                continue
            if row.get("form") not in {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F"}:
                continue
            filing = by_accession.get(row.get("accn"), {})
            output.append({"concept": f"{taxonomy}:{concept}", "unit": unit, "value": str(row["val"]),
                           "observation_date": row.get("end"), "filing_date": row["filed"],
                           "accession": row.get("accn"), "form": row.get("form"),
                           "acceptance_at": accepted_at(filing.get("acceptanceDateTime")),
                           "source_kind": "SEC_COMPANYFACTS_ENTITY_LEVEL", "primary_document": filing.get("primaryDocument"),
                           "available_at": None, "availability_status": "ACCEPTANCE_LOWER_BOUND_NOT_DISSEMINATION_TIME"})
    return output


def reconstruct(public_float_usd, exact_price, *, class_confirmed, same_measurement_date, same_share_basis):
    """Called only with reviewed disclosure inputs; never uses a market-price API."""
    if not class_confirmed:
        return "AMBIGUOUS_SHARE_CLASS", None
    if not same_measurement_date or not same_share_basis or exact_price is None:
        return "INSUFFICIENT_PRICE_BASIS", None
    value, price = Decimal(str(public_float_usd)), Decimal(str(exact_price))
    if not value.is_finite() or not price.is_finite() or value <= 0 or price <= 0:
        return "INSUFFICIENT_PRICE_BASIS", None
    return "SEC_DERIVED_HISTORICAL_ESTIMATE", str(value / price)


def validate_record(row):
    if row.get("schema_version") != "sec-float-evidence-v1" or row.get("status") not in STATUSES:
        raise ValueError("invalid SEC evidence version/status")
    if row.get("verified_pit") is not False:
        raise ValueError("SEC pilot must not promote estimates to verified PIT")
    if not row.get("security", {}).get("security_id"):
        raise ValueError("missing sampled security identity")
    for estimate in row.get("derived_estimates", []):
        for key in ["accession", "source_url", "source_sha256", "observation_date", "share_class",
                    "public_float_usd", "disclosed_price_usd", "estimated_shares", "supporting_passage"]:
            if not estimate.get(key):
                raise ValueError("estimate missing " + key)
        status, shares = reconstruct(estimate["public_float_usd"], estimate["disclosed_price_usd"],
            class_confirmed=estimate.get("class_confirmed") is True,
            same_measurement_date=estimate.get("same_measurement_date") is True,
            same_share_basis=estimate.get("same_share_basis") is True)
        if status != "SEC_DERIVED_HISTORICAL_ESTIMATE" or Decimal(shares) != Decimal(estimate["estimated_shares"]):
            raise ValueError("unjustified float-share estimate")
    if row["status"] == "SEC_DERIVED_HISTORICAL_ESTIMATE" and not row.get("derived_estimates"):
        raise ValueError("estimate status without evidence")


def apply_reviews(result_path, review_path, cache_root, output):
    """Derive only from explicitly reviewed original-document evidence.

    Review supplies the class allocation and same-date/basis rationale. Matching
    a passage/hash checks provenance; it does not certify the reviewer's judgment.
    """
    if Path(output).resolve() == Path(result_path).resolve():
        raise ValueError("review output must preserve the original pilot result")
    result = json.loads(Path(result_path).read_text())
    reviews = json.loads(Path(review_path).read_text())
    lookup = {row["security"]["security_id"]: row for row in result["results"]}
    for review in reviews:
        row = lookup[review["security_id"]]
        document = next(d for d in row["documents"] if d["accession"] == review["accession"])
        if document.get("source", {}).get("status") != 200:
            raise ValueError("cannot reconstruct from unavailable original filing")
        source = document["source"]
        body = (Path(cache_root) / f"{sha(document['url'].encode())}.body").read_bytes()
        if sha(body) != source["sha256"] or sha(body) != review["source_sha256"]:
            raise ValueError("review original document hash mismatch")
        parsed = parse_filing(body)
        passage = review["supporting_passage"]
        if passage not in parsed["text"] or not review.get("reviewer") or not review.get("basis_rationale"):
            raise ValueError("review must identify source passage, reviewer and basis rationale")
        if review.get("kind") == "CLASSIFICATION_ONLY":
            if review["status"] not in {"AMBIGUOUS_SHARE_CLASS", "INSUFFICIENT_PRICE_BASIS", "SEC_REPORTED_SHARE_COUNT_ONLY"}:
                raise ValueError("invalid reviewed classification")
            row["status"] = review["status"]
            row["classification_review"] = review
            validate_record(row)
            continue
        date_text = review["observation_date"]
        possible = [f for f in parsed["facts"] if f["name"].split(":")[-1] == "EntityPublicFloat"
                    and inline_value(f) is not None
                    and Decimal(inline_value(f)) == Decimal(review["public_float_usd"])
                    and parsed["units"].get(f["unit_ref"], "").strip().lower() == "iso4217:usd"
                    and date_text in parsed["contexts"].get(f["context_ref"], {}).get("text", "")
                    and any(token.isdigit() and int(token) == int(row["security"]["cik"])
                            for token in parsed["contexts"].get(f["context_ref"], {}).get("text", "").split())]
        if not possible:
            raise ValueError("public-float amount/date not corroborated by original inline XBRL")
        if review.get("kind") == "REPORTED_NONAFFILIATE_COUNT":
            counts = re.findall(r"([0-9][0-9,]*)\s+(?:Class\s+[A-Z]\s+common\s+stock\s+)?shares", passage, re.I)
            if not review.get("class_confirmed") or not any(Decimal(c.replace(",", "")) == Decimal(review["reported_shares"]) for c in counts):
                raise ValueError("reported non-affiliate shares not corroborated")
            row["reported_nonaffiliate_share_counts"] = [{**review, "source_url": document["url"],
                "acceptance_at": document["acceptance_at"], "available_at": None, "verified_pit": False}]
            row["status"] = "SEC_REPORTED_SHARE_COUNT_ONLY"
            validate_record(row)
            continue
        # Require a literal dollar quote in the reviewed passage. An arbitrary
        # daily market price cannot enter through this interface.
        amounts = re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", passage)
        if not any(Decimal(s.replace(",", "")) == Decimal(review["disclosed_price_usd"]) for s in amounts):
            raise ValueError("disclosed share price missing from reviewed passage")
        status, value = reconstruct(review["public_float_usd"], review["disclosed_price_usd"],
            class_confirmed=review.get("class_confirmed") is True,
            same_measurement_date=review.get("same_measurement_date") is True,
            same_share_basis=review.get("same_share_basis") is True)
        row["status"] = status
        if value is not None:
            # Preserve an exact decimal string, not a rounded integer share count.
            estimate = {**review, "estimated_shares": format(Decimal(value), "f"),
                        "source_url": document["url"], "acceptance_at": document["acceptance_at"],
                        "available_at": None, "classification": status,
                        "split_dilution_carry_forward": "NOT_AUTHORIZED", "verified_pit": False}
            row["derived_estimates"].append(estimate)
        validate_record(row)
    result["review_source_sha256"] = sha(Path(review_path).read_bytes())
    save(output, result)
    return result


def summarize(result_path, sample_path, output):
    from collections import Counter
    result = json.loads(Path(result_path).read_text())
    sample = json.loads(Path(sample_path).read_text())
    records = result["results"]
    for row in records:
        validate_record(row)
    def source_ok(row, kind):
        return any(s["kind"] == kind and s.get("status") == 200 for s in row["sources"])
    public_rows = [r for r in records if any(f["concept"] == "dei:EntityPublicFloat" for f in r["facts"])
                   or any(d.get("float_passages") for d in r["documents"])]
    observed_facts = [f for r in records for f in r["facts"]]
    accepted = [f["acceptance_at"] for f in observed_facts if f.get("acceptance_at")]
    available_anchors = []
    for row in records:
        floated = [f for f in row["facts"] if f["concept"] == "dei:EntityPublicFloat"]
        ages, temporal_counts = [], Counter()
        for cycle in sample["calendar"]:
            candidates = [f for f in floated if f.get("acceptance_at") and
                          datetime.fromisoformat(f["acceptance_at"]) <= datetime.fromisoformat(cycle["anchor_at"])]
            if candidates:
                latest = max(candidates, key=lambda f: (f["observation_date"], f["acceptance_at"]))
                state = availability(cycle["anchor_at"], latest["acceptance_at"], latest["observation_date"])
                ages.append(state["measurement_age_days"])
                temporal_counts[state["status"]] += 1
        available_anchors.append({"security_id": row["security"]["security_id"], "ticker": row["security"]["ticker"],
            "cycles_with_accepted_float_value_usd": len(ages),
            "measurement_age_days_min": min(ages) if ages else None, "measurement_age_days_max": max(ages) if ages else None,
            "actual_publication_time_verified": False, "strict_verified_pit_cycles": 0,
            "temporal_status_counts": dict(temporal_counts)})
    network_scope = []
    cache = Path(result_path).parent / "cache/http-ledger.json"
    if cache.exists():
        network_scope = json.loads(cache.read_text())
    compact = {"schema_version": "sec-float-coverage-v1", "outcome": "ACCESS_BLOCKED" if not any(source_ok(r,"submissions") for r in records) else "PILOT_COMPLETED_WITH_LIMITATIONS",
        "m1_status": "BLOCKED_DATA", "sample_size": len(records),
        "sample_design": sample["selection"], "representative_sample": False,
        "exchange_counts": dict(Counter(r["security"]["exchange"] for r in records)),
        "split_flagged_securities": sum(r["security"]["has_split"] for r in records),
        "change_flagged_securities": sum(r["security"]["change_flag"] for r in records),
        "confirmed_delisted_or_renamed": None,
        "sec_historical_issuer_name_changes": sum(bool(r.get("sec_identity",{}).get("formerNames")) for r in records),
        "cik_mapping": {"structurally_present": sum(bool(r["security"].get("cik")) for r in records),
                        "denominator": len(records), "issuer_metadata_corroborated": sum(source_ok(r,"submissions") for r in records),
                        "share_class_mapping_verified": 0},
        "sec_access": {"http_attempts": len(network_scope), "http_status_counts": dict(Counter(str(r['status']) for r in network_scope)),
                       "submissions_ok": sum(source_ok(r,"submissions") for r in records),
                       "companyfacts_ok": sum(source_ok(r,"companyfacts") for r in records),
                       "original_documents_ok": sum(d.get("source",{}).get("status")==200 for r in records for d in r["documents"])},
        "filing_availability": {"securities_with_recent_annual_or_quarterly": sum(bool(sum(r.get("filing_counts",{}).values())) for r in records),
                                "availability_rate": None if not any(source_ok(r,"submissions") for r in records) else sum(bool(sum(r.get("filing_counts",{}).values())) for r in records)/len(records),
                                "scope": "RETRIEVED_RECENT_SUBMISSIONS_ONLY"},
        "public_float_disclosures": {"securities_observed": len(public_rows),
                                    "coverage_rate": None if not any(source_ok(r,"companyfacts") for r in records) else len(public_rows)/len(records)},
        "defensible_estimates_observed": sum(len(r["derived_estimates"]) for r in records),
        "direct_nonaffiliate_share_count_observations": sum(len(r.get("reported_nonaffiliate_share_counts", [])) for r in records),
        "earliest_observed_acceptance_at": min(accepted) if accepted else None,
        "acceptance_scope": "All retrieved concepts with matched submission metadata, not only public float",
        "earliest_known_publication_at": None,
        "status_counts": dict(Counter(r["status"] for r in records)),
        "cycle_coverage": {"requested_cycles": 120, "sample_security_cycle_pairs": len(records)*120,
                           "validated_float_share_pairs": 0, "whole_universe_estimated_coverage": None,
                           "staleness_by_security": available_anchors},
        "reverse_split_quality": "MEASUREMENT_DATE_ONLY_NO_POST_SPLIT_OR_DILUTION_CARRY_FORWARD" if any(r['derived_estimates'] for r in records) else "UNASSESSED_NO_RECONSTRUCTED_FLOAT_SHARE_BASIS",
        "massive_current_float_comparison": {"status": "NOT_PERFORMED_NO_FREE_CURRENT_FLOAT_CAPTURE_FOR_SAMPLE", "current_float_substitution": False},
        "request_evidence": network_scope,
        "securities": [{"ticker": r["security"]["ticker"], "security_id": r["security"]["security_id"],
                         "cik": r["security"].get("cik"), "exchange": r["security"]["exchange"],
                         "selection_cycle": r["security"]["selection_cycle"], "previous_rth_close": r["security"]["previous_rth_close"],
                         "has_split": r["security"]["has_split"], "change_flag": r["security"]["change_flag"],
                         "status": r["status"], "errors": r["errors"], "historical_symbols": r["security"]["historical_symbols"],
                         "latest_public_float_fact": next(iter(sorted([f for f in r['facts'] if f['concept']=='dei:EntityPublicFloat'], key=lambda f:(f['observation_date'],f['filing_date']),reverse=True)),None),
                         "derived_estimates": r["derived_estimates"],
                         "reported_nonaffiliate_share_counts": r.get("reported_nonaffiliate_share_counts",[]),
                         "classification_review": r.get("classification_review"),
                         "source_snapshot_sha256": r["security"]["source_snapshot_sha256"]} for r in records],
        "source_hashes": {"sample": sha(Path(sample_path).read_bytes()), "results": sha(Path(result_path).read_bytes())}}
    save(output, compact)
    return compact


def run(sample_path, root, output, user_agent=UA, offline=False):
    sample = json.loads(Path(sample_path).read_text())
    client = SECClient(Path(root) / "cache", user_agent, offline=offline)
    results = []
    for security in sample["securities"]:
        row = {"schema_version": "sec-float-evidence-v1", "security": security,
               "status": "UNRESOLVED", "sources": [], "errors": [], "facts": [], "documents": [],
               "derived_estimates": [], "verified_pit": False}
        cik = security.get("cik")
        if not cik or not str(cik).isdigit():
            row["errors"].append("NO_HISTORICAL_CIK_MAPPING")
            results.append(row)
            continue
        cik = str(int(cik)).zfill(10)
        submissions, facts = None, None
        for kind, url in [("submissions", f"https://data.sec.gov/submissions/CIK{cik}.json"),
                          ("companyfacts", f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")]:
            try:
                payload, source = client.json(url)
                row["sources"].append({"kind": kind, **source})
                if str(int(payload["cik"])) != str(int(cik)):
                    raise ValueError("SEC_CIK_IDENTITY_MISMATCH")
                if kind == "submissions":
                    submissions = payload
                    row["sec_identity"] = {k: payload.get(k) for k in ["cik", "name", "tickers", "exchanges", "formerNames"]}
                else:
                    facts = payload
            except (RuntimeError, ValueError, KeyError) as error:
                row["errors"].append(f"{kind}:{error}")
        filings = recent_filings(submissions or {})
        row["filing_history_scope"] = "RECENT_SUBMISSIONS_ONLY_NO_HISTORICAL_SHARDS"
        row["older_submission_files_available"] = len((submissions or {}).get("filings", {}).get("files", []))
        if facts:
            row["facts"] = extract_facts(facts, filings)
        relevant = [f for f in filings if f.get("filingDate", "9999") <= "2026-11-13"]
        annuals = sorted([f for f in relevant if f.get("form") in {"10-K", "20-F", "40-F"}], key=lambda f: f["filingDate"], reverse=True)
        quarters = sorted([f for f in relevant if f.get("form") == "10-Q"], key=lambda f: f["filingDate"], reverse=True)
        chosen = (annuals[:1] + quarters[:1])  # <=48 original documents in this 24-security pilot.
        row["filing_counts"] = {"annual": len(annuals), "quarterly": len(quarters)}
        for filing in chosen:
            acc = filing["accessionNumber"]
            document = filing.get("primaryDocument", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", document):
                row["errors"].append("UNSAFE_OR_MISSING_DOCUMENT_NAME")
                continue
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{document}"
            evidence = {"accession": acc, "form": filing["form"], "filing_date": filing["filingDate"],
                        "acceptance_at": accepted_at(filing.get("acceptanceDateTime")), "url": url}
            try:
                body, source = client.get(url)
                evidence["source"] = source
                if source["status"] == 200:
                    parsed = parse_filing(body)
                    evidence.update({k: parsed[k] for k in ["facts", "contexts", "units", "float_passages"]})
                    # Keep full original locally and only narrow passages in results.
                    save(Path(root) / "parsed" / f"{cik}-{acc}.json", parsed)
                else:
                    evidence["error"] = f"SEC_HTTP_{source['status']}"
            except (RuntimeError, ValueError) as error:
                evidence["error"] = str(error)
            row["documents"].append(evidence)
        public = [f for f in row["facts"] if f["concept"] == "dei:EntityPublicFloat"]
        shares = [f for f in row["facts"] if f["unit"] == "shares"]
        if public or any(d.get("float_passages") for d in row["documents"]):
            row["status"] = "INSUFFICIENT_PRICE_BASIS"
        elif shares or any(d.get("facts") for d in row["documents"]):
            row["status"] = "SEC_REPORTED_SHARE_COUNT_ONLY"
        # No automatic promotion from an issuer-level concept or guessed quote.
        results.append(row)
        validate_record(row)
        save(Path(root) / "pilot-evidence.json", {"schema_version": "sec-float-pilot-v1", "results": results})
        print(json.dumps({"ticker": security["ticker"], "status": row["status"], "facts": len(row["facts"]),
                          "documents": len(row["documents"]), "errors": row["errors"]}), flush=True)
    report = {"schema_version": "sec-float-pilot-v1", "m1_status": "BLOCKED_DATA", "sample_size": len(results),
              "results": results, "request_count": len(client.ledger), "request_budget": client.budget,
              "sample_source_sha256": sha(Path(sample_path).read_bytes()),
              "selection": sample["selection"], "sampling": sample["sampling"]}
    save(output, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select")
    select.add_argument("--manifest", required=True)
    select.add_argument("--output", required=True)
    probe = sub.add_parser("run")
    probe.add_argument("--sample", required=True)
    probe.add_argument("--root", required=True)
    probe.add_argument("--output", required=True)
    probe.add_argument("--user-agent", default=os.getenv("SEC_USER_AGENT", UA), help="Identified project contact; alternatively set SEC_USER_AGENT privately")
    probe.add_argument("--offline", action="store_true")
    summary = sub.add_parser("summarize")
    summary.add_argument("--results", required=True)
    summary.add_argument("--sample", required=True)
    summary.add_argument("--output", required=True)
    review = sub.add_parser("review")
    review.add_argument("--results", required=True)
    review.add_argument("--reviews", required=True)
    review.add_argument("--cache-root", required=True)
    review.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "select":
        select_sample(args.manifest, args.output)
    elif args.command == "run":
        run(args.sample, args.root, args.output, args.user_agent, args.offline)
    elif args.command == "summarize":
        summarize(args.results, args.sample, args.output)
    else:
        apply_reviews(args.results, args.reviews, args.cache_root, args.output)
