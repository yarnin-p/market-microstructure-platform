"""Versioned TASK 002.1 coverage repair and methodology comparison."""
import argparse
import heapq
import itertools
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import pyarrow.parquet as pq

from .api import APIError, load_key, safe_url
from .m2_pilot import event_table, fingerprint
from .m2_report import records
from .replay_methodology import (POLICIES, ReplayState, condition_maps, gap_diagnostics,
                                 ordering, outcome_sensitivity)
from .storage import digest, file_hash, write_json
from .tick_ingest import TickClient, normalize
from .tick_replay import SECOND, correction_key, ns, quote_at_event, number

CONFIG = "configs/task-002-1-qa-v1.json"


def roots(config):
    return Path("data/runs", config["baseline_run"]), Path("data/runs", config["run_id"]), Path("reports", config["run_id"])


def tree_hashes(root):
    return {str(p): file_hash(p) for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".writer.lock"}


def freeze(config):
    base, root, _ = roots(config)
    path = root / "execution.json"
    identity = {"config": config, "config_hash": digest(config),
                "code_hashes": {str(p): file_hash(p) for p in Path("market_lab").glob("*.py")}}
    if path.exists():
        prior = json.loads(path.read_text())
        if any(prior[k] != v for k, v in identity.items()):
            raise ValueError("QA code/config changed; use a new run ID")
        return prior
    assert subprocess.check_output(["git", "rev-parse", config["baseline_commit"]], text=True).strip().startswith(config["baseline_commit"])
    selection = json.loads((base / "selection.json").read_text())
    before = {**tree_hashes(base), **tree_hashes(Path("reports", config["baseline_run"]))}
    identity.update(baseline_files=before, source_selection_sha256=file_hash(base / "selection.json"),
                    baseline_commit=config["baseline_commit"], m1_before=fingerprint(selection["config"]["source_m1_run"]))
    write_json(path, identity)
    return identity


def repair_window(client, original, output, max_new_trade_pages):
    """Continue the old cursor chain; never modify the original coverage file."""
    output = Path(output)
    manifest = output / "coverage.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text())
        if saved["request"] != original["request"]:
            raise ValueError("repair window configuration mismatch")
        for page in saved["pages"]:
            if file_hash(page["path"]) != page["sha256"]:
                raise ValueError("repair source hash mismatch")
        if saved["complete"]:
            if json.loads(Path(saved["pages"][-1]["path"]).read_text()).get("next_url"):
                raise ValueError("false terminal-page completion")
            return saved
    coverage = json.loads(json.dumps(original))
    coverage.update(complete=False, error=None, original_page_count=len(original["pages"]),
                    original_complete=original["complete"], repair_version="task-002-1-v1")
    seen = set()
    # Re-walk immutable cached prefix and tail; terminal page is the only success.
    for page in coverage["pages"]:
        if file_hash(page["path"]) != page["sha256"]:
            raise ValueError("repair prefix source hash mismatch")
    last_body = json.loads(Path(coverage["pages"][-1]["path"]).read_text())
    path = last_body.get("next_url")
    prior_last = max((r.get("sip_timestamp", 0) for r in last_body["results"]), default=0)
    while path:
        marker = digest(path)
        if marker in seen:
            coverage["error"] = "REPAIR_PAGINATION_LOOP"
            break
        seen.add(marker)
        # Reserve the remaining global pages for optional bounded quote probes.
        url = safe_url(path)
        key = digest({"url": url.split("?",1)[0], "params": dict(parse_qsl(urlparse(url).query))})
        cached = (client.root / "pages" / (key + ".meta.json")).exists()
        if client.ledger["pages"] >= max_new_trade_pages and not cached:
            coverage["error"] = "REPAIR_NEW_TRADE_PAGE_BUDGET"
            break
        try:
            body, source = client.get(path)
            rows = body.get("results")
            if not isinstance(rows, list):
                raise APIError("REPAIR_INVALID_RESULTS")
            stamps = [r.get("sip_timestamp") for r in rows]
            if any(not isinstance(t, int) or isinstance(t, bool) or not coverage["request"]["start_ns"] < t <= coverage["request"]["end_ns"] for t in stamps):
                raise APIError("REPAIR_INVALID_OR_OUT_OF_RANGE_TIMESTAMP")
            if stamps != sorted(stamps) or stamps and stamps[0] < prior_last:
                raise APIError("REPAIR_NON_MONOTONIC_CURSOR")
            coverage["pages"].append({**source, "rows": len(rows)})
            coverage["raw_rows"] += len(rows)
            if stamps:
                prior_last = stamps[-1]
            path = body.get("next_url")
            write_json(manifest, coverage)
        except APIError as error:
            coverage["error"] = str(error)
            break
    coverage["complete"] = path is None and coverage["error"] is None
    coverage["remaining_cursor"] = path
    write_json(manifest, coverage)
    return coverage


