# SEC EDGAR Historical Float feasibility และ reconstruction pilot

วันที่ 15 พฤศจิกายน 2026 · Outcome ปัจจุบัน: **`ACCESS_BLOCKED`** · M1: **`BLOCKED_DATA`**

ได้คัดและตรวจ mapping evidence ของ historical securities 24 ตัวจาก M1 exploration universe และ execute SEC pilot จริงแล้ว คำขอแรกถูก SEC ปฏิเสธ HTTP 403 พร้อมหน้า “Your Request Originates from an Undeclared Automated Tool” จึงหยุดเรียก host เพิ่ม ผลนี้ยังใช้วัด coverage หรือความถูกต้องของ float reconstruction ไม่ได้

ไม่มี SEC-derived estimate ถูกส่งเข้า M1 ไม่มี current-float substitution และไม่มีการเริ่ม M2 Original M1 artifacts และ strict PIT gate คงเดิม

## Sample ที่ใช้จริง

เลือกจาก `m1-universe-120-20261115-v2` โดยใช้ exploration 80 cycles เท่านั้น Records ต้องผ่าน historical listing, price, type และ identity gates แต่ float ยัง unresolved จึงเรียกว่า feasibility candidates ไม่ใช่ verified micro-float population

แต่ละตลาดเลือก 4 securities ที่เรียง split/change flags ก่อน และอีก 4 ตัวแรกตาม ticker จากกลุ่มไม่มี flags กำหนด selection ก่อนอ่าน SEC outcomes รวม **24 securities: NASDAQ 8, NYSE American 8, NYSE 8** มี split flags 12 ตัว และ change/unverified-observation flags 5 ตัว ตัวอย่างทั้งหมดเคยมี previous RTH close อยู่ในช่วง `0 < P0 <= 3` ใน exploration

| Primary listing | Securities |
| --- | --- |
| NASDAQ | AMIX, BYND, CREG, FEED, AAME, ABAT, ABOS, ABVC |
| NYSE American | GORO, APUS, GPUS, HCWC, AEON, AGIG, AIB, AIM |
| NYSE | ALIT, BRCC, LFT, NRDY, ACH, AHT, AIV, AMC |

Sample เป็น purposive feasibility sample ไม่ representative และไม่ได้เลือกจาก continuation outcomes Change flags ไม่ใช่หลักฐาน delisting/rename; ยังไม่มี SEC confirmation ของกรณีเหล่านั้น และไม่อ้างว่าได้ครอบคลุม filing coverage conditions จริงก่อนเข้าถึง filings

ทุกตัวมี CIK จาก historical Massive reference พร้อม security ID, cycle ที่เลือก, P0, source snapshot hash และ raw-reference locator เก็บใน local sample manifest การมี CIK 24/24 คือ structural issuer mapping ไม่ใช่ SEC corroboration หรือ share-class mapping สำเร็จ

## ผล live access ที่สังเกต

```text
GET https://data.sec.gov/submissions/CIK0001617867.json
HTTP 403
Content-Type: text/html
Response body: 4818 bytes
Body SHA-256: 1f845d94567f549891225527b258d6b38fc34429e15c1c4586dbd067ee667437
Requested: 2026-11-15T03:09:42.911790+00:00
Received: 2026-11-15T03:09:44.131254+00:00
```

ส่ง identified User-Agent ระบุเจ้าของ/project/GitHub contact URL พร้อม `Accept-Encoding: gzip, deflate` แต่ SEC ยังจัด request เป็น undeclared automation ข้อความปฏิเสธไม่ใช่ JSON company submissions และไม่ใช่หลักฐานว่า AMIX ไม่มี filing

Client บันทึก failed response และหยุด host หลัง 403/429 ข้อมูล 23 securities ถัดไปถูกทำเครื่องหมาย blocked-before-request; ไม่ส่ง HTTP requests ซ้ำทุก ticker Companyfacts และ original filing documents ยังไม่ได้ดึง จึงไม่มี accession, actual filing acceptance time หรือ public-float disclosure ที่ตรวจยืนยันได้จาก pilot นี้

การลองแก้ User-Agent ด้วยอีเมลจาก Git config ยัง **ไม่ได้ถูก execute**: automatic approval review ปฏิเสธการเปิดเผย contact ภายนอกก่อนผู้ใช้อนุญาต รอการอนุญาตใช้ contact แล้วจึงพิจารณาคำขอเดิมแบบ bounded อีกครั้ง ไม่เปลี่ยน IP/proxy/identity เพื่อหลบ SEC restriction

## Coverage และ quality ปัจจุบัน

