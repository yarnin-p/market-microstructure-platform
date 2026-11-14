"""Incremental bounded-batch evidence writer for future event/tick producers.

No download, sampling or truncation. Caller controls bounded batches; each batch is
partitioned by cycle/session and content-addressed so retries are idempotent.
"""
import re
from pathlib import Path

import json
from .storage import digest, parquet, write_json


def append_evidence(root, run_id, dataset, rows, schema, dataset_id=None):
    if dataset not in {"ticks", "events"} or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("invalid dataset or run ID")
    base = Path(root) / "runs" / run_id / dataset
    if dataset == "ticks":
        if not dataset_id or not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id):
            raise ValueError("ticks require a stable shared dataset_id")
        reference = base / "dataset-reference.json"
        value = {"dataset_id": dataset_id}
        if reference.exists() and json.loads(reference.read_text()) != value:
            raise ValueError("run already references a different tick dataset")
        write_json(reference, value)
        base = Path(root) / "datasets" / "ticks" / dataset_id
    groups = {}
    for row in rows:
        for field in ["cycle_id", "ticker", "event_id", "session"]:
            if field not in row:
                raise ValueError(f"missing evidence field: {field}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["cycle_id"]) or row["session"] not in {"AFTER_HOURS", "PREMARKET", "RTH", "CLOSED"}:
            raise ValueError("invalid evidence partition")
        groups.setdefault((row["cycle_id"], row["session"]), []).append(row)
    outputs = []
    for (cycle, session), batch in groups.items():
        path = base / f"cycle={cycle}" / f"session={session}" / (digest(batch) + ".parquet")
        if not path.exists():
            parquet(path, batch, schema)
        outputs.append(str(path))
    return outputs
