# TASK 003.2 — Historical NBBO Coverage Feasibility Probe

Run: `m3-nbbo-probe-20261115-v1` · Baseline: `48a69aa`

**Recommendation: `QUOTE_EXPANSION_CONDITIONALLY_FEASIBLE`**

Historical quote retrieval ใช้งานได้ด้วย subscription เดิมและต้นทุนข้อมูลต่ำ แต่การดึงเพิ่มไม่ได้ทำให้ทุก target มี fresh-valid NBBO: probe นี้มีเพียง **3/10 selected targets** ที่ผ่าน quality/freshness และจับคู่ quote marks ได้ **4 distinct clock pairs จาก 2 securities** จึงรองรับการขยายแบบกำหนดขอบเขตและตรวจ missingness ต่อ ไม่ใช่การรับรองว่าจะเติมครบ 385 targets หรือได้ executable fills

คำแนะนำนี้ใช้ coverage/validity/resource cost ตามเกณฑ์ที่ freeze ก่อน acquisition ไม่ใช้เครื่องหมายบวก/ลบของ mark changes

## Selection และขอบเขต

ใช้ `quote-top-up-plan.json` ของ TASK 003.1 โดยตรง: first 10 จาก deterministic cycle-round-robin queue ตรงกับ `pilot_queue` ทุกแถว ไม่เลือกตาม realized returns ไม่เพิ่ม cycles ไม่แตะ holdout ไม่เปลี่ยน frozen C0/C1/C2 หรือ QA sensitivities และไม่คำนวณ confirmation signals ใหม่

Selection มี 2 entry targets และ 8 exit targets แต่ละ window ขอ `(T−5 seconds−1ns, T]` ด้วย historical ticker/security identity เดิม การเพิ่ม 1ns รักษา quote ที่อายุครบ 5 วินาทีตาม frozen freshness rule

| Cycle | Ticker | Target | Quotes ที่ได้ | Pagination | Fresh-valid mark |
|---|---|---|---:|---|---|
| 2026-05-27 | NNBR | Exit | 0 | Complete | ไม่ผ่าน: cached predecessor stale |
| 2026-05-28 | BIVI | Exit | 0 | Complete | Missing predecessor |
| 2026-05-29 | ATNM | Entry | 4 | Complete | ไม่ผ่าน: corrected quotes |
| 2026-06-01 | AREN | Exit | 0 | Complete | ไม่ผ่าน: cached corrected/stale |
| 2026-06-02 | XWEL | Exit | 0 | Complete | ไม่ผ่าน: cached predecessor stale |
| 2026-06-03 | EVTV | Exit | 80 | Complete | ผ่าน |
| 2026-06-04 | BGI | Exit | 0 | Complete | ไม่ผ่าน: cached corrected/stale |
| 2026-06-05 | BNBX | Exit | 0 | Complete | ไม่ผ่าน: cached predecessor stale |
| 2026-06-08 | FFAI | Exit | 4 | Complete | ผ่าน |
| 2026-06-09 | QRHC | Entry | 6 | Complete | ผ่าน |

ครบ pagination **10/10** หมายถึง provider คืน terminal cursor ไม่ใช่ independent exchange-feed certification มี **6 empty windows** ซึ่งไม่พิสูจน์ outage หรือไม่มี standing quote เพียงไม่มี quote update ที่ provider คืนในช่วง 5 วินาทีนั้น การมองย้อนหลังไกลขึ้นไม่ทำให้ stale quote ผ่าน freshness rule เดิมโดยอัตโนมัติ

## Quality และ paired coverage

- New observations **94**: valid observations 90, corrected/non-valid 4; corrected 4 แถวทั้งหมดอยู่ใน ATNM (condition 81 `Corrected_Price`) ไม่ใช้เป็น original PIT NBBO
- Selected fresh-valid targets **3**: entry 1 (QRHC), exit 2 (EVTV, FFAI)
- เมื่อรวม cache เดิมใน candidate pair set: fresh-valid entry marks **7**, exit marks **2**; entry count นี้รวม cached marks จึงไม่เท่ากับ newly retrieved entry target 1 จุด
- Candidate clock pairs **31**, supported pairs **4**, unsupported **27** มีเหตุผลและ source-linked entry/exit quality ทุกคู่
- Supported pairs มาจาก EVTV 3 clocks และ FFAI 1 clock ไม่ใช่ 4 independent securities การใช้คู่เดียวกันใน common/own clocks หรือหลาย QA policies อยู่ใน `uses` ไม่บวกซ้ำเป็น pairs ใหม่
- QRHC ได้ fresh entry mark แต่ยังไม่มี exit quote ที่รองรับคู่ภายในขอบเขตที่อนุญาต จึงไม่สร้างผลคู่ขึ้นเอง
- ไม่ใช้ future quotes: quote timestamp <= entry/exit target ทุกครั้ง และไม่ย้อนเลือก earlier valid quote ข้าม latest invalid/corrected observation

Fresh-valid selected-target spread: min **$0.0008**, median **$0.0100**, max **$0.0300**, mean **$0.0136**, n=3

Fresh-valid selected-target quote age: min **0.000069029s**, median **1.234913655s**, max **1.376472312s**, mean **0.870484999s**, n=3

สำหรับ candidate pairs: fresh entry spread n=7, median $0.01, range $0.0021–$0.04; fresh exit spread n=2, range $0.0008–$0.01 การแจกแจงอายุ predecessor ทั้งหมดแยกอยู่ใน summary และรวม stale/non-valid contexts ไม่ใช่ valid-mark distribution

