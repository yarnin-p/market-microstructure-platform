# MARKET MICROSTRUCTURE PLATFORM
## MASTER RESEARCH & ENGINEERING PLAN — V0.1

### Role and Operating Model

You are the Engineering & Execution Agent for a quantitative Market Microstructure Research Platform.

ChatGPT acts as the Research Lead responsible for research hypotheses, statistical methodology, experimental design, research architecture, and evidence interpretation.

You are responsible for technical planning, implementation, execution, testing, validation, and reproducibility.

The Git repository is greenfield. Do not attempt to recover previous work.

**First produce a concrete engineering implementation plan based on this specification. Do not independently redefine the research objectives.**

Technical challenges, feasibility concerns, and proposed alternatives should be reported explicitly.

---

# 1. Research Mission

Investigate whether US micro-float stocks exhibit measurable price continuation after first reaching +10% relative to the previous Regular Trading Hours closing price.

Research must distinguish:

1. Initial +10% price continuation
2. Price confirmation
3. Transient or false price spikes
4. Microstructure-supported price movement
5. Price-path behavior versus executable trading opportunities

Do not optimize trading strategies during initial research.

---

# 2. Historical Universe

Data provider: Massive Stocks Advanced.

Universe filters:

- Primary listing exchange: NASDAQ, NYSE American (AMEX), NYSE only
- Shares float: 100,000–15,000,000 inclusive
- Previous RTH closing price: greater than $0 and at most $3
- Historical window: 120 completed trading cycles
- Use historical eligibility rather than current security attributes wherever possible

Primary listing exchange is distinct from the venue on which a trade executes.

Preserve historical symbols, delisted securities, security identifiers, exchange information, and data provenance.

Historical float information must be handled carefully.

Never silently substitute today's float for historical point-in-time float.

If historical float is unavailable, distinguish:

- Verified point-in-time float
- Historical proxy or estimated float
- Current float proxy
- Unresolved float

Do not mix these populations in the primary statistical analysis without explicit labeling.

---

# 3. Trading Cycle

For trading date D:

Previous RTH Close → After-Hours → Premarket → Current RTH Close.

Example:

Monday RTH Close → Monday AH → Tuesday PRE → Tuesday RTH Close.

Use America/New_York timezone and a reliable exchange calendar.

Handle:

- Daylight-saving transitions
- Weekends and holidays
- Early closes
- Missing market sessions
- Trading halts
- Cross-session event continuity

Reference price P0 is the previous RTH closing price.

The +10% threshold is:

P_trigger = P0 × 1.10

The same reference price must remain fixed throughout each cycle.

Define and document reference-close and corporate-action conventions.

---

# 4. Research Experiments

## Experiment A — Baseline First Touch

Detect the first eligible trade reaching +10% for each security within each trading cycle.

Use explicit trade-condition eligibility rules.

For each event record:

- Security identifier and ticker
- Trading cycle and session
- Reference price
- First-touch timestamp
- Trigger price
- Trades and quotes around the event
- Data quality and market-state flags

Measure:

- 5-minute forward return
- 15-minute forward return
- 30-minute forward return
- 60-minute forward return
- Cycle-end return
- MFE and MAE
- Time-to-target
- Time-to-invalidation
- First-passage outcomes

Evaluate candidate upside/downside barriers:

- +3% / -3%
- +5% / -3%
- +10% / -5%

Measure these relative to the event observation price. Also retain targets relative to the previous RTH close as a separate metric family.

Preserve censored outcomes.

Do not assume that every first touch is an executable trading opportunity.

## Experiment B — Price Confirmation

Compare three initial confirmation families:

C1: Trade Persistence

C2: Price Acceptance

C3: Bid Confirmation

All confirmation rules must use only information available at or before confirmation time.

Evaluate confirmation delay, observation time, subsequent entry price, and forward outcome.

Avoid look-ahead bias and immortal-time bias.

Do not declare confirmation superior merely because it selects events that survived an initial observation window.

Use comparable decision times and appropriate control groups.

Confirmation thresholds are research parameters, not assumed truths.

## Experiment C — Microstructure Investigation

Study:

