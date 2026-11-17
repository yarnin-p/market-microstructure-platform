# RTPR PR deduplication — 2026-11-02 UTC

| Metric | Count |
|---|---:|
| Rule Match (Normal PR) messages | 5 |
| Impact Wire messages | 11 |
| Total in-scope messages | 16 |
| Distinct exact headlines before content review | 13 |
| Unique announcements | 13 |
| Rule Match only | 2 |
| Impact Wire only | 8 |
| Both feeds | 3 |
| Duplicate records removed from unique list | 3 |
| Ambiguous event assignments requiring manual review | 0 |

All 16 in-scope messages have a mapping. 2 + 8 + 3 = 13 events. 13 + 3 + 0 = 16 messages. The per-event duplicate count excludes the representative.

## Source and observation clock

Message totals cover qualifying bot PR cards in the two Telegram exports, selected by the half-open UTC interval [2026-11-02 00:00, 2026-11-03 00:00). The export message ID identifies the original alert and `date_unixtime` supplies the observed delivery timestamp. Publication timestamps and the source-latency fields are excluded from the ordering.

When two members of an event share its earliest export second (0 events), the lower Telegram message ID selects the representative deterministically. Delivery order within that second is unresolved at finer precision.

The normalized RTPR release snapshots (files under `data/news-snapshots/releases` in the RTPR project) supply article IDs and archived article bodies. Collector observations have a broader population than delivered Telegram cards. They were used for linkage and content review. The counts describe archived Telegram deliveries.

The export omitted the article link on 3 cards. Their original URL stays blank in the mapping. A ticker, full headline, and same-day feed observation in the normalized archive identified each underlying announcement. When multiple article IDs matched a card, they already belonged to the same content-confirmed event. The mapping reports all possible linked article IDs.

The canonical URL uses the retained article identity without the time-limited signature. The published mapping preserves the original host and path and omits signed query strings. Alerts labeled (no headline) are linked by article ID and use the archived title. Their original headline placeholders remain in the mapping.

GMHS, MEDS and SUNE each matched across both feeds by canonical article ID. The two LUD releases cover distinct transactions.

## Excluded messages in the exports

| Feed | Category | Count | Telegram IDs |
|---|---|---:|---|

16 scoped PR cards + 0 out-of-scope messages = 16 messages in the two daily export slices.

## Input fingerprints

- rule_match · `result copy.json` · SHA-256 `8f7eb0ce378d6caca1e4a5780bd886fcbbd9c8021fbcd7e912801c7b618565b9`
- impact_wire · `result.json` · SHA-256 `f83698462ac045a0be52775b11c9023b196d5edc32e4d0ab9948b262f003203d`
