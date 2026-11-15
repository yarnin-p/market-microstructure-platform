import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("sec_float_pilot", Path(__file__).parents[1] / "scripts/sec_float_pilot.py")
sec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sec)


def test_inline_extraction_preserves_units_scale_dimensions_and_dates():
    # Synthetic parser fixture only; not market evidence.
    body = b'''<html><xbrli:context id="c"><xbrli:entity><xbrldi:explicitMember dimension="ClassAxis">ClassAMember</xbrldi:explicitMember></xbrli:entity><xbrli:period><xbrli:instant>2025-06-30</xbrli:instant></xbrli:period></xbrli:context>
    <p>Public float held by non-affiliates: <ix:nonFraction name="dei:EntityPublicFloat" contextRef="c" unitRef="USD" scale="6">12.5</ix:nonFraction>.</p>
    <ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" contextRef="c" unitRef="shares">4,000,000</ix:nonFraction></html>'''
    parsed = sec.parse_filing(body)
    public = next(f for f in parsed["facts"] if f["name"] == "dei:EntityPublicFloat")
    assert public["unit_ref"] == "USD" and sec.inline_value(public) == "12500000.0"
    assert parsed["contexts"]["c"]["dimensions"] == ["ClassAxis"]
    assert "2025-06-30" in parsed["contexts"]["c"]["text"]
    assert parsed["float_passages"]


@pytest.mark.parametrize("kwargs,status", [
    ({"class_confirmed": False, "same_measurement_date": True, "same_share_basis": True}, "AMBIGUOUS_SHARE_CLASS"),
    ({"class_confirmed": True, "same_measurement_date": False, "same_share_basis": True}, "INSUFFICIENT_PRICE_BASIS"),
    ({"class_confirmed": True, "same_measurement_date": True, "same_share_basis": False}, "INSUFFICIENT_PRICE_BASIS"),
])
def test_issuer_float_wrong_date_or_split_basis_cannot_be_divided(kwargs, status):
    assert sec.reconstruct("1000000", "0.50", **kwargs) == (status, None)


def test_defensible_calculation_is_estimate_only_and_zero_price_rejected():
    policy = {"class_confirmed": True, "same_measurement_date": True, "same_share_basis": True}
    assert sec.reconstruct("1200000", "0.30", **policy) == ("SEC_DERIVED_HISTORICAL_ESTIMATE", "4.0000E+6")
    assert sec.reconstruct("1200000", "0", **policy)[1] is None
    assert sec.reconstruct("1200000", None, **policy)[1] is None


def test_share_counts_and_public_float_usd_remain_separate_and_no_future_filing_leakage():
    facts = {"facts": {"dei": {
        "EntityPublicFloat": {"units": {"USD": [
            {"val": 1200000, "filed": "2026-03-15", "end": "2025-06-30", "accn": "a", "form": "10-K"},
            {"val": 99000000, "filed": "2027-03-15", "end": "2026-06-30", "accn": "b", "form": "10-K"}]}},
        "EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"val": 9000000, "filed": "2026-03-15", "end": "2026-03-01", "accn": "a", "form": "10-K"}]}}
    }}}
    filings = [{"accessionNumber": "a", "acceptanceDateTime": "2026-03-15T21:05:00Z"}]
    rows = sec.extract_facts(facts, filings)
    assert len(rows) == 2
    assert {r["unit"] for r in rows} == {"USD", "shares"}
    assert rows[0]["observation_date"] == "2025-06-30"
    assert rows[0]["filing_date"] == "2026-03-15"
    assert rows[0]["available_at"] is None


def test_acceptance_after_close_not_known_at_anchor_and_publication_not_asserted():
    a = sec.availability("2026-03-16T20:00:00Z", "2026-03-16T20:05:00Z", "2025-06-30")
    assert a["status"] == "NOT_YET_ACCEPTED_AT_ANCHOR" and a["measurement_age_days"] > 200
    b = sec.availability("2026-03-16T20:00:00Z", "2026-03-16T19:59:00Z", "2025-06-30")
    assert b["acceptance_at_or_before_anchor"] and b["available_at"] is None
    assert sec.accepted_at("2026-03-16T20:00:00") is None
    with pytest.raises(ValueError):
        sec.availability("2026-03-16T20:00:00", None, "2025-06-30")


class Response:
    headers = {"Content-Type": "application/json", "Set-Cookie": "not-persisted"}

    def __init__(self, status, body=b'{"cik":1617867}'):
        self.status_code, self.body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, _):
        yield self.body


class Session:
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        assert kwargs["allow_redirects"] is False
        return next(self.responses)


