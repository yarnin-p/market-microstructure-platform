"""Prepare the complete review package; never authorizes Tick acquisition."""
import csv,json
from collections import Counter
from pathlib import Path
from market_lab.manifest270 import ROOT,REPORT,RUN,read
from market_lab import census as old,candidate_census as prior
from market_lab.storage import file_hash,write_json

s=read(REPORT/'summary.json');cfg=read(ROOT/'config.json');manifest=read(ROOT/'final-acquisition-manifest.json')
audit=read(ROOT/'seed-audit.json');extras=list(csv.DictReader((REPORT/'additional-ah-candidates.csv').open()))
dailycap=read(ROOT/'daily13-capture.json')
import io
from decimal import Decimal
daily={r['T']:r for r in csv.DictReader(io.StringIO(dailycap['csv']))}
for row in audit:
    d=daily.get(row['ticker']);p0=row['previous_rth_close']
    row['daily13_high']=d['h']if d else None
    row['daily13_trigger_reproduced']=bool(d and p0 and Decimal(d['h'])>=Decimal(p0)*Decimal('1.10'))
old.table(REPORT/'seed-270-universe-audit.csv',audit,['ticker','status','reasons','security_id','security_type','historical_primary_exchange','previous_rth_close','current_float_proxy_shares','daily13_high','daily13_trigger_reproduced','float_effective_date','float_retrieved_at','float_is_verified_pit','reference_source','price_source','float_source'])
# Every original captured Tick page is preserved byte-for-byte.
paused=read(prior.ROOT/'tick-cache-at-pause.json')
for p,h in paused.items():assert file_hash(p)==h
now=list((old.ROOT/'raw').glob('*/page-[0-9][0-9][0-9][0-9][0-9].json'))
assert {str(p)for p in now}==set(paused),'Tick pages changed before manifest approval'
for p,h in read(old.ROOT/'frozen.json')['protected_hashes'].items():assert file_hash(p)==h
write_json(REPORT/'integrity.json',{'original_tick_pages_preserved':len(paused),'new_tick_pages_before_approval':0,
    'old_research_protected_hashes_passed':True,'final_manifest_sha256':file_hash(ROOT/'final-acquisition-manifest.json'),
    'seed_sha256':file_hash('configs/census-seed-270-20261113.txt'),'frozen_replay_sha256':file_hash('market_lab/tick_replay.py'),
    'tick_permission':'AWAITING_USER_APPROVAL'})
pending_lock={'run_id':RUN,'status':'AWAITING_USER_APPROVAL',
    'manifest_sha256':file_hash(ROOT/'final-acquisition-manifest.json'),'manifest_path':str((ROOT/'final-acquisition-manifest.json').resolve())}
lock_path=old.ROOT/'required-approved-manifest.json'
if lock_path.exists()and read(lock_path)['status']=='USER_APPROVED':
    assert read(lock_path)['manifest_sha256']==pending_lock['manifest_sha256']
else:write_json(lock_path,pending_lock)
source_index={}
for p in (ROOT/'ah').glob('*.json'):
    v=read(p);source_index[p.stem]={'path':str(p.resolve()),'sha256':file_hash(p),'source':v['source'],'source_kind':v['source_kind'],'bars':len(v['bars'])}
write_json(REPORT/'source-index.json',{'config':cfg,'daily13_source':{'path':str((ROOT/'daily13-capture.json').resolve()),'sha256':file_hash(ROOT/'daily13-capture.json'),'rows':dailycap['source_rows']},
    'ah_aggregate_sources':source_index,'raw_cache_diagnostics':{p.stem:{'path':str(p.resolve()),'sha256':file_hash(p)}for p in (ROOT/'raw-ah-rescue').glob('*.json')}})
write_json(Path('configs/manifest270-ah-20261113-v3.json'),cfg)
write_json(REPORT/'resources.json',{'new_ah_aggregate_request_attempts':len(list((ROOT/'attempts').glob('*.json'))),
    'new_ah_raw_responses':len(list((ROOT/'raw-aggregates').glob('*.json'))),'reused_ah_summaries':202,
    'daily13_grouped_provider_requests':1,'daily13_query_projection_rows':dailycap['source_rows'],
    'ah_connectivity_probe_requests':1,'new_tick_requests_before_approval':0,'preserved_tick_pages':len(paused),
    'additional_tick_requests_minimum':s['Additional REST Calls Required minimum'],
    'exact_future_tick_request_count':'unknown until pagination is exhausted','permission':'AWAITING_USER_APPROVAL'})
