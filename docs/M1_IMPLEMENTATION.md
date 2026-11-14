# M1 implementation และหลักฐานการตรวจ

วันที่ 15 พฤศจิกายน 2026 · implementation ภายใต้ authorization ที่บันทึกใน [decision](decisions/2026-11-15-m1-authorization.md)

Historical float ที่ไม่มี evidence เป็น `UNRESOLVED` และ value เป็น null เสมอ Current float ไม่ถูกขอหรือใช้แทน การประมวลผลครบ cycle กับ primary research readiness เป็นคนละสถานะ M2 ยังไม่เริ่ม

## Requirement reconciliation

| ข้อกำหนดตามแผน | Implementation / evidence |
| --- | --- |
| Versioned spec และ policy | `docs/specs/master-research-engineering-plan-v0.1.md`, `configs/m1-v1.json`, approved decision |
| Historical discovery | ใช้ dated `/v3/reference/tickers`, complete cached cursor chains, ไม่สร้าง universe จาก today's active list |
| Listing allowlist | explicit XNAS/XASE/XNYS mapping; directory ตรวจผ่าน live connector; execution venue ไม่ใช่ listing filter |
| Security identity | separate identity gate; missing/ambiguous IDs ไม่ eligible, original FIGI/CIK/ticker เก็บใน provenance; duplicate aliases ไม่ถูกนับเป็นสอง eligible securities |
| Previous close | unadjusted provider daily close, Decimal P0 และ threshold, ไม่มี forward-fill; source-row locator; cross-check live daily summary |
| Float integrity | latest endpoint disabled; verified PIT requires explicit cohort/source/time/validity fields; proxy/current ไม่ผ่าน; validator recomputes float จาก evidence |
| Corporate actions | complete saved cursor-chain importer, hashed source captures, cross-symbol split checks, unresolved identity continuity, dividend evidence; no automatic split/total-return normalization |
| Calendar / holdout | materialized 120-cycle schedule, frozen 80/40; pilot label; DST/holidays/early-close tests; unobserved overnight ไม่อ้างว่า market closed |
| Schema / storage | `universe-snapshot-v2.json`, Decimal128, Parquet/ZSTD, local partitioned data; old v1 artifacts ไม่ overwrite |
| Resume / immutability | config/code/source-index/actions hashes, locks, fsync+atomic rename, page checksums, interruption tests, same-run directory drift rejection |
| API transport | trusted pagination host, redaction, offline mode, request budget including retries, bounded Retry-After; current-float access disabled |
| Data quality | all 7 gate counts, missingness แม้ fail gate อื่น, per-cycle reference/tick/halt coverage states, source checksums and row validation |
| Run provenance | policy/config/calendar/source/dependency/code hashes, git state, input dataset fingerprint, start/end times; no event outcomes estimated |
| Query contract | full-population DuckDB counts; bounded extracts พร้อม total/truncation labels; complete local evidence สำหรับ future Research MCP |
| Export contract | ZIP optional ตาม approved master; existing exporter retained and tested |

ใช้ modules เดิม `api`, `calendar`, `eligibility`, `pipeline`, `storage`, `results`, `cli` และเพิ่ม `corporate_actions`, `audit` แทนการสร้างทุก file placeholder ใน proposed structure หน้าที่ P0/identity/provenance อยู่ใน pipeline และ eligibility ใน M1; ยังไม่แยกเป็นบริการหรือ MCP Server

## Verification evidence

- [Baseline](../reports/m1-implementation-20261115/baseline.json): source hashes ก่อนแก้และ baseline 62 tests
- [Test results](../reports/m1-implementation-20261115/tests.txt): 87 tests ผ่าน รวม regression, temporal evidence, wrong proxy labels, corrupted cache, exact Decimal threshold และ interrupted page/cycle resume
- [Live capability audit](../reports/m1-implementation-20261115/api-audit.json): 16 connector calls ที่บันทึกไว้, 2 tick windows, 400 tick/quote records รวม; ไม่ follow tick pagination และไม่คำนวณ outcomes
- [Pilot acceptance](../reports/m1-pilot-20261115-v3/acceptance.json): 3 cycles / 39,734 observation records; technical validation PASS, research readiness false
- [Pilot resume](../reports/m1-implementation-20261115/resume-pilot.json): ทั้ง 3 snapshots ไม่เปลี่ยน checksum, fingerprint เดิม, network calls 0
- [Reference-close cross-check](../reports/m1-implementation-20261115/close-crosscheck.json): AAPL 2026-11-12 grouped daily กับ live daily summary ตรงกัน เป็น same-vendor check ไม่ใช่ official auction verification
- [Full-window acceptance](../reports/m1-universe-120-20261115-v2/acceptance.json): ประมวลผลครบ 120/120 cycles, 1,568,804 records; technical validation PASS, research readiness false

