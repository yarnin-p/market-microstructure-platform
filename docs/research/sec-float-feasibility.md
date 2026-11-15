# SEC EDGAR Historical Float feasibility และ reconstruction pilot

วันที่ 15 พฤศจิกายน 2026 · Outcome: **`PILOT_COMPLETED_WITH_LIMITATIONS`** · M1: **`BLOCKED_DATA`**

หลังใช้ identified User-Agent ตาม contact ที่ผู้ใช้อนุญาต SEC pilot อ่าน submissions และ companyfacts ได้ครบ **24/24 securities** พร้อม original filings **48 ฉบับ** สร้าง historical share-count estimates ที่มี disclosed price basis ได้ **4 กรณี** และพบ directly reported non-affiliate share counts อีก **2 กรณี** ผลนี้ยังไม่รับรอง daily historical float หรือ primary PIT eligibility ของ M1

สิ่งที่พิสูจน์ได้คือ SEC มี historical public-float disclosures และบางกรณี reconstruct shares ได้จาก original filing เดียวกัน ข้อจำกัดหลักเป็นราคาอ้างอิงที่ไม่เปิดเผย, class allocation, measurement staleness, splits/dilution และ publication timing ไม่มีการแทนด้วย current float หรือ shares outstanding และยังไม่เริ่ม M2

## Sample และการเลือก

เลือกจาก `m1-universe-120-20261115-v2` โดยใช้ **exploration 80 cycles เท่านั้น** แต่ละตลาดเลือก 4 securities ที่เรียง split/change flags ก่อน และ 4 ตัวแรกตาม ticker จากกลุ่มไม่มี flags กำหนด selection ก่อนอ่าน SEC outcomes รวม 24 securities ตลาดละ 8 ตัว มี split flags 12 และ change/unverified-observation flags 5

| Primary listing | Securities |
| --- | --- |
| NASDAQ | AMIX, BYND, CREG, FEED, AAME, ABAT, ABOS, ABVC |
| NYSE American | GORO, APUS, GPUS, HCWC, AEON, AGIG, AIB, AIM |
| NYSE | ALIT, BRCC, LFT, NRDY, ACH, AHT, AIV, AMC |

ตรวจ local source snapshots แล้วทั้ง 24 selected records ผ่าน exchange/price/type/identity gates จริง และมี `0 < previous_rth_close <= 3` แต่ float gate ยัง unresolved Sample นี้เป็น **purposive feasibility candidates ไม่ใช่ representative sample หรือ verified micro-float population**

Historical Massive reference มี CIK ครบ 24 ตัว พร้อม source snapshot hash, record locator, selection cycle และ P0 SEC metadata ยืนยัน CIK response ตรง 24/24 แต่ CIK เป็น issuer identifier ไม่รับรอง share-class allocation ทุกกรณี

SEC submissions พบ historical issuer names ใน 15 ตัว เช่น FEED มี former name NanoVibronix และ AGIG/ACH มี name history รายงานนี้ไม่ตีความ name change เป็น confirmed ticker rename/delisting ปัจจุบันยังไม่มี delisted/ticker-reuse case ที่ตรวจยืนยันครบใน sample

## Actual access และ request accounting

คำขอแรกที่ใช้ project URL เป็น contact ได้ HTTP 403 และถูกเก็บไว้ใน `data/sec-pilot-20261115-v1/` หลังผู้ใช้ระบุชื่อ/contact และอนุญาตให้ส่งใน User-Agent คำขอเดิมได้ HTTP 200 จึงรัน pilot ต่อด้วย cache root ใหม่โดยรักษาหลักฐานเดิม

| Transport scope | Requests | ผล |
| --- | ---: | --- |
| Initial project-URL identification | 1 | HTTP 403; หยุด host ตาม policy |
| Authorized identified-contact pilot | 96 | HTTP 200 ทุกคำขอ |
| รวม actual HTTP attempts | **97** | ต่ำกว่า engineering budget 110 |
| Offline normalization/review/summary | 0 additional | reuse cache/checksums |

Successful requests ประกอบด้วย submissions 24, companyfacts 24 และ original documents 48 เริ่ม 2026-11-15T03:34:26Z ถึง 03:36:28Z ใช้ single worker เว้นอย่างน้อย 1.1 วินาทีต่อ network request ไม่มี automatic retries, redirects หรือ bulk-universe downloads Contact email ไม่อยู่ใน Git, request ledger หรือ response metadata ที่ส่งมอบ

Exact URL patterns ที่ใช้:

```text
https://data.sec.gov/submissions/CIK##########.json
https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
https://www.sec.gov/Archives/edgar/data/{CIK}/{accession_without_hyphens}/{primaryDocument}
```

