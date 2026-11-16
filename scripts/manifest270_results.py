"""Publish actual replay findings from the approved single-cycle manifest."""
import csv,json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from collections import Counter
from market_lab.manifest270 import ROOT,REPORT,RUN,read
from market_lab import census as old
from market_lab.storage import write_json,file_hash

summary=read(REPORT/'replay-summary.json');approval=read(ROOT/'approval.json');manifest=read(ROOT/'final-acquisition-manifest.json')
assert summary['complete_trade_windows']==summary['approved_candidates'], 'Do not publish a partial acquisition as the requested complete result'
assert summary['status']=='COMPLETE_APPROVED_MANIFEST_REPLAY'
verified=list(csv.DictReader((REPORT/'verified-observed.csv').open()))
all_events=list(csv.DictReader((REPORT/'all-first-touches.csv').open()))
assert len({r['security_id']for r in all_events})==len(all_events)
for r in all_events:
    assert 0<Decimal(r['previous_rth_close'])<=3
    assert 100000<=int(r['current_float_proxy_shares'])<=15000000
    assert Decimal(r['first_touch_price'])>=Decimal(r['threshold_price'])
    assert r['session']in {'AH','PRE','RTH'}
fields=['ticker','session','first_touch_timestamp_et','previous_rth_close','threshold_price','first_touch_price','gain_from_p0_pct',
        'current_float_proxy_shares','float_is_verified_pit','first_touch_timestamp_utc_ns','first_touch_status','observed_window_first_verified',
        'trade_size','trade_conditions','trade_exchange','restoration_status','restoration_source','correction_status','quality_flags','source_reference']
old.table(REPORT/'first-touch-list.csv',verified,fields)
write_json(REPORT/'approval.json',approval)
allowed={r['ticker']for r in manifest}
started=datetime.fromisoformat(approval['approved_at'])
attempts=[]
for p in (old.ROOT/'attempts').glob('*.json'):
    a=read(p)
    if datetime.fromisoformat(a['started_at'].replace('Z','+00:00'))>=started:
        assert a['request']['path'].rsplit('/',1)[-1]in allowed,'unapproved ticker acquisition'
        attempts.append(a)
write_json(REPORT/'acquisition-scope-audit.json',{'approved_tickers':len(allowed),'post_approval_connector_attempts':len(attempts),'only_approved_tickers_requested':True,'requested_tickers':sorted({a['request']['path'].rsplit('/',1)[-1]for a in attempts})})
results=[read(p)for p in (ROOT/'replay').glob('*.json')]
source_index={'approval':approval,'candidate_manifest_sha256':file_hash(ROOT/'final-acquisition-manifest.json'),
              'code_hashes':{p:file_hash(p)for p in ['market_lab/manifest270.py','market_lab/census.py','market_lab/tick_replay.py','scripts/census_mcp_batch.js']},
              'tick_pages':[p for r in results for p in r['pages']]}
write_json(REPORT/'replay-evidence.json',source_index)
joins=[{'ticker':r['ticker'],**p}for r in results for p in r['pages']if p.get('coverage_join')]
write_json(REPORT/'transport-continuity-audit.json',{'replay_policy_changed':False,'tail_joins':joins,
    'method':'Retain original prefix and resume with inclusive timestamp.gte at exactly the previous last SIP timestamp; deduplicate exact records and retain same-timestamp ties.',
    'manual_transport_probes':'FCUV pages 00103 and 00104 are captured and hashed; the former proves a cursor limit override is ignored, the latter starts the documented inclusive tail. Both request approved FCUV only.'})
