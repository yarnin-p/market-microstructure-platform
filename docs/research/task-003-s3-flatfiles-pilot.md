# TASK 003-S3 — Massive Flat Files & Confirmation Revalidation

Run `m3-s3-pilot-20261116-v1` · baseline `eb95502` · branch `feat/task-003-s3-flatfiles`

**Overall: CONDITIONAL; technical validation PASS.** ทดลองจริงเฉพาะ2 source dates โดยเก็บ risk set40ไว้ครบ ไม่เปิด holdout ไม่แก้ TASK005.1 และไม่ซื้อ subscription เพิ่ม

## การเข้าถึงและ daily cache

ใช้ S3 clientโดยตรงเนื่องจากconnectorเดิมรองรับREST สำหรับS3 endpoint `https://files.massive.com`, bucket `flatfiles` ด้วย credentials ที่ runtime ไม่บันทึกใน Git ตรวจ HEAD7 objects ก่อนตรึง pilot เลือก May28/29 จากลำดับ audit cases เดิม ไม่เลือกตามผลตอบแทน ใช้ quote2ไฟล์และtrade1ไฟล์ รวม16,890,044,044 compressed bytes

| Dataset/date | Compressed bytes | SHA256 | LastModified |
|---|---:|---|---|
| quotes / 2026-05-28 | 6,534,615,098 | `aea61ef7559b6df43dfa0b2d4515137954b8c87af66eb9a910fd18b87caf5704` | 2026-05-29T04:42:54+00:00 |
| quotes / 2026-05-29 | 6,869,823,802 | `3022fc163a0b88eee04f1f394d1c85c6701cf925df02dbcb86faf628910d2734` | 2026-05-30T04:49:02+00:00 |
| trades / 2026-05-28 | 3,485,605,144 | `f98b14598f1624eca78241ebfc3b3f94556c3ac2ab2bcad84fdcd775d7ddc5a3` | 2026-05-29T04:33:13+00:00 |

Source identity เก็บ key,size,ETag,LastModified,download timestamp,SHA256,local path และpost-download HEAD verification โดยไม่ใช้ multipart ETag เป็น MD5 ชุดใหม่ที่sourceเปลี่ยนจะได้snapshotใหม่ ไม่เขียนทับชุดเก่า

พบ IncompleteReadError ในหนึ่ง byte range: หยุดเป็น INCOMPLETE เก็บ checkpoint และ error เดิม แล้วresumeส่วนที่ขาดภายในงบเดิม มีconservative8MiB chargeสำหรับข้อมูลที่อาจเข้ามาก่อน read exception ไม่ถือว่าครบจน assembled length,identity และSHAผ่าน Operational revisionv2เพิ่มattempt-state markersเพื่อให้resume ingestionได้ ไม่เปลี่ยน quote-state/confirmation semantics

## Streaming ingestion / date alignment

| Source | Raw CSV rows | Selected rows | Decoded upper bound | Min SIP | Max SIP | Outside UTC date |
|---|---:|---:|---:|---:|---:|---:|
| quotes/2026-05-28 | 365,566,423 | 341,972 | 71,602,575,380 | 1779946201011662214 | 1780012800465919489 | 14500 |
| quotes/2026-05-29 | 384,477,250 | 589,657 | 75,358,970,808 | 1780032601012328898 | 1780099200455962602 | 14230 |
| trades/2026-05-28 | 148,515,202 | 330,827 | 33,904,185,286 | 1779955200000606416 | 1780012809190924220 | 8508 |

หลังเก็บ initial Arrow partial attemptไว้ ใช้DuckDB relationอ่านgzipแบบstreamingArrowbatches65,536rows กรอง original historical tickers เก็บทุก raw field เป็นstringและtimestamp19digitsเป็นint64 ไม่แปลงผ่านfloat แบ่งParquetตามdate/tickerพร้อมzero-row partitions ใช้DuckDBอ่านโดยไม่ materialize market-wide CSV Completed sources/extractionsใช้ซ้ำ; incomplete gzip attemptsเก็บแยกและเริ่มscanเฉพาะไฟล์ที่ยังไม่ครบ ไม่อ้างว่าgzipseekได้โดยไม่replayprefix

