# TASK 001 แผนวิศวกรรม M1 และการตรวจความเป็นไปได้

วันที่ 14 พฤศจิกายน 2026 · สถานะ `PLAN_READY_FOR_REVIEW` · ไม่ใช่หลักฐานว่า M1 ผ่าน validation

แผนนี้ใช้ [Master Research & Engineering Plan V0.1](../../specs/master-research-engineering-plan-v0.1.md) ที่ผู้ใช้แนบเป็นข้อกำหนดของงานรอบนี้ เป้าหมายคือเตรียม Historical Universe and Massive Data Audit ให้ตรวจสอบย้อนหลังได้ ก่อนเริ่ม tick replay หรือวิจัย continuation ไม่มีการเปลี่ยน research objectives, สูตร +10%, ช่วง float หรือการแบ่ง 80/40

ข้อสรุปทางวิศวกรรม: historical reference, daily prices, trades และ NBBO มี documented API รองรับ แต่ **Massive ไม่ให้ historical float** จึงยังรับรอง primary point-in-time micro-float universe ไม่ได้ การมี pipeline ที่รันจบต้องแยกจากการมีข้อมูลพร้อมสำหรับ primary research

## 1. ขอบเขตและสถานะไฟล์ใน workspace

TASK 001 รอบนี้ส่งมอบ planning package, documentation audit และ calendar feasibility check ก่อน implementation ตามประโยคท้ายของ specification: “Begin with a technically validated plan for M1, then await implementation authorization.”

ณ เวลา intake โฟลเดอร์มี `market_lab/`, tests, schemas, README และ reports ที่ยังไม่ commit อยู่แล้ว จึงเก็บไว้ทั้งหมด ไม่ถือว่าเป็น greenfield directory ว่าง และไม่รับรองผลของไฟล์เหล่านั้นจากชื่อหรือข้อความในรายงาน ไม่กู้คืนงานจาก chat หรือ repository อื่น

เอกสารเดิม `docs/specs/TASK-001-exchange-restriction.md` บันทึกการตัดสินใจเรื่อง CS-only, anchor eligibility และ unresolved float ไว้ แต่ยังไม่ได้ตรวจ provenance ของการอนุมัติเหล่านั้นในงานรอบนี้ ส่วน `standardized-research-results-user-contract.md` กำหนด mandatory ZIP ซึ่งต่างจาก master ที่เพิ่งแนบซึ่งกำหนด optional export จึงแสดงเป็นประเด็นให้ Research Lead ยืนยันก่อนเปลี่ยน behavior ของ implementation เดิม

ไม่เขียนทับ code หรือผลรันเดิม การตรวจ implementation หลังอนุมัติจะเป็น requirement reconciliation กับ source ปัจจุบัน ไม่ใช่การรื้อสร้างใหม่โดยอัตโนมัติ

## 2. Proposed architecture

ใช้ Python สำหรับ orchestration; เก็บ immutable source responses ใน local object directories; normalized evidence เป็น Parquet/ZSTD; DuckDB ทำ analytical views/query; `exchange_calendars` และ `zoneinfo` สำหรับเวลา; pytest สำหรับ unit/integration tests ส่วน SciPy/statsmodels อยู่ใน M5 และ Polars เพิ่มเมื่อมี workload ที่พิสูจน์ประโยชน์

```text
Versioned spec + approved research policy + immutable run config
                     ↓
Calendar → historical discovery → identity / listing evidence
                     ↓                         ↓
Daily reference closes + corporate actions + float evidence
                     ↓
Per-gate universe decisions → quality validation → run manifest
                     ↓
Parquet evidence + DuckDB views → bounded local queries
                     ↓
M2 replay → M3 baseline → M4 confirmation → M5 validation → M6 gateway
```

แยกข้อมูล 7 ส่วน: historical market data, eligibility, event ledger, replay evidence, experiment outcomes, run metadata และ quality findings ไม่รวม event-level evidence เหลือเพียง summary และไม่คัดลอก raw tick dataset ต่อ experiment

Research Gateway ในอนาคตอ่าน views/partitions เดียวกันได้ โดยใช้ authentication, allowlisted read-only query templates, pagination, timeout, row/byte limits และ query audit; M1 ออกแบบ contracts เท่านั้น ไม่สร้าง MCP Server

## 3. File และ module structure ที่เสนอ