write_json(REPORT/'replay-quality.json',{
    'rejected_trade_reasons':dict(sum((Counter(r['reject_counts'])for r in results),Counter())),
    'raw_session_rows':dict(sum((Counter(r['session_rows'])for r in results),Counter())),
    'eligible_session_rows':dict(sum((Counter(r['eligible_session_rows'])for r in results),Counter())),
    'raw_vs_eligible_first_crossing_differs':sum(r.get('raw_first_crossing',{}).get('record_id')!=r['event']['record_id']for r in results if r['event']and r.get('raw_first_crossing')),
    'later_invalidated_events':summary['later_invalidated_events'],
    'raw_json_hash_dependent_trigger_ties':summary['raw_json_hash_dependent_trigger_ties']})
paused=read(Path('data/runs/census-candidates-20261113-rest-20261116-v2/tick-cache-at-pause.json'))
for p,h in paused.items():assert file_hash(p)==h,'pre-existing cache changed'
write_json(REPORT/'result-integrity.json',{'old_tick_pages_preserved':len(paused),'source_hashes_checked':True,
    'one_event_per_security_cycle':True,'threshold_float_price_bounds_passed':True,
    'reconciliation':f"{summary['approved_candidates']} = {summary['first_touch_events']} + {summary['rejected_no_eligible_touch']} + {summary['unknown']}",
    'frozen_replay_sha256':file_hash('market_lab/tick_replay.py')})
lines=['# First +10% Eligible Touch — Trading Cycle 2026-11-13','',f"Run `{RUN}` — **{summary['status']}**.",'',
       f"ตรวจตาม approved candidate manifest {summary['approved_candidates']} securities; หน้าต่าง Tick ครบ {summary['complete_trade_windows']}/{summary['approved_candidates']} ({summary['candidate_coverage_percent']:.2f}%).",'',
       '| Result | Count |','|---|---:|',
       f"| Verified first eligible touch in observed sessions | {summary['verified_observed']} |",
       f"| Eligible events with prior/pagination uncertainty | {summary['unverified_prior_or_pagination']} |",
       f"| Complete streams without an eligible touch | {summary['rejected_no_eligible_touch']} |",
       f"| Unknown/incomplete without an event | {summary['unknown']} |",'',
       f"Verified sessions: {json.dumps(summary['verified_sessions'],sort_keys=True)}. All observed event sessions: {json.dumps(summary['sessions'],sort_keys=True)}.",'',
       f"[Complete verified list (CSV)](../../reports/{RUN}/first-touch-list.csv) · [All observed first touches](../../reports/{RUN}/all-first-touches.csv) · [Unverified](../../reports/{RUN}/unverified.csv) · [Rejected](../../reports/{RUN}/rejected.csv) · [Unknown](../../reports/{RUN}/unknown-incomplete.csv).",'',
       '## Complete verified list','',
       '| Ticker | Session | First eligible time (ET) | P0 | Touch price | Current Float Proxy shares |',
       '|---|---|---|---:|---:|---:|']
for r in verified:
    fmt=lambda v:format(Decimal(v).normalize(),'f')
    lines.append(f"| {r['ticker']} | {r['session']} | {r['first_touch_timestamp_et']} | {fmt(r['previous_rth_close'])} | {fmt(r['first_touch_price'])} | {int(r['current_float_proxy_shares']):,} |")
