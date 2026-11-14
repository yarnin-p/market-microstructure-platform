import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from market_lab.api import Massive, APIError, safe_url
from market_lab.calendar import cycles, segment
from market_lab.eligibility import exchange, float_gate, price_gate, event_eligibility, validate_evidence, identity
from market_lab.eligibility import type_gate
from market_lab.pipeline import classify, build, validate, SCHEMA
from market_lab.results import query
from market_lab.storage import parquet


DIRECTORY = [{"mic": mic, "id": i, "name": name, "type": "exchange", "asset_class": "stocks", "locale": "us"}
             for i, (mic, name) in enumerate([("XNAS", "Nasdaq"), ("XNYS", "New York Stock Exchange"),
                  ("XASE", "NYSE American, LLC"), ("ARCX", "NYSE Arca"), ("XBOS", "Nasdaq BX")])]


def ev(kind="float", **overrides):
    return {"kind": kind, "security_id": "FIGI1", "effective_from": "2025-01-01T00:00:00Z",
            "effective_to": "2027-01-01T00:00:00Z", "available_at": "2025-01-01T00:00:00Z",
            "source": "test-fixture-not-market-data", "source_sha256": "a" * 64,
            "shares_float": 1_000_000, "primary_exchange": "XNAS", "cohort": "VERIFIED_PIT",
            "source_kind": "AUDITED_HISTORICAL_RECORD", "measurement_at": "2025-01-01T00:00:00Z",
            "validity_policy": "synthetic-fixture-only", **overrides}


def ref(ticker="TEST", code="XNAS", sid="FIGI1"):
    return {"ticker": ticker, "primary_exchange": code, "share_class_figi": sid, "type": "CS", "market": "stocks", "currency_name": "usd"}


@pytest.mark.parametrize("code,name", [("XNAS", "NASDAQ"), ("XASE", "NYSE American (AMEX)"), ("XNYS", "NYSE")])
def test_allowed(code, name):
    assert exchange(code, "stocks", DIRECTORY)[:2] == ("ELIGIBLE", name)


@pytest.mark.parametrize("code", ["OTC", "OTCQB", "OTCQX", "OTC Pink"])
def test_otc(code):
    assert exchange(code, "otc", DIRECTORY)[0] == "INELIGIBLE"


@pytest.mark.parametrize("code", ["ARCX", "XBOS"])
def test_not_parent_company_allowlist(code):
    assert exchange(code, "stocks", DIRECTORY)[0] == "INELIGIBLE"


@pytest.mark.parametrize("code", [None, "", "UNKNOWN", "12", "XNGS"])
def test_unknown_not_included(code):
    assert exchange(code, "stocks", DIRECTORY)[0] == "UNRESOLVED"


@pytest.mark.parametrize("price,expected", [(0,"INELIGIBLE"),(-1,"INELIGIBLE"),(0.01,"ELIGIBLE"),(3,"ELIGIBLE"),
                                         (3.01,"INELIGIBLE"),(None,"UNRESOLVED"),(float('nan'),"UNRESOLVED"),(True,"UNRESOLVED")])
def test_price_boundaries(price, expected):
    assert price_gate(price)[0] == expected


@pytest.mark.parametrize("value,expected", [(99999,"INELIGIBLE"),(100000,"ELIGIBLE"),(15000000,"ELIGIBLE"),(15000001,"INELIGIBLE")])
def test_float_boundaries(value, expected):
    assert float_gate([ev(shares_float=value)], "FIGI1", "2026-11-12T21:00:00Z")[0] == expected


def test_float_no_current_or_future_substitution():
    at = "2026-11-12T21:00:00Z"
    assert float_gate([], "FIGI1", at)[0] == "UNRESOLVED"
    assert float_gate([ev(available_at="2026-11-13T00:00:00Z")], "FIGI1", at)[0] == "UNRESOLVED"
    assert float_gate([ev(effective_from="2026-11-13T00:00:00Z")], "FIGI1", at)[0] == "UNRESOLVED"
    assert float_gate([ev(), ev(shares_float=2_000_000)], "FIGI1", at)[2] == "CONFLICTING_FLOAT_EVIDENCE"
    assert float_gate([ev()], "OTHER_SECURITY", at)[0] == "UNRESOLVED"


