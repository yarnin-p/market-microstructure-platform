# RTPR after-release price opportunities · 2026-10-26

[All 58 announcement–ticker rows](pr_day_reaction_20261026.csv) · [Sampled NBBO evidence](pr_day_quote_evidence_20261026.json) · [Deduplicated announcements](dedup_summary_20261026.md)

The 54 Telegram announcements linked to 58 announcement–ticker pairs. The historical XNAS/XASE/XNYS scope retained 45 distinct tickers across 42 announcements. Every in-scope ticker had a price bar after publication.

| Price comparison | Tickers | Announcements |
|---|---:|---:|
| Later high above the first observed post-release price | 40/45 | 38/42 |
| Later high at least 10% above the first observed post-release price | 13/45 | 13/42 |
| Latest observed price of the day above the first observed post-release price | 11/45 | 11/42 |
| Later high above the last same-day pre-release price | 27/27 with pre-release marks | 24 |

The 13 tickers with at least 10% upside from the first observed post-release price were SRTM +63.87%, SHFS +38.49%, VBIO +28.87%, VAI +20.37%, NXTS +14.15%, XLO +13.64%, OPNW +12.90%, BIVI +11.48%, DRIO +11.46%, EQ +10.92%, EPOW +10.54%, HCTI +10.45%, and CANF +10.00%.

The first post-release observation can arrive well after publication. For 23 tickers, even the start of its first observed price bar was at least 60 seconds after publication. The last pre-release price can also be stale. Its age is included in the CSV. The high is selected with hindsight and can reflect later developments on the same day.

## Ask-to-bid examples

For six selected tickers, compare the first valid displayed ask sampled after Telegram receipt to a later displayed bid near the trade-price peak. Five showed a positive gross difference before costs.

| Ticker | Gross ask-to-bid difference |
|---|---:|
| SRTM | +63.42% |
| SHFS | +36.09% |
| VAI | +15.00% |
| VBIO | +10.00% |
| EPOW | +4.17% |
| NXTS | −5.87% |

These are displayed quotes with size and SIP timestamps. Execution would depend on timing, liquidity and costs. The six-case check samples quotes around the trade-price peak, so its counts apply to that sample. The entry sample spans 12 seconds after Telegram receipt, extended to five minutes for SRTM after the initial sample returned no valid quote. The quoted SRTM ask arrived about 106 seconds after the alert. The peak sample caps at 1,000 records and can have remaining pages. Each capture records request bounds, hashes, and sampled quote timestamps and sizes.

## Price window and sources

Measure from the earliest linked publication through 20:00 ET on October 26. Use unadjusted Massive one-minute bars over 04:00–20:00 ET, with previously captured one-second bars replacing complete minutes around publication where covered. Ignore bars that straddle publication. The baseline is the open of the first eligible post-publication bar and the peak is the maximum ensuing high, including that bar. The CSV includes the first bar's timestamp, the price before publication when observed, peak-bar time and resolution, and hashes of the local captures. Four minute series were reused from the RTPR Gainers archive and the other 41 were fetched through Massive REST. The secondary pre-release comparison uses the latest completed same-day bar before publication. Observed prices describe market movement. The separate quote sample checks the gross price difference across the spread.
