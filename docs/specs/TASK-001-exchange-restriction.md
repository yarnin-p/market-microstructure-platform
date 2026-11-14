# TASK 001 — Historical Universe Builder: Exchange Restriction

วันที่: 2026-11-14

สถานะ: ผู้ใช้อนุมัติ greenfield implementation แล้ว มี executable pipeline, unit/integration tests และ consolidated bundle foundation; ผล live execution และข้อจำกัดข้อมูลให้ดู reports และ README

## ขอบเขตและหลักฐานปัจจุบัน

ข้อกำหนดนี้ใช้กับ historical universe ทั้ง 120 trading cycles และ tick-level replay research ทั้งหมดที่ต่อยอดจาก universe ดังกล่าว

ตอน intake ครั้งแรก repository มีเพียง `.git` ต่อมาผู้ใช้ยืนยันว่าเป็น greenfield และให้ implement โดยไม่รอ source เดิม การตัดสินใจใหม่นี้ supersede ข้อความรอ implementation ต้นฉบับด้านล่าง

## User decisions — implementation update

- Anchor eligibility ณ previous RTH close; freeze initial universe ต่อ cycle
- Track historical exchange changes ภายใน cycle และ revalidate ที่ event timestamp เมื่อพบ change; ขาดหลักฐานให้ UNRESOLVED
- Primary exchange: NASDAQ / NYSE American (AMEX) / NYSE; ไม่กรอง trade execution venue
- Security type: Common Stock (`CS`) เท่านั้น ไม่รวม ADR/ADRC, ETF, warrants หรือประเภทอื่น Missing type เป็น UNRESOLVED; ไม่เพิ่มเงื่อนไขประเทศจดทะเบียนบริษัทจากการตีความ US listing
- Previous RTH close: `0 < price <= 3`; float: `100000 <= shares_float <= 15000000`
- Massive historical float unavailable: ใช้ reproducible unresolved workflow และ optional audited effective-dated evidence; ห้ามใช้ float ปัจจุบันหรือ shares outstanding แทน
- Final external output ต่อ experiment เป็น `research_bundle.zip` เดียว ตาม standardized research bundle contract ไม่ต้องรวม daily exports เอง
- TASK 001 ยังไม่ดาวน์โหลด bulk ticks หรือสร้าง continuation research findings

ไม่เปลี่ยน float range 100,000–15,000,000, previous RTH close price range $0–$3, นิยาม +10%, confirmation, pullback, continuation หรือ false-spike classification ตามข้อความส่งต่อของผู้ใช้ ทั้งหมดยังต้องตรวจเทียบกับต้นฉบับ

## Mandatory requirements

| ID | ข้อกำหนด |
| --- | --- |
| EX-01 | รับเฉพาะ security ที่มี primary listing exchange อยู่ใน NASDAQ, NYSE American (AMEX) หรือ NYSE |
| EX-02 | ตัด OTC, OTCQB, OTCQX, OTC Pink และทุก exchange นอก allowlist รวมถึงตลาดอื่นที่มีเจ้าของหรือ brand เดียวกัน |
| EX-03 | ใช้ Massive reference-data identifiers และ mapping ที่ตรวจสอบได้เป็น canonical exchange names ห้ามตัดสินด้วย substring ของชื่อหรือชื่อกลุ่มบริษัท |
| EX-04 | ประเมิน listing eligibility ตาม historical trading cycle ของแต่ละ record ห้ามนำ listing ปัจจุบันไปใช้ย้อนหลัง |
| EX-05 | เก็บ raw exchange codes และ normalized classifications ใน universe snapshots พร้อมหลักฐานย้อนตรวจได้ |
| EX-06 | หากยืนยัน historical listing eligibility ไม่ได้ ให้เป็น UNRESOLVED และไม่นำเข้า eligible universe โดยอัตโนมัติ |
| EX-07 | เพิ่ม unit tests สำหรับ exchange filtering และ historical exchange changes ใน builder เดิมเมื่อได้ source code |
| EX-08 | ข้อจำกัดนี้ใช้กับ primary listing เท่านั้น ห้ามใช้ allowlist นี้กรอง execution venue ของ trades หรือ quotes |

## Reference-data mapping

ใช้ `primary_exchange` จาก historical ticker reference record เป็น listing identifier และใช้ `/v3/reference/exchanges?asset_class=stocks&locale=us` ประกอบการแปลรหัส เก็บ `id`, `mic`, `operating_mic` และ `name` ที่ใช้จริงโดยไม่สลับ identifier namespaces

Canonical names ที่อนุญาตคือ `NASDAQ`, `NYSE American (AMEX)`, `NYSE` เท่านั้น

