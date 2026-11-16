# TASK 005 — สรุปผลตรวจและเงื่อนไขก่อนเปิด holdout

ตรวจ offline จาก Full30 โดยเริ่มที่ baseline `1c02e67` และรันใหม่เป็น `m5-preholdout-audit-20261116-v2` ครบ 30 วัน, 720 opportunities, 93 เหตุการณ์ และ 627 opportunities ที่ไม่เกิดเหตุการณ์ โดยแยก Development10 ไว้ตามเดิม ไม่เรียกข้อมูลตลาดเพิ่มและไม่เปิด holdout

## ผลที่ตรวจยืนยันได้

สร้างลำดับราคาจาก raw cache ใหม่ครบ 93 เหตุการณ์ โดยใช้ implementation ตรวจสอบแยกจาก replay เดิม ตรวจเงื่อนไข trade, SIP timestamps ระดับ nanosecond, ties, corrections, threshold จาก P0, ราคาที่แตะจริง และ first passage ของทุก barrier/gap policy พบความคลาดเคลื่อนกับผลเดิม **0 เหตุการณ์** ตรวจ pagination chain ของ source windows, hashes, event IDs และน้ำหนักทั้ง 720 opportunities แล้ว

| +3%/−3%, primary no-mechanical-gap | เหตุการณ์ | ขึ้นก่อน | ลงก่อน | Neither | น้ำหนัก: ขึ้นก่อน | น้ำหนัก: ลงก่อน | น้ำหนัก: Neither |
|---|---:|---:|---:|---:|---:|---:|---:|
| ทั้งสอง strata | 93 | 26 | 62 | 5 | 28.96% | 65.56% | 5.48% |
| Current-float proxy | 62 | 15 | 44 | 3 | 24.20% | 71.09% | 4.70% |
| Complementary | 31 | 11 | 18 | 2 | 35.60% | 57.82% | 6.58% |

แต่ละ stratum มี 360 sampled opportunities ก่อนคัดเหตุการณ์ ตารางใช้ทุก initial event ของ stratum เป็น denominator รวม Neither ไม่มีการตัดเหลือเฉพาะเหตุการณ์ที่แตะ barrier น้ำหนักอ้างจาก `reports/m4-temporal-cumulative30-20261116-v1/analytical-weights.json` โดยจับคู่ cycle/security กับผล independent audit ส่วนต่างลงก่อนลบขึ้นก่อนแบบถ่วงน้ำหนักรวมคือ **36.60 percentage points** เป็นผล exploration ที่เห็นก่อนตั้งคำถามหลัก ไม่ใช่ผลยืนยันทฤษฎีหรือผลกำไร

Primary barrier ไม่มี CENSORED/AMBIGUOUS ใน 93 เหตุการณ์นี้ แต่ forward returns มี missingness สูง: 5/15/30/60 นาที censor 43/48/56/57 เหตุการณ์ตามลำดับ ไม่เติมผลตอบแทนเป็นศูนย์และไม่ใช้ราคาล่าสุดที่หมดอายุแทน

ใน 271 จุดประเมินที่ censor รวม 6 horizons (นับจุดประเมินซ้ำเหตุการณ์ได้) พบ 155 จุดไม่มีรายการที่ provider ส่งกลับในช่วง 60 วินาทีล่าสุด, 86 จุดมีรายการแต่ถูกกติกาคัดออก, 19 จุดมี eligible print แต่ยังติดสาเหตุอื่น เช่น ข้ามช่วงไม่สังเกต และ 11 จุดมี target หลัง cycle จบ การไม่มีรายการใน window ที่ pagination ครบอาจสอดคล้องกับสภาพคล่องต่ำ แต่ไม่พิสูจน์ว่า feed สมบูรณ์หรือไม่มี halt

Sensitivity gap 300 วินาทีให้ขึ้น/ลง/Neither/censor = 26/42/2/23; gap 900 วินาที = 26/56/4/7 เทียบ primary 26/62/5/0 ไม่เปลี่ยน primary policy เพื่อเพิ่มหรือลดผลที่ต้องการ

NBBO ที่ touch ใช้งานได้ 50/93: อยู่ระหว่าง bid/ask 43 และสูงกว่า ask 7; อีก 43 ขาดหรือไม่ผ่านคุณภาพ จึงไม่ใช่หลักฐาน executable fills ทั้ง 93 trigger มีขนาดอย่างน้อย 100 หุ้น แต่ odd-lot sensitivity เปลี่ยน touch record 58 ครั้ง พบ same-SIP หลายราคา 1 ครั้งและไม่พบ touch correction ที่ยัง unresolved ใน sample นี้

