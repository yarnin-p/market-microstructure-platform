# RTPR displayed entry and exit audit · 2026-10-26

[All 45 quote comparisons](pr_execution_quote_audit_20261026.csv) · [Request bounds and capture hashes](pr_execution_quote_sources_20261026.json) · [Price movement report](pr_day_reaction_20261026.md)

| Outcome | Stocks |
|---|---:|
| Valid entry ask observed | 45 |
| Later bid above entry ask in sampled window | 15 |
| Later bids observed, none above entry ask in sample | 21 |
| No comparable exit quote in sample | 9 |

Among the 40 ticker price movers in the prior report, 15 showed a positive difference across the spread. Of all 15 positive comparisons, 15 displayed at least 100 shares on each relevant side, 11 showed at least +1% and 4 showed at least +10% before fees. In 9 of the positive cases, the entry ask appeared within 60 seconds of alert receipt. Displayed sizes describe separate moments on each side. Order routing, exchange access, latency and queue or liquidity changes determine whether an order would have filled.

| Ticker | Entry ask | Entry ET | Later bid | Exit ET | Gross difference | Smaller displayed side (shares) |
|---|---:|---|---:|---|---:|---:|
| SRTM | $0.447 | 07:31:50.908 | $0.7305 | 08:23:01.665 | +63.42% | 100 |
| SHFS | $0.1064 | 08:24:03.197 | $0.1448 | 08:30:35.944 | +36.09% | 200 |
| VAI | $2.2 | 06:58:20.183 | $2.53 | 07:59:39.807 | +15.00% | 100 |
| VBIO | $1.1 | 08:00:06.004 | $1.21 | 08:00:20.147 | +10.00% | 100 |
| CVM | $1.68 | 08:01:41.829 | $1.8 | 09:26:23.148 | +7.14% | 100 |
| CANF | $1.96 | 07:00:32.584 | $2.07 | 07:03:11.024 | +5.61% | 100 |
| OPNW | $1.6 | 16:30:48.713 | $1.68 | 16:48:58.254 | +5.00% | 100 |
| SWMR | $8.87 | 12:00:09.510 | $9.24 | 13:10:22.424 | +4.17% | 100 |
| EPOW | $4.08 | 11:00:10.462 | $4.25 | 11:03:23.010 | +4.17% | 100 |
| IAM | $14.42 | 08:22:21.450 | $14.94 | 09:52:51.052 | +3.61% | 100 |
| AMAN | $10.4 | 06:11:29.576 | $10.72 | 07:37:40.249 | +3.08% | 100 |
| FTEK | $1.46 | 08:36:21.357 | $1.47 | 09:29:03.157 | +0.68% | 300 |
| HCTI | $7.28 | 09:00:00.004 | $7.31 | 11:20:56.339 | +0.41% | 100 |
| DAVI | $5.1 | 07:30:24.887 | $5.12 | 08:56:01.679 | +0.39% | 100 |
| IPI | $32.16 | 09:12:40.332 | $32.23 | 11:08:54.688 | +0.22% | 100 |

## Scope and method

Use the first observed Telegram alert for each deduplicated event. Use the first regular two-sided NBBO update from that time through 20:00 ET with positive displayed sizes and bid below ask. Entry queries are time ordered and capture the first page of up to 100 updates. Select the highest post-entry trade-price bar from the previous day study and inspect up to 2,000 time-ordered quote updates around that bar, from one second before to one second after its interval and strictly after entry. When the initial window has no valid quote, the audit uses a second window of up to 120 seconds ending at the same cutoff. The exit mark is the highest valid bid in the selected sample. The selected bar uses hindsight. A positive result provides an observed price pair and a negative or missing result applies only to the sampled interval. Full-session exit quotes were outside the sample. 1 exit responses had another page. The CSV records sample-level coverage, timestamps, quoted sizes, and entry delay for every ticker.

Quote condition 1 and share-size fields follow the provider reference. [Massive quote conditions](https://massive.com/knowledge-base/article/how-do-i-look-up-what-a-stock-quote-condition-code-means) · [Historical NBBO endpoint](https://massive.com/docs/rest/stocks/trades-quotes/quotes).
