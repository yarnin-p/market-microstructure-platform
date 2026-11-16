# Trading Cycle 2026-11-13 — 270 Seed + AH Manifest Review

ผลหลังอนุมัติและตรวจ Tick: [First Touch results](2026-11-13-first-touch-results.md).

Run `manifest270-ah-20261113-20261116-v3` — **AWAITING USER APPROVAL**.

## Mandatory gate before Tick resume

| Item | Observed count |
|---|---:|
| Daily Aggregate Candidates | 270 |
| Historical Universe PASS | 79 |
| Historical Universe EXCLUDED | 134 |
| Historical Universe UNRESOLVED | 57 |
| Additional AH price candidates | 23 |
| — provider minute-aggregate evidence | 14 |
| — cached raw minute-high diagnostics | 9 |
| Final proposed Tick Acquisition Manifest | 102 |
| Already cached completely | 47 |
| Additional REST calls required | **at least 55** |

The exact remaining REST page/call total cannot be known before pagination. Each of the 55 missing security streams needs at least one initial request; further pages are retained and followed within bounded batches. No extra Tick requests or First-Touch replay were started after the user’s stop/approval instruction. The 559 previously captured Tick pages and their hashes remain unchanged. No caches/checkpoints were deleted.

[Final manifest, every ticker and cache disposition](../../reports/manifest270-ah-20261113-20261116-v3/final-acquisition-manifest.csv) · [Full 270-row gate audit](../../reports/manifest270-ah-20261113-20261116-v3/seed-270-universe-audit.csv) · [Additional AH price/time/P0 evidence](../../reports/manifest270-ah-20261113-20261116-v3/additional-ah-candidates.csv) · [AH discovery coverage](../../reports/manifest270-ah-20261113-20261116-v3/ah-discovery-coverage.csv) · [Integrity](../../reports/manifest270-ah-20261113-20261116-v3/integrity.json).

## Final proposed list — all 102 tickers

Seed PASS (79):

```
AARD ACTU AEI AIMD AKAN ALGS AMST APUS ATXG AUUD
BCDA BCG BIRD BJDX BOF CDIO CHGA CIIT CJMB CNET
CNSY COPR DWSN EDVA ENSC FCUV FEMY FIEE GOAI GUTS
GWAV GYGY IMCC IZEA MEDS MITQ MKZR MODD MTVA MYSE
NAII NCRA NHTC NORD NXB NXTS ODYS ONFO OPNW PARA
PAVM PODC PWCM QCLS QRHC RAIN REED RENX SCKT SEAT
SGLY SHFS SHIM SLND SMSI SNAL SNWV SWRD TGL TOMZ
UONEK VIDA VTSI WKSP WVVI XBIO XELB XRTX ZSTK
```

Additional AH provider aggregates (14):

```
AEON APRE CAPS CDT FEAM GP GXAI KIDZ LSF NOMA
OGEN PFSA SPRU XXII
```

Cached raw AH price diagnostics (9; cache replay only, not confirmed eligible touches):

```
AIRI AMCI BNKK CABR CITR CRVO ERNA GBR HTCR
```

These nine have actual cached raw-price minute highs >=1.10×P0 but lack corresponding provider final AH OHLC confirmation. They remain explicit diagnostic candidates because final bars can remove corrected/cancelled prices, and raw highs can also come from odd lots or other ineligible conditions. All nine already have complete caches and require no new REST acquisition. Their eligibility is not assumed; the approval-gated replay will classify them as verified, unverified or rejected. This keeps available evidence without advertising raw prints as eligible signals.

## Research scope and historical gates

The restored frozen trading cycle begins at Nov12 16:00 ET. AH: (16:00,20:00) Nov12; PRE: [04:00,09:30) Nov13; RTH: [09:30,16:00] Nov13. Overnight 20:00–04:00 is unobserved. P0 is the frozen unadjusted provider daily close on Nov12, not Nov13 close or an AH last print. The calendar-day Nov13-only interpretation is superseded.

All 270 submitted ticker strings are unique and matched the historical reference exactly, including NMZr. Security type was read from historical reference, never inferred from W/WS/R suffixes. Known exclusion takes priority; otherwise missing evidence produces UNRESOLVED. Among excluded rows, actual types are 65 WARRANT, 51 CS failing other gates, 9 ADRC, 6 ETF, 2 RIGHT and 1 FUND. The full CSV gives exchange, type, P0, current float, source locators and reasons for every row.