Source filename/time alignment ตรวจจากทุกrecordและเทียบกับclock/sessionเดิม พบclosingSIPspillข้ามUTC date จึงแก้unsupportedUTC-onlyadmissionเป็นprovider04–20ETโดยมีversionedaddendumก่อนS3signals ไม่ขยายcoverageไปยังspill/admininterval และไม่เลื่อนหรือลบtimestamp Stocks sourceครอบคลุมPRE/RTH/AHตามผู้ให้บริการ ไม่ใช่หลักฐาน24-hour continuous coverage AHอาจเป็นวันก่อนcycleและFriday AHอาจอยู่ในMonday cycle ดังนั้นsource-day denominatorไม่เท่ากับcycle-date denominator

## REST/S3 frozen cases

| Case | Record reconciliation | REST / S3 rows | State at target |
|---|---|---:|---|
| BIVI | REST_AND_S3_RECONCILED | 0 / 0 | QUOTE_STATE_INVALID_OR_STALE |
| ATNM | SOURCE_DISAGREEMENT | 4 / 4 | QUOTE_STATE_INVALID_OR_STALE |
| EVTV | SOURCE_COVERAGE_UNKNOWN | 80 / None | SOURCE_COVERAGE_UNKNOWN |
| FFAI | SOURCE_COVERAGE_UNKNOWN | 4 / None | SOURCE_COVERAGE_UNKNOWN |
| QRHC | SOURCE_COVERAGE_UNKNOWN | 6 / None | SOURCE_COVERAGE_UNKNOWN |

ครบทั้ง5caseในรายงาน แต่EVTV/FFAI/QRHCอยู่นอก2วันpilotจึงUNKNOWN ไม่ใช่no-updateหรือfailure ส่วนoverlapเปรียบเทียบinteger SIP/PT/sequence,bid/ask price,size,exchange,conditions,indicators,tape,TRF พร้อมลำดับและduplicates พยานbefore/inside/afterwindowอยู่ในreconciliation.json โดยfollowingquoteไม่ถูกใช้ย้อนตัดสินอดีต

Integrity regressionพบว่าDuckDBยอมรับgzipที่CRCผิด จึงบังคับindependent gzip CRC/length passก่อนadmitข้อมูล มีunit testsครอบคลุมCRC-mismatchและtruncation Exactdecodedbytesยืนยันโดยcounterในgzip-integrity.json ไม่ใช้conservativeCSVupperเป็นexactsize

Empty REST ไม่พิสูจน์provider loss และS3/RESTเป็นช่องทางของผู้ให้บริการเดียวกัน ไม่ใช่independent market-data sources ข้อมูลผิดเงื่อนไข/correctedถูกเก็บและinvalidate current state ไม่ย้อนเลือกearlier valid quote

ATNM strictdisagreementแจกแจงรายfieldในreconciliation.json: ถ้าcore_fields_reconciled_excluding_optional_trf_diagnostic=true หมายถึงcorequotesตรงกัน โดยTRFmissing/zeroยังเก็บเป็นstrictdifference ไม่ตัดfieldออกเพื่อทำให้ผ่าน ทั้งสองdeliveryยังมีcorrectedconditionsเดียวกันจึงไม่กลายเป็นvalidNBBOโดยอัตโนมัติ

Bounded BIVI trade reconciliation: `{"ticker": "BIVI", "status": "REST_AND_S3_RECONCILED", "overlap_start_ns": 1779955199999999999, "overlap_end_ns": 1779998400000000000, "rest_records": 644, "s3_records": 644, "rest_only_count": 0, "s3_only_count": 0, "source_audit": {"raw": 644, "unique": 644, "duplicates": 0}, "shared_fields": ["sip_timestamp", "participant_timestamp", "sequence_number", "exchange", "price", "size", "conditions"], "correction_metadata_comparison": {"0": 644}, "limitation": "Shared-field reconciliation only; no replacement of original REST correction reconstruction or trade outcomes."}` ไม่เปลี่ยนtrade/correction evidenceเดิม