def repair(config, env_file=None, offline=False):
    base, root, dest = roots(config)
    freeze(config)
    client = TickClient(root / "raw", config, load_key(env_file), offline)
    opportunities = records(base / "opportunities/opportunities.parquet")
    evidence = []
    for request in config["repair_windows"]:
        opportunity = next(o for o in opportunities if all(o[k] == v for k, v in request.items()))
        original = opportunity["trade_coverage"]
        if original["complete"]:
            raise ValueError("expected an incomplete original pilot window")
        output = root / "repairs" / request["cycle_id"] / request["ticker"]
        coverage = repair_window(client, original, output, config["max_new_trade_pages"])
        evidence.append({**request, "original_complete": False, "original_pages": len(original["pages"]),
                         "original_rows": original["raw_rows"], "repaired_complete": coverage["complete"],
                         "repaired_pages": len(coverage["pages"]), "repaired_rows": coverage["raw_rows"],
                         "new_pages": len(coverage["pages"]) - len(original["pages"]), "error": coverage["error"],
                         "coverage_manifest": str(output / "coverage.json"), "coverage_sha256": file_hash(output / "coverage.json")})
        print(json.dumps(evidence[-1]), flush=True)
    write_json(dest / "coverage-repair.json", {"windows": evidence, "new_http_requests": len(client.ledger["attempts"]),
        "new_pages": client.ledger["pages"], "new_decoded_bytes": client.ledger["decoded_bytes"], "budget": config,
        "coverage_claim": "Provider cursor exhaustion only, not independent consolidated-feed certification"})
    return evidence


TRADE_COLUMNS = ["record_id", "trade_id", "price", "size", "sip_timestamp", "participant_timestamp", "sequence_number",
                 "exchange", "trf_id", "correction", "session", "conditions_json", "source_json", "normalization_status"]


def parquet_rows(path):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=4096, columns=TRADE_COLUMNS):
        yield from batch.to_pylist()


def iter_normalized(paths):
    # Pages are timestamp monotone. Merge equal-SIP boundary groups globally so
    # pagination cannot change a tie-break or silently duplicate a print.
    for _, group in itertools.groupby(heapq.merge(*(parquet_rows(p) for p in paths), key=ordering), key=lambda r: r.get("sip_timestamp")):
        seen = set()
        for row in sorted(group, key=ordering):
            if row["record_id"] not in seen:
                seen.add(row["record_id"])
                yield row


def input_paths(config, opportunity, cycle, repaired):
    _, root, _ = roots(config)
    original = opportunity["normalization"]
    if file_hash(original["path"]) != original["sha256"]:
        raise ValueError("baseline normalized hash mismatch")
    paths = [original["path"]]
    coverage = opportunity["trade_coverage"]
    repair_path = root / "repairs" / cycle["cycle_id"] / opportunity["ticker"] / "coverage.json"
    if repaired and repair_path.exists():
        coverage = json.loads(repair_path.read_text())
        for index, page in enumerate(coverage["pages"][coverage["original_page_count"]:]):
            output = repair_path.parent / "normalized" / f"page-{index:03d}.parquet"
            if not output.exists():
                normalize({**coverage, "pages": [page], "raw_rows": page["rows"]}, opportunity["security_id"], cycle, output)
            audit = json.loads(output.with_suffix(".audit.json").read_text())
            if file_hash(output) != audit["sha256"]:
                raise ValueError("repair normalized hash mismatch")
            paths.append(str(output))
    return paths, coverage


