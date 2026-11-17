# RTPR PR deduplication — 2026-10-26 UTC

[Unique announcements](unique_pr_20261026.csv) · [Alert-to-event mapping](duplicate_mapping_20261026.csv) · [Price reaction report](pr_price_reaction_20261026.md)

| Metric | Count |
|---|---:|
| Rule Match (Normal PR) messages | 37 |
| Impact Wire messages | 55 |
| Total in-scope messages | 92 |
| Distinct exact headlines before content review | 57 |
| Unique announcements | 54 |
| Rule Match only | 18 |
| Impact Wire only | 27 |
| Both feeds | 9 |
| Duplicate records removed from unique list | 38 |
| Ambiguous event assignments requiring manual review | 0 |

All 92 in-scope messages have a mapping. 18 + 27 + 9 = 54 events. 54 + 38 + 0 = 92 messages. The per-event duplicate count excludes the representative.

## Source and observation clock

Message totals cover qualifying bot PR cards in the two Telegram exports, selected by the half-open UTC interval [2026-10-26 00:00, 2026-10-27 00:00). The export message ID identifies the original alert and `date_unixtime` supplies the observed delivery timestamp. Publication timestamps and the source-latency fields are excluded from the ordering.

When two members of an event share its earliest export second (0 events), the lower Telegram message ID selects the representative deterministically. Delivery order within that second is unresolved at finer precision.

The normalized RTPR release snapshots (files under `data/news-snapshots/releases` in the RTPR project) supply article IDs and archived article bodies. Collector observations have a broader population than delivered Telegram cards. They were used for linkage and content review. The saved Discord search pages did not supply a matching October 26 export for these two feeds. Raw RTPR Wire files start on October 28. These counts therefore describe the archived Telegram deliveries.

The export omitted the article link on 16 cards. Their original URL stays blank in the mapping. A ticker, full headline, and same-day feed observation in the normalized archive identified each underlying announcement. When multiple article IDs matched a card, they already belonged to the same content-confirmed event. The mapping reports all possible linked article IDs.

The canonical URL uses the retained article identity without the time-limited signature. The repository mapping preserves the original article host and path when present. Time-limited query strings were removed from 76 archived links for publication. The unredacted URLs remain in the local export.

## Cross-article decisions

| Announcement | Content evidence | Archived article IDs |
|---|---|---|
| AMAN | Corxel US and Amanat definitive business combination, CX11/CX12 portfolio | nGNE1f5281-20261026, nGNX9R0HVW-20261026 |
| CANF | Namodenoson Phase IIa pancreatic cancer final ESMO data, 16.39-month PFS case | nGNE8nXZzf-20261026, nGNX3jh0cB-20261026 |
| EPOW | Sunrise Guizhou received RMB 110M of RMB 200M at RMB 2B post-money | nGNE6PPf5N-20261026, nGNXb2wZPk-20261026 |
| ERICB | Ericsson Class B buyback report for Oct 19–23, same daily transaction table | nPNAr8wFta-20261026, nPnqpyy9a-20261026, nPre0hFn4a-20261026, nWkr6tqPFf-20261026 |
| FFAI | FFR closed acquisition of Faraday Future robotics business, same closing and platform; longer copies include OmniMind and shipment update | nBw64rzhka-20261026, nBw9drTgqa-20261026, nPn28YW3da-20261026, nPn2jVMPGa-20261026 |
| MGNX | Lorigerlimab LINNET Phase 2 interim data, 25% ORR and 44% DCR | nGNETM8T5-20261026, nGNXbtFtBd-20261026 |
| OPTT | Ocean Power and Stratum nonbinding LOI, PowerBuoy and offshore renewable data center demonstration | nGNE9L6bbF-20261026, nGNX5FjlRz-20261026, nGNX71lgjY-20261026 |
| VAI | Oct 19 agreement for US$5M private placement supporting Youngstown compute center | nGNE4SWBbQ-20261026, nGNX1FxTgz-20261026 |

Separate EXOR events were retained. One reports completed periodic repurchases and the other launches a second tranche. The four FFAI/FFR release variants share the same acquisition closing. The additional OmniMind and shipment detail in two variants was kept in their original mapping rows.

## Excluded messages in the exports

| Feed | Category | Count | Telegram IDs |
|---|---|---:|---|
| impact_wire | human | 3 | 1545, 1546, 1547 |
| impact_wire | test | 2 | 1549, 1551 |
| rule_match | draft | 16 | 1554, 1555, 1557, 1559, 1562, 1564, 1565, 1567, 1571, 1572, 1573, 1575, 1577, 1579, 1581, 1583 |
| rule_match | human | 2 | 1537, 1538 |
| rule_match | test | 3 | 1548, 1550, 1552 |

92 scoped PR cards + 26 out-of-scope messages = 118 messages in the two daily export slices.

## Input fingerprints

- rule_match · `result copy.json` · SHA-256 `8f7eb0ce378d6caca1e4a5780bd886fcbbd9c8021fbcd7e912801c7b618565b9`
- impact_wire · `result.json` · SHA-256 `f83698462ac045a0be52775b11c9023b196d5edc32e4d0ab9948b262f003203d`