ชื่อด้านล่างเป็น target responsibilities ไม่ใช่คำสั่งให้ overwrite modules เดิมหรือยืนยันว่า modules เหล่านี้ implement แล้ว

```text
docs/specs/                         versioned requirements
docs/plans/task-001-m1-v0.1/         แผนนี้และ feasibility evidence
docs/decisions/                     approved decisions + supersession
configs/                           immutable research/run policy
schemas/v1/                        table + manifest contracts
market_lab/
  cli.py                           audit / calendar / universe / validate / query
  api.py                           transport, auth, pagination, retries
  calendar.py                      cycles, boundaries, splits, session labels
  reference.py                     discovery, dated listings, ticker events
  identity.py                      share-class identity and symbol intervals
  closes.py                        P0 evidence and discrepancy checks
  corporate_actions.py             split/dividend evidence and flags
  float_evidence.py                 provenance, validity, cohort classification
  eligibility.py                   pure per-gate decisions
  storage.py                       atomic writes, locks, hashes, checkpoints
  datasets.py                      immutable dataset catalog and partitions
  quality.py                       coverage and integrity findings
  provenance.py                    run identity and evidence lineage
  queries.py                       complete aggregation + bounded extracts
tests/unit/                        offline deterministic cases
tests/integration/                 replayed API fixtures + storage/restart
tests/live/                        bounded opt-in entitlement/coverage audit
data/                              ignored; configurable external data root
reports/<run_id>/                   compact audit outputs
```

Dependency versions จะ lock หลัง compatibility audit; feasibility check รอบนี้ใช้ `exchange-calendars==4.13.2` ที่มีอยู่แล้ว ไม่อ้างว่าได้เลือกหรือทดสอบ dependencies ทั้ง stack

## 4. Massive API feasibility

ตรวจ official documentation และ connector endpoint discovery วันที่ 2026-11-14 การตรวจนี้ **ไม่ใช่ authenticated data request** และยังไม่ยืนยัน entitlement/coverage ของบัญชีจริง

| หน้าที่ | Endpoint | การใช้ใน M1 และข้อจำกัด |
| --- | --- | --- |
| Historical discovery | `/v3/reference/tickers` | ระบุ `market=stocks`, `date`, `active=true`, `limit=1000`; เก็บ pagination ครบและรายการ inactive สำหรับ audit แบบเจาะจง |
| Dated details | `/v3/reference/tickers/{ticker}` | ขอ `date` ชัดเจนเพื่อ enrich identifiers/listing; ไม่ใช้ข้อมูลวันนี้เติมย้อนหลัง |
| Types / listing mapping | `/v3/reference/tickers/types`, `/v3/reference/exchanges` | เก็บ dictionary/version/hash; listing MIC แยกจาก execution exchange IDs |
| Reference close | `/v2/aggs/grouped/locale/us/market/stocks/{date}` | ใช้ `adjusted=false`; ดึงรายวันสำหรับ anchor dates; null/missing ต้องมี finding |
| Close cross-check | `/v1/open-close/{stocksTicker}/{date}` | `adjusted=false`, sample ticker/date ที่ pre-register; cross-check ไม่ใช่ independent vendor validation |
| Float | `/stocks/vX/float` | latest-only; ใช้ได้เฉพาะ current proxy audit ไม่ใช่ historical verification |
| Corporate actions | `/stocks/v1/splits`, `/stocks/v1/dividends` | เก็บ execution/ex-dividend dates, ratios และ provenance; endpoint รุ่นใหม่ต้อง probe schema จริง |
| Symbol history | `/vX/reference/tickers/{id}/events` | ช่วย rename audit; absence/error ไม่พิสูจน์ว่าไม่มี corporate event |
| Trade eligibility dictionary | `/v3/reference/conditions` | snapshot condition codes; aggregate update rules ไม่เท่ากับ approved research eligibility |
| Future replay feasibility | `/v3/trades/{stockTicker}`, `/v3/quotes/{stockTicker}` | timestamp ranges, pagination, ns timestamps; M1 ใช้ได้เฉพาะ bounded probe หลังอนุมัติ |