ต้องสร้าง explicit mapping จาก response ของ Massive ที่ตรวจแล้ว ไม่เดา numeric exchange IDs ไม่เพิ่มตลาดจากชื่อเจ้าของ และไม่ถือว่าทุกตลาดใน `operating_mic` เดียวกันมีสิทธิ์โดยอัตโนมัติ หากพบ segment MIC หรือ alias ให้ตรวจความสัมพันธ์ก่อนเพิ่ม mapping พร้อม version และ provenance

เอกสารนี้ยังไม่กำหนด production code-to-name table เพราะยังไม่ได้ตรวจ reference-data response ของ integration จริง Unknown หรือ unmapped code ต้องเป็น UNRESOLVED; code ที่ตรวจแล้วว่าอยู่นอก allowlist ต้องเป็น INELIGIBLE

Exchange directory เป็นแหล่งแปลรหัส ไม่ใช่หลักฐาน listing history ของ security

## Historical eligibility และ cycle boundaries

รักษา trading cycle: previous RTH close → after-hours → premarket → current RTH close โดยใช้ America/New_York, exchange calendar, DST, holidays และ early closes ตามนิยามต้นฉบับ

Historical ticker requests ต้องระบุ `date` อย่างชัดเจน เก็บ request date และ response evidence ห้าม fallback เป็น today's listing เมื่อ historical lookup ล้มเหลว และห้ามสร้าง candidate universe จากรายชื่อหุ้นที่ยัง active วันนี้เพียงอย่างเดียว

ต้องตรวจว่าข้อมูลย้อนหลังมีความละเอียดเพียงพอกับเวลาที่ประเมิน eligibility จริงหรือไม่ การมี parameter `date` ไม่ได้พิสูจน์ intraday effective time หรือ publication-time availability ของทุก field

เมื่อพบการย้ายตลาด ให้แยก security identity ออกจาก ticker label และใช้ effective-dated evidence ห้ามเขียนทับ snapshots เก่าด้วยตลาดปัจจุบัน

**การตัดสินใจที่ยืนยันแล้ว:** initial eligibility ใช้ ณ previous RTH close และ cycle interval คือ `(anchor, current RTH close]` การเปลี่ยนตลาดไม่เพิ่มสมาชิกเข้า frozen universe; ตรวจ exchange ที่ event time เมื่อพบ change และใช้ UNRESOLVED หาก effective time ไม่ชัด

## Classification และ snapshot evidence

| Classification | ความหมาย | ใช้เป็น eligible input ของ replay |
| --- | --- | --- |
| ELIGIBLE | มี historical evidence ที่ตรงเวลาประเมิน และ primary listing อยู่ใน allowlist | ผ่าน exchange gate เท่านั้น ยังต้องผ่านเงื่อนไข universe อื่น |
| INELIGIBLE | ยืนยันได้ว่า primary listing ในเวลาที่เกี่ยวข้องอยู่นอก allowlist | ไม่ใช้ |
| UNRESOLVED | ข้อมูลขาด, unknown mapping, หลักฐานขัดแย้ง หรือเวลาการเปลี่ยนตลาดไม่ชัด | ไม่ใช้; เก็บไว้ตรวจสอบ |

Snapshot ต้องเก็บข้อมูลต่อไปนี้ โดยปรับชื่อ field ให้สอดคล้องกับ schema เดิมเมื่อกู้ source ได้:

- cycle identifier, cycle boundaries และ eligibility evaluation time/policy
- ticker และ security identifiers ที่ provider มีให้ พร้อมสถานะการ resolve identity
- raw `primary_exchange` แบบไม่แก้ไข, canonical exchange name และ normalized classification
- eligibility reason เช่น `ALLOWED_PRIMARY_LISTING`, `DISALLOWED_PRIMARY_LISTING`, `MISSING_HISTORICAL_REFERENCE`, `UNMAPPED_EXCHANGE_CODE`, `AMBIGUOUS_EFFECTIVE_TIME`, `CONFLICTING_EVIDENCE`
- source endpoint, historical request date, retrieval timestamp, effective interval เมื่อมีหลักฐาน และ reference response locator/hash โดยไม่บันทึก API credentials
- mapping version และ eligibility-policy version เพื่อให้ replay อ้างอิงผลเดิมได้

เก็บ INELIGIBLE และ UNRESOLVED ใน audit output แยกจาก eligible input และรายงานจำนวนแต่ละสถานะต่อ cycle ห้ามใช้ null/unknown แทน false โดยไม่เก็บเหตุผล

## Tick replay contract

เลือก security จาก historical universe ที่ผ่าน exchange gate จากนั้นรับ tick data จาก execution venues ที่ provider ส่งมาได้ตาม research/data-quality rules เดิม รวมถึง venue นอกสาม listing exchanges และ TRF/off-exchange reporting ที่เกี่ยวข้อง

ห้ามใช้ trade `exchange`, `trf_id` หรือ tape เป็นตัวแทนของ primary listing eligibility ห้ามอนุมาน primary listing จาก venue ที่มีปริมาณซื้อขายสูงสุด และห้ามเพิ่ม venue predicate จาก TASK 001