lines=['# Trading Cycle 2026-11-13 — 270 Seed + AH Manifest Review','',f"Run `{RUN}` — **AWAITING USER APPROVAL**.",'',
    '## Mandatory gate before Tick resume','',
    '| Item | Observed count |','|---|---:|',
    '| Daily Aggregate Candidates | 270 |','| Historical Universe PASS | 79 |','| Historical Universe EXCLUDED | 134 |','| Historical Universe UNRESOLVED | 57 |',
    '| Additional AH price candidates | 23 |','| — provider minute-aggregate evidence | 14 |','| — cached raw minute-high diagnostics | 9 |',
    '| Final proposed Tick Acquisition Manifest | 102 |','| Already cached completely | 47 |','| Additional REST calls required | **at least 55** |','',
    'The exact remaining REST page/call total cannot be known before pagination. Each of the 55 missing security streams needs at least one initial request; further pages are retained and followed within bounded batches. No extra Tick requests or First-Touch replay were started after the user’s stop/approval instruction. The 559 previously captured Tick pages and their hashes remain unchanged. No caches/checkpoints were deleted.', '',
    f'[Final manifest, every ticker and cache disposition](../../reports/{RUN}/final-acquisition-manifest.csv) · [Full 270-row gate audit](../../reports/{RUN}/seed-270-universe-audit.csv) · [Additional AH price/time/P0 evidence](../../reports/{RUN}/additional-ah-candidates.csv) · [AH discovery coverage](../../reports/{RUN}/ah-discovery-coverage.csv) · [Integrity](../../reports/{RUN}/integrity.json).','',
    '## Final proposed list — all 102 tickers','',
    'Seed PASS (79):','', '```',]