Historical ticker lists เป็น effective-dated reconstruction ที่ provider ดูแล ณ เวลาดึง ไม่ใช่ archived publication snapshot; ไม่มี identifier เดียวรับรอง continuity ทุกเหตุการณ์ ใช้ share-class identity evidence และ ambiguity flags ห้าม join ด้วย CIK อย่างเดียวเพราะหนึ่ง issuer มีหลาย share classes ได้ [Massive security master](https://massive.com/knowledge-base/article/does-massive-have-a-downloadable-security-master)

Float endpoint ไม่มี historical lookup และ unknown date parameter อาจถูกละเลย จึงต้องมี request-parameter allowlist และป้องกันการเลื่อน current float เป็น verified historical float [Massive historical float](https://massive.com/knowledge-base/article/does-massive-have-historical-float-data)

NBBO เป็น top-of-book ไม่ใช่ full depth; documented Stocks Advanced access ไม่รับรองว่าบัญชีที่เชื่อมต่อมีสิทธิ์หรือทุก security/session มีข้อมูล [Trades](https://massive.com/docs/rest/stocks/trades-quotes/trades), [Quotes](https://massive.com/docs/rest/stocks/trades-quotes/quotes)

## 5. Historical security discovery และ exchange eligibility

1. สร้าง 120 cycles พร้อม anchor session ก่อน cycle แรก รวม 121 RTH session dates
2. Enumerate dated reference ที่ anchor และ cycle dates; ไม่ใช้ survivor list วันนี้เป็นจุดเริ่มต้น และไม่กรอง `type`/`exchange` ก่อนบันทึก evidence เพื่อไม่ให้ missing fields หายจาก audit
3. เก็บ raw ticker, composite/share-class FIGI, CIK, listing/delisting fields, request date และ retrieval timestamp; สร้าง internal `security_id` พร้อม identity status และ evidence links
4. วันที่มี rename/ticker reuse/FIGI change ให้ตรวจ events และ dated details ไม่ถือว่าชื่อเหมือนกันคือหลักทรัพย์เดียวกัน; unresolved identities ยังอยู่ใน audit population แต่ยังไม่รวม primary eligible population
5. ประเมิน primary listing ด้วย explicit versioned mapping ที่เสนอ: `XNAS → NASDAQ`, `XASE → NYSE American (AMEX)`, `XNYS → NYSE` ต้องตรวจ dictionary จริงก่อน activate ห้ามเพิ่มทุก MIC ใต้ operating MIC เดียวกัน
6. Known out-of-scope listing → gate fail; missing/unmapped/contradictory listing → unknown ไม่ใช้ trade execution venue เป็น listing gate
7. เสนอ freeze initial universe ณ previous RTH close และ revalidate identified changes ที่ event time; dated records อย่างเดียวไม่พิสูจน์เวลา intraday หากไม่ชัดให้ unresolved ห้ามใช้ cycle-end information ย้อนเปลี่ยน membership ที่ anchor

Research Lead ต้องยืนยัน CS-only เทียบกับ scope “US micro-float stocks” และ policy anchor/event-time ใน decision table ด้านล่าง discovery เก็บทุกชนิดไว้ก่อนเพื่อไม่สูญเสีย audit denominator

## 6. P0 และ corporate-action conventions

ข้อเสนอ: `P0_raw` เป็น unadjusted provider daily close ของ previous RTH session; `0 < P0 <= 3`; `P_trigger = P0 × 1.10` ใช้ decimal arithmetic ไม่ปัดราคาให้ชน threshold ก่อนเปรียบเทียบ P0 คงที่ตลอด cycle

Daily close เป็น provider aggregate close ตาม trade conditions ยังไม่รับรองว่าเป็น official listing-auction price ต้อง audit เทียบ daily ticker summary และ targeted closing trades รวมกรณี closing print มี SIP timestamp หลัง scheduled close [Daily summary](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary), [Daily trade-condition semantics](https://massive.com/knowledge-base/article/does-a-form-t-trade-update-a-pre-market-minute-bars-high-low-open-and-close)

ไม่ forward-fill วันที่ไม่มี close ไม่ใช้ after-hours close หรือ previous available close ข้าม missing session; เก็บ `reference_close_method`, source record และ quality status

ข้อเสนอ corporate-action policy: ใช้ราคา nominal unadjusted ใน ordinary cycles; cycle ที่มี split/reverse split ระหว่าง anchor กับ end ให้ `CORPORATE_ACTION_UNRESOLVED` และแยกจาก primary analysis จน Research Lead อนุมัติวิธีเทียบราคา ถ้าต้อง normalize ต้องใช้ basis เดียวทั้ง P0 และ ticks โดยไม่ reset P0 กลาง cycle เก็บ raw เสมอ เงินปันผลให้แยก flag/cohort; ไม่ปรับ total-return เอง [Splits](https://massive.com/docs/rest/stocks/corporate-actions/splits)

แยก `scheduled_close`, `reference_observation_time`, `reference_available_at` และ `retrieved_at`: daily bar ที่รู้หลังปิดตลาดอาจไม่ใช่สิ่งที่ผู้เข้าตลาดรู้ ณ anchor จริง จึงต้องติด label retrospective reference และห้ามอ้าง executable signal ก่อนทราบ P0 หากไม่มี available-at evidence

## 7. Historical float policy

เก็บ float evidence แยกจาก shares outstanding และ market-cap/price; ห้ามแทนกันโดยปริยาย

| Cohort | เกณฑ์ evidence | การใช้ |
| --- | --- | --- |
| `VERIFIED_PIT` | source ที่ตรวจสอบได้, measurement/effective time, available-at ไม่เกิน evaluation time, validity policy ที่อนุมัติ | primary analysis เมื่อ gates อื่นผ่าน |
| `HISTORICAL_PROXY` | historical estimate พร้อมวิธีคำนวณและ limitations | แยก exploratory/sensitivity population |
| `CURRENT_PROXY` | latest observation ที่ไม่พิสูจน์ past availability | audit/sensitivity เท่านั้น |
| `UNRESOLVED` | ไม่มี/ขัดแย้ง/เวลาไม่พอ | นับใน coverage; ไม่เติมเลขสมมติ |

เก็บ observation date กับ effective interval แยกกัน ไม่สร้าง validity interval ยาวข้ามเดือนเพียงเพราะมีตัวเลขหนึ่งวัน Staleness/carry-forward และการใช้ filing-based estimate ต้อง Research Lead กำหนด การไม่มี historical float เป็น **data blocker** แม้ software tests ผ่าน

Float threshold รวม endpoints: 100,000 และ 15,000,000 หุ้น หาก float เป็น unknown แต่ price fail ผลรวมเป็น INELIGIBLE ได้ แต่ต้องยังนับ float unknown ใน independent missingness metrics

## 8. 120-cycle calendar และ holdout

ใช้ `America/New_York` ใน business rules; persist UTC timestamps และ ET session dates เก็บ calendar name/version และ materialized schedule hash ไม่ใช้ weekday arithmetic

ผล local feasibility check เมื่อเสนอ `end_date=2026-11-13`:

| รายการ | ช่วง |
| --- | --- |
| Previous anchor สำหรับ cycle แรก | 2026-05-26 RTH close |
| 120 completed cycles | 2026-05-27 ถึง 2026-11-13 |
| Exploration 80 cycles | 2026-05-27 ถึง 2026-09-18 |
| Holdout 40 cycles | 2026-09-21 ถึง 2026-11-13 |

Calendar check ผ่าน session uniqueness/order, 80/40 non-overlap, spring/fall DST, holiday exclusion และ 13:00 ET early-close examples ดู [evidence](evidence/calendar-check.json) และ [reproduction script](evidence/check_calendar.py) เป็นการทดสอบ library โดยตรง ไม่ใช่การรับรอง calendar module เดิม

เสนอ cycle interval `(previous scheduled RTH close, current scheduled RTH close]` แยก session AH/PRE/RTH และ outside-coverage interval ไม่ reset detector ตอนข้าม session ขอบเขต PRE/RTH เช่น 09:30 ให้ belongs-to-RTH อย่างแน่นอน Closing auction/late report ที่ timestamp ข้าม close ต้องมี explicit association policy ก่อน M2/M3

XNYS calendar ให้ regular schedule; ต้อง cross-check XNAS/XASE session exceptions ด้วย official schedules และเก็บ exceptions หลักทรัพย์เฉพาะตัวแยกต่างหาก AH/PRE coverage ไม่ควรเดาจากชื่อ listing venue หรือถือว่าทุก venue ปิด 20:00 ในวัน early close Overnight และ feed gaps เป็น coverage state ไม่ใช่ข้อพิสูจน์ว่าไม่มี trades; halt ต้องมี authoritative market-state evidence ไม่อนุมานจาก zero ticks [NYSE schedule](https://www.nyse.com/trade/hours-calendars), [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars)

Freeze split manifest ก่อนอ่าน event outcomes; M1 ตรวจ holdout ได้เฉพาะ data coverage/integrity ห้ามเลือก parameters จาก continuation outcomes ของ 40 cycles หลัง

## 9. Universe และ evidence schemas ที่เสนอ

ทุก table มี `schema_version`, dataset ID, source lineage และ null semantics: null = unknown/not measured ไม่ใช้ 0 แทน unavailable ตัวเงินเป็น Decimal128; timestamps เป็น UTC ns หรือ int64 ns; share quantity เป็น decimal เมื่อ source รองรับ fractional quantity

| Table / key | Required fields |
| --- | --- |
| `cycles` / cycle_id | trading_date, previous_session, anchor/end UTC, RTH open, segments, early_close, split_group, schedule_hash |
| `security_observations` / observation_id | internal security_id, raw ticker, FIGIs, CIK, type, raw primary_exchange, active, requested_as_of_date, effective precision, available_at nullable, retrieved_at, source_ref, identity_status |
| `symbol_intervals` / interval_id | security_id, historical ticker, valid_from/to, interval_precision, evidence_refs, ambiguity flags |
| `reference_closes` / security_id + cycle_id + method_version | raw_price, reference_session, currency, adjustment_basis, observation/availability times, source_ref, quality flags |
| `float_observations` / float_observation_id | security_id, float_value, cohort, measurement/effective/available times, validity policy, estimator_version nullable, evidence_refs |
| `corporate_actions` / action_id | security_id, type, effective_time/precision, raw factors, available_at, source_refs |
| `universe_decisions` / run_id + cycle_id + security_id | evaluation_time, price/float/listing/type/identity gates, overall status, all reason_codes, cohort, input observation IDs, policy/mapping versions |
| `coverage` / dataset + cycle + segment | request status, expected boundaries, received boundaries, counts, completeness evidence, gap status; zero rows separate from failed request |
| `source_records` / source_ref | dataset/object ID, relative URI, SHA-256, endpoint, sanitized params, provider request_id, page ordinal, row locator, retrieval UTC |
| `quality_findings` / finding_id | run/dataset/security/cycle scope, rule/version, severity, expected/actual, evidence_refs, resolution |

Overall eligibility: known fail อย่างน้อยหนึ่ง gate → `INELIGIBLE`; ไม่มี fail แต่มี unknown → `UNRESOLVED`; ทุก mandatory gate ผ่านและ policy approved → `ELIGIBLE` เก็บผลแต่ละ gate เพื่อคำนวณ overlapping exclusions ได้ และรายงาน mutually exclusive overall counts ต่างหาก

Future contracts ต้องรองรับ `events(event_id, security_id, cycle_id, observed_at, available_at, P0, observation_price, trigger_price, condition_policy, source_trade_ref, quote_refs, quality_flags)` และ separate feature/outcome records keyed ด้วย event + definition version + horizon/barrier pair เก็บ censoring reason/time, target basis (`EVENT_PRICE`/`P0`), MFE/MAE, time-to-target/invalidation และ tie/unknown ordering โดยยังไม่สร้างค่าผลวิจัยใน M1

## 10. Storage, resumability และ reproducibility

```text
data/raw/massive/<endpoint>/<request_hash>/<payload_hash>.json.gz
data/catalog/datasets/<dataset_id>/manifest.json
data/normalized/<dataset_id>/<table>/date=YYYY-MM-DD/*.parquet
data/runs/<run_id>/universe/cycle=YYYY-MM-DD/*.parquet
data/runs/<run_id>/quality/*.parquet
data/runs/<run_id>/checkpoints/*.json
data/ticks/<tick_dataset_id>/date=YYYY-MM-DD/bucket=NN/*.parquet  # M2
reports/<run_id>/{manifest,coverage,quality,acceptance}.json
reports/<run_id>/report.md
```

Raw payload เป็น evidence ไม่ rewrite in place; provider correction ได้ object/version ใหม่ Parquet ใช้ date partitions และ bounded-size files; ไม่แบ่งทุก ticker เป็น tiny file โดยไม่มี measurement DuckDB views scan ทุก partition ของ run สำหรับ full counts และ summaries; จำกัดเฉพาะ returned extracts ไม่ sampling statistical denominator Optional bundle เป็น export เท่านั้นตาม master ล่าสุด

Request fingerprint ครอบ endpoint, canonical params, provider/schema version โดยไม่รวม secrets; dataset identity ผูก response hashes ด้วย ไม่ถือว่า request เดิมจะได้ data เดิมตลอดไป Checkpoint state `PENDING/RUNNING/COMPLETE/FAILED` ระดับ page และ cycle; mark complete หลัง fsync/atomic rename และตรวจ hash สำเร็จ มี one-writer lock และ reclaim policy สำหรับ interrupted worker

Resume อ่าน immutable successful pages; failure ไม่ cache เป็น valid empty result; deduplicate ด้วย source identity/record locator ไม่ใช้ timestamp อย่างเดียว หาก config/code/schema เปลี่ยนให้ new run; cache reuse ต้อง explicit dataset version Retry เฉพาะ timeout/429/5xx ตาม Retry-After และ bounded exponential backoff; 401/403 หยุด audit และบันทึก entitlement failure Pagination cursor loop/missing page เป็น failure; next_url ตรวจ trusted host และลบ credentials ก่อน log

Run manifest: run_id, experiment_id/stage, normalized config + hash, approved decisions + versions, input dataset IDs/hashes, code commit หรือ source-tree hash + dirty flag, dependency lock hash, schema versions, calendar/timezone, 120 requested cycles, processed/verified/missing cycles, split manifest, start/end UTC, row counts, output checksums, validation status, research_ready และ limitation codes

ใช้ deterministic research fingerprint จาก config+inputs+code+schemas; แยก execution attempt ID/time ออกจาก fingerprint Snapshot/report rerun ต้องเทียบ logical content hash ได้ แม้ volatile execution timestamp ต่างกัน

## 11. Implementation phases และ gates

| Phase | งานและ deliverables | Gate |
| --- | --- | --- |
| P0 ตอนนี้ | preserve spec, architecture, API documentation audit, calendar check, decisions | planning package reviewable; implementation ยังรอ authorization |
| P1 | reconcile existing code against approved requirements; immutable config/contracts; calendar tests | policy version fixed, unit/contract tests pass |
| P2 | bounded authenticated Massive audit, dictionary snapshots, dated identity/close/float capability report | entitlement findings explicit; no silent fallback |
| P3 | historical discovery + closes + float evidence intake + quality decisions; 3-cycle pilot | pagination, lineage, resume, counts and identity checks pass |
| P4 | 120-cycle reference/universe build; full queryable ledger and audit report | all cycle states accounted for; reproducibility checks pass |
| P5 | M1 acceptance review: technical integrity and research readiness separately | no M2 until M1 validation accepted; unresolved core eligibility blocks primary research |

M2–M6 ใช้ milestone gates ตาม master: M2 ต้อง replay source ordering/coverage ได้; M3 ต้อง first-touch และ censored baseline fixtures ผ่าน; M4 ต้อง pre-specified confirmation กับ comparable decision-time controls; M5 ใช้ clustered/dependence-aware statistical method ที่ Research Lead อนุมัติและ frozen holdout; M6 query/auth/resource-limit tests ต้องผ่าน ทุก milestone มี test, quality report, reproducible run และ explicit acceptance โดยไม่ implement ใน TASK 001

## 12. Test และ data-quality strategy

| Layer | Cases และ expected evidence |
| --- | --- |
| Unit: boundaries | float 99,999 / 100,000 / 15,000,000 / 15,000,001; price 0 / positive / 3 / >3; null, NaN, invalid currency; exact decimal +10% |
| Unit: identity/listing | each allowed MIC, outside MIC, unknown, CIK shared by two classes, ticker reuse/rename, missing FIGI, transfer during cycle, conflicting evidence |
| Unit: PIT | available_at after anchor rejected for PIT; unknown publication time labeled; conflicting float intervals unresolved; current float never primary |
| Unit: time | weekends/holidays, DST both directions, early close, previous anchor, no duplicate boundary ownership, missing close not forward-filled |
| Integration: API | multipage fixtures, repeating next_url, 429 recovery, 401/403 failure, malformed response, empty valid result vs timeout; credentials absent from artifacts |
| Integration: persistence | kill between download/write/checkpoint; resume equals uninterrupted logical outputs; changed input/config cannot overwrite old run; tampered checksum fails |
| Integration: query | all 120 cycles aggregate without manual merge; complete ledger drilldown to source row; extract limit does not change total count; schema roundtrip preserves nulls/Decimals/ns |
| Live audit | pre-register sample dates/tickers by data edge cases, recent/oldest window access, historical inactive/rename samples, 3-cycle pilot; report account-specific results separately |

P2 live budget proposal: ≤30 HTTP requests total including retries, ≤100 trade rows และ ≤100 quote rows ต่อ probe, ≤2 tick windows of 60 seconds; ไม่ auto-follow tick pagination; reference pilot pagination ใช้ budget stop พร้อม incomplete status ห้ามสรุป complete จาก truncated sample Tick sample ใช้ตรวจ transport/schema เท่านั้น ไม่วัด continuation หรือใช้คัด parameters

Daily quality report ต้องแสดง expected/processed/complete cycles, unique security counts, all gate denominators, missing identity/exchange/type/P0/float, independent exclusions, proxy distribution, stale/conflicting evidence และ source coverage ต่อ session ไม่มี ticks ไม่แปลว่า no event/no halt ถ้า coverage ยังไม่พิสูจน์

## 13. Risks และ Research Lead decisions

| ID | ประเด็นที่ต้องยืนยัน | ข้อเสนอและผลกระทบ |
| --- | --- | --- |
| D01 | Study end date | 2026-11-13; freeze calendar/split; เปลี่ยนวันต้อง new config/run |
| D02 | Historical float source / fallback | primary ใช้ VERIFIED_PIT เท่านั้น; ไม่มี source ให้ unresolved; proxy cohort ต้องอนุมัติแยก ไม่สรุป micro-float finding จาก current float |
| D03 | Eligibility timing | freeze ณ previous close, audit changes ระหว่าง cycle; exact change time unknown → unresolved event eligibility |
| D04 | Security type scope | เสนอ CS-only ตาม local decision note แต่ต้อง reconcile กับ master/Research Lead; discovery ไม่ prefilter |
| D05 | Reference close / availability | unadjusted provider daily close สำหรับ retrospective research; official auction และ real-time available-at ยังต้อง validation |
| D06 | Split/dividend cycles | flag และแยก split cycles จนอนุมัติ price-basis policy; dividend sensitivity แยก; ห้ามเกิด synthetic +10% จาก split |
| D07 | Session/overnight/late-print policy | outside observed coverage เป็น unknown; closing print association และ AH early-close windows ต้อง approved convention |
| D08 | Output contract conflict | master ล่าสุดให้ queryable evidence เป็นหลักและ ZIP optional; local contract เดิมบังคับ ZIP; แผนนี้ใช้ master โดยยังไม่แก้ exporter เดิม |
| D09 | First-touch conditions/time ordering | research allowlist, odd lots, late/corrected trades, SIP vs participant ordering ต้องตัดสินก่อน M3; ไม่ copy aggregate rules เป็น research truth |

D01–D08 ต้องมี disposition ก่อน freeze production M1 config (อาจอนุมัติ explicit unresolved workflow ได้); D09 ต้องบันทึกว่า deferred และต้อง resolved ก่อน event research ส่วน C1/C2/C3 thresholds, horizon observation rule/staleness, barrier ties และ clustered inference เป็น methodology decisions ใน milestones ถัดไป ไม่เดาค่าใน M1

Risks เพิ่มเติม: missing historical attributes ทำให้ selection bias, source revisions ทำให้ผล drift, FIGI discontinuity ทำให้นับซ้ำ/รวมผิด security, close availability ทำให้ look-ahead, API volume/storage ทำให้ run ไม่ครบ, holdout inspection ทำให้ leakage แต่ละ risk ต้องมี finding/code ไม่ซ่อนด้วย success exit code

## 14. Measurable acceptance criteria

**TASK 001 planning acceptance:** มี spec exact copy และ hash; ครบ architecture/module/API/discovery/P0/float/exchange/calendar/schema/storage/resume/test/provenance/risk topics; มี calendar output ที่ทำซ้ำได้; source citations ตรวจได้; แยก documented capability ออกจาก live verification และมี unresolved decisions ชัดเจน

**M1 technical acceptance หลัง implementation:**

1. Schedule มี exactly 120 unique ordered cycles + prior anchor, 80 exploration/40 holdout แบบไม่ overlap และแต่ละ cycle มี state แม้ data missing
2. ทุก discovered record มี source locator/hash, requested date และ retrieval time; identity ambiguity ไม่ถูก silently merged
3. Eligibility ledger มีทุก gate และทุก reason; mutually exclusive status counts รวมเท่ากับ candidate denominator; missingness รายงานแม้ record fail gate อื่น
4. ไม่มี current float ที่ labeled VERIFIED_PIT; ไม่มี shares-outstanding substitute; every verified PIT claim มี auditable evidence/time policy
5. Every eligible record ผ่าน listing/float/P0/identity/type policy ที่อนุมัติและมี provenance ครบ; missing/unresolved ไม่ auto-pass
6. Unit/integration cases ด้านบนผ่าน; interrupted resume ให้ logical hashes/counts เท่ากับ uninterrupted run; corruption/config mismatch ถูก reject
7. Single local query aggregate ทั้ง 120 cycles และ drilldown กลับ source rows ได้; bounded extraction ไม่ตัด statistical population
8. Live entitlement/coverage audit รายงานจริงทุก requested capability; output status แยก `technical_validation` กับ `research_ready` และ never estimate event statistics ใน M1

**M1 research-readiness gate:** decision policies approved; eligible primary cohort มี historical float และ historical eligibility evidence จริง; unresolved coverage มีผลต่อ completeness ต้องเปิดเผยและได้รับ acceptance โดย Research Lead ก่อน M2 ไม่มี minimum sample size ที่ engineering ตั้งเอง และ zero eligible เพราะ unresolved float ไม่ใช่ negative research result หาก unresolved blocker ยังอยู่ให้ M1 `BLOCKED_DATA` แม้ technical checks PASS ไม่เลื่อนไป M2 อัตโนมัติ

## 15. Exact next execution steps

1. Research Lead review D01–D08 และอนุมัติ implementation ของ M1 ตาม plan นี้; unresolved data policy ต้องระบุชัด ไม่ตีความ silence เป็น approval
2. ตรวจ source ที่มีอยู่แบบ requirement-to-code matrix; ระบุ reuse/change/missing และ preserve user changes ทั้งหมด
3. Freeze research policy, config/schema versions และ lockfile; เพิ่ม focused contract/calendar/eligibility tests ก่อนแก้ pipeline
4. รัน bounded authenticated P2 audit ตาม budget และเก็บ sanitized raw responses/manifest; ถ้า historical float ไม่มีให้ unresolved workflow ตาม decision ที่อนุมัติ
5. รัน P3 pilot 3 cycles ที่เลือกจาก calendar/data edge cases; ทดสอบ interruption/resume, evidence drilldown และ count reconciliation
6. เมื่อ pilot ผ่าน จึงรัน historical reference/universe 120 cycles ใน P4 โดยไม่ bulk-download ticks และไม่ประเมิน holdout outcomes
7. ส่ง acceptance report พร้อม technical/research-readiness แยกกัน; M2 เริ่มได้หลัง M1 gate ผ่านเท่านั้น

## 16. หลักฐานการตรวจในงานรอบนี้

- เก็บ specification ที่แนบแบบ byte-identical และบันทึก SHA-256 ใน `evidence/planning-audit.json`
- อ่าน official Massive documentation และใช้ Massive connector ค้น endpoint definitions; ยังไม่ได้เรียก authenticated market-data API
- รัน calendar feasibility script และ assertions จริง ผลอยู่ใน `evidence/calendar-check.json`; ไม่ได้รัน existing platform test suite หรือรับรอง reports เดิม
- ไม่แก้ implementation, ไม่ bulk-download ticks, ไม่ commit/push; ไฟล์ใน package นี้เป็นข้อเสนอพร้อมตรวจอนุมัติ

แหล่ง API เพิ่มเติม: [All Tickers](https://massive.com/docs/rest/stocks/tickers/all-tickers), [Ticker Overview](https://massive.com/docs/rest/stocks/tickers/ticker-overview), [Exchanges](https://massive.com/docs/rest/stocks/market-operations/exchanges), [Conditions](https://massive.com/docs/rest/stocks/market-operations/condition-codes)