- Bid-ask spread
- Trade frequency
- Quote persistence
- Trade volume
- Float turnover
- Aggressive trade-flow estimates
- Best bid/ask liquidity
- Session-dependent behavior

Distinguish observed price continuation from execution-aware profitability proxies.

Do not assume NBBO provides full order-book depth.

---

# 5. Statistical Research Design

Split 120 cycles chronologically:

- First 80 cycles: Exploration and Development
- Final 40 cycles: Holdout Validation

Do not optimize parameters using the holdout set.

Calculate:

- Sample counts and denominators
- Continuation probabilities
- Return distributions and quantiles
- MFE/MAE distributions
- First-passage probabilities
- Confidence intervals
- Statistical uncertainty
- Performance by session and relevant cohorts
- Sensitivity to data quality and parameter assumptions

Account for dependence between observations from the same security and trading cycle.

Separate exploratory findings from validated findings.

---

# 6. Data Architecture

Prefer a local-first architecture.

Suggested technologies:

- Python
- Massive API
- Parquet
- DuckDB
- Exchange calendar library
- PyArrow / Polars where appropriate
- SciPy / statsmodels
- pytest

Separate:

A. Historical market data

B. Universe eligibility

C. Event ledger

D. Replay evidence

E. Experiment outcomes

F. Research run metadata

G. Data quality and validation

Use immutable experiment configurations, reproducible run identifiers, and versioned schemas.

Do not store multi-GB raw market data in Git.

Partition large internal datasets where beneficial for performance and resumability.

---

# 7. Research Evidence & Results Contract

All experiments must preserve complete queryable event-level results.

Do not retain only aggregated summaries.

Store:

- Full event ledger
- Event feature values
- Outcome records
- Cycle-level metrics
- Research configuration
- Data quality information
- Tick-level source references
- Experiment provenance
- Statistical test definitions

Every event must be traceable back to the relevant security, trading cycle, historical market data, and source records.

Support aggregation across all 120 cycles automatically.

The system must be designed so that a future Research MCP Server can query all experiment evidence without downloading or transferring the complete raw dataset into ChatGPT.

A consolidated research bundle may be supported as an optional export, not the primary analytical interface.

---

# 8. Future Research MCP

Plan for a read-only Research Gateway accessible to ChatGPT.

Expected capabilities:

- List experiments and runs
- Inspect dataset schemas
- Query complete event-level results
- Aggregate research outcomes
- Inspect individual events
- Retrieve targeted tick/quote windows
- Compare experiment versions
- Query historical universe decisions
- Audit data quality and provenance

Use secure authentication, resource limits, and bounded result sizes.

Do not implement the full MCP Server in TASK 001.

Ensure the underlying data contracts support it.

---

# 9. Implementation Milestones

M1 — Historical Universe and Massive Data Audit

M2 — Tick-Level Data Ingestion and Replay

M3 — First-Touch Event Detection and Baseline Measurement

M4 — Price Confirmation Models

M5 — Statistical Validation and Holdout Research

M6 — Research MCP Integration

Each milestone must include tests, data-quality checks, reproducible outputs, and explicit acceptance criteria.

Do not start the next major milestone until the current milestone has passed validation.

---

# 10. Immediate Engineering Planning Task

Start with M1.

Prepare a concrete technical implementation plan containing:

1. Project module structure
2. Massive API endpoints and data capabilities
3. Historical security discovery approach
4. Previous RTH close methodology
5. Historical float limitations and proposed handling
6. Exchange eligibility mapping
7. 120-cycle calendar construction
8. Universe data schemas
9. Local storage architecture
10. Resumable ingestion strategy
11. Data quality validation
12. Unit and integration test strategy
13. Evidence and run metadata schemas
14. Risks, blockers, and measurable acceptance criteria

Identify assumptions requiring Research Lead decisions.

Do not fabricate unavailable historical data.

Do not bulk-download all historical tick data during initial planning.

## Required Plan Output

Provide:

- Proposed architecture
- Implementation phases
- File/module structure
- Key engineering decisions
- Data integrity risks
- Massive API feasibility findings
- Acceptance criteria for TASK 001
- Exact next execution steps

Respond in Thai, retaining English technical terminology.

**Do not implement the entire platform in one pass. Begin with a technically validated plan for M1, then await implementation authorization.**