def replay_pair(config, opportunity, cycle, conditions, repaired):
    paths, coverage = input_paths(config, opportunity, cycle, repaired)
    pairs = defaultdict(list)
    observed_end = 0
    for row in iter_normalized(paths):
        observed_end = max(observed_end, row.get("sip_timestamp") or 0)
        if row.get("correction") == 12:
            pairs[correction_key(row)].append(row)
    complete = coverage["complete"] and opportunity["normalization"]["invalid_timestamp_rows"] == 0
    maps = condition_maps(conditions)
    states = {p: ReplayState(p, cycle, opportunity, json.loads(Path("configs/m2-pilot-v1.json").read_text()),
                            maps[p], complete, config["run_id"], observed_end) for p in POLICIES}
    distribution = Counter()
    raw_session_counts = Counter()
    for row in iter_normalized(paths):
        row["restoration_status"] = "AS_RECORDED"
        if row.get("correction") == 1:
            matches = [r for r in pairs[correction_key(row)] if r["sip_timestamp"] > row["sip_timestamp"]]
            row = dict(row)
            if len(matches) == 1:
                row.update({k: matches[0][k] for k in ["price", "size", "conditions_json"]})
                row.update(restoration_status="ORIGINAL_FIELDS_FROM_MATCHING_12", restoration_source=matches[0]["source_json"])
            else:
                row["restoration_status"] = "CORRECTION_RECONSTRUCTION_UNRESOLVED"
        codes = tuple(json.loads(row["conditions_json"]))
        raw_session_counts[row["session"]] += 1
        for policy, state in states.items():
            passed, reason = state.feed(row)
            distribution[(opportunity["sample"], row["session"], policy, codes, passed, reason)] += 1
    return states, distribution, raw_session_counts, coverage


