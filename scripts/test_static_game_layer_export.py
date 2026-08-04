import csv
import json

import export_static_dashboard as exporter
from test_temp_utils import repo_temp_dir


GAME_REPORT_FIELDS = [
    "report_classification",
    "meeting_date",
    "report_start_date",
    "report_end_date",
    "unified_name",
    "english_report_name",
    "unified_id",
    "unified_publisher_name",
    "sg_downloads",
    "sg_revenue_gross",
    "ios_top_free_rank",
    "ios_top_grossing_rank",
    "android_top_free_rank",
    "android_top_grossing_rank",
    "sg_release_date_reference",
    "sea_market_1_country",
    "sea_market_1_downloads",
    "sea_market_1_revenue_gross",
    "pc_title",
    "steam_app_id",
    "steam_url",
    "pc_release_date",
    "steamdb_peak",
    "steamdb_reviews",
]

GAME_ENRICHED_FIELDS = [
    "report_name",
    "release_date_used",
    "developer",
    "publisher",
    "platforms_confirmed",
    "summary_sentence_1",
    "summary_sentence_2",
    "release_date_source_url",
    "source_urls",
]

NEWS_FIELDS = [
    "meeting_date",
    "report_start_date",
    "report_end_date",
    "context_type",
    "event_date",
    "hot_score",
    "source",
    "title",
    "title_en",
    "url",
    "include_in_final_report",
    "final_report_section",
    "editor_decision",
    "editor_note",
]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    originals = {
        "docs": exporter.DOCS,
        "assets": exporter.ASSETS,
        "data": exporter.DATA,
        "final_csv": exporter.FINAL_CSV,
        "latest_finalized_csv": exporter.LATEST_FINALIZED_CSV,
        "docs_final_csv": exporter.DOCS_FINAL_CSV,
        "docs_final_json": exporter.DOCS_FINAL_JSON,
        "docs_weekly_staging_json": exporter.DOCS_WEEKLY_STAGING_JSON,
        "metadata": exporter.METADATA,
        "weekly_summary": exporter.WEEKLY_SUMMARY,
        "schedule": exporter.SCHEDULE,
        "meeting_pack_output_root": exporter.MEETING_PACK_OUTPUT_ROOT,
    }
    try:
        with repo_temp_dir("static_game_layer_export_") as tmp_path:
            docs = tmp_path / "docs"
            output = tmp_path / "data" / "output"
            finalized = tmp_path / "data" / "finalized_briefs"
            local_app = tmp_path / "data" / "local_app"
            config = tmp_path / "config"
            meeting_dir = output / "meeting_pack" / "2026-08-04"

            exporter.DOCS = docs
            exporter.ASSETS = docs / "assets"
            exporter.DATA = docs / "data"
            exporter.FINAL_CSV = output / "final_sg_market_scan_current_workflow.csv"
            exporter.LATEST_FINALIZED_CSV = finalized / "latest_finalized_brief.csv"
            exporter.DOCS_FINAL_CSV = docs / "data" / "final_sg_market_scan_current_workflow.csv"
            exporter.DOCS_FINAL_JSON = docs / "data" / "final-report.json"
            exporter.DOCS_WEEKLY_STAGING_JSON = docs / "data" / "weekly-staging-summary.json"
            exporter.METADATA = local_app / "extraction_metadata.json"
            exporter.WEEKLY_SUMMARY = output / "weekly_candidate_capture_summary.json"
            exporter.SCHEDULE = config / "static_report_schedule.json"
            exporter.MEETING_PACK_OUTPUT_ROOT = output / "meeting_pack"

            write_csv(
                meeting_dir / "game_report_layer.csv",
                [
                    {
                        "report_classification": "mobile_led_cross_platform",
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-01",
                        "unified_name": "Hololive Dreams",
                        "english_report_name": "Hololive Dreams",
                        "unified_id": "holo",
                        "unified_publisher_name": "CyberAgent",
                        "sg_downloads": "8613",
                        "sg_revenue_gross": "180003.03",
                        "ios_top_free_rank": "87",
                        "ios_top_grossing_rank": "125",
                        "android_top_free_rank": "48",
                        "android_top_grossing_rank": "10",
                        "sg_release_date_reference": "2026-07-09",
                        "sea_market_1_country": "SG",
                        "sea_market_1_downloads": "8613",
                        "sea_market_1_revenue_gross": "180003.03",
                        "pc_title": "Hololive Dreams",
                        "steam_app_id": "100",
                        "steam_url": "https://store.steampowered.com/app/100",
                        "pc_release_date": "2026-07-09",
                        "steamdb_peak": "16791",
                        "steamdb_reviews": "1000",
                    },
                    {
                        "report_classification": "pc_only",
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-01",
                        "pc_title": "Pass the Fear",
                        "steam_app_id": "200",
                        "steam_url": "https://store.steampowered.com/app/200",
                        "pc_release_date": "2026-07-23",
                        "steamdb_peak": "26028",
                        "steamdb_reviews": "500",
                    },
                ],
                GAME_REPORT_FIELDS,
            )
            write_csv(
                meeting_dir / "game_enriched_layer.csv",
                [
                    {
                        "report_name": "Hololive Dreams",
                        "release_date_used": "2026-07-09",
                        "developer": "Test Dev",
                        "publisher": "CyberAgent",
                        "platforms_confirmed": "Mobile + PC",
                        "summary_sentence_1": "Hololive Dreams is a mobile-led cross-platform game.",
                        "summary_sentence_2": "The title has SG revenue and matching PC evidence.",
                        "release_date_source_url": "https://example.com/release",
                        "source_urls": "https://example.com",
                    }
                ],
                GAME_ENRICHED_FIELDS,
            )
            write_csv(
                meeting_dir / "news_context_review.csv",
                [
                    {
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-03",
                        "context_type": "high_score_game_announcement",
                        "event_date": "2026-07-28",
                        "hot_score": "74",
                        "source": "Pocket Tactics",
                        "title": "Call of Duty: Modern Warfare 4 release date",
                        "title_en": "",
                        "url": "https://example.com/cod",
                        "include_in_final_report": "yes",
                        "final_report_section": "Game Announcements",
                        "editor_decision": "include",
                        "editor_note": "Reviewed announcement note.",
                    }
                ],
                NEWS_FIELDS,
            )
            exporter.METADATA.parent.mkdir(parents=True, exist_ok=True)
            exporter.METADATA.write_text(
                json.dumps(
                    {
                        "sensor_tower_data_as_of_date": "2026-08-01",
                        "last_successful_sensor_tower_report_start_date": "2026-07-21",
                        "last_successful_sensor_tower_report_end_date": "2026-08-01",
                    }
                ),
                encoding="utf-8",
            )
            exporter.SCHEDULE.parent.mkdir(parents=True, exist_ok=True)
            exporter.SCHEDULE.write_text(
                json.dumps({"last_completed_meeting_date": "2026-07-21", "upcoming_meeting_date": "2026-08-04"}),
                encoding="utf-8",
            )
            exporter.WEEKLY_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
            exporter.WEEKLY_SUMMARY.write_text("{}", encoding="utf-8")

            exporter.main()
            latest_html = (docs / "latest-brief.html").read_text(encoding="utf-8")
            payload = json.loads((docs / "data" / "final-report.json").read_text(encoding="utf-8"))
            exported_rows = list(csv.DictReader((docs / "data" / "final_sg_market_scan_current_workflow.csv").open(encoding="utf-8-sig")))

            assert_true("Meeting: 04 Aug 2026" in latest_html, "meeting date should come from game layer")
            assert_true("Hololive Dreams" in latest_html, "game layer mobile row should render")
            assert_true("Pass the Fear" in latest_html, "game layer PC row should render")
            assert_true("Hololive Dreams is a mobile-led cross-platform game." in latest_html, "enrichment summary should render")
            assert_true("Reviewed announcement note." in latest_html, "reviewed news note should render")
            assert_true(len(payload["rows"]) == 2, "final JSON should use game layer rows")
            assert_true(len(payload["news_context"]) == 1, "final JSON should use reviewed news rows")
            assert_true(len(exported_rows) == 2, "final CSV export should match game layer rows")
    finally:
        exporter.DOCS = originals["docs"]
        exporter.ASSETS = originals["assets"]
        exporter.DATA = originals["data"]
        exporter.FINAL_CSV = originals["final_csv"]
        exporter.LATEST_FINALIZED_CSV = originals["latest_finalized_csv"]
        exporter.DOCS_FINAL_CSV = originals["docs_final_csv"]
        exporter.DOCS_FINAL_JSON = originals["docs_final_json"]
        exporter.DOCS_WEEKLY_STAGING_JSON = originals["docs_weekly_staging_json"]
        exporter.METADATA = originals["metadata"]
        exporter.WEEKLY_SUMMARY = originals["weekly_summary"]
        exporter.SCHEDULE = originals["schedule"]
        exporter.MEETING_PACK_OUTPUT_ROOT = originals["meeting_pack_output_root"]
    print("STATIC_GAME_LAYER_EXPORT_PASS")


if __name__ == "__main__":
    main()
