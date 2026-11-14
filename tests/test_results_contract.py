import pyarrow as pa
import pytest

from market_lab.datasets import append_evidence
from market_lab.results import query


def test_full_evidence_and_focused_extract(tmp_path):
    rows = [{"cycle_id":"2026-11-13", "session":"RTH", "event_id":f"e{i}", "ticker":"TEST", "price":float(i)} for i in range(1001)]
    schema = pa.schema([(k,pa.string()) for k in ["cycle_id","session","event_id","ticker"]]+[("price",pa.float64())])
    paths = append_evidence(tmp_path,"run","events",rows,schema)
    assert append_evidence(tmp_path,"run","events",rows,schema) == paths
    result = query(tmp_path,"run","events",{"cycle_id":"2026-11-13","session":"RTH"},limit=5)
    assert result["matching_rows"]==1001 and result["returned_rows"]==5
    assert result["truncated_extract"]
    assert query(tmp_path,"run","events",{"event_id":"e1000"})["rows"][0]["price"]==1000
    assert query(tmp_path,"run","events",aggregate=True)["matching_rows"]==1001
    with pytest.raises(ValueError): query(tmp_path,"../escape")


def test_raw_ticks_shared_across_experiments(tmp_path):
    rows=[{"cycle_id":"2026-11-13","session":"RTH","event_id":None,"ticker":"TEST","price":2.0}]
    schema=pa.schema([(k,pa.string()) for k in ["cycle_id","session","event_id","ticker"]]+[("price",pa.float64())])
    p1=append_evidence(tmp_path,"run1","ticks",rows,schema,dataset_id="source-v1")
    p2=append_evidence(tmp_path,"run2","ticks",rows,schema,dataset_id="source-v1")
    assert p1==p2 and len(list(tmp_path.rglob("*.parquet")))==1
    assert query(tmp_path,"run1","ticks",aggregate=True)["matching_rows"]==1
    assert query(tmp_path,"run2","ticks",aggregate=True)["matching_rows"]==1