def test_invalid_evidence():
    with pytest.raises(ValueError):
        validate_evidence([ev(available_at="2026-01-01")])
    with pytest.raises(ValueError):
        validate_evidence([ev(shares_float=-1)])
    assert identity({"cik": "123", "ticker": "TEST"}) is None


def test_calendar_120_holidays_and_early_close():
    c = cycles("2026-11-13", 120)
    assert len(c) == len({r["cycle_id"] for r in c}) == 120
    assert "2026-07-03" not in {r["cycle_id"] for r in c}
    friday = cycles("2025-11-28", 1)[0]
    assert friday["anchor_date"] == "2025-11-26"
    assert friday["end_at"] == "2025-11-28T18:00:00+00:00"
    monday = cycles("2025-12-01", 1)[0]
    assert monday["anchor_at"] == "2025-11-28T18:00:00+00:00"


def test_dst_and_sessions():
    c = cycles("2026-03-09", 1)[0]
    assert c["anchor_at"] == "2026-03-06T21:00:00+00:00"
    assert c["rth_open"] == "2026-03-09T13:30:00+00:00"
    assert segment(c,c["anchor_at"]) == "OUTSIDE_CYCLE"
    assert segment(c,"2026-03-06T21:00:01Z") == "AFTER_HOURS"
    assert segment(c,"2026-03-08T12:00:00Z") == "OUTSIDE_OBSERVED_COVERAGE"
    assert segment(c,"2026-03-09T08:00:00Z") == "PREMARKET"
    assert segment(c,c["rth_open"]) == "RTH"
    assert segment(c,c["end_at"]) == "RTH"


def row_for(observed=None, evidence=None, anchor=None):
    c = cycles("2026-11-13", 1)[0]
    rows, _ = classify("test", c, [anchor or ref()], [{"T":"TEST", "c":2}],
                       observed if observed is not None else [ref()], DIRECTORY, evidence if evidence is not None else [ev()], [], actions={"complete": True})
    return rows[0]


def test_freeze_and_revalidate_transfer():
    r = row_for([ref(code="ARCX")])
    assert r["status"] == "ELIGIBLE"
    assert r["change_status"] == "CHANGE_IDENTIFIED"
    assert event_eligibility(r,"2026-11-13T15:00:00Z",[],DIRECTORY)["status"] == "UNRESOLVED"
    precise = ev("exchange", primary_exchange="ARCX", effective_from="2026-11-13T14:30:00Z")
    assert event_eligibility(r,"2026-11-13T14:30:00Z",[precise],DIRECTORY)["status"] == "INELIGIBLE"
    assert r["status"] == "ELIGIBLE"  # no mutation of anchor snapshot


def test_no_intra_cycle_entry_and_no_ticker_identity_join():
    r = row_for([ref(code="XNAS")], anchor=ref(code="ARCX"))
    assert r["status"] == "INELIGIBLE"
    assert event_eligibility(r,"2026-11-13T15:00:00Z",[ev("exchange")],DIRECTORY)["status"] == "INELIGIBLE"
    r = row_for([ref(sid="DIFFERENT_SECURITY")])
    assert r["change_status"] == "UNVERIFIED"


def test_conflicting_event_evidence_and_boundary():
    r = row_for()
    assert event_eligibility(r,r["anchor_at"],[],DIRECTORY)["status"] == "INELIGIBLE"
    assert event_eligibility(r,"2026-11-13T15:00:00Z",[ev("exchange"),ev("exchange",primary_exchange="XNYS")],DIRECTORY)["status"] == "UNRESOLVED"


def test_execution_venue_irrelevant():
    r = row_for()
    for venue in [4, 11, 12, 62, 999]:
        # Event eligibility does not take execution venue as an input.
        trade = {"exchange":venue,"timestamp":"2026-11-13T15:00:00Z"}
        assert event_eligibility(r,trade["timestamp"],[],DIRECTORY)["status"] == "ELIGIBLE"


