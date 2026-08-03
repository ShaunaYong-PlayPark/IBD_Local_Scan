import csv
from datetime import date
from pathlib import Path

import build_radar_manual_check_candidates as radar
from test_temp_utils import repo_temp_dir


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def fixture_payload():
    return {
        "generated_at": "2026-07-26T05:41:20+00:00",
        "retention_days": 110,
        "items": [
            {
                "site_id": "sg_source",
                "site_name": "SG Source",
                "source": "SG Source",
                "title": "Known Game launched in Singapore",
                "title_en": "Known Game launched in Singapore",
                "url": "https://example.com/known-sg",
                "published_at": "2026-07-26T00:00:00+00:00",
                "first_seen_at": "2026-07-26T01:00:00+00:00",
                "last_seen_at": "2026-07-26T01:00:00+00:00",
                "region": "SG",
                "region_label": "Singapore",
                "content_type": "launch",
                "source_dedicated": True,
                "ingestion_path": "direct_feed",
            },
            {
                "site_id": "my_source",
                "site_name": "MY Source",
                "source": "MY Source",
                "title": "Mystic Quest now available",
                "title_en": "Mystic Quest now available",
                "url": "https://example.com/mystic-my",
                "published_at": "2026-07-25T00:00:00+00:00",
                "first_seen_at": "2026-07-25T01:00:00+00:00",
                "last_seen_at": "2026-07-25T01:00:00+00:00",
                "region": "MY",
                "region_label": "Malaysia",
                "content_type": "general",
                "source_dedicated": True,
                "ingestion_path": "direct_feed",
            },
            {
                "site_id": "misc_source",
                "site_name": "Misc Source",
                "source": "Misc Source",
                "title": "Puzzle hints and answers released",
                "title_en": "Puzzle hints and answers released",
                "url": "https://example.com/misc",
                "published_at": "2026-07-25T00:00:00+00:00",
                "region": "MISC",
                "region_label": "Misc",
                "content_type": "launch",
            },
        ],
    }


