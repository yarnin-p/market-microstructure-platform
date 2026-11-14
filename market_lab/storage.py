import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported JSON type: {type(value).__name__}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=json_default, allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=json_default) + "\n")
    durable_replace(temp, path)


def parquet(path, rows, schema=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), temp, compression="zstd")
    durable_replace(temp, path)


def durable_replace(temp, path):
    with Path(temp).open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temp, path)
    fd = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def raw_schema():
    return pa.schema([(s, pa.string()) for s in ["request_hash", "retrieved_at", "request", "response"]])