P0 ตรงกับ M1 source ที่มี hash ครบ ทั้ง 93 ผ่าน action/exchange gates เดิมและระบุ `NO_SPLIT_OBSERVED`; ไม่พบ corporate action ใหม่ที่พิสูจน์ความไม่สอดคล้องของ basis ภายใน sample นี้ แต่ไม่ได้รับรองว่าผู้ให้ข้อมูลไม่ตกหล่น corporate actions และ P0 ยังเป็น `UNADJUSTED_PROVIDER_DAILY_CLOSE` / `RETROSPECTIVE_NOT_EXECUTABLE` ไม่ใช่การรับรองราคา official auction หรือ historical float แบบ PIT

C0/C1/C2 ใช้ initial risk set เดียวกัน ตรวจ common-clock marks 5,952 จุดโดยไม่มี error และคง unconfirmed/insufficient/not-yet-confirmed/censored ไว้ครบ C2 confirmed เพียง 9 เหตุการณ์ ยังเล็กเกินกว่าจะยืนยันประสิทธิภาพ

## สิ่งที่ยังไม่ผ่านก่อนใช้ holdout เชิงยืนยัน

- **Technical audit: PASS; overall readiness: CONDITIONAL; formal statistical clearance: BLOCKED.** การจำลอง rare-domain ให้ candidate interval coverage 91.5% ต่ำกว่า diagnostic floor 93% (1,000 repetitions; Monte Carlo SE 0.88 percentage points)
- อีกสามสถานการณ์ได้ 94.9%, 96.6%, 95.2% สำหรับ estimand ของ observed classifications ภายใต้ประชากรจำลองเฉพาะนั้น ไม่ใช่หลักประกัน 95% CI ของตลาด โดย informative missingness ครอบคลุม latent complete-path target เพียง 38.7%
- Protocol v2 กำหนดให้ผ่านทั้งสี่สถานการณ์ ห้ามเลือกทิ้งกรณีที่ไม่ผ่าน ต้องมี statistical amendment และตรวจ calibration ใหม่ก่อนเข้าถึง holdout เกณฑ์จำนวนเหตุการณ์ขั้นต่ำเพียงอย่างเดียวยังไม่พิสูจน์ว่าแก้ undercoverage ได้
- Holdout ต้องมีการอนุมัติใหม่และงบเรียกข้อมูลที่ตรึงก่อนเริ่ม ชุดนี้ระบุ sampling rule เท่านั้น ยังไม่สร้างรายชื่อ securities หรือเรียก tick ของ holdout ไม่ถือว่าอนุมัติการทำงานขั้นต่อไป

[Protocol v2](../plans/TASK-005-holdout-preregistration-v2.md) กำหนด primary estimand, unknown-outcome bounds, sampling design, fixed barriers, common-clock secondary comparisons และ SUPPORTED/UNSUPPORTED/INCONCLUSIVE ไว้ล่วงหน้า โดยเปิดเผย exploratory origin ของคำถาม ห้าม retune หลังเห็นผล holdout

## หลักฐานและการรันซ้ำ

รายงานเต็มและหลักฐานอยู่ที่ `reports/m5-preholdout-audit-20261116-v2/` มี event-level JSON/Parquet, censoring witnesses, calibration, source hashes, protocol binding และ manifest พร้อม local ZIP ที่ตรวจแล้ว Raw data ไม่ถูกส่งขึ้น GitHub ส่วน Parquet เป็น audit results ไม่ใช่ bulk market data

บน checkout ใหม่ ให้สร้าง v1 audit ด้วย `configs/task-005-audit-v1.json` ก่อน แล้วรัน v2 ด้วย `configs/task-005-audit-v2.json` เพื่อให้มีผลเปรียบเทียบตาม config; ทั้งสองใช้ cache เดิม offline เท่านั้น หากมี run ID แล้วให้เลือก ID ใหม่ ห้ามเขียนทับ จากนั้นรัน `market_lab.audit_supplement`, pytest และ `scripts.finalize_preholdout_audit_v2` ตามคำสั่งในรายงานเต็ม Publication ของ v2 ตรวจ hash ของ artifacts เดิม 13,818 ไฟล์และผลรันซ้ำ 7 ชุดตรงกัน

Tests ผ่าน 255 tests; raw-cache reads รวม supplemental audit 1,951,463,480 bytes ต่ำกว่างบ 8 GiB ไม่มีการแก้ M1, SEC evidence, กฎเดิม หรือ prior research runs
