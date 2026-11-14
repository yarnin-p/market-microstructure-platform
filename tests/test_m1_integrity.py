import json
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from market_lab.api import APIError, Massive
from market_lab.calendar import cycles, segment
from market_lab.corporate_actions import action_gate, action_index, import_connector_actions
from market_lab.eligibility import float_gate, validate_evidence
from market_lab.pipeline import build, classify, validate, SCHEMA
from market_lab.storage import digest, file_hash, parquet, write_json
from test_universe import DIRECTORY, FakeAPI, Response, Session, ev, ref, row_for


@pytest.mark.parametrize("cohort", ["CURRENT_PROXY", "HISTORICAL_PROXY", "UNRESOLVED", None])
def test_non_pit_float_never_qualifies(cohort):
    status, value, _, _ = float_gate([ev(cohort=cohort)], "FIGI1", "2026-11-12T21:00:00Z")
    assert (status, value) == ("UNRESOLVED", None)


def test_latest_provider_float_cannot_be_relabeled():
    evidence = ev(source="https://api.massive.com/stocks/vX/float")
    with pytest.raises(ValueError, match="latest float"):
        validate_evidence([evidence])
    assert float_gate([evidence], "FIGI1", "2026-11-12T21:00:00Z")[1] is None


def test_latest_float_http_disabled_even_with_date(tmp_path):
    api = Massive(tmp_path, "secret", Session([]))
    with pytest.raises(APIError, match="CURRENT_FLOAT_DISABLED"):
        api.get("/stocks/vX/float", {"ticker": "TEST", "date": "2026-05-27"})
    assert api.requests == 0


@pytest.mark.parametrize("overrides", [
    {"measurement_at": None}, {"validity_policy": None},
    {"measurement_at": "2026-11-14T00:00:00Z"}, {"source_kind": "CURRENT_SNAPSHOT"},
])
def test_verified_pit_requires_temporal_provenance(overrides):
    with pytest.raises(ValueError):
        validate_evidence([ev(**overrides)])


def test_duplicate_share_class_cannot_be_counted_as_two_eligible_securities():
    c = cycles("2026-11-13", 1)[0]
    rows, _ = classify("r", c, [ref(), ref(ticker="RENAMED")],
                       [{"T": "TEST", "c": 2}, {"T": "RENAMED", "c": 2}],
                       [ref()], DIRECTORY, [ev()], [], {"complete": True})
    assert len(rows) == 2  # preserve audit observations
    assert all(r["identity_status"] == r["status"] == "UNRESOLVED" for r in rows)
    assert len({r["record_id"] for r in rows}) == 2


def test_no_currency_cannot_pass_usd_price_gate():
    r = ref(); r.pop("currency_name")
    assert row_for(anchor=r)["currency_status"] == "UNRESOLVED"
    r["currency_name"] = "cad"
    assert row_for(anchor=r)["status"] == "INELIGIBLE"


def test_exact_decimal_threshold_and_roundtrip(tmp_path):
    c = cycles("2026-11-13", 1)[0]
    rows, _ = classify("r", c, [ref()], [{"T": "TEST", "c": 0.1}], [ref()], DIRECTORY, [], [])
    assert rows[0]["trigger_price"] == Decimal("0.11")
    p = tmp_path / "rows.parquet"
    parquet(p, rows, SCHEMA)
    assert pq.ParquetFile(p).read().to_pylist() == rows


def test_fixed_holdout_and_missing_dates_do_not_shift_split():
    schedule = cycles("2026-11-13", 120)
    assert [c["split_group"] for c in schedule] == ["EXPLORATION"] * 80 + ["HOLDOUT"] * 40
    assert schedule[0]["anchor_date"] == "2026-05-26"
    assert schedule[79]["cycle_id"] == "2026-09-18"
    assert schedule[80]["cycle_id"] == "2026-09-21"
    assert cycles("2026-11-13", 3)[0]["split_group"] == "PILOT"


def test_fall_dst_and_unobserved_overnight():
    c = cycles("2026-11-02", 1)[0]
    assert c["anchor_at"] == "2026-10-30T20:00:00+00:00"
    assert c["rth_open"] == "2026-11-02T14:30:00+00:00"
    assert segment(c, "2026-11-02T07:00:00Z") == "OUTSIDE_OBSERVED_COVERAGE"


def test_split_and_dividend_are_separate_price_basis_flags():
    c = cycles("2026-11-13", 1)[0]
    data = {"splits": [{"ticker": "TEST", "execution_date": "2026-11-13", "split_from": 20, "split_to": 1}],
            "dividends": [{"ticker": "DIV", "ex_dividend_date": "2026-11-13"}]}
    index = action_index(data)
    assert action_gate(c, "TEST", index, True)[:2] == ("UNRESOLVED", "SPLIT_CYCLE_PRICE_BASIS_UNRESOLVED")
    status, _, rows = action_gate(c, "DIV", index, True)
    assert status == "ELIGIBLE" and rows[0]["kind"] == "dividends"
    assert action_gate(c, "NONE", index, False)[0] == "UNRESOLVED"