| Metric | ผลจริงและความหมาย |
| --- | --- |
| Securities sampled / local mapping examined | 24 |
| CIK present in historical Massive evidence | 24/24 = 100%; issuer-level only |
| SEC issuer metadata corroborated | 0 confirmed; ยังวัด mapping accuracy ไม่ได้ |
| SEC HTTP attempts | 1; HTTP 403 |
| Submissions / companyfacts / original documents ที่อ่านสำเร็จ | 0 / 0 / 0 |
| Filing availability rate | **unknown/null**; ห้ามตีความเป็น 0% coverage |
| Public float disclosures observed | 0 retrieved; underlying coverage unknown |
| Defensible float-share estimates | 0 produced |
| Classification | UNRESOLVED 24 |
| Earliest known publication / acceptance | unknown/null |
| Staleness relative to cycles | unmeasurable without observations |
| Reverse-split reconstruction quality | unassessed; local split flags มี 12 securities |
| Current Massive Float comparison | ไม่ได้ทำ เพราะไม่มี comparable SEC estimates |
| 120-cycle coverage | 2,880 sample-security/cycle pairs ใน scope; ไม่มี pair ที่ validated; complete-universe coverage unknown |

Machine-readable results: [sec-float-coverage-v1.json](sec-float-coverage-v1.json) แยก successful retrievals ออกจาก unknown source coverage มี security IDs, CIKs, sample dates/P0, per-security status, errors, staleness placeholders และ HTTP evidence พร้อม hash ไม่มีการ extrapolate 0 retrieved เป็น coverage ของ SEC ทั้งระบบ

ไม่เรียก paid API เพื่อเอา current float มาเปรียบเทียบ และไม่ใช้ current float เติม historical evidence การไม่มี comparable observations ครั้งนี้จึงเป็น `NOT_PERFORMED_NO_COMPARABLE_HISTORICAL_ESTIMATES` แทนการสร้างตัวเลข comparison

## Extraction และ reconstruction ที่ implement

โค้ด standalone: [sec_float_pilot.py](../../scripts/sec_float_pilot.py) และ versioned contract: [sec-float-evidence-v1.json](../../schemas/sec-float-evidence-v1.json)

1. คัด historical sample จาก local immutable M1 Parquet และเก็บ source hashes โดยไม่เขียนข้อมูลกลับ M1
2. ดึง dated filing metadata จาก submissions และ concepts จาก companyfacts โดยกรอง filing/measurement dates ไม่เกิน study end 2026-11-13; ไม่เลือก latest facts ย้อนแทนทุกช่วง
3. แยก `dei:EntityPublicFloat` unit USD ออกจาก `dei:EntityCommonStockSharesOutstanding`, `us-gaap:CommonStockSharesOutstanding` และ `us-gaap:CommonStockSharesIssued` unit shares ไม่ใช้ outstanding/issued เป็น float
4. เลือก original annual filing ล่าสุดกับ 10-Q ล่าสุดต่อ security จาก recent submissions อย่างละหนึ่งไฟล์ จำกัดสูงสุด 48 original documents; historical submission shards ยังไม่ดาวน์โหลดและต้องเปิดเผยขอบเขตนี้
5. Parse inline XBRL เพื่อรักษา context dates/dimensions, unit definitions, scale, sign และ original fact text พร้อม passages รอบ non-affiliate disclosure เก็บ full source ใน ignored local cache
6. `review` command รับ human-reviewed basis ที่ผูก original document URL/hash, accession, observation date, share class, explicit price และ supporting passage จึงค่อยคำนวณ USD/price ตรวจ amount/date กับ original inline XBRL, USD unit และ literal quoted price ใน passage
7. หาก class/date/price/share basis ยืนยันไม่ได้ จะได้ `AMBIGUOUS_SHARE_CLASS` หรือ `INSUFFICIENT_PRICE_BASIS` ไม่เรียก historical price API เพื่อหา denominator มาแทน
8. แยก acceptance timestamp, measurement date และ `available_at` โดย actual publication time ยังคง null ไม่เดา timezone ให้ naive acceptance timestamps

Review output ต้องเป็นไฟล์ใหม่ ไม่ overwrite original result และค่าที่คำนวณได้เป็น **`SEC_DERIVED_HISTORICAL_ESTIMATE`** เท่านั้น ไม่ใช่ verified historical free float Matching hash/text พิสูจน์ lineage แต่ยังไม่รับรอง judgment เรื่อง share-class allocation จึงเก็บ reviewer และ basis rationale ไว้ตรวจต่อ

Status contract รองรับครบ: `SEC_DERIVED_HISTORICAL_ESTIMATE`, `SEC_REPORTED_SHARE_COUNT_ONLY`, `INSUFFICIENT_PRICE_BASIS`, `AMBIGUOUS_SHARE_CLASS`, `UNRESOLVED` ข้อมูลนี้ไม่ใช้ schema ของ primary M1 gate และ `verified_pit` ต้องเป็น false เสมอ

## PIT, measurement staleness และ share basis