## C0/C1 reproduction และ C2 comparison

ตรวจ original C0/C1/C2 signal/outcomes 240 checks และQA rows **640** แถวตรงเดิมทุกแถว ทั้ง40 initial eventsและ2condition policies รวมC1 counted/observed/session-boundและD60sensitivities

Original primary C2 baselineทั้ง40คือconfirmed6,unconfirmed24,insufficient10 ตารางต่อไปไม่ใช้เฉพาะผู้รอดจนconfirmเป็นdenominator และแยกsubsetที่sourceครบออกจากnonpilotที่ไม่มีข้อมูล

| Policy | Initial | S3 source-covered | Status all40 | Baseline on covered subset | S3 on covered subset |
|---|---:|---:|---|---|---|
| C2_S3_FROZEN_RULE | 40 | 12 | {'INSUFFICIENT_DATA': 33, 'UNCONFIRMED': 6, 'CONFIRMED': 1} | {'INSUFFICIENT_DATA': 5, 'UNCONFIRMED': 6, 'CONFIRMED': 1} | {'INSUFFICIENT_DATA': 5, 'UNCONFIRMED': 6, 'CONFIRMED': 1} |
| C2_S3_STATE_BASED | 40 | 12 | {'INSUFFICIENT_DATA': 33, 'UNCONFIRMED': 4, 'CONFIRMED': 3} | {'INSUFFICIENT_DATA': 5, 'UNCONFIRMED': 6, 'CONFIRMED': 1} | {'INSUFFICIENT_DATA': 5, 'UNCONFIRMED': 4, 'CONFIRMED': 3} |

`C2_S3_FROZEN_RULE` เรียก original C2 unchanged:bid>=originalthreshold,span>=10s,5sfreshness/gap,60sdeadline ส่วน `C2_S3_STATE_BASED_V1` เป็นsensitivityที่ตรึงก่อนoutcomes:causal timer10s,currentvalidstate age<=60s,<=60sdeadline,resetเมื่อinvalid/below/sessionเปลี่ยน ค่า5sfreshnessยังรายงานแยก ไม่ใช่การเปลี่ยนruleเดิมเพื่อให้confirmมากขึ้น

No-forward-fill across invalidation/session/unknown coverage; same-SIP eventsมาก่อนtimerและsame-SIP+sequenceที่ขัดกันเป็นambiguous Testยืนยันว่าfuture invalidationไม่ย้อนเปลี่ยนsignalอดีต Timeline40eventsอยู่ในevent-level-results.json ส่วนnonpilotทั้งหมดยังINSUFFICIENT_DATAอย่างชัดเจน

| Policy | Covered classification changes | Changed signal clock/price | Delay median s | Fresh ask/bid mark pairs |
|---|---:|---:|---:|---:|
| C2_S3_FROZEN_RULE | 0 | 0 | 10.052383551 | 4 |
| C2_S3_STATE_BASED | 2 | 3 | 16.153197229 | 7 |

Change-explanations.jsonตรวจ48coveredcomparisons ไม่พบunexplainedfrozen-rulechange; frozen-ruleตรงRESTทั้ง12events ในขณะที่state-policyให้2additionalconfirmationsและ1earlier/differentclockจากนิยามที่แยกไว้ ไม่ใช่การแก้ผลoriginalC2

Per-event evidenceเก็บold/new signals,timestamps,delays,state age/freshness,source rows,waiting price change,own-clock/common-clock5/15/30/60m,MFE/MAE,barriers/censoring และquote marksครบ Recompute trade outcomesเฉพาะsignal status/time/priceเปลี่ยน ที่เหมือนเดิมreuse frozen outcomesพร้อมprovenance Cohorts/weights/SECmetadataทั้ง40joinกลับจากbaselineไว้ในfrozen_risk_metadata ไม่มีcurrent-float refresh