PASS requires historical XNAS/XASE/XNYS, CS, 0<P0<=3, original identity/currency/corporate-action/continuity gates, and 100K–15M current float proxy shares. Float is explicitly retrospective; the retained snapshot was retrieved after the study date and does not establish historical PIT float eligibility. Unknown float is never replaced with shares outstanding or inferred from names. All 79 seed PASS rows independently reproduce the supplied Daily13 high >=1.10×P0 condition in the current unadjusted grouped response.

## AH discovery coverage

The historical-quality/current-proxy pool contains 394 unique securities. Removing the 79 seed PASS identities leaves 315 outside-seed AH opportunities. All 315 have explicit AH screening dispositions: 202 aggregate summaries reused from the immutable existing REST caches, plus 113 targeted AH-only REST aggregate queries. The 113 include 16 raw-cache positive cases checked against provider aggregates. No full-universe 885 Tick or aggregate loop was resumed.

AH-only REST requests use adjusted=false, one-minute bars, Nov12 16:00 through 19:59:59.999 ET, sort ascending and limit 50,000 (well above the 240 base minutes). Historical complete Tick caches can supply conservative raw minute-high negatives. Raw positives are retained separately and checked against provider OHLC. Explicit EMPTY connector responses are retained as zero returned aggregate bars; they are not called verified zero-trade streams. Initial empty-message parser errors were resolved offline from the captured responses, without redownloading.

Every additional row identifies its P0, 1.10 threshold, AH price high, crossing-minute start in ET/UTC, provider/raw evidence kind and source hash. Aggregate timestamps identify minute intervals, not the eventual exact SIP First Touch time. The comparison with Nov13 Daily High explains why each additional ticker was absent from the seed; a missing seed is never silently explained by an invented reason.

Daily bar prices do not reliably discover Form T extended-session highs; minute AH/PRE bars treat Form T differently. See [Massive’s Form T and daily/minute distinction](https://massive.com/knowledge-base/article/does-a-form-t-trade-update-a-pre-market-minute-bars-high-low-open-and-close). Therefore Daily13 high alone is not cycle coverage proof. The requested supplement here is AH-only: PRE-only movers outside the seed that never crossed during AH remain a discovery limitation, so this manifest is not represented as a mathematically exhaustive whole-universe cycle census.

HTCR is a concrete seed-reconciliation boundary case: P0=1.34, threshold=1.474, Daily13 high=1.474. The inclusive Decimal rule qualifies it, although it is absent from the supplied 270 names. The source does not establish why it was omitted; no floating-point or data-vintage cause is asserted.

## Approval and subsequent execution

No Tick acquisition is authorized yet. The broker checks a pending user-approval lock and a hash-bound ticker whitelist. Once the user approves this explicit manifest, only these identities may resume Tick requests; complete caches are reused and partial streams resume their exact next cursors. No automatic additions are allowed. Any change to the approved list requires a revised manifest.

After approval, replay will use unchanged sip-first-touch-v1 rules: Decimal threshold, exact SIP ordering/ties, positive decimal size/price, participant delay checks, frozen condition eligibility including Form T/odd lots, and correction/original-state reconstruction. One primary event per security/cycle is retained. Verified observed-window touches, unverified prior/coverage cases and rejected candidates will be separate. PRE/RTH full-cycle-first statuses retain the overnight limitation. No first-touch prices/times have been fabricated from minute bars.

All prior M1–M5/005.1 research artifacts and frozen policies remain unchanged. Only retained reference metadata and newly authorized data for this single exploratory cycle are used; no pre-existing holdout tick/cohort results or additional research cycles are opened. No S3 data were downloaded. Raw data stay local; this package versions the reproducible gate code and compact review artifacts.

Reproduce the review: `.venv/bin/python -m market_lab.manifest270 prepare`; run `scripts/manifest270_ah_batch.js` only for pending AH aggregate requests; `.venv/bin/python -m market_lab.manifest270 build`; `PYTHONPATH=. .venv/bin/python scripts/manifest270_report.py`. The old full-universe Tick broker cannot resume while approval is pending.