def test_403_stops_host_across_resume_and_is_not_empty_data(tmp_path, monkeypatch):
    session = Session([Response(403, b'Access denied')])
    monkeypatch.setattr(sec.requests, "Session", lambda: session)
    client = sec.SECClient(tmp_path)
    _, meta = client.get("https://data.sec.gov/submissions/CIK0001617867.json")
    assert meta["status"] == 403
    resumed = sec.SECClient(tmp_path)
    with pytest.raises(RuntimeError, match="HOST_BLOCKED"):
        resumed.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0001617867.json")
    assert len(session.calls) == 1
    assert "Set-Cookie" not in (tmp_path / "http-ledger.json").read_text()


def test_request_budget_cache_reuse_and_corruption(tmp_path, monkeypatch):
    session = Session([Response(200)])
    monkeypatch.setattr(sec.requests, "Session", lambda: session)
    client = sec.SECClient(tmp_path, budget=1)
    url = "https://data.sec.gov/submissions/CIK0001617867.json"
    assert client.json(url)[0]["cik"] == 1617867
    assert client.json(url)[0]["cik"] == 1617867
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        client.get("https://data.sec.gov/submissions/CIK0000008177.json")
    next(tmp_path.glob("*.body")).write_bytes(b'tampered')
    with pytest.raises(ValueError, match="checksum"):
        client.get(url)
    assert len(session.calls) == 1


def test_unsafe_hosts_and_offline_miss_never_call_network(tmp_path):
    client = sec.SECClient(tmp_path, offline=True)
    with pytest.raises(ValueError):
        client.get("https://evil.example/submissions/CIK1.json")
    with pytest.raises(RuntimeError, match="OFFLINE_CACHE_MISS"):
        client.get("https://data.sec.gov/submissions/CIK0001617867.json")
    assert client.ledger == []


def test_verified_pit_and_estimate_without_evidence_are_rejected():
    row = {"schema_version": "sec-float-evidence-v1", "security": {"security_id": "SYNTHETIC"},
           "verified_pit": True, "status": "SEC_DERIVED_HISTORICAL_ESTIMATE", "derived_estimates": []}
    with pytest.raises(ValueError, match="verified PIT"):
        sec.validate_record(row)
    row["verified_pit"] = False
    with pytest.raises(ValueError, match="without evidence"):
        sec.validate_record(row)


def test_review_requires_hashed_original_currency_date_and_price_passage(tmp_path):
    url = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/synthetic.htm"
    body = b'''<html><xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <xbrli:context id="c"><xbrli:period><xbrli:instant>2025-06-30</xbrli:instant></xbrli:period></xbrli:context>
    <p>The aggregate market value of common stock held by non-affiliates on June 30, 2025 was
    <ix:nonFraction name="dei:EntityPublicFloat" contextRef="c" unitRef="USD">1,200,000</ix:nonFraction>
    based on the closing price of $0.30 per share on that date.</p></html>'''
    (tmp_path / f"{sec.sha(url.encode())}.body").write_bytes(body)
    row = {"schema_version": "sec-float-evidence-v1", "security": {"security_id": "SYNTHETIC"},
           "status": "INSUFFICIENT_PRICE_BASIS", "verified_pit": False, "derived_estimates": [],
           "documents": [{"accession": "a", "url": url, "acceptance_at": "2026-03-01T21:00:00Z",
                          "source": {"status": 200, "sha256": sec.sha(body)}}]}
    result_path, review_path = tmp_path / "results.json", tmp_path / "reviews.json"
    sec.save(result_path, {"results": [row]})
    passage = sec.parse_filing(body)["float_passages"][0]["text"]
    review = {"security_id": "SYNTHETIC", "accession": "a", "source_sha256": sec.sha(body),
              "public_float_usd": "1200000", "disclosed_price_usd": "0.30", "observation_date": "2025-06-30",
              "share_class": "Common stock", "class_confirmed": True, "same_measurement_date": True,
              "same_share_basis": True, "reviewer": "synthetic-test-only", "basis_rationale": "synthetic fixture",
              "supporting_passage": passage}
    sec.save(review_path, [review])
    result = sec.apply_reviews(result_path, review_path, tmp_path, tmp_path / "reviewed.json")
    estimate = result["results"][0]["derived_estimates"][0]
    assert estimate["estimated_shares"] == "4000000" and estimate["verified_pit"] is False
    assert json.loads(result_path.read_text())["results"][0]["derived_estimates"] == []
    review["disclosed_price_usd"] = "0.50"
    sec.save(review_path, [review])
    with pytest.raises(ValueError, match="share price missing"):
        sec.apply_reviews(result_path, review_path, tmp_path, tmp_path / "bad.json")
    review["disclosed_price_usd"] = "0.30"; review["observation_date"] = "2026-06-30"
    sec.save(review_path, [review])
    with pytest.raises(ValueError, match="amount/date"):
        sec.apply_reviews(result_path, review_path, tmp_path, tmp_path / "bad.json")
