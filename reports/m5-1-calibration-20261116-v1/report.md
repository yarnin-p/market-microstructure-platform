# TASK 005.1 — Rare-event statistical calibration repair

Run `m5-1-calibration-20261116-v1`; baseline `2a1c6a5`; branch `feat/task-005-1-calibration-repair`.

**ผลตัดสิน: BLOCKED** — Fieller แก้ rare-domain ในชุดเดิมได้ แต่ไม่ผ่าน stress case ที่ตรึงก่อนทดสอบ จึงยังปลดข้อกั้นไม่ได้ ไม่เปลี่ยนวิธีหลักหลังเห็น independent validation และไม่ออก protocol v3 ที่พร้อมใช้งาน

ไม่ได้เปิด holdout หรือเรียกข้อมูลตลาดเพิ่ม ไม่เปลี่ยน Full30, 93 events, current-float proxy, M1/SEC evidence, first-touch, conditions, censoring, barriers หรือ C0/C1/C2; protocol v2 และผล 91.5% เดิมยังคงเดิม

## วินิจฉัยก่อนเปลี่ยนวิธี

ชุดเดิมสร้างซ้ำได้ตรงเดิมทั้งสี่สถานการณ์ จากประชากรและ RNG เดิม (รวม failure เดิม) รายงาน development-diagnosis.md ถูกบันทึกก่อนเปิดชุด independent; ชุดนี้ใช้พัฒนาวิธี ไม่ใช่หลักฐานอิสระ

rare_domain เดิมมีเหตุการณ์เฉลี่ย17.826 ครั้ง, 17.112/30 dates และ44.928/60 date/security strata ไม่มีเหตุการณ์ Estimated denominator RSE เฉลี่ย24.87% เทียบ regular12.08% จึงไม่ควรปฏิบัติต่อ denominator เหมือนจำนวนที่ทราบแน่นอน

Variance ของ ratio ที่เกิดจริงในการจำลอง0.0563817 แต่ค่าเฉลี่ย plug-in variance0.0481273 คิดเป็น85.36% ของ empirical variance; bias−0.00809 และ skewness−0.09263 มี boundary estimate1/1000 จึงไม่มีหลักฐานว่าความเบ้รุนแรงหรือขอบเขตเป็นสาเหตุหลักในกรณีเดิม การแยกส่วน residual ที่ known truth ได้ mean variance2187.20 เทียบ empirical2326.41; เป็น diagnostic จาก finite Monte Carlo ไม่ใช่ข้อพิสูจน์ bias เชิงทฤษฎีของ total covariance

Covariance estimator ใช้ unequal weights, month/date และ security strata, ทั้งสอง FPC และทุก zero-event opportunity ตรวจ exact enumeration ของ controlled unequal-weight population แล้วได้ covariance แบบ unbiased ตรงกัน Repeated securities และ serial dates เป็น fixed population structure ไม่ใช้ IID event bootstrap

t26 เป็น approximation ไม่ใช่ exact sparse-domain pivot Diagnostic normal-critical sensitivity อยู่ใน diagnostic-sensitivities.json ไม่ได้ใช้เลือก critical หรือเพิ่มค่าจนผ่าน

## วิธีที่ตรึงก่อนชุดอิสระ

- **FIELLER_SCORE (primary):** ค่า critical เดิม2.055529438642871 ใช้ inverse test ของ (Y−theta Z)^2 <= c^2 V(Y−theta Z) แทนการตรึง residual variance ไว้ที่ ratio estimate เก็บ raw unbounded/disconnected sets แล้วตัดกับ physical space[-1,1] อย่างชัดเจน ไม่อ้าง exact bivariate-normal Fieller theorem กับ survey design นี้
- **BONFERRONI_TOTAL_BOX (secondary):** สร้าง marginal t intervals ของสอง total โดยจัด alpha ด้วย Bonferroni แล้ว project rectangle เป็น ratio ถ้า denominator interval คร่อมศูนย์ให้ insufficient information ไม่ใช่ point estimateศูนย์ วิธีนี้ conservative แต่ marginal t approximation ไม่ใช่ finite-sample guarantee และห้ามเลื่อนเป็น primary หลังเห็น validation
- Studentized two-stage resampling พิจารณาแล้วไม่ใช้ในงานนี้: ต้องระบุ pseudo-population/FPC rescaling และ sparse replicate handling ให้ถูกต้องก่อน ไม่มี naive bootstrap ของ individual events และไม่มีการเลือกวิธีใหม่หลังเห็น independent results

## Coverage และความกว้าง

แต่ละแถว1000 repetitions; ตัวเลข coverage รวมทุกครั้ง ไม่มีการตัด EMPTY_DOMAIN หรือ unbounded repetitions ออกจาก denominator ช่วง Wilson95% เป็น Monte Carlo uncertainty ของ coverage ไม่ใช่ CI ตลาด Width ของ Fieller/Box วัดใน physical parameter space; Wald เดิมเก็บ raw width เพื่อให้เทียบ baseline ได้ตรงเดิม Mean widths จึงต้องอ่านพร้อมข้อแตกต่างนี้