def fixture_schedule(upcoming="2026-07-28"):
    return {
        "last_completed_meeting_date": "2026-07-14",
        "upcoming_meeting_date": upcoming,
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


def dated_item(label, event_date, region="SG"):
    return {
        "site_id": f"{region.lower()}_source_{label}",
        "site_name": f"{region} Source",
        "source": f"{region} Source",
        "title": f"{label} launched",
        "title_en": f"{label} launched",
        "url": f"https://example.com/{label}",
        "published_at": f"{event_date}T00:00:00+00:00",
        "first_seen_at": f"{event_date}T01:00:00+00:00",
        "last_seen_at": f"{event_date}T01:00:00+00:00",
        "region": region,
        "region_label": "Singapore" if region == "SG" else region,
        "content_type": "launch",
        "source_dedicated": True,
        "ingestion_path": "direct_feed",
    }


def dated_payload(*items):
    return {
        "generated_at": "2026-07-26T05:41:20+00:00",
        "retention_days": 110,
        "items": list(items),
    }


def known_titles():
    return {radar.normalize_text("Known Game"): "Known Game"}


def test_json_fixture_parsing():
    payload = fixture_payload()
    assert_equal(len(radar.radar_items(payload)), 3, "fixture item count")
    assert_equal(payload["retention_days"], 110, "fixture retention days")


def test_region_priority_sorting():
    payload = fixture_payload()
    rows = radar.build_candidates(payload, known_titles())
    assert_equal([row["candidate_region"] for row in rows], ["SG", "MY"], "region priority order")


def test_launch_term_filtering():
    item = fixture_payload()["items"][1]
    row = radar.candidate_from_item(item, fixture_payload(), known_titles())
    assert_true(row is not None, "launch term should include non-launch content_type")
    assert_true("now available" in row["launch_signal_reason"], "launch reason includes term")


def test_misc_exclusion():
    payload = fixture_payload()
    rows = radar.build_candidates(payload, known_titles())
    assert_true("MISC" not in [row["candidate_region"] for row in rows], "MISC excluded")


def test_global_cap_behavior():
    payload = {
        "generated_at": "2026-07-26T05:41:20+00:00",
        "retention_days": 110,
        "items": [],
    }
    for index in range(55):
        payload["items"].append(
            {
                "site_id": "global",
                "site_name": "Global Source",
                "source": "Global Source",
                "title": f"Global Game {index} launched worldwide",
                "title_en": f"Global Game {index} launched worldwide",
                "url": f"https://example.com/global-{index}",
                "published_at": "2026-07-26T00:00:00+00:00",
                "region": "GLOBAL",
                "region_label": "Global",
                "content_type": "launch",
            }
        )
    rows = radar.build_candidates(payload, {})
    assert_equal(sum(1 for row in rows if row["candidate_region"] == "GLOBAL"), 50, "GLOBAL cap")


def test_known_existing_match_marked_not_removed():
    rows = radar.build_candidates(fixture_payload(), known_titles())
    known_rows = [row for row in rows if row["known_existing_match"]]
    assert_equal(len(known_rows), 1, "known existing row retained")
    assert_equal(known_rows[0]["candidate_region"], "SG", "known row region")


def test_default_report_period_filtering():
    start, end = radar.report_period(fixture_schedule())
    assert_equal(start, date(2026, 7, 14), "default report period start")
    assert_equal(end, date(2026, 7, 27), "default report period end")

    rows = radar.build_candidates(
        dated_payload(
            dated_item("before", "2026-07-13"),
            dated_item("inside", "2026-07-20"),
            dated_item("after", "2026-07-28"),
        ),
        {},
        start,
        end,
    )
    assert_equal([row["candidate_game_name"] for row in rows], ["inside"], "default report window")
    assert_equal(rows[0]["report_start_date"], "2026-07-14", "row report start")
    assert_equal(rows[0]["report_end_date"], "2026-07-27", "row report end")
    assert_equal(rows[0]["radar_event_date"], "2026-07-20", "row event date")


def test_item_before_report_start_excluded():
    start, end = radar.report_period(fixture_schedule())
    rows = radar.build_candidates(dated_payload(dated_item("before", "2026-07-13")), {}, start, end)
    assert_equal(rows, [], "item before report start excluded")


def test_item_on_report_start_included():
    start, end = radar.report_period(fixture_schedule())
    rows = radar.build_candidates(dated_payload(dated_item("start", "2026-07-14")), {}, start, end)
    assert_equal(len(rows), 1, "item on report start included")


def test_item_on_report_end_included():
    start, end = radar.report_period(fixture_schedule())
    rows = radar.build_candidates(dated_payload(dated_item("end", "2026-07-27")), {}, start, end)
    assert_equal(len(rows), 1, "item on report end included")


def test_item_after_report_end_excluded():
    start, end = radar.report_period(fixture_schedule())
    rows = radar.build_candidates(dated_payload(dated_item("after", "2026-07-28")), {}, start, end)
    assert_equal(rows, [], "item after report end excluded")


def test_postponed_meeting_extends_report_end_date():
    start, end = radar.report_period(fixture_schedule("2026-08-04"))
    assert_equal(start, date(2026, 7, 14), "postponed report start")
    assert_equal(end, date(2026, 8, 3), "postponed report end")
    rows = radar.build_candidates(
        dated_payload(
            dated_item("old-window-end", "2026-07-27"),
            dated_item("extended-window", "2026-08-03"),
            dated_item("too-late", "2026-08-04"),
        ),
        {},
        start,
        end,
    )
    assert_equal(
        [row["candidate_game_name"] for row in rows],
        ["extended-window", "old-window-end"],
        "postponed window includes extended dates only",
    )


def test_csv_headers_exact():
    with repo_temp_dir("radar_manual_check_") as tmp:
        path = Path(tmp) / "out.csv"
        radar.write_csv(path, [])
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
    assert_equal(headers, radar.CSV_FIELDS, "CSV headers")


def main():
    test_json_fixture_parsing()
    test_region_priority_sorting()
    test_launch_term_filtering()
    test_misc_exclusion()
    test_global_cap_behavior()
    test_known_existing_match_marked_not_removed()
    test_default_report_period_filtering()
    test_item_before_report_start_excluded()
    test_item_on_report_start_included()
    test_item_on_report_end_included()
    test_item_after_report_end_excluded()
    test_postponed_meeting_extends_report_end_date()
    test_csv_headers_exact()
    print("RADAR_MANUAL_CHECK_CANDIDATES_TEST_PASS")


if __name__ == "__main__":
    main()
