import json
import tempfile
from pathlib import Path

import candidate_store
import current_report_watchlist_workflow as final_workflow
import meeting_date_final_report


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def layer2_row(uid, app_id, ranking_date):
    return {
        "run_timestamp_utc": f"{ranking_date}T00:00:00+00:00",
        "ranking_date": ranking_date,
        "country": "SG",
        "platform": "ios",
        "app_id": app_id,
        "released_tag_matches": "~ 1 week",
        "sg_chart_matches": "Top Grossing #10",
        "best_sg_rank": "10",
        "candidate_reason": "Test candidate.",
        "chart_match_details_json": json.dumps(
            [{"chart_type": final_workflow.IOS_REV_CHART, "chart_label": "Top Grossing", "rank": 10}]
        ),
        "unified_app_id": uid,
        "unified_app_name": uid,
        "ios_app_ids": app_id,
        "android_app_ids": "",
        "unified_lookup_status": "test",
        "raw_unified_app_json": "{}",
    }


def metadata_row(uid, app_id, title):
    return {
        "unified_app_id": uid,
        "unified_app_name": title,
        "publisher_name": "Test Publisher",
        "publisher_id": "test_publisher",
        "developer": "",
        "genre": "Arcade",
        "category_ids": "",
        "category_labels": "Arcade",
        "ios_app_ids": app_id,
        "android_app_ids": "",
        "platforms_seen_in_layer1": "ios",
        "best_sg_rank": "10",
        "release_date": "2026-07-20",
        "country_release_date": "2026-07-20",
        "representative_country_release_date": "2026-07-20",
        "active": "True",
        "valid_in_sg": "True",
        "metadata_lookup_status": "test",
        "raw_app_metadata_json": "{}",
        "original_title": title,
        "detected_language": "latin",
        "machine_english_title": title,
        "manual_english_title": "",
        "display_title": title,
        "translation_source": "test",
        "translation_confidence": "high",
        "translation_review_status": "not_required",
        "translation_note": "",
    }


def store_row(uid, title, detected_date):
    return {
        **{field: "" for field in candidate_store.STORE_FIELDS},
        "unified_app_id": uid,
        "ios_app_ids": f"ios_{uid}",
        "title": title,
        "english_display_title": title,
        "original_title": title,
        "publisher": "Test Publisher",
        "genre": "Arcade",
        "platform": "iOS",
        "release_date": detected_date,
        "country_release_date": detected_date,
        "release_evidence_date": detected_date,
        "first_detected_date": detected_date,
        "first_detected_timestamp_utc": f"{detected_date}T00:00:00+00:00",
        "latest_extraction_date": detected_date,
        "latest_extraction_timestamp_utc": f"{detected_date}T00:00:00+00:00",
        "latest_ranking_date": detected_date,
        "source_bucket": "~ 1 week",
        "sg_top_grossing_evidence_at_detection": "Stored test evidence.",
        "sg_chart_matches_at_detection": "Top Grossing #10",
        "best_sg_rank_at_detection": "10",
        "display_title": title,
        "active": "True",
        "valid_in_sg": "True",
        "raw_layer2_rows_json": json.dumps([layer2_row(uid, f"ios_{uid}", detected_date)]),
        "detection_history_json": json.dumps([{"ranking_date": detected_date}]),
    }


def test_meeting_day_step_order():
    expected_scripts = [
        "scripts/weekly_candidate_capture.py",
        "scripts/prepare_report_period_candidates.py",
        "scripts/refresh_report_period_ranks.py",
        "scripts/layer4_fetch_sea6_sales_metrics.py",
        "scripts/current_report_watchlist_workflow.py",
    ]
    assert_equal([script for _, script in meeting_date_final_report.STEPS], expected_scripts, "Meeting-day step order")

    original_run_script = meeting_date_final_report.run_script
    original_write_metadata = meeting_date_final_report.write_successful_sensor_tower_refresh_metadata
    calls = []
    try:
        meeting_date_final_report.run_script = lambda label, script: calls.append(script)
        meeting_date_final_report.write_successful_sensor_tower_refresh_metadata = lambda: calls.append("metadata")
        meeting_date_final_report.main()
    finally:
        meeting_date_final_report.run_script = original_run_script
        meeting_date_final_report.write_successful_sensor_tower_refresh_metadata = original_write_metadata
    assert_equal(calls, expected_scripts + ["metadata"], "Meeting-day main should capture before consolidation")


