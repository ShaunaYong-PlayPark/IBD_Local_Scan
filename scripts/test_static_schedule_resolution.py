from datetime import date

import resolve_static_automation as resolver


BASE_SCHEDULE = {
    "last_completed_meeting_date": "2026-07-14",
    "upcoming_meeting_date": "2026-07-28",
    "meeting_time": "16:00",
    "timezone": "Asia/Singapore",
    "weekly_candidate_capture": {
        "enabled": True,
        "weekday": "Tuesday",
        "ranking_date_offset_days": 2,
    },
    "meeting_day_final_report": {
        "enabled": True,
        "run_on": "upcoming_meeting_date",
        "ranking_date_offset_days": 1,
    },
}


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def main():
    assert_equal(
        resolver.resolve_auto_mode(BASE_SCHEDULE, date(2026, 7, 21)),
        "weekly-capture",
        "Tuesday before meeting should run weekly capture",
    )
    start, end, ranking = resolver.report_dates(BASE_SCHEDULE, "weekly-capture", date(2026, 7, 21))
    assert_equal(start.isoformat(), "2026-07-14", "Weekly report start")
    assert_equal(end.isoformat(), "2026-07-27", "Weekly report end")
    assert_equal(ranking.isoformat(), "2026-07-19", "Weekly ranking date should account for ST lag")

    assert_equal(
        resolver.resolve_auto_mode(BASE_SCHEDULE, date(2026, 7, 28)),
        "meeting-day-final-report",
        "Meeting day should run final report",
    )
    start, end, ranking = resolver.report_dates(BASE_SCHEDULE, "meeting-day-final-report", date(2026, 7, 28))
    assert_equal(start.isoformat(), "2026-07-14", "Final report start")
    assert_equal(end.isoformat(), "2026-07-27", "Final report end")
    assert_equal(ranking.isoformat(), "2026-07-26", "Final report ranking date")

    assert_equal(
        resolver.resolve_auto_mode(BASE_SCHEDULE, date(2026, 7, 22)),
        "static-export-only",
        "Wednesday should not run extraction",
    )
    assert_equal(
        resolver.resolve_auto_mode(BASE_SCHEDULE, date(2026, 7, 26)),
        "static-export-only",
        "Sunday should not run weekly capture",
    )

    postponed = dict(BASE_SCHEDULE)
    postponed["upcoming_meeting_date"] = "2026-08-04"
    assert_equal(
        resolver.resolve_auto_mode(postponed, date(2026, 7, 28)),
        "weekly-capture",
        "Postponed cycle Tuesday before meeting should run weekly capture",
    )
    assert_equal(
        resolver.resolve_auto_mode(postponed, date(2026, 8, 4)),
        "meeting-day-final-report",
        "Postponed meeting date should run final report",
    )
    start, end, ranking = resolver.report_dates(postponed, "meeting-day-final-report", date(2026, 8, 4))
    assert_equal(start.isoformat(), "2026-07-14", "Postponed final report keeps start date")
    assert_equal(end.isoformat(), "2026-08-03", "Postponed final report extends to day before meeting")
    assert_equal(ranking.isoformat(), "2026-08-02", "Postponed final report ranking date")

    print("STATIC_SCHEDULE_RESOLUTION_PASS")


if __name__ == "__main__":
    main()