Quote entry ask/exit bidใช้เฉพาะcausal fresh-valid endpointsและรายงานtrade-pathstatusแยก ตัวเลขmarkไม่ใช่fills,realizedP&Lหรือprofitability State supportที่age>5sอาจconfirmstate-sensitivityได้แต่ไม่ผ่านfresh execution-mark gate ไม่มีการเพิ่มliquidityหรือqueueevidenceขึ้นเอง

## Resource / integrity results

S3 attempts **28 / 32**, charged received bytes **16,931,987,084 / 21,474,836,480**, active acquisition seconds **3164.8 / 3600**.
CSV decoded upper **180,865,731,474**, total decoded-work upper including CRC/recovery/benchmarks **180,346,692,282**, last-resume conservative transfer/ingest peak RSS **488,308,736 bytes**, current local storage **16,938,947,880 bytes**, conservative staging upper **23,808,771,682 bytes** ต่ำกว่าdisk ceiling; RSSตัวเลขนี้ครอบคลุมlastresumeเท่านั้น Earlierquote-extractioncombinedRSSไม่ถูกpersistจึงยังไม่certifywhole-runmemorybudget แม้per-processguardsผ่าน Implementstricter1.5GiBparsercapและpersistentmetricsแล้ว ไม่โหลดmarket-wideCSVเข้าRAM.
Tests **286 passed** (84 existing warnings); covered signal reruns **48** และstate prefix-causality checks **6** ผ่าน Prior artifacts **13,999** hashes unchanged.

## Readiness / migration

**CONDITIONAL** สำหรับการขยาย:เทคนิคcache/parser/replayผ่าน แต่2source datesไม่validatecomplete40-eventdevelopment sampleหรือทั้ง5auditdates ต้องอธิบายsource discrepanciesและcoverageก่อนใช้สัญญาณเป็นผลวิจัยต่อ S3snapshotอาจเป็นrevised historical content; replayพิสูจน์SIP-causalityภายในsnapshot ไม่รับรองpublication-vintage PITหรือindependent exchange-feed truth

เตรียมproposalแยกสำหรับ11source datesที่จำเป็นต่อoriginal10cycles รวมpreceding AH, reuse2pilotfilesและไม่เกิน9additional quote dates แต่ยังไม่อนุมัติหรือดาวน์โหลดเพิ่ม เอกสาร `docs/plans/TASK-003-S3-development-expansion-proposal.md` ระบุงบและgatesแยก ไม่แตะ120cyclesหรือholdout TASK005.1 statistical clearanceยังBLOCKEDและไม่ถูกแก้ในงานนี้

## Reproduction

ติดตั้ง optional dependency `pip install -e ".[flatfiles]"`; กำหนดMASSIVE_S3_ACCESS_KEY_ID/MASSIVE_S3_SECRET_ACCESS_KEYหรือprivate runtime credentials file ห้ามใส่keysในconfig

ใช้new run IDแล้วfreeze metadata/selection/budgetsก่อน `market_lab.flatfile_cache probe`, `market_lab.flatfile_transfer`, `market_lab.flatfile_integrity`, `market_lab.flatfile_ingest_duckdb --watch`, `market_lab.flatfile_revalidation baseline`, `market_lab.flatfile_revalidation revalidate`, `market_lab.flatfile_reconcile`, `scripts.validate_flatfile_pilot`, pytest และpublisherนี้ Existing completeddaily cachesใช้ซ้ำได้โดยตรวจhashก่อน ไม่เขียนทับรายงานที่ตีพิมพ์แล้ว

Official references: [S3 quickstart](https://massive.com/docs/flat-files/quickstart), [Stocks sessions](https://massive.com/docs/flat-files/stocks/overview), [Quotes](https://massive.com/docs/flat-files/stocks/quotes), [Trades](https://massive.com/docs/flat-files/stocks/trades), [timestamp units](https://massive.com/knowledge-base/article/what-timezone-are-massives-timestamps-in). ตัวเลขผลจริงอ้างจากlocal immutable evidence ไม่ได้อนุมานcoverageจากคำโฆษณาของผู้ให้บริการ