def test_candidate_store_consolidation():
    originals = {
        "config": candidate_store.CONFIG_PATH,
        "store": candidate_store.CANDIDATE_STORE_CSV,
        "snapshot": candidate_store.SNAPSHOT_DIR,
        "layer2": candidate_store.LAYER2_CSV,
        "layer3": candidate_store.LAYER3_CSV,
        "layer3_5": candidate_store.LAYER3_5_CSV,
    }
    with tempfile.TemporaryDirectory(prefix="ibd_meeting_consolidation_test_") as tmp:
        tmp_path = Path(tmp)
        candidate_store.CONFIG_PATH = tmp_path / "settings.json"
        candidate_store.CANDIDATE_STORE_CSV = tmp_path / "weekly_candidate_store.csv"
        candidate_store.SNAPSHOT_DIR = tmp_path / "snapshots"
        candidate_store.LAYER2_CSV = tmp_path / "layer2_unified_candidates.csv"
        candidate_store.LAYER3_CSV = tmp_path / "layer3_unique_game_metadata.csv"
        candidate_store.LAYER3_5_CSV = tmp_path / "layer3_5_title_normalised_metadata.csv"

        candidate_store.CONFIG_PATH.write_text(
            json.dumps(
                {
                    "report_start_date": "2026-07-14",
                    "report_end_date": "2026-08-03",
                    "ranking_date": "2026-07-26",
                }
            ),
            encoding="utf-8",
        )
        previous = [
            store_row("previous_uid", "Previous Weekly Game", "2026-07-21"),
            store_row("duplicate_uid", "Duplicate Game", "2026-07-21"),
            store_row("outside_uid", "Outside Game", "2026-06-30"),
        ]
        candidate_store.write_csv(candidate_store.CANDIDATE_STORE_CSV, previous, candidate_store.STORE_FIELDS)
        candidate_store.write_csv(
            candidate_store.LAYER2_CSV,
            [
                layer2_row("current_uid", "ios_current_uid", "2026-07-26"),
                layer2_row("duplicate_uid", "ios_duplicate_uid", "2026-07-26"),
            ],
            list(layer2_row("current_uid", "ios_current_uid", "2026-07-26").keys()),
        )
        candidate_store.write_csv(
            candidate_store.LAYER3_5_CSV,
            [
                metadata_row("current_uid", "ios_current_uid", "Current Week Game"),
                metadata_row("duplicate_uid", "ios_duplicate_uid", "Duplicate Game"),
            ],
            list(metadata_row("current_uid", "ios_current_uid", "Current Week Game").keys()),
        )

        current_rows, store_rows, _ = candidate_store.upsert_from_current_outputs()
        assert_equal({row["unified_app_id"] for row in current_rows}, {"current_uid", "duplicate_uid"}, "Current-week capture rows")
        assert_true(any(row["unified_app_id"] == "current_uid" for row in store_rows), "Current-week candidates saved")
        assert_equal(
            sum(1 for row in store_rows if row.get("unified_app_id") == "duplicate_uid"),
            1,
            "Duplicate candidates should not repeat in store",
        )

        selected = candidate_store.select_report_period_candidates()
        selected_ids = {row["unified_app_id"] for row in selected}
        assert_equal(selected_ids, {"previous_uid", "duplicate_uid", "current_uid"}, "Extended report period candidates")
    candidate_store.CONFIG_PATH = originals["config"]
    candidate_store.CANDIDATE_STORE_CSV = originals["store"]
    candidate_store.SNAPSHOT_DIR = originals["snapshot"]
    candidate_store.LAYER2_CSV = originals["layer2"]
    candidate_store.LAYER3_CSV = originals["layer3"]
    candidate_store.LAYER3_5_CSV = originals["layer3_5"]


def test_na_rank_does_not_remove_qualifying_game():
    game = {
        "unified_app_id": "na_rank_uid",
        "unified_app_name": "N/A Rank Game",
        "display_title": "N/A Rank Game",
        "publisher_name": "Test Publisher",
        "ios_app_ids": "123",
        "android_app_ids": "",
        "country_release_date": "2026-07-20",
        "genre": "Arcade",
    }
    chart = {
        "has_top_free": False,
        "has_top_grossing": False,
        "ios_dl_rank": None,
        "ios_rev_rank": None,
        "android_dl_rank": None,
        "android_rev_rank": None,
        "first_top_grossing_seen_date": "",
    }
    countries = [{"unified_app_id": "na_rank_uid", "country": "SG", "gross_revenue_dollars": "1500", "total_downloads": "25"}]
    config = {"report_start_date": "2026-07-14", "report_end_date": "2026-08-03", "ranking_date": "2026-08-02"}
    final = final_workflow.final_row(
        game,
        chart,
        countries,
        config,
        "2026-08-04T00:00:00+00:00",
        "Strong Market Signal",
        "Stored weekly candidate with SG gross revenue > $1,000 during the report period",
    )
    assert_equal(final["Game Title"], "N/A Rank Game", "Qualifying game should still produce final row")
    assert_true("#NA" in final["SG App Store Ranks"], "Missing ranks should display N/A")


def main():
    test_meeting_day_step_order()
    test_candidate_store_consolidation()
    test_na_rank_does_not_remove_qualifying_game()
    print("MEETING_DAY_CAPTURE_CONSOLIDATION_PASS")


if __name__ == "__main__":
    main()