def test_parquet_roundtrip(tmp_path):
    r = row_for()
    path = tmp_path/"data.parquet"
    parquet(path,[r],SCHEMA)
    assert pq.ParquetFile(path).read().to_pylist() == [r]
    assert pq.ParquetFile(path).metadata.row_group(0).column(0).compression == "ZSTD"


class FakeAPI:
    def __init__(self):
        self.errors, self.evidence = [], []
        self.requests = self.cache_hits = 0
    def exchanges(self): return DIRECTORY
    def tickers(self, day): return [ref()]
    def prices(self, day): return [{"T":"TEST","c":2}]


def test_pipeline_resume_validate_query(tmp_path):
    root, reports = tmp_path/"data", tmp_path/"reports"
    api = FakeAPI()
    m = build(api,root,reports,"test","2026-11-13",2,[ev()])
    assert m["processed_cycles"] == 2
    assert validate(reports/"test")["technical_validation"] == "PASSED"
    first = Path(m["cycles"][0]["snapshot"]).stat().st_mtime_ns
    api.tickers = lambda day: (_ for _ in ()).throw(AssertionError("must resume"))
    build(api,root,reports,"test","2026-11-13",2,[ev()])
    assert Path(m["cycles"][0]["snapshot"]).stat().st_mtime_ns == first
    result = query(root,"test",filters={"ticker":"TEST"},limit=1)
    assert result["matching_rows"] == 2 and result["truncated_extract"]
    assert query(root,"test",aggregate=True)["matching_rows"] == 2
    with pytest.raises(ValueError,match="configuration/code"):
        build(api,root,reports,"test","2026-11-13",1,[ev()])
    p = Path(m["cycles"][0]["snapshot"])
    p.write_bytes(b"tampered")
    with pytest.raises(ValueError,match="hash mismatch"):
        validate(reports/"test")


def test_unresolved_full_population_report(tmp_path):
    m = build(FakeAPI(),tmp_path/"data",tmp_path/"reports","unresolved","2026-11-13",1)
    assert m["completed_cycles"] == 0 and m["processed_cycles"] == 1
    result = validate(tmp_path/"reports/unresolved")
    assert result["counts"]["unresolved"] == 1
    assert not result["research_ready"]


class Response:
    def __init__(self, body, code=200): self.body,self.status_code=body,code
    def json(self): return self.body