def analyze(config):
    base, root, dest = roots(config)
    execution = freeze(config)
    selection = json.loads((base / "selection.json").read_text())
    context = json.loads((base / "context.json").read_text())
    conditions = {r["id"]: r for r in context["conditions"]}
    cycles = {c["cycle_id"]: c for c in selection["calendar"]}
    baseline_events = records(base / "events/events.parquet")
    baseline_outcomes = records(base / "outcomes/outcomes.parquet")
    opportunities = records(base / "opportunities/opportunities.parquet")
    all_events, all_outcomes, all_opportunities, comparisons, audits, gaps = [], [], [], [], Counter(), []
    old_by_pair = {(e["security_id"], e["cycle_id"]): e for e in baseline_events}
    for opportunity in opportunities:
        if "normalization" not in opportunity:
            all_opportunities.append({**opportunity, "variant": "HISTORICAL_EXCLUDED_UNCHANGED"})
            continue
        cycle = cycles[opportunity["cycle_id"]]
        is_repair = any(all(opportunity[k] == v for k, v in r.items()) for r in config["repair_windows"])
        for repaired in ([False, True] if is_repair else [False]):
            variant = "QA_REPAIRED" if repaired else "QA_UNREPAIRED"
            states, distribution, raw_sessions, coverage = replay_pair(config, opportunity, cycle, conditions, repaired)
            for panel in ([variant] if is_repair else ["QA_UNREPAIRED", "QA_REPAIRED"]):
                audits.update({(panel, *key): n for key,n in distribution.items()})
            for policy, state in states.items():
                variants = [variant] if is_repair else ["QA_UNREPAIRED", "QA_REPAIRED"]
                current_event = state.event
                diagnostic = gap_diagnostics(state.eligible, cycle, state.complete)
                for version in variants:
                    opp = {"run_id": config["run_id"], "variant": version, "condition_policy": policy,
                        "cycle_id": opportunity["cycle_id"], "ticker": opportunity["ticker"], "security_id": opportunity["security_id"],
                        "sample": opportunity["sample"], "cohorts": opportunity["cohorts"],
                        "sec_overlap": bool(opportunity.get("sec_evidence")),
                        "complete_observed_sessions": state.complete,
                        "observed_opportunity_eligible": state.complete and not state.unknown_prior,
                        "strict_full_cycle_opportunity_eligible": False,
                        "zero_event_observed": state.complete and not state.unknown_prior and current_event is None,
                        "event_id": current_event["event_id"] if current_event else None,
                        "eligible_trades": len(state.eligible), "reject_counts": dict(state.reject_counts),
                        "raw_session_counts": dict(raw_sessions), "rejected_crossings": state.rejected_crossings,
                        "subsequent_crossings": state.recrosses, "provider_pages": len(coverage["pages"]),
                        "coverage_error": coverage["error"], "unknown_price_evidence_records": len(state.unknown_times)}
                    all_opportunities.append(opp)
                    if current_event:
                        event = {**current_event, "variant": version}
                        all_events.append(event)
                        for seconds in config["gap_sensitivities_seconds"]:
                            all_outcomes.append({**outcome_sensitivity(state, cycle, selection["config"], seconds),
                                                 "variant": version, "cohorts": opportunity["cohorts"],
                                                 "sec_overlap": bool(opportunity.get("sec_evidence"))})
                    old = old_by_pair.get((opportunity["security_id"], opportunity["cycle_id"]))
                    comparisons.append({"variant": version, "condition_policy": policy, "ticker": opportunity["ticker"],
                        "cycle_id": opportunity["cycle_id"], "sample": opportunity["sample"],
                        "baseline_event_id": old["event_id"] if old else None,
                        "baseline_timestamp": old["event_timestamp"] if old else None,
                        "new_event_id": current_event["event_id"] if current_event else None,
                        "new_timestamp": current_event["event_timestamp"] if current_event else None,
                        "timestamp_changed": (old["event_timestamp"] if old else None) != (current_event["event_timestamp"] if current_event else None),
                        "baseline_observed_verified": old["observed_window_first_verified"] if old else None,
                        "new_observed_verified": current_event["observed_sessions_first_verified"] if current_event else None,
                        "strict_full_cycle_verified": False})
                if policy == "HIGH_LOW_ONLY":
                    gaps.append({"ticker": opportunity["ticker"], "cycle_id": opportunity["cycle_id"], "variant": variant, **diagnostic})
            print(json.dumps({"ticker": opportunity["ticker"], "cycle": opportunity["cycle_id"], "variant": variant,
                              "complete": coverage["complete"], "events_by_policy": {p: bool(s.event) for p,s in states.items()}}), flush=True)
    for name, rows in [("events",all_events),("outcomes",all_outcomes),("opportunities",all_opportunities),("comparisons",comparisons)]:
        event_table(root / name / f"{name}.parquet", rows)
    condition_audit = [{"variant":v,"sample": s,"session": session,"policy": p,"codes": list(codes),"accepted": accepted,
                        "reason": reason,"trades": n} for (v,s,session,p,codes,accepted,reason),n in sorted(audits.items())]
    write_json(dest / "condition-distributions.json", {"scope":"SEPARATE_UNREPAIRED_AND_REPAIRED_WINDOWS; DEDUPLICATED_RESTORED_RECORDS",
        "condition_dictionary":context['conditions'],"rows":condition_audit,
        "limitations":"Combination counts are disjoint; per-code totals overlap for multi-condition prints. Invalid/rejected prints remain in raw evidence."})
    write_json(dest / "gap-diagnostics.json", gaps)
    write_json(dest / "first-touch-comparison.json", comparisons)
    write_json(dest / "summary.json", summarize(all_opportunities,all_events,all_outcomes,baseline_events,baseline_outcomes))
    audit_examples(config, all_events)
    verify_integrity(config, execution)
    return {"events":len(all_events),"outcomes":len(all_outcomes),"opportunities":len(all_opportunities)}


