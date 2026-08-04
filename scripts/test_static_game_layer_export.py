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
    "sg_revenue_prior_store",
    "chart_rank_match_status",
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
    "genre",
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
    assert_true(
        exporter.continuity_table_text(
            "Mobile version was first covered in the 21 Jul 2026 brief. This report adds the later Steam PC release."
        ) == "Mobile first covered in 21 Jul 2026 brief; later Steam PC release added here.",
        "continuity table wording",
    )
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
                        "pc_release_date": "2026-07-23",
                        "steamdb_peak": "16791",
                        "steamdb_reviews": "1000",
                    },
                    {
                        "report_classification": "mobile_only",
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-01",
                        "unified_name": "Old Revenue Game",
                        "english_report_name": "Old Revenue Game",
                        "unified_id": "old",
                        "unified_publisher_name": "Old Publisher",
                        "sg_downloads": "1000",
                        "sg_revenue_gross": "1500",
                        "sg_revenue_prior_store": "100",
                        "chart_rank_match_status": "matched",
                        "ios_top_free_rank": "100",
                        "ios_top_grossing_rank": "",
                        "android_top_free_rank": "90",
                        "android_top_grossing_rank": "",
                        "sg_release_date_reference": "2026/06/16",
                        "sea_market_1_country": "SG",
                        "sea_market_1_downloads": "1000",
                        "sea_market_1_revenue_gross": "1500",
                    },
                    {
                        "report_classification": "mobile_only",
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-01",
                        "unified_name": "Star Sailors",
                        "english_report_name": "Star Sailors",
                        "unified_id": "star-sailors",
                        "unified_publisher_name": "Com2uS Holdings",
                        "sg_downloads": "2536",
                        "sg_revenue_gross": "13495.77",
                        "sg_revenue_prior_store": "0",
                        "chart_rank_match_status": "matched",
                        "sg_release_date_reference": "2026/02/19",
                        "sea_market_1_country": "SG",
                        "sea_market_1_downloads": "2536",
                        "sea_market_1_revenue_gross": "13495.77",
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
                    {
                        "report_classification": "pc_only",
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-01",
                        "pc_title": "Future PC Game",
                        "steam_app_id": "201",
                        "pc_release_date": "2026-08-10",
                        "steamdb_peak": "30000",
                        "steamdb_reviews": "600",
                    },
                ],
                GAME_REPORT_FIELDS,
            )
            write_csv(
                meeting_dir / "game_enriched_layer.csv",
                [
                    {
                        "report_name": "Hololive Dreams",
                        "release_date_used": "2026-07-23",
                        "developer": "Test Dev",
                        "publisher": "CyberAgent",
                        "genre": "Rhythm RPG",
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
                    },
                    {
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-01",
                        "context_type": "high_score_game_announcement",
                        "event_date": "2026-08-02",
                        "hot_score": "90",
                        "source": "Pocket Tactics",
                        "title": "Out-of-period announcement",
                        "title_en": "Out-of-period announcement",
                        "url": "https://example.com/out-of-period",
                        "include_in_final_report": "yes",
                        "final_report_section": "Game Announcements",
                        "editor_decision": "include",
                        "editor_note": "Should be filtered by event date.",
                    },
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
            assert_true("Future PC Game" not in latest_html, "PC-only releases outside the period should not render")
            assert_true("Old Revenue Game" not in latest_html, "old revenue-active game should not render in final report")
            assert_true("Star Sailors" in latest_html, "zero-prior-revenue commercial signal should render despite old Sensor Tower date")
            star_payload = next(row for row in payload["rows"] if row["Game Title"] == "Star Sailors")
            assert_true("prior revenue was $0" in star_payload["Inclusion Reason"], "commercial-signal inclusion reason should stay in data")
            assert_true("prior revenue was $0" not in star_payload["Key Details"], "key details should describe the game, not inclusion logic")
            assert_true("Mobile Games" in latest_html, "mobile release group should render")
            assert_true("Mobile + PC Games" in latest_html, "mobile plus PC release group should render")
            assert_true("PC-only Games" in latest_html, "PC-only release group should render")
            mobile_group_start = latest_html.index("<h3 class=\"signal-heading\">Mobile Games")
            mobile_pc_group_start = latest_html.index("<h3 class=\"signal-heading\">Mobile + PC Games")
            mobile_group_html = latest_html[mobile_group_start:mobile_pc_group_start]
            assert_true("data-table" not in mobile_group_html, "empty release groups should not show irrelevant tables")
            assert_true("Mobile-led game with PC version" in latest_html, "cross-platform classification should be visible")
            assert_true("Mobile game" in latest_html, "mobile classification should be visible")
            assert_true("PC-only game" in latest_html, "PC-only classification should be visible")
            assert_true("hololive Dreams is a mobile-led Rhythm RPG" in latest_html, "gameplay summary should render")
            assert_true("Its USP is the hololive fan ecosystem" in latest_html, "USP summary should render")
            assert_true("Rhythm RPG" in latest_html, "enrichment genre should render")
            assert_true("Reviewed announcement note." in latest_html, "reviewed news note should render")
            assert_true("Out-of-period announcement" not in latest_html, "out-of-period news should not render")
            card_starts = []
            cursor = 0
            marker = '<article class="signal-card'
            while True:
                start = latest_html.find(marker, cursor)
                if start < 0:
                    break
                card_starts.append(start)
                cursor = start + len(marker)
            cards = [latest_html[start : latest_html.index("</article>", start)] for start in card_starts]
            mobile_card = next(card for card in cards if "Hololive Dreams" in card)
            pc_card = next(card for card in cards if "Pass the Fear" in card)
            assert_true("SG Performance" in mobile_card, "mobile games should show SG performance")
            assert_true("PC Context" in mobile_card, "mobile plus PC games should show PC context")
            assert_true("PC Context" in pc_card, "PC-only games should show PC context")
            assert_true("SG Performance" not in pc_card, "PC-only games should not show SG performance")
            assert_true("Top Markets" not in pc_card, "PC-only games should not show SEA market cards")
            assert_true("Ranks" not in pc_card, "PC-only games should not show app store ranks")
            assert_true("$0" not in pc_card and ">0<" not in pc_card and ">N/A<" not in pc_card, "PC-only cards should not show mobile placeholder stats")
            assert_true("Watchlist focus" not in latest_html and "monitoring item" not in latest_html, "monitoring summary should be absent")
            pc_payload = next(row for row in payload["rows"] if row["Game Title"] == "Pass the Fear")
            pc_export = next(row for row in exported_rows if row["Game Title"] == "Pass the Fear")
            for pc_row in (pc_payload, pc_export):
                assert_true(pc_row["SG Gross Revenue"] == "", "PC-only rows should not export SG revenue")
                assert_true(pc_row["SG Downloads"] == "", "PC-only rows should not export SG downloads")
                assert_true(pc_row["Top 3 Markets"] == "", "PC-only rows should not export SEA markets")
                assert_true(pc_row["SG App Store Ranks"] == "", "PC-only rows should not export app store ranks")
            assert_true(len(payload["rows"]) == 3, "final JSON should use qualifying game layer rows")
            assert_true(len(payload["news_context"]) == 1, "final JSON should use reviewed news rows")
            assert_true(len(exported_rows) == 3, "final CSV export should match qualifying game layer rows")
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