Machine evidence เก็บ URL จริง, HTTP status, timestamps, decoded-body bytes และ SHA-256 ทุก request ดู [coverage v2](sec-float-coverage-v2.json) ส่วน [coverage v1](sec-float-coverage-v1.json) เก็บ initial access-blocked attempt ไว้ ไม่ใช้แทนผลล่าสุด

## Coverage และ classifications ที่สังเกต

| Metric | ผล |
| --- | --- |
| Securities examined | 24 |
| CIK present / SEC issuer metadata corroborated | 24/24 / 24/24 |
| Submissions / companyfacts อ่านได้ | 24 / 24 |
| Latest annual + latest quarterly original documents | 48 |
| Securities with public-float USD disclosures | 24/24 ใน sample; รวม AIB ที่รายงาน 0 |
| `SEC_DERIVED_HISTORICAL_ESTIMATE` | 4 |
| `SEC_REPORTED_SHARE_COUNT_ONLY` | 2; เป็น directly stated non-affiliate shares ในสองกรณีนี้ |
| `INSUFFICIENT_PRICE_BASIS` | 16 |
| `AMBIGUOUS_SHARE_CLASS` | 2 |
| `UNRESOLVED` หลัง source review | 0 ใน pilot classification; primary M1 float ยัง unresolved |
| Verified PIT observations / M1-ready daily float pairs | 0 / 0 |

24/24 public-float USD coverage ไม่ใช่ 24/24 float-share coverage อัตรา 4/24 derived และ 2/24 directly reported เป็น descriptive counts ของ sample นี้ ไม่ประมาณ coverage ทั้ง universe Historical submission shards ยังไม่ได้ดึง; latest annual/quarterly documents เป็นขอบเขตของการอ่าน original filings ไม่ใช่ exhaustive filing search

## Reconstruction ที่มี defensible source basis

คำนวณจาก `EntityPublicFloat` USD และราคาที่ระบุใน original disclosure เดียวกัน ตรวจ inline XBRL context date/CIK/unit และ share-class wording ไม่ใช้ market-price API หรือ arbitrary historical close

| Security / class | Measurement date | Public float USD | Disclosed price | Estimated shares ประมาณ | Filing acceptance UTC |
| --- | --- | ---: | ---: | ---: | --- |
| CREG / Common | 2025-12-31 | 27,900,000 | 1.33 | 20,977,444 | 2026-03-31 21:27:23 |
| GORO / Common | 2025-06-30 | 83,177,835 | 0.61 | 136,357,107 | 2026-03-18 20:36:19 |
| GPUS / Class A | 2025-06-30 | 12,100,000 | 1.40 | 8,642,857 | 2026-04-15 20:31:26 |
| AIV / Class A | 2025-06-30 | 1,200,000,000 | 8.65 | 138,728,324 | 2026-03-02 21:41:30 |