## Quote marks เทียบ observed trade-path marks

นิยาม `relative quote-mark change = exit bid / entry ask − 1` และ `absolute mark difference = exit bid − entry ask` คำนวณเฉพาะคู่ที่ทั้ง entry/exit fresh, positive/uncrossed, sizes >0, regular/non-corrected และมี complete lookback coverage

| Security / frozen use | Entry ask | Exit bid | Quote-mark change | Observed trade-path change | Quote minus trade (percentage points) |
|---|---:|---:|---:|---:|---:|
| EVTV / C0, touch+5m | 1.98 | 1.95 | -1.5152% | -1.5152% | 0.0000 |
| EVTV / C2, common touch+5m | 1.99 | 1.95 | -2.0101% | -1.9263% | -0.0838 |
| EVTV / C1 counted/session-bound, common touch+5m | 1.99 | 1.95 | -2.0101% | -1.9263% | -0.0838 |
| FFAI / C1 counted/session-bound, common touch+5m | 0.3350 | 0.3321 | -0.8657% | -0.4192% | -0.4465 |

C1 rows รวม deadline sensitivities ที่ให้ clock เดียวกัน ไม่ใช่ observations เพิ่ม Future quote context ไม่ถูกใช้ย้อนกลับเป็น entry evidence ข้อมูล trade benchmark มาจาก baseline ที่ไม่เปลี่ยน และเปรียบเทียบเฉพาะ trade marks ที่ baseline รองรับ

**ตัวเลขทั้งหมดเป็น quote/trade market-mark differences ไม่ใช่ fills, realized P&L หรือ backtested executable profit** ไม่ได้พิสูจน์ available order size, queue priority, routing, latency, fees หรือ continuous bid/ask path ระหว่าง endpoints ผลลบในตารางไม่ได้เป็นเหตุผลของ feasibility recommendation

## Resource utilization จริง

| Resource | ใช้จริง | Hard maximum |
|---|---:|---:|
| Unique windows | 10 | 10 |
| HTTP attempts | 10 | 40 |
| Successful pages | 10 | 40 |
| Pages/window | 1 ทุก window | 4 |
| Decoded response bytes | 24,495 | 67,108,864 (64 MiB) |
| Execution wall time | 6.7046 seconds | 600 seconds |
| New run storage | 1,011,194 bytes ก่อน final reports | 268,435,456 (256 MiB) |

ไม่มี HTTP error, incomplete pagination หรือ budget exhaustion มี per-response 8 MiB limit, persistent shared ledger, 250ms minimum spacing, timeout และ wall-time watchdog หนึ่งวินาทีก่อน hard ceilingเพื่อเหลือเวลาปิดไฟล์ แต่ไม่เพิ่มงบ acquisition บน resume

## Validation

- **214 tests passed**, 84 existing pandas deprecation warnings
- Raw page SHA-256, terminal cursors, bounds/order, normalized Parquet hashes, entry/exit raw quote timestamps/prices ตรวจผ่าน
- Deterministic reevaluation เท่ากับ persisted results; ไม่มี future quote evidence
- Prior artifacts **4,003 files** ไม่เปลี่ยน รวม M1, SEC evidence, prior M2/M3 results
- Resume ตรวจ hashes ของ new-run artifacts **54 files** ตรงเดิม และ HTTP attempts เพิ่ม **0**
- Hard budgets ผ่านทั้งหมด ไม่มีการ fetch remaining 375 windows หรือ additional historical cycles

## Recommendation และข้อจำกัดการขยาย

`QUOTE_EXPANSION_CONDITIONALLY_FEASIBLE`: API/entitlements/pagination ใช้ได้และต้นทุนรอบนี้ต่ำ อีกทั้งเติม valid paired marks ได้จริง แต่ missing updates และ corrected fields เป็นข้อจำกัดด้านข้อมูลที่เพิ่ม requests อย่างเดียวไม่จำเป็นต้องแก้ได้

หากมีการอนุมัติรอบต่อไป ควรรักษา deterministic queue และ quality criteria พร้อมรายงาน paired coverage/missingness แยกตาม security/session การขยายไม่ควรสมมติว่า 3/10 เป็น population success probability เพราะนี่เป็น fixed feasibility prefix ไม่ใช่ random sample ของ 385 targets และสี่คู่ที่ได้มี dependence ภายในสอง securities ยังไม่มีการดำเนินการขยายในงานนี้

## Artifacts และ reproduction

- Full immutable data: `data/runs/m3-nbbo-probe-20261115-v1/`
- Raw: `raw/*.json` พร้อม source SHA-256; per-window normalized Parquet: `windows/NN/quotes.parquet`
- Queryable full pairs: `pairs.parquet`; complete results: `results.json`
- Compact evidence: `reports/m3-nbbo-probe-20261115-v1/`
- `coverage-quality.json` เก็บ before/after marks ทุก window; `quote-mark-pairs.json` เก็บทุก supported/unsupported pair พร้อม source locators และ policy uses

```sh
.venv/bin/python -m market_lab.nbbo_probe validate
.venv/bin/python -m market_lab.nbbo_probe run
```

เมื่อ run มี `results.json` แล้ว คำสั่ง run จะอ่านผลเดิม ไม่ acquire เพิ่ม การเปลี่ยน code/config ต้องใช้ run ID ใหม่ Source hashes และ budget/selection freeze อยู่ใน execution.json ไม่เปลี่ยน original quote plan ที่ยังบันทึกสถานะ proposal ของ TASK 003.1 ไว้ตามประวัติ
