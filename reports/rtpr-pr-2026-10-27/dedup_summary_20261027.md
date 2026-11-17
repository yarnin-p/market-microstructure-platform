# RTPR PR deduplication — 2026-10-27 UTC

| Metric | Count |
|---|---:|
| Rule Match (Normal PR) messages | 15 |
| Impact Wire messages | 27 |
| Total in-scope messages | 42 |
| Distinct exact headlines before content review | 32 |
| Unique announcements | 31 |
| Rule Match only | 8 |
| Impact Wire only | 19 |
| Both feeds | 4 |
| Duplicate records removed from unique list | 11 |
| Ambiguous event assignments requiring manual review | 0 |

All 42 in-scope messages have a mapping. 8 + 19 + 4 = 31 events. 31 + 11 + 0 = 42 messages. The per-event duplicate count excludes the representative.

## Source and observation clock

Message totals cover qualifying bot PR cards in the two Telegram exports, selected by the half-open UTC interval [2026-10-27 00:00, 2026-10-28 00:00). The export message ID identifies the original alert and `date_unixtime` supplies the observed delivery timestamp. Publication timestamps and the source-latency fields are excluded from the ordering.

When two members of an event share its earliest export second (0 events), the lower Telegram message ID selects the representative deterministically. Delivery order within that second is unresolved at finer precision.

The normalized RTPR release snapshots (files under `data/news-snapshots/releases` in the RTPR project) supply article IDs and archived article bodies. Collector observations have a broader population than delivered Telegram cards. They were used for linkage and content review. The saved Discord search pages did not supply a matching October 27 export for these two feeds. Raw RTPR Wire files start on October 28. These counts therefore describe the archived Telegram deliveries.

The export omitted the article link on 6 cards. Their original URL stays blank in the mapping. A ticker, full headline, and same-day feed observation in the normalized archive identified each underlying announcement. When multiple article IDs matched a card, they already belonged to the same content-confirmed event. The mapping reports all possible linked article IDs.

The canonical URL uses the retained article identity without the time-limited signature. The published mapping preserves the original host and path and omits signed query strings. The three alerts labeled (no headline) are linked by article ID and use the archived title. Their original headline placeholders remain in the mapping.

## Cross-article decisions

| Announcement | Content evidence | Archived article IDs |
|---|---|---|
| BEEM | ScoutDI orders for inspections of FPSOs in West Africa during pending acquisition by Beam Global | nGNX6H9w5K-20261027, nGNE9tjLj5-20261027 |
| MEGL | Oct 22 letter of intent with SIN HOPEWAY for five-year timber cooperation and USD 500M trade | nGNE20KgR7-20261027, nGNX57X5mp-20261027 |
| SKYA | Same SkyAI–Bastion tender support and settlement, amended offer includes pre-funded and stapled warrants | nGNX3vRXWw-20261027, nGNXbQr1Y5-20261027 |

SKYA and Bastion announced the same tender support settlement and amendment, so they map to one event. BAER/MTEK and FNGR/GNS are each one article linked to two ticker observations.

## Excluded messages in the exports

All 42 messages in the daily export slices were in scope.

## Input fingerprints

- rule_match · `result copy.json` · SHA-256 `8f7eb0ce378d6caca1e4a5780bd886fcbbd9c8021fbcd7e912801c7b618565b9`
- impact_wire · `result.json` · SHA-256 `f83698462ac045a0be52775b11c9023b196d5edc32e4d0ab9948b262f003203d`
