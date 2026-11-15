import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("ortex_probe", Path(__file__).parents[1] / "scripts/probe_ortex_float.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Response:
    headers = {"Content-Type": "application/json", "Set-Cookie": "must-not-be-saved"}

    def __init__(self, status):
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, _):
        yield json.dumps({"data": [], "meta": {}}).encode()


class Session:
    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == (10, 25)
        assert kwargs["headers"]["Ortex-Api-Key"] == "TEST"
        return Response(next(self.statuses))

    def close(self):
        pass


def test_resume_counts_rate_limited_attempt_against_total_budget(tmp_path, monkeypatch):
    session = Session([200, 200, 429, 200, 200])
    monkeypatch.setattr(probe.requests, "Session", lambda: session)
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)
    output = tmp_path / "probe"
    assert len(probe.run(output)["attempts"]) == 3
    assert len(probe.run(output, resume=True)["attempts"]) == 5
    assert len(probe.run(output, resume=True)["attempts"]) == 5
    assert len(session.calls) == 5
    ledger = (output / "manifest.json").read_text()
    assert "Set-Cookie" not in ledger and "Ortex-Api-Key" not in ledger
    assert len({r["response_file"] for r in json.loads(ledger)["attempts"]}) == 5


def test_auth_failure_stops_and_existing_output_is_not_overwritten(tmp_path, monkeypatch):
    session = Session([401])
    monkeypatch.setattr(probe.requests, "Session", lambda: session)
    output = tmp_path / "probe"
    assert len(probe.run(output)["attempts"]) == 1
    with pytest.raises(FileExistsError):
        probe.run(output)
    assert len(session.calls) == 1