| Suite / scenario | Wald coverage | Fieller coverage (MC Wilson95%) | Box coverage | Fieller width mean / median | Fieller raw unbounded / empty |
|---|---:|---:|---:|---:|---:|
| Original: regular | 94.9% | 95.4% (93.9%–96.5%) | 99.8% | 0.414 / 0.410 | 0 / 0 |
| Original: rare_domain | 91.5% | 95.5% (94.0%–96.6%) | 99.9% | 1.039 / 1.011 | 1 / 0 |
| Original: informative_missing | 96.6% | 96.9% (95.6%–97.8%) | 99.9% | 0.290 / 0.288 | 0 / 0 |
| Original: holdout_census_dates | 95.2% | 95.5% (94.0%–96.6%) | 99.6% | 0.282 / 0.282 | 0 / 0 |
| Independent: regular_p1 | 96.1% | 96.5% (95.2%–97.5%) | 100.0% | 0.257 / 0.255 | 0 / 0 |
| Independent: rare_domain_p1 | 92.5% | 94.6% (93.0%–95.8%) | 100.0% | 0.601 / 0.594 | 0 / 0 |
| Independent: informative_missing_p1 | 95.0% | 95.9% (94.5%–97.0%) | 99.9% | 0.286 / 0.283 | 0 / 0 |
| Independent: holdout_census_dates_p1 | 95.5% | 95.8% (94.4%–96.9%) | 100.0% | 0.235 / 0.235 | 0 / 0 |
| Independent: regular_p2 | 94.6% | 95.5% (94.0%–96.6%) | 100.0% | 0.332 / 0.329 | 0 / 0 |
| Independent: rare_domain_p2 | 93.7% | 94.6% (93.0%–95.8%) | 100.0% | 0.554 / 0.548 | 0 / 0 |
| Independent: informative_missing_p2 | 95.1% | 95.4% (93.9%–96.5%) | 100.0% | 0.232 / 0.231 | 0 / 0 |
| Independent: holdout_census_dates_p2 | 94.8% | 95.0% (93.5%–96.2%) | 100.0% | 0.270 / 0.269 | 0 / 0 |
| Independent: rare_005 | 71.5% | 83.4% (81.0%–85.6%) | 100.0% | 1.213 / 1.296 | 139 / 1 |
| Independent: rare_010_small | 91.4% | 94.3% (92.7%–95.6%) | 100.0% | 0.760 / 0.747 | 0 / 0 |
| Independent: rare_020_large | 92.7% | 95.3% (93.8%–96.4%) | 100.0% | 0.912 / 0.895 | 0 / 0 |
| Independent: rare_005_census | 92.5% | 95.9% (94.5%–97.0%) | 100.0% | 1.282 / 1.252 | 2 / 0 |

ค่า mean/median width ของทุกวิธี, MC SE, raw geometries, invalid/empty sets, conditional informative diagnostics, bias/variance และ domain-count distributions มีครบใน development-summary.json / validation-summary.json และราย repetition ของแต่ละสถานการณ์

## ข้อกั้นที่ยังเหลือ

Fieller ผ่านชุดเดิมทั้งสี่ที่95.4%,95.5%,96.9%,95.5% โดย rare-domain mean width เพิ่มจาก Wald0.886 เป็น1.039 (median0.874 เป็น1.011) อย่างไรก็ตาม independent rare_005 ได้เพียง83.4% ต่ำกว่าเกณฑ์93% อย่างชัดเจน จึงต้องคง BLOCKED ตามกติกาที่ตรึงไว้

rare_005 มีเหตุการณ์เฉลี่ย7.693 (0–18), zero-event dates เฉลี่ย23.948/30, denominator RSE40.09%, boundary estimates218/1000 จาก166 Fieller misses ทุกกรณีไม่มีการสังเกตอีก barrier direction และ149 อยู่ที่ขอบ parameter space การไม่เห็นหมวดตรงข้ามทำให้ estimated contrast variance เสื่อมสภาพได้ แม้ algebra ของ Fieller ถูกต้องและ total covariance ผ่าน unit checks ปัญหานี้เป็นข้อจำกัด sparse normal approximation ไม่ใช่เหตุผลให้แก้ first-touch หรือ barriers

กรณีนี้มี EMPTY_DOMAIN1 และ raw insufficient/unbounded138 ครั้ง ทั้งหมดถูกเก็บไว้; coverage83.4% รวม vacuous empty setแล้ว กรณี bounded ก็ยังต้องผ่าน information gates ไม่ใช่สิทธิ์ให้สรุปผลเมื่อเห็นเพียงฝั่งเดียว

Box ได้ coverage100% ใน independent stress นี้ แต่ width median2.0 คือเต็ม parameter space และมี raw unbounded/empty322 ครั้ง จึงไม่ใช่ชัยชนะเชิงความแม่นยำ ไม่แทนวิธีหลักหลังเปิด validation และไม่อ้างว่า finite synthetic1000/1000 พิสูจน์ coverage100% จริง

