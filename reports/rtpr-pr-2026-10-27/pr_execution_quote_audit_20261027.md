# RTPR displayed entry and exit audit · 2026-10-27

[All 33 quote comparisons](pr_execution_quote_audit_20261027.csv) · [Request bounds and capture hashes](pr_execution_quote_sources_20261027.json) · [Price movement report](pr_day_reaction_20261027.md)

| Outcome | Stocks |
|---|---:|
| Valid entry ask observed | 33 |
| Later bid above entry ask in sampled window | 12 |
| Later bids observed, none above entry ask in sample | 10 |
| No comparable exit quote in sample | 11 |

Among the 32 ticker price movers in the prior report, 12 showed a positive difference across the spread. Of all 12 positive comparisons, 12 displayed at least 100 shares on each relevant side, 10 showed at least +1% and 5 showed at least +10% before fees. In 5 of the positive cases, the entry ask appeared within 60 seconds of alert receipt. Displayed sizes describe separate moments on each side. Order routing, exchange access, latency and queue or liquidity changes determine whether an order would have filled.

| Ticker | Entry ask | Entry ET | Later bid | Exit ET | Gross difference | Smaller displayed side (shares) |
|---|---:|---|---:|---|---:|---:|
| NUWE | $3.36 | 09:00:00.001 | $5.96 | 16:35:53.626 | +77.38% | 100 |
| SXTP | $0.93 | 08:06:20.759 | $1.19 | 08:45:18.474 | +27.96% | 700 |
| MEGL | $0.77 | 07:00:12.007 | $0.95 | 07:00:57.161 | +23.38% | 400 |
| MMA | $0.3063 | 07:05:38.840 | $0.3387 | 12:04:28.553 | +10.58% | 100 |
| NVA | $3.1 | 06:41:36.130 | $3.41 | 06:54:54.515 | +10.00% | 100 |
| SOAR | $0.2457 | 08:05:21.526 | $0.265 | 08:17:04.596 | +7.86% | 400 |
| CDT | $0.0983 | 08:01:19.484 | $0.1036 | 08:19:43.838 | +5.39% | 300 |
| GNS | $0.128 | 08:00:42.557 | $0.1343 | 12:12:50.126 | +4.92% | 100 |
| SWMR | $9.4 | 08:14:18.811 | $9.65 | 15:10:06.464 | +2.66% | 100 |
| CAMP | $3.7 | 08:34:01.950 | $3.75 | 15:50:11.124 | +1.35% | 200 |
| TNXP | $5.41 | 07:16:13.065 | $5.46 | 10:51:39.314 | +0.92% | 100 |
| FNGR | $0.152 | 08:01:40.602 | $0.1529 | 09:31:52.410 | +0.59% | 100 |

## Scope and method

Use the first observed Telegram alert for each deduplicated event. Use the first regular two-sided NBBO update from that time through 20:00 ET with positive displayed sizes and bid below ask. Entry queries are time ordered and capture the first page of up to 100 updates. Select the highest post-entry trade-price bar from the previous day study and inspect up to 2,000 time-ordered quote updates around that bar, from one second before to one second after its interval and strictly after entry. When the initial window has no valid quote, the audit uses a second window of up to 120 seconds ending at the same cutoff. The exit mark is the highest valid bid in the selected sample. The selected bar uses hindsight. A positive result provides an observed price pair and a negative or missing result applies only to the sampled interval. Full-session exit quotes were outside the sample. 0 exit responses had another page. The CSV records sample-level coverage, timestamps, quoted sizes, and entry delay for every ticker.

Quote condition 1 and share-size fields follow the provider reference. [Massive quote conditions](https://massive.com/knowledge-base/article/how-do-i-look-up-what-a-stock-quote-condition-code-means) · [Historical NBBO endpoint](https://massive.com/docs/rest/stocks/trades-quotes/quotes).
