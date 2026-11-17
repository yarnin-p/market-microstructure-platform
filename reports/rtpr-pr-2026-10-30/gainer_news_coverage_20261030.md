# Gainer news coverage · 2026-10-30 UTC

The dated archive contains 39 Gainers with a regular-session high at least 20% above the comparable previous regular close on XNAS, XASE or XNYS. Six had a same-day issuer release, external news story or regulatory disclosure with positive observed upside and no matching delivery in the two Telegram feeds. Three of the six had public news before the regular-session peak, matching the earlier [Gainer audit protocol](../rtpr-gainer-news-coverage-2026-10-26-to-29/protocol.md). The other three also rose after publication, from a later price baseline.

| Ticker | Deduplicated news | Archive finding | News vs. RTH peak | RTH gain | Post-news upside | Evidence |
|---|---|---|---|---:|---:|---|
| BTOC | Armlogi disclosed that it regained Nasdaq minimum bid price compliance | No matching RTPR article found | Before | +30.99% | $2.12 → $2.79 (+31.60%) | [8-K](https://www.sec.gov/Archives/edgar/data/1972529/000121390026113962/ea0310166-8k_armlogi.htm), [06:09 ET coverage](https://www.streetinsider.com/Corporate%2BNews/Armlogi%2Bregains%2BNasdaq%2Bcompliance%2Bwith%2Bminimum%2Bbid%2Bprice%2Brule/27260900.html) |
| LGPS | LogProstyle paid its second previously declared cash dividend installment of $0.0115 per share | RTPR article found. No matching feed alert observed | Before | +20.76% | $0.625 → $0.7125 (+14.00%) | [RTPR](https://rtpr.io/a/nBw327MJDa-20261030), [Issuer](https://www.logprostyle.co.jp/news/pressrelease/) |
| XPOF | Bloomberg reported Fund 1 take-private interest. A later shareholder filing detailed a $5.61–$7.00 indication | No matching RTPR article found | Before | +25.13% | $4.55 → $4.99 (+9.67%) | [09:58 ET news record](https://www.streetinsider.com/dr/quote.php?q=XPOF), [Shareholder letter](https://www.sec.gov/Archives/edgar/data/1802156/000092189526002888/ex991sc13da413866017_103026.htm) |
| ZJYL | Jin Medical disclosed completion of the Kangma equity transfer and no need to issue 622,123 substitute shares | No matching RTPR article found | After | +52.15% | $2.205 → $2.45 (+11.11%) | [6-K](https://www.sec.gov/Archives/edgar/data/1837821/000121390026114281/ea0309976-6k_jinmedical.htm) |
| SGRX | Sangrix disclosed conversion of $3.3 million in senior secured notes plus interest into Class A shares | No matching RTPR article found | After | +177.71% | $0.9116 → $0.95 (+4.21%) | [6-K](https://www.sec.gov/Archives/edgar/data/1735556/000110465926120695/tm2628575d1_6k.htm) |
| CHOW | ChowChow Cloud announced closing of its previously announced private placement | RTPR article found. No matching feed alert observed | After | +246.48% | $5.3214 → $5.39 (+1.29%) | [RTPR](https://rtpr.io/a/nGNX3xHhJY-20261030) |

Four of the six had no matching article in the checked RTPR archive. LGPS and CHOW had an RTPR article. The CHOW release arrived at 13:30 ET, after its 11:02 ET RTH high and after the raw wire capture's final frame. TNMG had a recorded Impact Wire delivery and is in the [main PR report](pr_with_upside_20261030.md).

FMC and NCPL are also present in the event CSV as third-party litigation notices. They recorded positive later highs and are outside the six issuer or market-news cases above. The ACCO and FMC 10-Q filings are linked to their October 29 RTPR earnings releases. The supplemental CSV records prior releases and later disclosures with October 30 event dates. The 39 rows reconcile to 10 Gainers with a same-day matched event in the event CSV and 29 with no verified same-day event in the checked sources. Earlier or later context can exist on those 29 rows.

## Coverage and price clock

- The audit cross-checked the archived RTPR all-article feed, normalized releases, both Telegram exports, 19 captured wire frames and independently indexed news and SEC filings. Massive News returned 686 records across three pages through its terminal page. Three completed SEC index screens returned 560, 778 and 46 filings across the form types listed in the source coverage JSON. The SEC screen CSV holds the 11 matched filings and review decisions. BTOC, ZJYL and SGRX have dated SEC evidence. BTOC was publicly covered by 06:09 ET, before the first archived trade at 09:38 ET. XPOF uses the 09:58 ET media timestamp and the first full minute from 09:59 ET. Its later 13D/A is evidence for the same event.
- The raw wire frames run from 01:00:02 to 12:00:32 UTC with continuity unverified. The full article archive and the alert archive have different coverage. An absent alert or article means no match in the checked records. The independent sources also have bounded coverage.
- Price upside uses the first complete post-news minute's open to the highest observed bar high through 20:00 ET. Minute-precision news uses the next minute. RTH peak timing uses cached minute bars. The Gainer denominator uses the archived regular-session aggregate, whose highs differ slightly from the cached minute-bar highs for BYSI and REKR. The CSV preserves both measurements. Upside uses observed traded prices and a peak selected in hindsight.

## Evidence files

- [All 39 Gainers](gainer_coverage_20261030.csv)
- [Matched events and prices](gainer_news_and_prices_20261030.csv)
- [Prior, later and secondary coverage](gainer_supplemental_news_20261030.csv)
- [SEC filing review](gainer_sec_screen_20261030.csv)
- [Source coverage and fingerprints](gainer_source_coverage_20261030.json)
