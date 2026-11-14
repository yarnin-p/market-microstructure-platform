"""Standalone planning check; does not import or validate market_lab.

Run from repository root:
  .venv/bin/python docs/plans/task-001-m1-v0.1/evidence/check_calendar.py
"""

import json
import platform
from importlib.metadata import version

import exchange_calendars as xc


def main():
    calendar = xc.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2026-01-01", "2026-11-13")[-120:]
    assert len(sessions) == 120
    assert sessions.is_unique and sessions.is_monotonic_increasing
    assert len(sessions[:80]) == 80 and len(sessions[80:]) == 40
    assert not set(sessions[:80]).intersection(sessions[80:])
    assert calendar.previous_session(sessions[0]).strftime("%Y-%m-%d") == "2026-05-26"

    holidays = ["2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26"]
    for day in holidays:
        assert not calendar.is_session(day), day
    for day in ["2026-11-27", "2026-12-24"]:
        close = calendar.session_close(day).tz_convert("America/New_York")
        assert (close.hour, close.minute) == (13, 0), day
    for day, expected_hour in [
        ("2026-03-06", 14), ("2026-03-09", 13),
        ("2026-10-30", 13), ("2026-11-02", 14),
    ]:
        assert calendar.session_open(day).hour == expected_hour, day

    cycles = []
    for index, session in enumerate(sessions):
        previous = calendar.previous_session(session)
        anchor = calendar.session_close(previous)
        end = calendar.session_close(session)
        assert anchor < calendar.session_open(session) < end
        if cycles:
            assert anchor.isoformat() == cycles[-1]["end_utc"]
        cycles.append({
            "ordinal": index + 1,
            "cycle_id": session.strftime("%Y-%m-%d"),
            "previous_session": previous.strftime("%Y-%m-%d"),
            "anchor_utc": anchor.isoformat(),
            "rth_open_utc": calendar.session_open(session).isoformat(),
            "end_utc": end.isoformat(),
            "split": "EXPLORATION" if index < 80 else "HOLDOUT",
        })

    print(json.dumps({
        "status": "PASS",
        "scope": "Standalone calendar feasibility; not market-data or platform validation",
        "python": platform.python_version(),
        "exchange_calendars": version("exchange_calendars"),
        "calendar": "XNYS",
        "timezone": "America/New_York",
        "proposed_end_date": "2026-11-13",
        "policy_status": "PROPOSED_NOT_APPROVED",
        "counts": {"cycles": 120, "exploration": 80, "holdout": 40},
        "first_cycle": cycles[0]["cycle_id"],
        "exploration_end": cycles[79]["cycle_id"],
        "holdout_start": cycles[80]["cycle_id"],
        "last_cycle": cycles[-1]["cycle_id"],
        "checks": [
            "120 unique ordered cycles", "80/40 disjoint split", "prior anchor",
            "adjacent cycle continuity", "holiday exclusion", "spring DST",
            "fall DST", "13:00 ET early closes",
        ],
        "cycles": cycles,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