Live probes ใช้ authenticated Massive connector; ไม่มี local REST key ใน environment จึงไม่อ้างว่า local REST authentication ผ่าน การรัน universe ใช้ cached REST source objects 1,782 ไฟล์ที่ตรวจเทียบ checksum กับ evidence registry เดิมก่อนใช้ และ corporate-action captures ใหม่ผ่าน connector (845 split records และ 28,464 dividend records รวมทุกประเภทหลักทรัพย์ก่อน join)

Connector ส่ง normalized tables ไม่ใช่ raw wire HTTP body จึงเก็บ tool response envelope, request parameters, retrieval UTC, row locator และ hash เป็น transport provenance แยกกัน Internal HTTP retries ของ connector ไม่ถูกเปิดเผย จึงไม่อ้างว่า 16 connector calls เท่ากับ 16 HTTP attempts

## Remaining data limitations และ milestone gate

1. ไม่มี verified historical float source สำหรับ primary cohort; zero qualified records ไม่ใช่ negative continuation finding
2. Historical reference เป็น effective-dated reconstruction; publication-time availability และ exact intraday listing changes ยังพิสูจน์ไม่ได้จาก daily records
3. มี missing historical identifiers/prices/listing fields ที่ต้องดู counts จริงในแต่ละ run; unknown ไม่ auto-pass
4. Corporate actions เป็น symbol-keyed retrospective metadata; ไม่รับรอง permanent identity continuity ผ่านทุก rename หรือ action revision
5. P0 ใช้ provider daily close และไม่มี exact available-at proof; ทุก row ระบุ `RETROSPECTIVE_NOT_EXECUTABLE`
6. Calendar regular hours ใช้ XNYS; venue-specific extended-session exceptions, overnight completeness และ halts ยังไม่ verified ถูกแสดงใน coverage ไม่ถือว่าไม่มีข้อมูลเท่ากับไม่มี trading
7. Trade eligibility/late-print ordering และ C1/C2/C3 research rules ยังคง deferred; ไม่มี first-touch event ledger ที่ผลิตจริงใน M1

M1 technical implementation ประเมินด้วย tests, persisted evidence และ validator ส่วน M1 research gate ยังคง `BLOCKED_DATA` เมื่อข้อมูลข้างต้น unresolved ไม่เริ่ม M2 โดยอัตโนมัติ

คำสั่ง reproduction และ input prerequisites อยู่ใน [README](../README.md) Raw market data ไม่อยู่ใน Git; ต้องใช้ local dataset ตาม manifest หรือดึง dataset version ใหม่ผ่านสิทธิ์ของบัญชีที่มี

## ผลส่งมอบสุดท้าย

| รายการ | ผล |
| --- | --- |
| Run | `m1-universe-120-20261115-v2` |
| Processed cycles | 120 / 120 |
| Security-cycle observation records | 1,568,804 |
| Exploration | 80 cycles / 1,038,821 records |
| Holdout | 40 cycles / 529,983 records |
| Overall INELIGIBLE | 1,422,848 |
| Overall UNRESOLVED | 145,956 |
| Float gate UNRESOLVED | 1,568,804; ทุก value เป็น null |
| Qualified primary records | 0 เพราะหลักฐานยังไม่ครบ; ไม่ใช่ market finding |
| Technical validation | PASSED |
| Primary research readiness | BLOCKED_DATA |

[Independent full-population checks](../reports/m1-implementation-20261115/full-population-checks.json) ยืนยันยอดตรงกับ summary, 80/40 split, record IDs ไม่ซ้ำ, current/fabricated float rows เป็น 0 และ code hashes ตรงกับ frozen config การ query จำกัด 1 row ยังรายงาน matching population ทั้ง 145,956 records ได้

[Completion record](../reports/m1-implementation-20261115/completion.json) เก็บ checksums ของรายงานสุดท้าย และ [attempt registry](../reports/m1-implementation-20261115/attempts.json) ระบุ runs ที่ superseded หลังแก้ ticker-rename action handling ไม่ใช้ runs เหล่านั้นเป็น final reproducibility evidence

`manifest.json` เป็น generation-time metadata; `acceptance.json` เป็นผล validator หลังสร้าง artifacts จึงเป็นแหล่งสถานะ technical validation สุดท้าย ต่างจาก `technical_validation=PENDING_VALIDATOR` ใน generation manifest ข้อมูลดิบและผลเดิมยังอยู่ในเครื่อง ไม่มี commit/push หรือการเริ่ม M2 ในงานนี้