def test_split_under_renamed_symbol_is_not_missed():
    c = cycles("2026-11-13", 1)[0]
    actions = {"complete": True, "splits": [{"ticker": "NEW", "execution_date": "2026-11-13", "id": "s"}]}
    rows, _ = classify("r", c, [ref()], [{"T": "TEST", "c": 2}], [ref(ticker="NEW")],
                       DIRECTORY, [ev()], [], actions)
    assert rows[0]["action_reason"] == "SPLIT_CYCLE_PRICE_BASIS_UNRESOLVED"
    assert rows[0]["status"] == "UNRESOLVED"
    rows, _ = classify("r", c, [ref()], [{"T": "TEST", "c": 2}], [], DIRECTORY, [ev()], [], actions)
    assert rows[0]["action_reason"] == "ACTION_SYMBOL_CONTINUITY_UNVERIFIED"


def test_request_budget_includes_retry_and_respects_retry_after(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr("market_lab.api.time.sleep", waits.append)
    response = Response({}, 429); response.headers = {"Retry-After": "7"}
    api = Massive(tmp_path, "secret", Session([response, Response({"results": []})]), max_requests=1)
    with pytest.raises(APIError, match="REQUEST_BUDGET_EXHAUSTED"):
        api.get("/v3/reference/tickers", {"date": "2026-11-13"})
    assert api.requests == 1 and waits == [7]


def test_malformed_json_array_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr("market_lab.api.time.sleep", lambda _: None)
    api = Massive(tmp_path, "secret", Session([Response([])]), retries=1)
    with pytest.raises(APIError, match="NETWORK_OR_INVALID_JSON"):
        api.get("/test")
    assert not list(tmp_path.rglob("*.parquet"))


def test_offline_cache_and_corruption(tmp_path):
    api = Massive(tmp_path, "secret", Session([Response({"results": [ref()]})]))
    api.tickers("2026-11-13")
    offline = Massive(tmp_path, offline=True)
    assert offline.tickers("2026-11-13") == [ref()]
    assert offline.requests == 0
    with pytest.raises(APIError, match="OFFLINE_CACHE_MISS"):
        offline.tickers("2026-11-12")
    next(tmp_path.rglob("*.parquet")).write_bytes(b"corrupt")
    with pytest.raises(APIError, match="CACHE_HASH_MISMATCH"):
        offline.tickers("2026-11-13")


def test_successful_page_reused_after_interruption(tmp_path):
    class Interrupted(Session):
        def get(self, *args, **kwargs):
            if self.calls:
                raise KeyboardInterrupt
            return super().get(*args, **kwargs)
    first = {"results": [ref()], "next_url": "https://api.massive.com/v3/reference/tickers?cursor=second"}
    with pytest.raises(KeyboardInterrupt):
        Massive(tmp_path, "secret", Interrupted([Response(first)])).tickers("2026-11-13")
    session = Session([Response({"results": [ref(ticker="OTHER", sid="FIGI2")]})])
    api = Massive(tmp_path, "secret", session)
    assert len(api.tickers("2026-11-13")) == 2
    assert api.requests == api.cache_hits == 1


def test_cycle_resume_after_interruption_preserves_committed_partition(tmp_path):
    api = FakeAPI()
    original = api.prices
    calls = 0
    def interrupt(day):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return original(day)
    api.prices = interrupt
    root, reports = tmp_path / "data", tmp_path / "reports"
    with pytest.raises(KeyboardInterrupt):
        build(api, root, reports, "resume", "2026-11-13", 3)
    p = next(root.rglob("snapshot.parquet")); before = file_hash(p)
    api.prices = original
    result = build(api, root, reports, "resume", "2026-11-13", 3)
    assert result["processed_cycles"] == 3 and file_hash(p) == before
    assert validate(reports / "resume")["technical_validation"] == "PASSED"


def test_validator_recomputes_float_even_when_artifact_hash_updated(tmp_path):
    m = build(FakeAPI(), tmp_path / "data", tmp_path / "reports", "r", "2026-11-13", 1)
    entry = m["cycles"][0]
    rows = pq.ParquetFile(entry["snapshot"]).read().to_pylist()
    rows[0]["shares_float"] = Decimal("1000000")
    rows[0]["float_status"] = "ELIGIBLE"
    parquet(entry["snapshot"], rows, SCHEMA)
    entry["snapshot_hash"] = file_hash(entry["snapshot"])
    write_json(tmp_path / "reports/r/manifest.json", m)
    with pytest.raises(ValueError, match="historical float"):
        validate(tmp_path / "reports/r")


def test_cli_default_does_not_export_bundle(tmp_path, monkeypatch):
    from market_lab import cli
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "Massive", lambda *a, **kw: FakeAPI())
    monkeypatch.setattr("sys.argv", ["market-lab", "build", "--run-id", "r", "--end", "2026-11-13", "--cycles", "1"])
    assert cli.main() == 2
    assert not list(tmp_path.rglob("*.zip"))
    assert json.loads((tmp_path / "reports/r/acceptance.json").read_text())["research_ready"] is False


def test_connector_actions_reject_incomplete_pagination(tmp_path):
    capture = {"path": "/stocks/v1/splits", "params": {"execution_date.gte": "2026-05-27", "execution_date.lte": "2026-11-13"},
               "retrieved_at": "2026-11-15T00:00:00Z", "response": {"structuredContent": {"result":
               'id,ticker,execution_date\na,TEST,2026-06-01\n\n\nNext page available. To fetch, call call_api with path="/stocks/v1/splits" and params={"cursor":"x"}'}}}
    write_json(tmp_path / "splits-connector.json", capture)
    with pytest.raises(ValueError, match="incomplete.*pagination"):
        import_connector_actions(tmp_path, tmp_path / "actions.json", "2026-05-27", "2026-11-13")