def summarize(opportunities, events, outcomes, baseline_events, baseline_outcomes):
    groups = []
    for variant in ["QA_UNREPAIRED", "QA_REPAIRED"]:
        for policy in POLICIES:
            for sample in ["SYSTEMATIC", "DIAGNOSTIC"]:
                for cohort in ["EXCHANGE_PRICE_ONLY", "MASSIVE_CURRENT_FLOAT_PROXY", "SEC_HISTORICAL_EVIDENCE_OVERLAP"]:
                    def member(r):
                        return bool(r.get("sec_overlap", r.get("sec_evidence"))) if cohort == "SEC_HISTORICAL_EVIDENCE_OVERLAP" else cohort in r.get("cohorts", [])
                    oo=[r for r in opportunities if r['variant']==variant and r.get('condition_policy')==policy and r['sample']==sample and member(r)]
                    ee=[r for r in events if r['variant']==variant and r['condition_policy']==policy and r['sample']==sample and member(r)]
                    group={"variant":variant,"condition_policy":policy,"sample":sample,"cohort":cohort,
                        "historical_quality_eligible_opportunities":len(oo),
                        "complete_provider_windows":sum(r['complete_observed_sessions'] for r in oo),
                        "observed_first_touch_denominator":sum(r['observed_opportunity_eligible'] for r in oo),
                        "strict_full_cycle_denominator":0,"strict_full_cycle_first_events":0,
                        "events":len(ee),"verified_observed_first_events":sum(r['observed_sessions_first_verified'] for r in ee),
                        "prefix_first_events":sum(r['prefix_first_verified'] for r in ee),
                        "zero_event_observed":sum(r['zero_event_observed'] for r in oo),"gap_sensitivities":{}}
                    for gap in ["GAP_300_SECONDS","GAP_900_SECONDS","NO_MECHANICAL_GAP"]:
                        rr=[r for r in outcomes if r['variant']==variant and r['condition_policy']==policy and r['sample']==sample and r['gap_policy']==gap and member(r)]
                        forward={}
                        for label in ['5m','15m','30m','60m','session_end','cycle_end']:
                            mm=[m for r in rr for m in r['forward'] if m['horizon']==label]
                            values=[float(m['return']) for m in mm if m['return'] is not None]
                            forward[label]={"event_denominator":len(mm),"uncensored":len(values),"censored":sum(m['censored'] for m in mm),
                                "censoring_rate":sum(m['censored'] for m in mm)/len(mm) if mm else None,
                                "mean_observed_return":sum(values)/len(values) if values else None,
                                "min":min(values) if values else None,"max":max(values) if values else None}
                        barriers={f"{u}/{d}":dict(Counter(b['outcome'] for r in rr for b in r['barriers'] if b['up']==u and b['down']==d))
                            for u,d in [('0.03','0.03'),('0.05','0.03'),('0.10','0.05')]}
                        group['gap_sensitivities'][gap]={"forward":forward,"barriers":barriers}
                    groups.append(group)
    return {"methodology_version":"task-002-1-observed-sessions-v2","groups":groups,
        "baseline":{"events":len(baseline_events),"observed_verified":sum(e['observed_window_first_verified'] for e in baseline_events),
                    "legacy_verified_label":sum(e['first_touch_status']=='VERIFIED_FIRST_TOUCH' for e in baseline_events),
                    "full_24_hour_opportunity_denominator":0},
        "statistical_scope":"FULL_FIXED_PILOT_ONLY; diagnostic and systematic kept separate; cohorts overlap",
        "primary_policy":"HIGH_LOW_ONLY / QA_REPAIRED / NO_MECHANICAL_GAP",
        "strict_status":"NOT_EVALUABLE_NO_OVERNIGHT_COVERAGE", "executable_profitability":"NOT_ASSESSED",
        "frozen_frame_opportunities":48,"unchanged_historical_exclusions":3,
        "significance":"NOT_ESTIMATED; repeated security-cycle observations and diagnostic selection bias"}


def raw_at(source_json):
    source=json.loads(source_json)
    if file_hash(source['path'])!=source['sha256']:
        raise ValueError('audit raw source hash mismatch')
    return json.loads(Path(source['path']).read_text())['results'][source['row']],source


