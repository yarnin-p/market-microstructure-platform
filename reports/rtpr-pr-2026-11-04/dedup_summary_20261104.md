# RTPR PR deduplication — 2026-11-04 UTC

| Metric | Count |
|---|---:|
| Rule Match (Normal PR) messages | 21 |
| Impact Wire messages | 61 |
| Total in-scope messages | 82 |
| Distinct exact headlines before content review | 61 |
| Unique announcements | 61 |
| Rule Match only | 5 |
| Impact Wire only | 43 |
| Both feeds | 13 |
| Duplicate records removed from unique list | 21 |
| Ambiguous event assignments requiring manual review | 0 |

All 82 in-scope messages have a mapping. 5 + 43 + 13 = 61 events. 61 + 21 + 0 = 82 messages. The per-event duplicate count excludes the representative.

## Source and observation clock

Message totals cover qualifying bot PR cards in the two Telegram exports, selected by the half-open UTC interval [2026-11-04 00:00, 2026-11-05 00:00). The export message ID identifies the original alert and `date_unixtime` supplies the observed delivery timestamp. Publication timestamps and the source-latency fields are excluded from the ordering.

When two members of an event share its earliest export second (0 events), the lower Telegram message ID selects the representative deterministically. Delivery order within that second is unresolved at finer precision.

The normalized RTPR release snapshots (files under `data/news-snapshots/releases` in the RTPR project) supply article IDs and archived article bodies. Collector observations have a broader population than delivered Telegram cards. They were used for linkage and content review. The counts describe the archived Telegram deliveries.

The export omitted the article link on 14 cards. Their original URL stays blank in the mapping. A ticker, full headline, and same-day feed observation in the normalized archive identified each underlying announcement. When multiple article IDs matched a card, they already belonged to the same content-confirmed event. The mapping reports all possible linked article IDs.

The canonical URL uses the retained article identity without the time-limited signature. The published mapping preserves the original host and path and omits signed query strings. Alerts labeled (no headline) are linked by article ID and use the archived title. Their original headline placeholders remain in the mapping.

## Cross-article decisions

| Announcement | Content evidence | Archived article IDs |
|---|---|---|
| ACIU | Same AC Immune Q3 financial and corporate update. | nGNE9DzwPb-20261104, nGNX6yX07J-20261104 |
| CNSP | Same Corero investment in Regional, with two wire copies. | nPreQ4Wv4a-20261104, nPnbMFTV7a-20261104 |
| EVAX | Same EVX-04 AML target validation data presentation at ASH. | nGNE5HMqVQ-20261104, nGNXbWfjWY-20261104 |
| EZRA | Same closing of the Oblivus acquisition. | nGNE10zBlf-20261104, nGNX3SKgDW-20261104 |
| MEGL | Same US$100 million credit facility for timber trading. | nGNX9yczVg-20261104, nGNE56HWl2-20261104 |
| ZENA | Same solar construction survey contracts and follow-on potential. | nGNX3SyqKy-20261104, nGNE1001zT-20261104 |

## Excluded messages in the exports

82 scoped PR cards accounted for all 82 messages in the UTC slices of the two exports.

## Input fingerprints

- rule_match · `result copy.json` · SHA-256 `8f7eb0ce378d6caca1e4a5780bd886fcbbd9c8021fbcd7e912801c7b618565b9`
- impact_wire · `result.json` · SHA-256 `f83698462ac045a0be52775b11c9023b196d5edc32e4d0ab9948b262f003203d`
