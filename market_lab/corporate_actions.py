"""Conservative action flags; no split adjustment or float inference."""
import csv
import io
import json
import re
from pathlib import Path

from .storage import file_hash, write_json


def connector_text(capture):
    response = capture["response"]
    if response.get("isError"):
        raise ValueError("connector returned error")
    text = response.get("structuredContent", {}).get("result")
    if text is None:
        text = next(c["text"] for c in response["content"] if c["type"] == "text")
    return text


def import_connector_actions(folder, output, start, end):
    """Normalize saved connector responses, requiring a complete cursor chain."""
    folder = Path(folder)
    result = {"schema_version": "corporate-actions-v1", "start": start, "end": end,
              "complete": True, "sources": []}
    for kind, date_field in [("splits", "execution_date"), ("dividends", "ex_dividend_date")]:
        paths = [folder / f"{kind}-connector.json"]
        paths += sorted(folder.glob(f"{kind}-[0-9]*-connector.json"), key=lambda p: int(p.name.split("-")[1]))
        expected = {f"{date_field}.gte": start, f"{date_field}.lte": end}
        rows, ids = [], set()
        for page_index, path in enumerate(paths):
            cap = json.loads(path.read_text())
            if cap["path"] != f"/stocks/v1/{kind}" or any(cap["params"].get(k) != v for k, v in expected.items()):
                raise ValueError("corporate action request range/cursor mismatch")
            text = connector_text(cap)
            split = text.split("\n\n\nNext page available.", 1)
            page = list(csv.DictReader(io.StringIO(split[0])))
            if not page or date_field not in page[0] or "id" not in page[0]:
                raise ValueError("invalid corporate action connector table")
            source = {"path": str(path.resolve()), "sha256": file_hash(path),
                      "retrieved_at": cap["retrieved_at"], "transport": "MASSIVE_CONNECTOR",
                      "endpoint": cap["path"], "page": page_index}
            result["sources"].append(source)
            for index, row in enumerate(page):
                if not start <= row[date_field] <= end or not row.get("ticker") or row["id"] in ids:
                    raise ValueError("duplicate or out-of-range corporate action")
                ids.add(row["id"])
                row["source_ref"] = {**source, "row_index": index}
                rows.append(row)
            match = re.search(r'Next page available\. To fetch, call call_api with path="([^"]+)" and params=(\{[^\n]+\})', text)
            if match:
                if match[1] != cap["path"] or page_index == len(paths) - 1:
                    raise ValueError("incomplete corporate action pagination")
                expected = json.loads(match[2])
            elif page_index != len(paths) - 1:
                raise ValueError("unexpected page after completed corporate action response")
        result[kind] = rows
    write_json(output, result)
    return {"splits": len(result["splits"]), "dividends": len(result["dividends"]), "sources": len(result["sources"])}


def load_actions(path, schedule):
    if path is None:
        return {"complete": False, "splits": [], "dividends": [], "sources": [], "error": "ACTION_COVERAGE_UNAVAILABLE"}
    result = json.loads(Path(path).read_text())
    if result.get("schema_version") != "corporate-actions-v1":
        raise ValueError("unsupported corporate action schema")
    if result["start"] > schedule[0]["cycle_id"] or result["end"] < schedule[-1]["cycle_id"]:
        raise ValueError("corporate actions do not cover requested cycles")
    if result.get("complete") and not result.get("sources"):
        raise ValueError("complete corporate actions require source evidence")
    for source in result["sources"]:
        if file_hash(source["path"]) != source["sha256"]:
            raise ValueError("corporate action source hash mismatch")
    return result


def action_index(actions):
    index = {}
    for kind, field in [("splits", "execution_date"), ("dividends", "ex_dividend_date")]:
        for row in actions.get(kind, []):
            index.setdefault(row["ticker"], []).append({"kind": kind, "date": row[field], **row})
    return index


def action_gate(cycle, ticker, index, complete, aliases=()):
    symbols = {ticker, *aliases}
    rows = [r for symbol in sorted(symbols) for r in index.get(symbol, [])
            if cycle["anchor_date"] < r["date"] <= cycle["cycle_id"]]
    if not complete:
        return "UNRESOLVED", "ACTION_COVERAGE_UNAVAILABLE", rows
    if any(r["kind"] == "splits" for r in rows):
        return "UNRESOLVED", "SPLIT_CYCLE_PRICE_BASIS_UNRESOLVED", rows
    return "ELIGIBLE", "NO_SPLIT_OBSERVED", rows