def audit_examples(config, revised_events):
    base,_,dest=roots(config)
    original=records(base/'events/events.parquet')
    opportunities=records(base/'opportunities/opportunities.parquet')
    audits=[]
    for ticker in ['HOTH','SNGX','DBGI']:
        old=next(e for e in original if e['ticker']==ticker)
        event=next(e for e in revised_events if e['ticker']==ticker and e['cycle_id']==old['cycle_id']
                   and e['variant']=='QA_REPAIRED' and e['condition_policy']=='HIGH_LOW_ONLY')
        raw,trade_ref=raw_at(event['source_json'])
        assert raw['sip_timestamp']==event['event_timestamp']
        if event['restoration_status']=='AS_RECORDED':
            assert number(raw['price'])==number(event['touch_price'])
        opportunity=next(o for o in opportunities if o['ticker']==ticker and o['cycle_id']==old['cycle_id'])
        q_path=Path(opportunity['normalization']['path']).with_name('quotes.parquet')
        quotes=pq.ParquetFile(q_path).read().to_pylist()
        within=opportunity['quote_coverage']['request']['start_ns'] < event['event_timestamp'] <= opportunity['quote_coverage']['request']['end_ns']
        if not within:
            audits.append({'ticker':ticker,'status':'REVISED_EVENT_OUTSIDE_ORIGINAL_QUOTE_WINDOW','event':event})
            continue
        before=quote_at_event(quotes,event,{'max_quote_age_seconds':5},opportunity['quote_coverage']['complete'])
        quote_raw,quote_ref=raw_at(before['source_json'])
        assert number(quote_raw['bid_price'])==number(before['bid']) and number(quote_raw['ask_price'])==number(before['ask'])
        price,bid,ask=number(event['touch_price']),number(before['bid']),number(before['ask'])
        relation='WITHIN_NBBO' if bid<=price<=ask else 'ABOVE_PRECEDING_ASK' if price>ask else 'BELOW_PRECEDING_BID'
        surrounding=[]
        for radius in [1,5]:
            after=[q for q in quotes if event['event_timestamp'] < (q.get('sip_timestamp') or 0) <= event['event_timestamp']+radius*SECOND
                   and number(q.get('bid_price')) is not None and number(q.get('ask_price')) is not None]
            support=next((q for q in after if number(q['bid_price'])<=price<=number(q['ask_price'])),None)
            if support:
                check,ref=raw_at(support['source_json'])
                assert check['sip_timestamp']==support['sip_timestamp']
                surrounding.append({'radius_seconds':radius,'records':len(after),'price_inside_subsequent_nbbo':True,
                    'first_support_delay_ns':support['sip_timestamp']-event['event_timestamp'],
                    'bid':support['bid_price'],'ask':support['ask_price'],'source':ref})
            else:
                surrounding.append({'radius_seconds':radius,'records':len(after),'price_inside_subsequent_nbbo':False})
        audits.append({'ticker':ticker,'cycle_id':event['cycle_id'],'event_timestamp':event['event_timestamp'],
            'touch_price':event['touch_price'],'threshold':event['threshold_price'],'conditions':json.loads(event['conditions_json']),
            'raw_trade':raw,'trade_source':trade_ref,'preceding_nbbo':before,'raw_quote':quote_raw,'quote_source':quote_ref,
            'relation':relation,'subsequent_quote_checks':surrounding,'revised_touch_same_as_original':old['record_id']==event['record_id'],
            'quotes_after_touch_used_for_trigger':False,'executable_fill_claim':False,
            'status':'RAW_TRADE_AND_NBBO_HASH_VERIFIED'})
    write_json(dest/'raw-nbbo-audit.json',audits)


def verify_integrity(config, execution):
    for path, expected in execution['baseline_files'].items():
        if file_hash(path)!=expected:
            raise ValueError("original 8a4903f pilot artifact changed: "+path)
    m1=execution['config']['baseline_run']
    selection=json.loads((Path('data/runs')/m1/'selection.json').read_text())
    if fingerprint(selection['config']['source_m1_run'])!=execution['m1_before']:
        raise ValueError("M1 changed")
    _,_,dest=roots(config)
    write_json(dest/'integrity.json',{"baseline_artifacts_unchanged":True,"m1_unchanged":True,
        "baseline_files_checked":len(execution['baseline_files']),"holdout_outcomes_accessed":False})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['freeze','repair','analyze'])
    p.add_argument('--config',default=CONFIG)
    p.add_argument('--env-file')
    p.add_argument('--offline',action='store_true')
    args=p.parse_args();config=json.loads(Path(args.config).read_text())
    if args.command=='freeze':
        freeze(config)
    elif args.command=='repair':
        repair(config,args.env_file,args.offline)
    else:
        print(json.dumps(analyze(config)),flush=True)


if __name__=='__main__':
    main()
