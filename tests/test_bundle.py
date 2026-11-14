import json
import zipfile

import pytest

from market_lab.bundle import export_bundle, validate_bundle, REQUIRED
from market_lab.pipeline import build
from test_universe import FakeAPI


def test_consolidated_bundle_and_budget(tmp_path):
    build(FakeAPI(),tmp_path/"data",tmp_path/"reports","r","2026-11-13",3)
    out=tmp_path/"research/r/research_bundle.zip"
    result=export_bundle(tmp_path/"reports/r",out)
    assert result["processed_cycles"]==3
    assert result["execution_status"]=="INCOMPLETE"
    assert validate_bundle(out)["cycle_records"]==3
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist())==REQUIRED
        m=json.loads(z.read("manifest.json"))
        assert m["raw_ticks_included"] is False
        assert json.loads(z.read("summary.json"))["total_detected_events"] is None
    export_bundle(tmp_path/"reports/r",out,1)
    with zipfile.ZipFile(out) as z:
        m=json.loads(z.read("manifest.json"))
        assert m["size_policy"]["budget_exceeded"]
    assert len(list(out.parent.glob("*.zip")))==1


def test_bundle_detects_tampering(tmp_path):
    build(FakeAPI(),tmp_path/"data",tmp_path/"reports","r","2026-11-13",1)
    out=tmp_path/"research_bundle.zip"
    export_bundle(tmp_path/"reports/r",out)
    with zipfile.ZipFile(out) as src:
        contents={n:src.read(n) for n in src.namelist()}
    contents["summary.json"]=b"{}"
    with zipfile.ZipFile(out,"w") as dest:
        for name,body in contents.items():dest.writestr(name,body)
    with pytest.raises(ValueError,match="checksum"):
        validate_bundle(out)


def test_no_silent_omission_of_existing_events(tmp_path):
    build(FakeAPI(),tmp_path/"data",tmp_path/"reports","r","2026-11-13",1)
    p=tmp_path/"data/runs/r/events/cycle=2026-11-13/events.parquet"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"event data cannot be silently omitted")
    with pytest.raises(ValueError,match="must not be silently omitted"):
        export_bundle(tmp_path/"reports/r",tmp_path/"bundle.zip")


def test_single_cli_run_exports_one_consolidated_bundle(tmp_path,monkeypatch):
    from market_lab import cli
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli,"Massive",lambda *args, **kwargs:FakeAPI())
    monkeypatch.setattr("sys.argv",["market-lab","run","--run-id","cli-run","--end","2026-11-13","--cycles","3","--export-bundle"])
    assert cli.main()==2  # explicitly incomplete because historical float is absent
    bundles=list((tmp_path/"research").rglob("*.zip"))
    assert len(bundles)==1
    assert validate_bundle(bundles[0])["cycle_records"]==3