seed=[r['ticker']for r in manifest if r['origin']=='SEED_270_PASS']
for i in range(0,len(seed),10):lines.append(' '.join(seed[i:i+10]))
lines+=['```','','Additional AH provider aggregates (14):','','```']
provider=[r['ticker']for r in extras if r['price_evidence_kind']=='PROVIDER_AH_AGGREGATE']
for i in range(0,len(provider),10):lines.append(' '.join(provider[i:i+10]))
lines+=['```','','Cached raw AH price diagnostics (9; cache replay only, not confirmed eligible touches):','','```']
raw=[r['ticker']for r in extras if r['price_evidence_kind']!='PROVIDER_AH_AGGREGATE'];lines+=[' '.join(raw),'```','',
    'These nine have actual cached raw-price minute highs >=1.10×P0 but lack corresponding provider final AH OHLC confirmation. They remain explicit diagnostic candidates because final bars can remove corrected/cancelled prices, and raw highs can also come from odd lots or other ineligible conditions. All nine already have complete caches and require no new REST acquisition. Their eligibility is not assumed; the approval-gated replay will classify them as verified, unverified or rejected. This keeps available evidence without advertising raw prints as eligible signals.', '',
    '## Research scope and historical gates','',
    'The restored frozen trading cycle begins at Nov12 16:00 ET. AH: (16:00,20:00) Nov12; PRE: [04:00,09:30) Nov13; RTH: [09:30,16:00] Nov13. Overnight 20:00–04:00 is unobserved. P0 is the frozen unadjusted provider daily close on Nov12, not Nov13 close or an AH last print. The calendar-day Nov13-only interpretation is superseded.', '',
    'All 270 submitted ticker strings are unique and matched the historical reference exactly, including NMZr. Security type was read from historical reference, never inferred from W/WS/R suffixes. Known exclusion takes priority; otherwise missing evidence produces UNRESOLVED. Among excluded rows, actual types are 65 WARRANT, 51 CS failing other gates, 9 ADRC, 6 ETF, 2 RIGHT and 1 FUND. The full CSV gives exchange, type, P0, current float, source locators and reasons for every row.', '',
    'PASS requires historical XNAS/XASE/XNYS, CS, 0<P0<=3, original identity/currency/corporate-action/continuity gates, and 100K–15M current float proxy shares. Float is explicitly retrospective; the retained snapshot was retrieved after the study date and does not establish historical PIT float eligibility. Unknown float is never replaced with shares outstanding or inferred from names. All 79 seed PASS rows independently reproduce the supplied Daily13 high >=1.10×P0 condition in the current unadjusted grouped response.', '',
    '## AH discovery coverage','',
    'The historical-quality/current-proxy pool contains 394 unique securities. Removing the 79 seed PASS identities leaves 315 outside-seed AH opportunities. All 315 have explicit AH screening dispositions: 202 aggregate summaries reused from the immutable existing REST caches, plus 113 targeted AH-only REST aggregate queries. The 113 include 16 raw-cache positive cases checked against provider aggregates. No full-universe 885 Tick or aggregate loop was resumed.', '',
    'AH-only REST requests use adjusted=false, one-minute bars, Nov12 16:00 through 19:59:59.999 ET, sort ascending and limit 50,000 (well above the 240 base minutes). Historical complete Tick caches can supply conservative raw minute-high negatives. Raw positives are retained separately and checked against provider OHLC. Explicit EMPTY connector responses are retained as zero returned aggregate bars; they are not called verified zero-trade streams. Initial empty-message parser errors were resolved offline from the captured responses, without redownloading.', '',
    'Every additional row identifies its P0, 1.10 threshold, AH price high, crossing-minute start in ET/UTC, provider/raw evidence kind and source hash. Aggregate timestamps identify minute intervals, not the eventual exact SIP First Touch time. The comparison with Nov13 Daily High explains why each additional ticker was absent from the seed; a missing seed is never silently explained by an invented reason.', '',
    'Daily bar prices do not reliably discover Form T extended-session highs; minute AH/PRE bars treat Form T differently. See [Massive’s Form T and daily/minute distinction](https://massive.com/knowledge-base/article/does-a-form-t-trade-update-a-pre-market-minute-bars-high-low-open-and-close). Therefore Daily13 high alone is not cycle coverage proof. The requested supplement here is AH-only: PRE-only movers outside the seed that never crossed during AH remain a discovery limitation, so this manifest is not represented as a mathematically exhaustive whole-universe cycle census.', '',
    'HTCR is a concrete seed-reconciliation boundary case: P0=1.34, threshold=1.474, Daily13 high=1.474. The inclusive Decimal rule qualifies it, although it is absent from the supplied 270 names. The source does not establish why it was omitted; no floating-point or data-vintage cause is asserted.', '',
    '## Approval and subsequent execution','',
    'No Tick acquisition is authorized yet. The broker checks a pending user-approval lock and a hash-bound ticker whitelist. Once the user approves this explicit manifest, only these identities may resume Tick requests; complete caches are reused and partial streams resume their exact next cursors. No automatic additions are allowed. Any change to the approved list requires a revised manifest.', '',
    'After approval, replay will use unchanged sip-first-touch-v1 rules: Decimal threshold, exact SIP ordering/ties, positive decimal size/price, participant delay checks, frozen condition eligibility including Form T/odd lots, and correction/original-state reconstruction. One primary event per security/cycle is retained. Verified observed-window touches, unverified prior/coverage cases and rejected candidates will be separate. PRE/RTH full-cycle-first statuses retain the overnight limitation. No first-touch prices/times have been fabricated from minute bars.', '',
    'All prior M1–M5/005.1 research artifacts and frozen policies remain unchanged. Only retained reference metadata and newly authorized data for this single exploratory cycle are used; no pre-existing holdout tick/cohort results or additional research cycles are opened. No S3 data were downloaded. Raw data stay local; this package versions the reproducible gate code and compact review artifacts.', '',
    'Reproduce the review: `.venv/bin/python -m market_lab.manifest270 prepare`; run `scripts/manifest270_ah_batch.js` only for pending AH aggregate requests; `.venv/bin/python -m market_lab.manifest270 build`; `PYTHONPATH=. .venv/bin/python scripts/manifest270_report.py`. The old full-universe Tick broker cannot resume while approval is pending.','']
Path('docs/research/2026-11-13-final-candidate-manifest.md').write_text('\n'.join(lines))
write_json(REPORT/'artifact-hashes.json',{p.name:file_hash(p)for p in sorted(REPORT.iterdir())if p.is_file()and p.name!='artifact-hashes.json'})
print(json.dumps(s,indent=2))