SEC companyfacts เป็นการรวม standard-taxonomy entity-wide XBRL facts จึงไม่รับรอง class-specific allocation หรือ custom/dimensional disclosures ครบทุกกรณี ต้องดู original contexts และ narrative ข้อมูล SEC ไม่ได้ให้ daily free-float shares โดยตรง [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

Public-float USD อาจวัด ณ historical measurement date แต่ยื่น filing ภายหลัง; ต้องใช้ accession/acceptance timestamp ของ filing ที่เปิดเผยค่านั้นจริง ไม่ใช้ measurement date เป็น publication date หรือใช้ amendment ที่ใหม่กว่าโดยไม่สน look-ahead

SEC ระบุว่าการเผยแพร่อาจตามหลัง acceptance และไม่มี timestamp รับรองเมื่อเนื้อหา first available บน sec.gov โค้ดจึงรายงาน accepted-before-anchor เป็นเพียง lower-bound check และไม่อ้างว่า filing ที่รับก่อน previous RTH close เล็กน้อยต้อง public แล้ว [SEC timestamp FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)

`availability()` คำนวณ acceptance เทียบแต่ละ anchor และ measurement age เป็นวัน แต่ไม่ authorize carry-forward หลัง dilution/split หรือสร้าง validity interval จาก annual value เอง การวัด coverage ที่มีประโยชน์หลังเข้าถึงข้อมูลต้องรายงานทั้ง USD disclosure coverage, defensible share-estimate coverage และ strict availability coverage แยกกัน

Reverse split หลัง measurement date อาจทำให้ raw historical share count เทียบกับ cycle basis ไม่ได้ ต้องตรวจ split ratios/effective dates, actual price basis และ subsequent dilution พร้อม evidence ก่อนอนุญาตให้ใช้ข้าม cycle หาก class allocation หรือ historical basis ขัดแย้ง ให้ unresolved ไม่ปรับตัวเลขเอง

## Fair Access, caching และ reproduction

SEC แนะนำ declared User-Agent และจำกัดรวมไม่เกิน 10 requests/วินาที โค้ดนี้ single worker เว้นอย่างน้อย 1.1 วินาทีต่อ request และมี persistent budget 110 attempts รวม failed attempts ไม่มี automatic retries/redirects และหยุด host เมื่อพบ 403/429 [SEC Developer Resources](https://www.sec.gov/about/developer-resources)

ใช้ connect/read timeout 10/30 วินาที จำกัด response 30 MiB และ elapsed check 60 วินาทีระหว่างอ่าน chunks Cache ผูก URL/hash; resume อ่าน cache เดิมและตรวจ checksum ก่อนใช้ Failed HTTP response ยังเก็บไว้เป็น evidence แต่ไม่ตีความเป็น empty facts ไม่อ่าน paid credentials/netrc และไม่ persist User-Agent contact value หรือ cookies

```sh
# คัด sample ซ้ำจาก M1 data ที่อยู่ในเครื่อง
.venv/bin/python scripts/sec_float_pilot.py select \
  --manifest reports/m1-universe-120-20261115-v2/manifest.json \
  --output data/sec-pilot-NEW-RUN/sample.json

# หลังอนุมัติ contact และแก้ access limitation แล้ว จึงใช้ --user-agent ที่ระบุตัวตนถูกต้อง
.venv/bin/python scripts/sec_float_pilot.py run \
  --sample data/sec-pilot-NEW-RUN/sample.json \
  --root data/sec-pilot-NEW-RUN \
  --output data/sec-pilot-NEW-RUN/results.json

# Reproduce สรุปผลรันนี้โดยไม่ใช้ network
.venv/bin/python scripts/sec_float_pilot.py summarize \
  --sample data/sec-pilot-20261115-v1/sample.json \
  --results data/sec-pilot-20261115-v1/results.json \
  --output docs/research/sec-float-coverage-v1.json

.venv/bin/python -m pytest -q tests/test_sec_float_pilot.py
```

Raw cache/sample/full evidence อยู่ใน `data/sec-pilot-20261115-v1/` ซึ่งไม่เข้า Git มี SHA-256 อ้างใน compact report Repository มี extraction code/schema/tests และ compact coverage report; clone อย่างเดียวไม่มี raw datasets สำหรับ reproduce การดาวน์โหลดครั้งนี้

Tests ใช้ synthetic fixtures ชัดเจน ครอบคลุม iXBRL scale/context/unit, issuer-class ambiguity, wrong measurement date, split-basis mismatch, explicit-price evidence, missing source, future filing cutoff, acceptance หลัง close, cache corruption, request budget และ 403 stop/resume Synthetic values ไม่เข้ารายงานตลาด

## การ scale และขั้นต่อไป

ยังประเมิน empirical coverage/throughput ของ SEC สำหรับ target universe ไม่ได้จาก access failure ครั้งนี้ ขั้นต่อไปคืออนุมัติ contact ที่ใช้กับ SEC แล้วทดลอง request เดิมแบบ bounded เมื่อ access ผ่าน จึง resume 24-security pilot ตรวจ original annual/quarterly documents และเก็บ actual acceptance/source evidence

จากนั้นให้ Research Lead ตรวจตัวอย่างที่ derive ได้เทียบ original disclosure, share-class mapping, dilution และ reverse splits ก่อนกำหนด validity/staleness policy การรวมเป็น daily panel ต้องแสดง missingness และ discontinuities; ไม่อาจคาดว่า SEC จะเติม float ให้ครบ 120 cycles ได้โดยตรง

ยังไม่ควร scale ทั้ง universe หรือเปลี่ยน primary gate จากผลนี้ SEC ยังคงเป็น no-additional-subscription candidate ที่มีคุณค่าด้าน filing provenance แต่ความครอบคลุม defensible historical share estimates ยังต้องพิสูจน์
