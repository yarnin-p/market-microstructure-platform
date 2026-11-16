# TASK003-S3 — provider session-date alignment amendment

Frozen before any S3 confirmation outcomes. No first-touch, trade, C0/C1/C2 thresholds, deadlines or quote validity/freshness rules change.

The first fully parsed quote object has365,566,423 rows, minimum SIP1779946201011662214 and maximum1780012800465919489, including14,500 rows outside the nominal UTC date. Its source key is the May28 trading date, but some closing SIP messages arrive after00:00 UTC (20:00 ET), by up to0.465919489s in this object. Earlier administrative quotes are also retained. A complete provider object cannot be rejected solely because every SIP timestamp does not fit a civil UTC date.

The original UTC-date-only admission assumption is superseded, explicitly and before signals, by the provider's documented Stocks Flat Files session:04:00–20:00 America/New_York. Use timezone-aware calendar conversion including DST. Coverage intervals represent only this observed provider session; do not expand them to late SIP spill, pre-session administrative records or24-hour continuous market coverage. Original cycle AH/PRE/RTH masks and resets still apply. All original rows and their timestamps remain in the immutable Parquet and raw source; no repair by shifting timestamps or dropping observations.

Admission requires a complete hashed/CRC-validated object and demonstrated timestamp-range intersection with its declared provider session. Record the full min/max and outside-UTC count, not a false zero-spill claim. Wrong-date objects with no session overlap remain coverage-unknown. REST/S3 timestamp/value reconciliation remains mandatory and provides a separate check within the selected windows. Provider-complete object/session evidence is not independent exchange-feed certification.

Source: https://massive.com/docs/flat-files/stocks/overview and https://massive.com/knowledge-base/article/what-timezone-are-massives-timestamps-in . The canonical window comes from provider documentation, not signal/return optimization. Original plan and earlier code hashes are preserved.
