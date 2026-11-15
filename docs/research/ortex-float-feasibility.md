# ORTEX Historical Float API feasibility

ตรวจวันที่ 15 พฤศจิกายน 2026 เวลา 09:44:20–09:44:50 Asia/Bangkok

**Outcome: `DEMO_RESTRICTED_OR_INCONCLUSIVE`**

Public demo authentication ทำงานจริงและ Historical Free Float endpoint คืนข้อมูล แต่ TEST key บังคับ sample window และผลเหมือนกันเมื่อเปลี่ยน PIT/split flags จึงยังยืนยัน historical point-in-time float สำหรับ M1 ไม่ได้ ORTEX มีเหตุผลให้ประเมินต่อด้วย controlled evaluation access; ยังไม่มีหลักฐานเพียงพอให้ซื้อ subscription หรือเปลี่ยน float gate

M1 ยังคง `BLOCKED_DATA` ไม่มีค่าใดจาก experiment นี้ถูกนำเข้า `VERIFIED_PIT` และไม่มีการเปลี่ยน approved filters, M1 outputs หรือเริ่ม M2

## Requests และผลจริง

Endpoint เดียวที่ทดสอบ:

```text
GET https://api.ortex.com/api/v11/stock/NYSE/AMC/reference/free_float/
```

ใช้ header ชื่อ `Ortex-Api-Key` กับ public demo value ตามคำสั่งผู้ใช้ ไม่มี paid key และไม่ได้เก็บ request authentication headers ใน evidence

Official OpenAPI example ให้ `NYSE/AMC` และ `from_date=2017-06-01` ส่วน `to_date` ไม่มี example และเป็น optional จึงละไว้ใน 4 calls แรก ไม่แต่ง example end date ขึ้นเอง

| Call | from_date | to_date | point_in_time | split_adjusted | HTTP | ผล |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2017-06-01 | omitted | true | false | 200 | 9 records |
| 2 | 2017-06-01 | omitted | false | false | 200 | 9 records |
| 3 | 2017-06-01 | omitted | true | true | 429 | `rateLimitExceeded` |
| 4 | 2017-06-01 | omitted | true | true | 200 | 9 records หลัง cooldown |
| 5 | 2026-05-27 | 2026-11-13 | true | false | 200 | 9 records ชุดเดิม |

รวม **5 API calls** นับ failed/rate-limited call ด้วย ไม่มี pagination requests หรือค้นหา ticker/date อื่นเพื่อเลี่ยง restriction Call 3 ได้ `Retry-After: 1` และ `RateLimit-Limit: 1`; script หยุด จากนั้น explicitly resume ภายใต้ ledger เดิมเพื่อใช้ budget ที่เหลือ เว้นอย่างน้อย 2 วินาทีระหว่างคำขอ ไม่มี automatic HTTP retry หรือ redirect

HTTP 200 ทุกครั้งมี top-level keys `request`, `instrument`, `resolved`, `pagination`, `data`, `meta` และ `Content-Type: application/json` แต่ละ row มี `date`, `sharesOutstanding`, `freeFloatShares`, `freeFloatPct`

`pagination.rowsThisPage=9`, `totalRows=9`, `next=null`, `previous=null`; `meta.credits.used=0.0`, `remaining=null` ข้อมูลนี้ยืนยันเฉพาะ trial responses ที่เห็น ไม่ยืนยันราคา/entitlement ของ paid product

HTTP 429 เป็น envelope `error` ประกอบด้วย status/code/message/details/request/help/context/retryable/requestId; `code=rateLimitExceeded`, `retryable=true` และ header `Ortex-Request-Id=940b63e0-0450-4fa4-af61-0a87ddc2c4de` ค่า `error.requestId` ใน body เป็น null จึงต้องเก็บ header ด้วย

## Historical records ที่ได้จริง

ทุก HTTP 200 ระบุ `resolved.from_date=2026-05-19`, `resolved.to_date=2026-10-16`, `page=1`, `page_size=10` แม้ส่ง date window อื่น

| date | freeFloatShares | sharesOutstanding | freeFloatPct |
| --- | ---: | ---: | ---: |
| 2026-05-19 | 693452303 | 754171721 | 91.948860 |
| 2026-05-28 | 693202303 | 754171721 | 91.915711 |
| 2026-06-26 | 831635220 | 892604638 | 93.169493 |
| 2026-06-30 | 835347607 | 892604638 | 93.585398 |
| 2026-08-07 | 828147706 | 892604638 | 92.778781 |
| 2026-08-08 | 827496166 | 892604638 | 92.705788 |
| 2026-08-11 | 827495995 | 892604638 | 92.705769 |
| 2026-08-12 | 831635220 | 892604638 | 93.169493 |
| 2026-08-16 | 835347607 | 892604638 | 93.585398 |

นี่คือ returned historical-looking sample records ที่ยังไม่ได้ตรวจเทียบ filing หรือแหล่งอิสระ ไม่ใช่ audited historical truth ค่า float สูงกว่า upper limit 15M ของ target universe ทั้งหมด จึงไม่ได้ทดสอบ coverage กลุ่ม micro-float