## Required test matrix

กรณีต่อไปนี้เป็น acceptance cases สำหรับ executable tests ที่ต้องเพิ่มใน builder เดิม ยังไม่ได้ implement หรือรันทดสอบ:

| Test | Input / scenario | Expected result |
| --- | --- | --- |
| T01 | historical listing ที่ตรวจแล้วเป็น NASDAQ / NYSE American (AMEX) / NYSE แยกสามกรณี | ELIGIBLE สำหรับ exchange gate |
| T02 | OTC / OTCQB / OTCQX / OTC Pink แยกทุกกรณี | INELIGIBLE เมื่อมีหลักฐานยืนยัน classification |
| T03 | ตลาดอื่น เช่น NYSE Arca หรือ Nasdaq BX ที่ตรวจแล้วเป็น primary listing นอก allowlist | INELIGIBLE แม้ชื่อมี NYSE หรือ Nasdaq |
| T04 | missing, null, empty หรือ unknown primary exchange | UNRESOLVED; ไม่ auto-include |
| T05 | historic OTC → NASDAQ | cycle ก่อนเปลี่ยน INELIGIBLE; หลังเปลี่ยน ELIGIBLE ตาม effective evidence |
| T06 | historic NASDAQ → OTC | cycle ก่อนเปลี่ยน ELIGIBLE; หลังเปลี่ยน INELIGIBLE แม้ข้อมูลวันนี้ต่างออกไป |
| T07 | NYSE → NASDAQ | ผ่าน exchange gate ทั้งสองช่วง; snapshots เก็บ raw/canonical ของแต่ละช่วงถูกต้อง |
| T08 | historical response ขาดหรือ error แต่ current response eligible | UNRESOLVED; ไม่ fallback ปัจจุบัน |
| T09 | transfer ตรง boundary หรือระหว่าง cycle โดย effective time ไม่ชัด | UNRESOLVED สำหรับ record ที่ได้รับผลกระทบ |
| T10 | ticker reuse / symbol change | ไม่สืบทอด exchange history ข้าม security โดย ticker อย่างเดียว |
| T11 | alias/segment MIC ที่ยืนยัน mapping แล้ว และอีกกรณีที่ยังไม่ยืนยัน | normalize ตาม mapping version / UNRESOLVED ตามลำดับ |
| T12 | historical evidence ขัดแย้งกัน | UNRESOLVED พร้อม reason และ provenance |
| T13 | serialize/deserialize snapshot | raw code, canonical name, classification และ evidence ยังครบ |

เพิ่ม integration/regression checks แยกจาก unit tests:

- eligible stock มี trades จาก eligible listing venues, venue อื่น และ TRF: TASK 001 ต้องไม่ทำให้ ticks เหล่านี้หายไป
- ครบทุก 120 cycle ตาม calendar เดิม ไม่มีการนำ snapshot วันนี้มาทดแทนวันที่ขาด และ replay ใช้ policy/mapping version ที่อ้างอิงได้
- DST, holiday และ early-close cycles ใช้ boundaries เดิมถูกต้อง รวมถึง transfer cases
- coverage report แยก ELIGIBLE / INELIGIBLE / UNRESOLVED และไม่รายงานว่า historical verification ครบหากยังมีข้อมูลขาด

## Original intake plan (superseded by greenfield authorization)

1. รับ repository/source และ specification ต้นฉบับ ตรวจ schema, cycle eligibility timing, tests และ Massive integration
2. ตรวจ Massive reference responses และ historical listing evidence แล้วทำ versioned explicit mapping; แยก data gaps จาก implementation gaps
3. เพิ่ม exchange gate และ snapshot evidence ใน builder เดิม โดยไม่แก้สูตรหรือ research classifications
4. เพิ่ม unit tests T01–T13 และ integration/regression checks ข้างต้น
5. ประเมินใหม่ทั้ง 120 cycles พร้อม audit counts เก็บผลเดิมไว้เปรียบเทียบ และให้ replay อ่าน universe version ที่ใช้ restriction นี้

ยังไม่มีการยืนยัน account entitlements, API responses, historical coverage หรือผล replay จากการอ่าน documentation เพียงอย่างเดียว

## Official sources

ตรวจเอกสารวันที่ 2026-11-14:

- [Massive Exchanges](https://massive.com/docs/rest/stocks/market-operations/exchanges): exchange reference identifiers และ mapping attributes; endpoint ไม่ใช่ security listing history
- [Massive All Tickers](https://massive.com/docs/rest/stocks/tickers/all-tickers): historical ticker reference และ primary listing information
- [Massive Trades](https://massive.com/docs/rest/stocks/trades-quotes/trades): trade-level exchange และ TRF fields เป็นคนละบริบทกับ primary listing