class Session:
    def __init__(self,responses): self.responses=list(responses); self.calls=[]
    def get(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        return self.responses.pop(0)


def test_pagination_cache_secret_redaction(tmp_path):
    session=Session([Response({"results":[{"ticker":"A"}],"next_url":"https://api.massive.com/v3/reference/tickers?cursor=abc&apiKey=secret"}),
                     Response({"results":[{"ticker":"B"}]})])
    api=Massive(tmp_path,"secret",session)
    assert len(api.tickers("2026-11-12"))==2
    assert len(api.tickers("2026-11-12"))==2
    assert len(session.calls)==2
    assert session.calls[0][1]["params"]["date"]=="2026-11-12"
    for p in tmp_path.rglob("*.parquet"):
        assert "secret" not in json.dumps(pq.ParquetFile(p).read().to_pylist())


def test_api_failures_and_foreign_pagination(tmp_path):
    api=Massive(tmp_path,"secret",Session([Response({},403)]))
    with pytest.raises(APIError,match="HTTP_403"): api.tickers("2026-11-12")
    assert not list(tmp_path.rglob("*.parquet"))
    with pytest.raises(APIError,match="UNSAFE"): safe_url("https://evil.example/?apiKey=secret")
    with pytest.raises(APIError,match="MISSING_API_KEY"): Massive(tmp_path).get("/test")


def test_missing_discovery_cannot_look_complete(tmp_path):
    api=FakeAPI()
    api.tickers=lambda day: []
    m=build(api,tmp_path/"data",tmp_path/"reports","empty","2026-11-13",2)
    assert m["completed_cycles"]==m["processed_cycles"]==0
    assert len(m["cycles"])==2
    assert validate(tmp_path/"reports/empty")["research_ready"] is False


@pytest.mark.parametrize("kind",["ADRC","ETF","WARRANT","RIGHT","UNIT","PFD","FUND"])
def test_only_common_stock(kind):
    assert type_gate(kind)[0]=="INELIGIBLE"
    r=ref();r["type"]=kind
    assert row_for(anchor=r)["status"]=="INELIGIBLE"


def test_unknown_type_and_known_common_stock():
    assert type_gate(None)[0]=="UNRESOLVED"
    assert type_gate("CS")[0]=="ELIGIBLE"


def test_price_failure_retains_candidates(tmp_path):
    api=FakeAPI()
    def failed(day): raise APIError("HTTP_500")
    api.prices=failed
    m=build(api,tmp_path/"data",tmp_path/"reports","missing-price","2026-11-13",1)
    assert m["cycles"][0]["counts"]["candidates"]==1
    assert m["cycles"][0]["counts"]["unresolved_price"]==1
    assert m["cycles"][0]["price_error"]=="HTTP_500"
    assert validate(tmp_path/"reports/missing-price")["research_ready"] is False


def test_validator_rejects_false_completion(tmp_path):
    build(FakeAPI(),tmp_path/"data",tmp_path/"reports","r","2026-11-13",1)
    path=tmp_path/"reports/r/manifest.json"
    m=json.loads(path.read_text());m["status"]="COMPLETE"
    path.write_text(json.dumps(m))
    with pytest.raises(ValueError,match="incomplete research"):
        validate(path.parent)


@pytest.mark.parametrize("before,after",[("XNAS","OOTC"),("OOTC","XNAS"),("XNYS","XNAS")])
def test_historical_exchange_changes_across_cycles(before,after):
    directory=DIRECTORY+[{"mic":"OOTC","name":"OTC Equity Security","type":"ORF","asset_class":"stocks","locale":"us"}]
    c=cycles("2026-11-13",2)
    r1,_=classify("r",c[0],[ref(code=before)],[{"T":"TEST","c":2}],[ref(code=before)],directory,[ev()],[])
    r2,_=classify("r",c[1],[ref(code=after)],[{"T":"TEST","c":2}],[ref(code=after)],directory,[ev()],[])
    assert r1[0]["primary_exchange_raw"]==before and r2[0]["primary_exchange_raw"]==after
    assert r1[0]["exchange_status"]==("INELIGIBLE" if before=="OOTC" else "ELIGIBLE")
    assert r2[0]["exchange_status"]==("INELIGIBLE" if after=="OOTC" else "ELIGIBLE")


def test_retries_are_counted_and_only_success_cached(tmp_path,monkeypatch):
    monkeypatch.setattr("market_lab.api.time.sleep",lambda _:None)
    session=Session([Response({},429),Response({},500),Response({"results":[ref()]})])
    api=Massive(tmp_path,"secret",session)
    assert len(api.tickers("2026-11-12"))==1
    assert api.requests==3 and len(api.errors)==2
    assert len(list(tmp_path.rglob("*.parquet")))==1


def test_concurrent_cache_requests_fetch_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import time
    session=Session([Response({"results":[ref()]})])
    original=session.get
    def slow(*args,**kwargs):
        time.sleep(0.02)
        return original(*args,**kwargs)
    session.get=slow
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(Massive(tmp_path,"secret",session).tickers,"2026-11-12") for _ in range(2)]
        assert all(len(f.result())==1 for f in futures)
    assert len(session.calls)==1


def test_failed_cycle_is_retriable_without_double_counting(tmp_path):
    api=FakeAPI()
    good=api.prices
    def fail(day): raise APIError("HTTP_500")
    api.prices=fail
    root,reports=tmp_path/"data",tmp_path/"reports"
    build(api,root,reports,"retry","2026-11-13",1,[ev()])
    api.prices=good
    m=build(api,root,reports,"retry","2026-11-13",1,[ev()])
    assert m["processed_cycles"]==1
    assert validate(reports/"retry")["counts"]["candidates"]==1
    assert query(root,"retry",aggregate=True)["matching_rows"]==1