Resolved instrument: AMC Entertainment Holdings, Inc.; `exchange_symbol=NYSE`, `ticker=AMC`, `ortexCid=1140353`, `ortexSid=3075032`, `ortexTid=6777647`, `isin=US00165C3025`, `figi=BBG000TDCWW0`, `mic=XNYS`, `operatingMic=XNYS`

## PIT และ split adjustment

เอกสารอธิบาย change-based series: แถวแรกอาจเป็น boundary value ที่ยกมาจากก่อน window และ PIT เปลี่ยน date ตาม first covering filing หรือ fallback 180 วัน พร้อมละค่าที่ถูกแทนก่อนเป็นที่รู้ได้ ส่วน `split_adjusted=false` ขอจำนวนหุ้นตาม basis ในอดีต ต่างจากค่าเริ่มต้นที่ปรับเป็น capital structure ปัจจุบัน นี่เป็น documented methodology ที่ยังต้องพิสูจน์ด้วย paid/evaluation records [Free Float reference](https://docs.ortex.com/reference/stock_reference_free_float_retrieve)

สิ่งที่สังเกต:

- Call 1/2 มี `resolved.point_in_time=true/false` ตามที่ขอ แต่ `data` ทั้ง 9 rows เท่ากันทุก field
- Call 1/4 มี `resolved.split_adjusted=false/true` ตามที่ขอ แต่ `data` ทั้ง 9 rows เท่ากันทุก field
- ไม่มี per-row filing accession, source document, publication timestamp, measurement timestamp หรือ indication ว่าแถวใดใช้ fallback 180 วัน
- `min_lag_days=0` ปรากฏใน PIT response แต่ไม่ได้ทดสอบ nonzero lag

จึงไม่สรุปว่า flags ไม่มีผลใน paid product หรือ ORTEX PIT ไม่ถูกต้อง ความเหมือนกันอาจเกิดจาก sample control หรือไม่มี relevant timing/split differences ในข้อมูลที่คืน Demo นี้แยกสองกรณีไม่ได้

## Trial restrictions และ M1 coverage

ทุก HTTP 200 มี `meta.testKeyNote` แจ้งว่า TEST ควบคุม date range, page และจำนวนผลลัพธ์เอง ไม่มี `meta.restriction` ใน responses ที่สังเกต แม้เอกสารกล่าวถึง block นี้สำหรับ trial trimming

ความต่างระหว่าง sent request กับ response สำคัญ: `request` echo ไม่มี `from_date`/`to_date` ที่ส่งจริง และ `resolved.defaultedFields` ใส่ date fields เป็น defaulted แม้ส่งมาแล้ว จึงต้องเก็บ client-side params คู่กับ response เสมอ ไม่พึ่ง echo เพียงอย่างเดียว

Call 5 ขอ M1 dates โดยตรงแต่ยังได้ sample window/rows เดิม มีหนึ่งแถวก่อน requested start และไม่มี rows หลัง 2026-08-16 แม้ resolved end เป็น 2026-10-16 เนื่องจากเป็น change-based series การไม่มีแถวรายวันเองไม่พิสูจน์ missing data; แต่ demo ที่บังคับ window ก็ไม่รับรอง validity interval หรือ coverage ไปจน 2026-11-13 เช่นกัน

**ไม่มีข้อสรุปว่า ORTEX ครอบคลุม 120 cycles หรือ target NASDAQ/NYSE American/NYSE micro-float universe** ยังไม่ได้ทดสอบ delisted sample, ticker rename, missing FIGI หรือ exact anchor-time availability

## Identifier mapping กับ Massive

ORTEX docs รองรับ exchange/ticker, `tid`, `sid`, `cid`, ISIN และ FIGI; FIGI ที่รับเป็น exchange-level หรือ share-class ส่วน composite FIGI ไม่รับ `from_date` ใช้เลือก historical instrument และ response ตาม listing เดิมข้าม ticker changes ส่วน `tid` ใช้ระบุ listing ที่ delisted ได้ นี่เป็น documentation claims ที่ demo AMC ครั้งนี้ยังไม่ทดสอบ [Identifying an instrument](https://docs.ortex.com/reference/identifying-an-instrument)

การตรวจ local M1 snapshot วันที่ cycle 2026-11-13 สำหรับ AMC พบ Massive `share_class_figi=BBG001SZYYL4`, `composite_figi=BBG000TDCVT6`, `primary_exchange=XNYS` ส่วน ORTEX response ให้ listing FIGI `BBG000TDCWW0` ค่าเหล่านี้เป็นคนละ identifier level; ticker/name ตรงกันยังไม่ใช่ verified crosswalk

ขั้นต่อไปควรใช้ share-class FIGI ของ Massive ใน namespace `figi` หลังได้ authorization สำหรับ evaluation และเทียบ resolved security/listing/ISIN/effective dates เก็บ ORTEX tid/sid กับ Massive share-class identity เป็น effective-dated crosswalk ห้ามใช้ composite fallback ใน `identity()` ของ M1 ส่งตรงไป ORTEX หรือใช้ CIK/ชื่อบริษัทอย่างเดียวรวมหลาย share classes ห้ามขยาย allowlist ด้วย ORTEX operating MIC ที่ครอบหลาย segments

## การ join ณ Previous RTH Close

ศักยภาพคือใช้ PIT และ unadjusted share count กับวันที่/ช่วง validity ของ security เดียวกัน แต่ M1 ต้องมี `measurement_at`, `available_at`, effective interval, validity policy และ audited historical source ก่อนผ่าน primary gate

Response มีแค่ date รายวัน ไม่ระบุ timezone หรือ intra-day publication time จึงพิสูจน์ไม่ได้ว่าค่าของ date D ใช้ได้แล้วก่อน RTH close ของ D โดยเฉพาะ filing หลังตลาดปิด ต้องขอ filing timestamps/source lineage และแยกค่าที่มาจาก fallback 180 วัน หากไม่มี timestamp อาจเสนอกติกา conservative next-session availability ให้ Research Lead อนุมัติ โดยยังไม่ยกระดับเป็น verified เอง

Boundary row ของ request window ไม่ควรถูกแปลเป็น measurement date ใหม่หรือสร้าง historical carry-forward interval โดยไม่มี source policy ตรวจ splits/reverse splits, share-class changes และ source revisions ควบคู่ เพื่อให้ float denominator อยู่ใน share basis เดียวกับ unadjusted P0

## Reproducible probe และ evidence

Script: [probe_ortex_float.py](../../scripts/probe_ortex_float.py)

```sh
.venv/bin/python scripts/probe_ortex_float.py --output data/ortex-demo-NEW-RUN
# เฉพาะเมื่อได้รับอนุมัติให้ใช้ budget ที่เหลือของ run เดิม:
.venv/bin/python scripts/probe_ortex_float.py --output data/ortex-demo-NEW-RUN --resume
```

Standalone script ไม่ import `market_lab` และไม่แตะ M1 datasets ใช้ public demo auth แบบกำหนดไว้ ไม่อ่าน paid credentials/netrc/proxy จาก environment จำกัด 5 attempts ต่อ persisted ledger, connect/read timeout 10/25 วินาที, response limit 2 MiB และตรวจ elapsed 40 วินาทีระหว่างอ่าน body `requests` read timeout เป็น inactivity timeout ไม่ใช่ hard process deadline ไม่มี background retry/pagination

ผลรันนี้อยู่ใน ignored local directory `data/ortex-demo-20261115-v1/`: manifest พร้อม exact sent params, selected response headers, UTC times, raw-body SHA-256, response JSON และ error JSON เก็บ credentials/cookies/request auth headers ออกทั้งหมด

Compact reviewable evidence: [ortex-float-probe-results.json](ortex-float-probe-results.json) มี samples, comparison flags, metadata, HTTP statuses และ source hashes Body SHA-256 คำนวณจาก HTTP bytes ก่อน pretty-print จึงไม่เท่ากับ hash ของ formatted response JSON

## Next evaluation และคำตัดสิน

**ORTEX ควรได้รับการประเมินต่อ** เพราะ demo ยืนยัน auth/endpoint/schema และมี PIT/unadjusted controls ที่ตรงกับโจทย์ในระดับ API design ผลลัพธ์ยังอยู่ที่ `DEMO_RESTRICTED_OR_INCONCLUSIVE`; transport success เป็นเพียงส่วนที่ผ่านทางเทคนิค ไม่ให้ outcome `DEMO_TECHNICALLY_VALIDATED` สำหรับ historical PIT compatibility

ก่อนพิจารณาซื้อ ให้ขอ controlled evaluation และ methodology clarification ผ่านผู้ใช้ โดยยังไม่ส่งข้อความหาผู้ให้บริการหรือซื้อในงานนี้ สิ่งที่ evaluation/paid access ต้องพิสูจน์:

1. ใช้ requested dates ได้จริงและมี coverage ตลอด 2026-05-27–2026-11-13 สำหรับ approved small sample จาก target universe รวม delisted/renamed securities
2. PIT/non-PIT ต่างกันอย่างตรวจสอบได้รอบ filing ที่เผยแพร่ช้าหรือหลัง RTH close พร้อม original source, actual availability time และ fallback classification
3. Unadjusted counts ตรง historical filings ก่อน/หลัง split และสอดคล้องกับ P0 basis
4. FIGI/ORTEX identity crosswalk แยก listing/security/share class ถูกต้อง รวม ticker reuse และ corporate actions
5. Boundary-row semantics, revisions, free-float definition และ historical data completeness มีหลักฐานเพียงพอ ไม่อนุมานจาก current figures
6. Entitlements, credits/rate limits, archival rights และ permitted local research storage รองรับงานจริง โดยประเมินก่อนซื้อ

เอกสารประกอบ: [Response Envelope](https://docs.ortex.com/reference/the-v11-response-envelope), [Response & Error Codes](https://docs.ortex.com/reference/v11-response-error-codes) เอกสาร envelope บางส่วนกล่าวว่า request เป็น literal echo; trial behavior ที่เห็นต่างออกไป จึงยึด captured client request และ server resolved values สำหรับข้อสรุปในงานนี้
