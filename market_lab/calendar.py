from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from importlib.metadata import version

import exchange_calendars as xcals
import pandas as pd

NY = ZoneInfo("America/New_York")


def cycles(end, count=120):
    if count < 1:
        raise ValueError("cycles must be positive")
    end = pd.Timestamp(end)
    start = end - pd.Timedelta(days=count * 3 + 30)
    cal = xcals.get_calendar("XNYS", start=start, end=end)
    sessions = cal.sessions[cal.sessions <= end]
    if len(sessions) < count + 1:
        raise ValueError("insufficient calendar sessions")
    rows = []
    for session in sessions[-count:]:
        previous = cal.previous_session(session)
        def local(day, hour):
            return datetime.combine(day.date(), time(hour), NY).isoformat()
        rows.append({"cycle_id": session.date().isoformat(), "anchor_date": previous.date().isoformat(),
                     "anchor_at": cal.session_close(previous).isoformat(),
                     "rth_open": cal.session_open(session).isoformat(), "end_at": cal.session_close(session).isoformat(),
                     "premarket_start": local(session, 4), "afterhours_end": local(previous, 20),
                     "calendar": "XNYS", "timezone": "America/New_York",
                     "calendar_version": version("exchange-calendars"),
                     "split_group": ("EXPLORATION" if len(rows) < 80 else "HOLDOUT") if count == 120 else "PILOT",
                     "early_close": cal.session_close(session).tz_convert(NY).hour < 16,
                     "extended_hours_status": "PROVIDER_COVERAGE_WINDOW_NOT_VENUE_SCHEDULE"})
    return rows


def segment(cycle, timestamp):
    t = pd.Timestamp(timestamp)
    if t.tzinfo is None:
        raise ValueError("timezone required")
    anchor, end = pd.Timestamp(cycle["anchor_at"]), pd.Timestamp(cycle["end_at"])
    if not anchor < t <= end:
        return "OUTSIDE_CYCLE"
    if t < pd.Timestamp(cycle["afterhours_end"]):
        return "AFTER_HOURS"
    if pd.Timestamp(cycle["premarket_start"]) <= t < pd.Timestamp(cycle["rth_open"]):
        return "PREMARKET"
    if pd.Timestamp(cycle["rth_open"]) <= t <= end:
        return "RTH"
    return "OUTSIDE_OBSERVED_COVERAGE"