Original sources: [CREG 10-K](https://www.sec.gov/Archives/edgar/data/721693/000121390026037674/ea0282209-10k_smart.htm), [GORO 10-K](https://www.sec.gov/Archives/edgar/data/1160791/000110465926031121/goro-20251231x10k.htm), [GPUS 10-K](https://www.sec.gov/Archives/edgar/data/896493/000121465926004697/hdi32026010k.htm), [AIV 10-K](https://www.sec.gov/Archives/edgar/data/922864/000119312526085547/aiv-20251231.htm)

CREG, GPUS และโดยเฉพาะ AIV ใช้ rounded/approximate public-float USD ตัวเลขผลหารที่เก็บเป็น Decimal คือ arithmetic precision ไม่ใช่ measurement accuracy AIV numerator ปัดเป็น $1.2 billion จึงเป็น estimate หยาบ ไม่ควรนำ digits ของผลหารไปอ้าง precision จริง

GPUS original listing table ระบุ GPUS เป็น Class A Common Stock และ public-float sentence จำกัด Class A ชัดเจน จึงไม่ได้รวม Class B โดยอัตโนมัติ AIV เป็น joint filing กับ operating partnership แต่ public-float context ที่ใช้มี issuer CIK0000922864 ตรงกับ sampled equity

ทุก estimate จำกัดที่ measurement date ไม่มี `effective_to` หรือ carry-forward authorization และไม่ถูก labeled `VERIFIED_PIT` การที่ GPUS estimate อยู่ระหว่าง 100K–15M ในเดือนมิถุนายน 2025 ไม่พิสูจน์ว่าผ่าน float filter ของ cycle ใดในปี 2026

## Directly reported non-affiliate shares

- **AHT:** ระบุ 5,843,444 common shares held by non-affiliates ณ 2025-06-30 กับ public-float USD 35,178,000; accepted 2026-03-20T21:51:49Z ไม่ต้องหารด้วยราคาที่เดาขึ้น [AHT 10-K](https://www.sec.gov/Archives/edgar/data/1232582/000123258226000067/aht-20251231.htm)
- **AMC:** ระบุ 433,143,561 Class A non-affiliate shares ณ 2025-06-30 พร้อม USD 1,342,745,039 และราคา $3.10; accepted 2026-02-23T12:07:22Z ใช้จำนวนที่รายงานตรง ไม่ใช้ 529,547,465 total shares outstanding ณอีกวันมาทดแทน [AMC 10-K](https://www.sec.gov/Archives/edgar/data/1411579/000141157926000016/amc-20251231x10k.htm)

สองกรณีนี้อยู่ใน status `SEC_REPORTED_SHARE_COUNT_ONLY` โดย subtype `REPORTED_NONAFFILIATE_COUNT` เพื่อแยกจาก generic total share counts ไม่มีการอ้างว่าจำนวนดังกล่าวยังใช้ได้รายวันในช่วง M1

## ข้อจำกัดที่พบจาก filings จริง

- **ALIT / BRCC:** public-float wording เป็น issuer/generic common equity ขณะที่ cover ระบุหลาย common classes ยังไม่ได้พิสูจน์ class allocation/economic rights ครบ จึง `AMBIGUOUS_SHARE_CLASS` ไม่อนุมาน float ทั้ง issuer เป็น class ที่ Massive ติดตาม
- **HCWC:** มี quoted price $0.76 และ rounded USD $11.4M ซึ่งหารได้เหมือนอยู่ตรงขอบ 15M แต่ยังมี class/basis history ที่ต้องตรวจต่อ จึงคง `INSUFFICIENT_PRICE_BASIS` ไม่ใช้ apparent ratio เพื่อตัดสิน eligibility
- **AIB:** รายงาน public-float USD เป็น 0 เป็น disclosure ที่พบจริง ไม่ใช่หลักฐานว่า current/tradable free-float shares เท่ากับ 0
- หลายบริษัทให้ public-float USD และ measurement date แต่ไม่ระบุราคาต่อหุ้นที่ใช้ การมี shares outstanding ใน cover อีกวันไม่ได้แก้ปัญหานี้
- Source formats แตกต่างกันทั้ง inline scale, context dimensions, long hidden XBRL headers และ amendments Parser จึงรักษา original context และค้น cover passage โดยไม่ตัดทิ้งที่ fixed 80KB แรก

## Availability และ staleness เทียบ previous RTH close

Measurement date, filing date, acceptance timestamp และ actual publication time เป็นคนละ field โค้ดกรอง future filings และเทียบ acceptance กับ UTC anchor ของแต่ละ cycle โดยไม่เดา timezone ให้ timestamps ที่ไม่ระบุ timezone

จาก matched companyfacts/submissions พบ accepted public-float **USD** observation ก่อน anchor ใน sample pairs ทั้ง 2,880 คู่ แต่ measurement age ของค่าที่เลือกอยู่ระหว่าง **146–838 วัน** นี่เป็นเพียง USD disclosure availability lower-bound ไม่ใช่ 2,880 usable float-share observations ยังไม่ได้กำหนด permitted staleness หรือ validity ผ่าน corporate actions

Earliest matched acceptance ของทุก concepts ที่ดึงได้คือ 2011-08-02T20:27:17Z ซึ่งไม่ใช่วันที่เริ่ม coverage ของ float หรือการยืนยัน first publication เวลา first available จริงบน sec.gov ยัง unknown/null SEC ระบุว่า acceptance กับการเผยแพร่อาจมี lag และไม่มี timestamp รับรองเมื่อเนื้อหาปรากฏครั้งแรก จึงไม่ตั้ง `available_at=acceptance_at` หรืออ้างว่าค่า accepted ก่อน close เล็กน้อยต้อง public แล้ว [SEC timestamp FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)

## Splits, dilution และ share-basis quality

Local M1 corporate-action evidence มี CREG reverse split 10:1 วันที่ 2026-06-16, GORO 4:1 วันที่ 2026-07-20 และ GPUS 5:1 วันที่ 2026-08-25 พร้อม stock dividend วันที่ 2026-09-15 เหตุการณ์เหล่านี้เกิดหลัง measurement dates ของ estimates

Pilot รักษา original measurement basis และ **ไม่หารปรับตัวเลขเดินหน้าตาม split ratio** เพราะ split อย่างเดียวไม่ account dilution, class transfers หรือ affiliate changes ระหว่างทาง แม้ 10-Q จะมี total shares outstanding ใหม่ก็ไม่ใช้แทน float Quality ณ measurement date มี source evidence; post-split/dilution daily reconstruction ยังไม่ได้ validated

ไม่ได้ดึง Massive Current Float เพิ่ม: งานนี้กำหนด no paid APIs และไม่มี free current-float capture สำหรับ sampled securities ใน local evidence จึงรายงาน comparison เป็น `NOT_PERFORMED_NO_FREE_CURRENT_FLOAT_CAPTURE_FOR_SAMPLE` แทนการทำ historical/current comparison ที่ไม่มีคู่ข้อมูล

## Code, schema และ reproduction

- [Standalone extraction/review code](../../scripts/sec_float_pilot.py)
- [Versioned SEC evidence schema](../../schemas/sec-float-evidence-v1.json)
- [Reviewed source bases และ passages](sec-float-reviewed-bases-v1.json)
- [Machine-readable coverage ล่าสุด](sec-float-coverage-v2.json)
- [Offline unit tests](../../tests/test_sec_float_pilot.py)

Raw source/cache และ full results อยู่ใน ignored `data/sec-pilot-20261115-v2/`; original blocked attempt อยู่ใน v1 ไม่ overwrite M1 artifacts Public reviewed passages, source URLs/hashes และ compact coverage อยู่ใน Git Contact email/cookies/request auth headers ไม่อยู่ใน outputs

```sh
# ตั้ง SEC_USER_AGENT เป็น identified name/contact ใน local shell โดยไม่ commit contact
.venv/bin/python scripts/sec_float_pilot.py select \
  --manifest reports/m1-universe-120-20261115-v2/manifest.json \
  --output data/sec-pilot-NEW-RUN/sample.json
.venv/bin/python scripts/sec_float_pilot.py run \
  --sample data/sec-pilot-NEW-RUN/sample.json \
  --root data/sec-pilot-NEW-RUN --output data/sec-pilot-NEW-RUN/results.json

# Offline reproduce จาก raw cache ที่มีอยู่แล้ว ไม่เรียก SEC เพิ่ม
.venv/bin/python scripts/sec_float_pilot.py run --offline \
  --sample data/sec-pilot-20261115-v1/sample.json \
  --root data/sec-pilot-20261115-v2 \
  --output data/sec-pilot-20261115-v2/results-normalized-v2.json
.venv/bin/python scripts/sec_float_pilot.py review \
  --results data/sec-pilot-20261115-v2/results-normalized-v2.json \
  --reviews docs/research/sec-float-reviewed-bases-v1.json \
  --cache-root data/sec-pilot-20261115-v2/cache \
  --output data/sec-pilot-20261115-v2/results-reviewed-v1.json
.venv/bin/python scripts/sec_float_pilot.py summarize \
  --sample data/sec-pilot-20261115-v1/sample.json \
  --results data/sec-pilot-20261115-v2/results-reviewed-v1.json \
  --output docs/research/sec-float-coverage-v2.json
.venv/bin/python -m pytest -q tests/test_sec_float_pilot.py
```

Client มี persistent request budget, 1.1-second spacing, connect/read timeouts 10/30 วินาที, response size limit 30 MiB และ elapsed checks ระหว่าง stream หยุด host เมื่อ 403/429 และไม่ auto-retry Failed response ไม่ใช่ empty dataset Cache ตรวจ SHA-256 ก่อน reuse รักษา original byte hashes ส่วน parser/reviewer outputs แยกเวอร์ชัน

SEC APIs ให้ standard-taxonomy entity-wide facts จึงต้องดู original disclosures สำหรับ class-specific interpretation ไม่ใช่ daily float feed [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) Rate policy และ declared User-Agent อ้างอิง [SEC Developer Resources](https://www.sec.gov/about/developer-resources)

## การ scale และ next step

SEC เหมาะเป็นแหล่ง historical filing evidence แบบไม่เพิ่ม subscription และ pilot พิสูจน์ว่าบาง disclosures ให้ source-supported share estimates หรือ direct non-affiliate counts ได้ การอ่าน 96 objects รวม decoded payload ประมาณ 163 MB ใน sample นี้ยังไม่ใช่ benchmark ของ full-universe throughput

ควรให้ Research Lead review ทั้ง 6 usable point observations และ 2 ambiguous class cases ก่อนกำหนด uncertainty, staleness และ share-basis rules จากนั้นเพิ่ม targeted filing/context handling และ validated corporate-action intervals ใน research estimate cohort แยกต่างหาก การค้น relevant historical submission shards ต้องเป็นงาน bounded ถัดไป ไม่เปลี่ยนเป็น bulk download ทันที

ยังไม่ extrapolate 4/24 หรือ 6/24 เป็น 120-cycle universe coverage และไม่เปลี่ยน primary historical float gate ค่าทั้งหมดเป็น dated research evidence; **M1 ยังคง `BLOCKED_DATA` และ M2 ยังไม่เริ่ม**