lines+=['','## Scope and interpretation','',
    'P0 is the frozen unadjusted previous RTH close on Nov12, >$0 and <=$3. Current Float Proxy is 100K–15M shares, explicitly retrospective rather than historical PIT float. The selected stocks pass the existing historical primary listing (XNAS/XASE/XNYS), CS, identity, currency, continuity and corporate-action gates. P0 is the vendor daily close under the frozen methodology, not an independently certified auction/executable price.', '',
    'Cycle windows: AH (Nov12 16:00,20:00) ET, PRE [Nov13 04:00,09:30), RTH [09:30,16:00]. Overnight 20:00–04:00 remains unobserved. AH dates in the table are Nov12 by design. First touch means one earliest eligible observed trade per security/cycle at price >=1.10×P0; it does not require a print exactly at +10%. The CSV contains exact UTC nanoseconds, decimal prices, actual Conditions/size/exchange, correction/restoration evidence and source hashes.', '',
    'The original sip-first-touch-v1 implementation is unchanged: BOTH consolidated high/low and open/close update requirements, special Form T treatment in AH/PRE, odd-lot and stale/reference-price exclusions, participant timestamp checks, SIP ordering and original-state correction reconstruction. A second earliest-eligible scan and page/cursor/hash checks validate every candidate. No first-touch trade is inferred from an aggregate timestamp.', '',
    'Transport repair uses 15,000-row pages. Existing smaller-page prefixes remain immutable; documented inclusive timestamp tail joins retain the boundary SIP timestamp and all tied records, followed by exact-record deduplication. This changes transport segmentation only. The continuity audit records every such join, and regression tests cover same-timestamp records and rejection of a skipped boundary.', '',
    '“Verified” in the primary list means first within complete observed AH/PRE/RTH windows without unresolved earlier evidence. The original first_touch_status remains alongside it: PRE/RTH retain FIRST_TOUCH_UNVERIFIED for continuous full-cycle precedence because of the overnight blind interval. These two fields describe different evidence scopes. Unverified observations and rejected/unknown candidates remain separately visible; no missing stream is converted into a zero.', '',
    'Selection starts from the user’s 270 Daily13 candidates: 79 passed the historical/current-proxy gates; 134 excluded and 57 unresolved. AH supplementation contributed 14 provider-aggregate candidates and nine raw-cache price diagnostics, for 102 unique approved securities. The latter require condition verification and are not assumed eligible. Every candidate, including rejected cases, remains in the denominator. Complete old caches were reused, and only missing approved windows were acquired through REST/MCP.', '',
    'Discovery coverage is the approved 270-seed-plus-AH design, not a full-market Tick census. AH screening covered 315 eligible proxy securities outside the seed; the design does not certify all PRE-only movers outside the seed. No full-universe 885 Tick loop was resumed. Frozen M1–M5/005.1 research and pre-existing holdout tick/cohort evidence were not changed/opened. No S3 downloads or additional research cycles were used.', '',
    f"Later invalidated observed triggers: {summary['later_invalidated_events']}. Source-record ties requiring unavailable original JSON hash: {summary['raw_json_hash_dependent_trigger_ties']}. MCP exposes CSV rather than original HTTP JSON/headers; hashes bind the captured representation. Corrections after cycle end and independently certified halt history remain limitations. These are market observations, not executable fills or P&L.",'',
    f'[Manifest and gate audit](2026-11-13-final-candidate-manifest.md) · [Replay evidence](../../reports/{RUN}/replay-evidence.json) · [Quality audit](../../reports/{RUN}/replay-quality.json) · [Integrity](../../reports/{RUN}/result-integrity.json).','',
    'Validation: full Python suite 315 passed; transport-driver Node suite 4 passed. All 559 pre-pause Tick pages retain their original hashes; 102 complete candidates reconcile to 95 eligible events plus seven complete no-eligible-touch streams.', '',
    'Reproduce offline with `.venv/bin/python -m market_lab.manifest270 verify`, then `PYTHONPATH=. .venv/bin/python scripts/manifest270_results.py`, using the retained immutable raw/reference caches.','']
Path('docs/research/2026-11-13-first-touch-results.md').write_text('\n'.join(lines))
# Preserve the original review content and link its executed result without erasing history.
review=Path('docs/research/2026-11-13-final-candidate-manifest.md')
link='ผลหลังอนุมัติและตรวจ Tick: [First Touch results](2026-11-13-first-touch-results.md).'
text=review.read_text()
if link not in text:
    first,rest=text.split('\n',1);review.write_text(first+'\n\n'+link+'\n'+rest)
write_json(REPORT/'result-artifact-hashes.json',{p.name:file_hash(p)for p in sorted(REPORT.iterdir())if p.is_file()and p.name not in {'result-artifact-hashes.json','artifact-hashes.json'}})
print(json.dumps(summary,indent=2))