## Informative missingness และ estimand

Delta ยังคง P(DOWNSIDE_FIRST)−P(UPSIDE_FIRST) จาก fixed +3/−3 และ all initial events; Neither/unknown คงแยก ไม่ใช้50/50เป็น market-neutral null ไม่ใช้ observed classification contrast แทน latent full-path probabilities

แต่ละ population รายงาน identification bounds ของ latent contrast แยกจาก confidence set อย่างชัดเจน ใน informative_missing ช่วงความเชื่อมั่นของ observed target อาจมี coverageดี แต่ไม่รับรอง latent target: ตารางต่อไปแสดงคนละเป้าหมาย

| Scenario | Observable truth | Latent truth | Identification bounds (not CI) | Fieller latent coverage |
|---|---:|---:|---|---:|
| informative_missing | 0.2234 | 0.3871 | [-0.07122343480758185, 0.5180930499712809] | 39.1% |
| informative_missing_p1 | 0.2309 | 0.3925 | [-0.05631399317406143, 0.518202502844141] | 33.1% |
| informative_missing_p2 | 0.3134 | 0.5157 | [0.005766062602965404, 0.6210873146622735] | 4.3% |

## Holdout information และ protocol

เกณฑ์เดิมยังต้องมีอย่างน้อย60 initial events บน20 event-bearing dates และ30 securities, อย่างน้อย10ในแต่ละ barrier direction, weighted unknown<=5%, complete prior coverage, ไม่มี source/identity/order discrepancy และ uncertainty set ที่ใช้งานได้ ไม่มี optional enlargement ตาม effect size

Synthetic holdout-date census มี mean event counts แตกต่างกันมากตามประชากร/อัตราเหตุการณ์ ไม่ใช่การคาดการณ์ actual holdout: original164.275, independent216.716/173.855 และ rare-census10.916 Stressที่ไม่ผ่านมี0/1000ครั้งที่ผ่านเกณฑ์จำนวนเหตุการณ์เดิม จึงไม่มีหลักฐานว่า count gate เพียงอย่างเดียวรับรอง coverage ได้ ห้ามใช้การคัดเฉพาะผู้ผ่าน gate มายกเว้น global failed scenario

ยังไม่ adopt protocol v3 เพราะ prespecified primary ไม่ผ่านทุก stress เก็บ protocol v2 และ blocker ไว้เดิม หากจะพัฒนาวิธี conservative fallback/rare-category inference ต่อ ต้องเลือกวิธีและ freeze independent population suite ใหม่ก่อนดูผล การใช้ Box เป็น primary หลังเห็น suiteนี้แล้วไม่ถือว่า independent validation

แม้ calibration ในอนาคตผ่าน ยังต้องอนุมัติ holdout และตรึง sampling implementation / bounded acquisition budget แยก งานนี้ไม่สร้าง holdout sample หรือเรียก tick

## ความครบถ้วนและการรันซ้ำ

Full suite: **266 tests passed**, 84 existing warnings. ตรวจซ้ำทุก draw **16,000** ครั้งจาก16 frozen populations ด้วย seedsเดิม ได้ totals/covariances/confidence sets ตรงทุกครั้ง และ independent direct-score inequality check ผ่าน ตรวจ artifactsเดิม **13,956** ไฟล์ hash ไม่เปลี่ยน

Reproduction (ใช้ cache ไม่ต้องมี API key): `.venv/bin/python -m market_lab.calibration_repair prepare`, `develop`, `validate`; `.venv/bin/python -m scripts.validate_calibration_repair`; full pytest; `.venv/bin/python -m scripts.finalize_calibration_repair --pytest-output PATH` ใช้ configที่กำหนด run ID ใหม่กับ --config ทุกคำสั่ง ห้ามเขียนทับ run เดิม หาก stageล้มเหลวเก็บ failureไว้และรายงาน partial ไม่เปลี่ยน seedเพื่อหลบ failure การตรวจ reproducibilityเป็น deterministic verification ไม่ใช่ independent suiteใหม่หรือการ tuning

Source hashes และ pre-execution config freeze อยู่ใน freeze.json; validation-started.json ผูกกับ development summary ก่อนเปิดชุดอิสระ; independent-verification.json ผูกทุก scenario output กับ SHA256; manifest.json และ ZIP validation ผูก report/test/source หลักฐานราย draw ทั้งหมดเป็น synthetic ไม่ใช่ raw market download

References: [von Luxburg & Franz (2009)](https://arxiv.org/abs/0711.0198), [NIST Fieller algebra](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/ratimean.htm), [Aubry (2024) two-stage SRSWOR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11404174/). ใช้ supporting mathematical structures เท่านั้น ไม่อ้างว่าบทความรับรอง calibration ของ implementation หรือข้อมูลตลาดของเรา
