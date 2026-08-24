import csv
import json
import re

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
    "region",
    "title",
    "title_en",
    "url",
    "include_in_final_report",
    "final_report_section",
    "editor_decision",
    "editor_note",
]

SEA_FIELDS = [
    "unified_id", "game_title", "original_title", "publisher", "developer", "genre", "platforms",
    "sea_st_gross_revenue", "sea_st_downloads", "countries_detected", "top_country_by_revenue",
    "known_existing", "manual_inclusion_override", "manual_inclusion_reason",
    "sg_revenue_gross", "sg_revenue_prior_store", "sg_downloads", "sg_ios_rank", "sg_android_rank",
    "my_revenue_gross", "my_revenue_prior_store", "my_downloads", "my_ios_rank", "my_android_rank",
    "ph_revenue_gross", "ph_revenue_prior_store", "ph_downloads", "ph_ios_rank", "ph_android_rank",
    "id_revenue_gross", "id_revenue_prior_store", "id_downloads", "id_ios_rank", "id_android_rank",
    "th_revenue_gross", "th_revenue_prior_store", "th_downloads", "th_ios_rank", "th_android_rank",
    "vn_revenue_gross", "vn_revenue_prior_store", "vn_downloads", "vn_ios_rank", "vn_android_rank",
    "report_start_date", "report_end_date", "ranking_data_as_of", "meeting_date", "source_files",
]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    assert_true(
        not exporter.country_game_is_included(
            {"id_revenue_gross": "7000", "id_revenue_prior_store": "", "known_existing": "false"}, "ID"
        ),
        "missing prior revenue must fail the country inclusion gate",
    )
    assert_true(
        not exporter.country_game_is_included(
            {"id_revenue_gross": "0", "id_revenue_prior_store": "", "known_existing": "true", "manual_inclusion_override": "yes"}, "ID"
        ),
        "manual approval must not bypass the strict country revenue gate",
    )
    assert_true(
        not exporter.country_game_is_included(
            {"id_revenue_gross": "7000", "id_revenue_prior_store": "100", "known_existing": "true"}, "ID"
        ),
        "known existing games with non-zero prior country revenue must stay excluded",
    )
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
                        "report_classification": "mobile_only",
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-01",
                        "unified_name": "SEA Shared RPG",
                        "english_report_name": "SEA Shared RPG",
                        "unified_id": "sea-shared-rpg",
                        "sg_revenue_gross": "5000",
                        "sg_downloads": "1000",
                        "sg_release_date_reference": "2026-07-22",
                    },
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
                    {
                        "meeting_date": "2026-08-04",
                        "report_start_date": "2026-07-21",
                        "report_end_date": "2026-08-03",
                        "context_type": "high_score_game_announcement",
                        "event_date": "2026-07-30",
                        "hot_score": "",
                        "source": "Regional Games Source",
                        "region": "SEA6",
                        "title": "Regional launch announcement with technical test",
                        "title_en": "Regional launch announcement with technical test",
                        "url": "https://example.com/regional-launch",
                        "include_in_final_report": "yes",
                        "final_report_section": "Game Announcements",
                        "editor_decision": "include",
                        "editor_note": "Approved regional announcement.",
                    },
                ],
                NEWS_FIELDS,
            )
            write_csv(
                meeting_dir / "sea_game_layer.csv",
                [
                    {
                        "unified_id": "shared-rpg",
                        "game_title": "SEA Shared RPG",
                        "original_title": "SEA Shared RPG",
                        "publisher": "SEA Publisher",
                        "genre": "Games",
                        "platforms": "iOS, Android",
                        "sea_st_gross_revenue": "25000",
                        "sea_st_downloads": "12000",
                        "countries_detected": "SG, MY, PH",
                        "top_country_by_revenue": "MY",
                        "known_existing": "false",
                        "sg_revenue_gross": "5000",
                        "sg_revenue_prior_store": "0",
                        "sg_ios_rank": "11",
                        "sg_android_rank": "12",
                        "my_revenue_gross": "18000",
                        "my_revenue_prior_store": "0",
                        "my_ios_rank": "22",
                        "my_android_rank": "23",
                        "ph_revenue_gross": "2000",
                        "ph_revenue_prior_store": "0",
                        "ranking_data_as_of": "2026-08-03",
                        "meeting_date": "2026-08-04",
                    },
                    {
                        "unified_id": "animals-garden-id",
                        "game_title": "Animals Garden",
                        "original_title": "Animals Garden",
                        "sea_st_gross_revenue": "5000",
                        "id_revenue_gross": "5000",
                        "id_revenue_prior_store": "100",
                        "known_existing": "true",
                        "meeting_date": "2026-08-04",
                    },
                    {
                        "unified_id": "unknown-prior",
                        "game_title": "Unknown Prior Game",
                        "original_title": "Unknown Prior Game",
                        "sea_st_gross_revenue": "7000",
                        "sg_revenue_gross": "7000",
                        "meeting_date": "2026-08-04",
                    },
                ],
                SEA_FIELDS,
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

            for exported_row in payload["rows"] + exported_rows:
                assert_true("Signal Type" not in exported_row, "Signal Type must not be exported")
                assert_true("Signal Definition" not in exported_row, "Signal Definition must not be exported")
                assert_true("signal_definition" not in exported_row, "signal_definition must not be exported")
                assert_true(str(exported_row.get("registry_game_id", "")).strip().lower() != "unconfirmed", "unconfirmed registry IDs must not be exported")

            assert_true("Meeting: 04 Aug 2026" in latest_html, "meeting date should come from game layer")
            assert_true("SEA6 Summary" in latest_html, "SEA6 summary should render")
            assert_true(latest_html.index("SEA6 Summary") < latest_html.index("Country Snapshot"), "SEA6 Summary should be the first report view")
            assert_true("SEA6 Gaming Market" in latest_html, "latest brief should use SEA6-neutral heading")
            assert_true("Singapore Gaming Market" not in latest_html, "Singapore should not be the default visible market heading")
            assert_true('data-sea-target="sea6-summary-panel"' in latest_html, "SEA6 tab should control the summary panel")
            for country_code in ("sg", "my", "ph", "id", "th", "vn"):
                assert_true(f'data-sea-target="sea-{country_code}"' in latest_html, f"{country_code} tab should control a country panel")
            css = (docs / "assets" / "static-dashboard.css").read_text(encoding="utf-8")
            assert_true("--dashboard-header-height" in css and "--dashboard-secondary-height" in css, "fixed stack should define shared offsets")
            assert_true(".site-header{position:fixed!important;top:0!important;left:0!important;right:0!important" in css, "main navigation should be the top fixed layer")
            assert_true(".fixed-secondary-row{position:fixed!important;top:var(--dashboard-header-height)!important" in css, "context and country tabs should share the second fixed row")
            assert_true(".sea-country-tabs{position:static!important" in css, "country tab bar should sit inside the fixed second row")
            assert_true("overflow:visible!important" in css and "flex-wrap:wrap!important" in css, "country tabs should wrap instead of horizontally scrolling")
            assert_true("21 Jul-01 Aug 2026" in latest_html, "context dates should use compact visible labels")
            assert_true("Meeting 04 Aug 2026" in latest_html and "Data 01 Aug 2026" in latest_html, "meeting and data labels should retain the year")
            assert_true(".fixed-secondary-inner{max-width:1480px!important;margin:0 auto!important" in css, "secondary navigation should use a centered inner container")
            assert_true(".dashboard-page main#main-content{padding-top:calc(var(--dashboard-header-height) + var(--dashboard-secondary-height) + 16px)!important}" in css, "content should clear the compact fixed stack")
            assert_true("Previous Briefs" not in latest_html, "duplicate previous-brief action should be removed from the context row")
            assert_true('<nav class="top-nav"' in latest_html and 'href="latest-brief.html"' in latest_html, "Latest Brief should remain in primary navigation")
            for country_name in ("Singapore", "Malaysia", "Philippines", "Indonesia", "Thailand", "Vietnam"):
                assert_true(country_name in latest_html, f"{country_name} country view should render")
            assert_true("SEA Shared RPG" in latest_html, "SEA top game should render")
            assert_true("Animals Garden" not in latest_html, "known-existing Animals Garden must not render")
            assert_true("Unknown Prior Game" not in latest_html, "missing prior revenue must not render")
            assert_true("Animals Garden" not in {row["game_title"] for row in payload["sea_summary"]["top_games"]}, "known-existing game must not enter SEA summary")
            assert_true("SG" in latest_html and "MY" in latest_html, "SEA country revenue chips should render")
            assert_true("Signal label" not in latest_html, "SEA summary should not render a signal label column")
            assert_true("Early Revenue Signal" not in latest_html, "early revenue signal labels should not render")
            assert_true("High Revenue Signal" not in latest_html, "high revenue signal labels should not render")
            for country_code, own_value, other_value in (("my", "$18,000", "$5,000"), ("th", "$0", "$5,000")):
                panel_start = latest_html.index(f'id="sea-{country_code}"')
                panel_end = latest_html.find('<section class="sea-view-panel', panel_start + 1)
                country_panel = latest_html[panel_start:panel_end if panel_end >= 0 else None]
                assert_true(own_value in country_panel, f"{country_code} panel should show its own country metric")
                if other_value != "$0":
                    assert_true(other_value not in country_panel, f"{country_code} panel should not leak SG metrics")
            sg_start = latest_html.index('id="sea-sg"')
            sg_end = latest_html.find('<section class="sea-view-panel', sg_start + 1)
            sg_panel = latest_html[sg_start:sg_end if sg_end >= 0 else None]
            my_start = latest_html.index('id="sea-my"')
            my_end = latest_html.find('<section class="sea-view-panel', my_start + 1)
            my_panel = latest_html[my_start:my_end if my_end >= 0 else None]
            assert_true("iOS #11" in sg_panel and "Android #12" in sg_panel, "Singapore should use SG ranks")
            assert_true("iOS #22" in my_panel and "Android #23" in my_panel, "Malaysia should use MY ranks")
            assert_true("iOS #11" not in my_panel and "Android #12" not in my_panel, "Malaysia must not reuse SG ranks")
            missing_rank_card = exporter.sea_country_card(
                {"game_title": "No Rank Game", "my_revenue_gross": "4000", "my_downloads": "10"}, "MY", []
            )
            assert_true("iOS #N/A" in missing_rank_card and "Android #N/A" in missing_rank_card, "missing country ranks should show N/A")
            ph_start = latest_html.index('id="sea-ph"')
            ph_end = latest_html.find('<section class="sea-view-panel', ph_start + 1)
            ph_panel = latest_html[ph_start:ph_end if ph_end >= 0 else None]
            assert_true("$2,000" not in ph_panel, "below-threshold PH rows should not be included")
            assert_true(payload["sea_summary"]["country_summaries"]["PH"]["game_count"] == 0, "PH summary should count only PH-qualified games")
            assert_true(payload["sea_summary"]["country_summaries"]["MY"]["game_count"] == 1, "MY summary should count its own qualifying game")
            assert_true('class="sea-non-tab-content"' in latest_html, "methodology content should remain outside country panels")
            assert_true("Future PC Game" not in latest_html, "PC-only releases outside the period should not render")
            assert_true("Old Revenue Game" not in latest_html, "old revenue-active game should not render in final report")
            star_payload = next(row for row in payload["rows"] if row["Game Title"] == "Star Sailors")
            assert_true("prior revenue was $0" in star_payload["Inclusion Reason"], "commercial-signal inclusion reason should stay in data")
            assert_true("prior revenue was $0" not in star_payload["Key Details"], "key details should describe the game, not inclusion logic")
            assert_true("Mobile + PC Games" in latest_html and "Mobile-only Games" in latest_html and "PC-only Games" in latest_html, "country game sections should be segmented")
            assert_true("Mobile game</span><span class=\"metric-badge neutral\">iOS, Android" not in latest_html, "mobile-only cards should not duplicate platform pills")
            assert_true("Country Snapshot" in latest_html, "country snapshot sections should render")
            assert_true(
                "Rank data reflects the downloaded Sensor Tower chart export." in latest_html
                and "N/A means the game was not present in the downloaded chart rows for that platform/country." in latest_html,
                "country rank limitation note should explain downloaded chart coverage and N/A values",
            )
            assert_true(latest_html.count("PC-only Games") >= 7, "PC-only game sections should appear in SEA6 and every country panel")
            assert_true("Pass the Fear" in latest_html and "Regional PC signal" in latest_html, "PC-only games should render as regional PC signals")
            pc_cards = re.findall(r'<article class="regional-pc-card">(.*?)</article>', latest_html, flags=re.S)
            assert_true(pc_cards and all("ST Gross Revenue" not in card and "ST Downloads" not in card and "iOS #" not in card and "Android #" not in card for card in pc_cards), "PC signal cards must not show mobile metrics")
            steam_context = exporter.steam_context_html(
                {"report_classification": "mobile_led_cross_platform", "Release Date": "2026-07-23", "steamdb_peak": "16791", "steamdb_reviews": "1000", "steam_url": "https://example.com/steam"}
            )
            assert_true("PC equivalent / Steam context" in steam_context, "mobile+PC games should show Steam context")
            assert_true("Peak 16,791" in steam_context and "Reviews 1,000" in steam_context, "mobile+PC Steam stats should render")
            assert_true("Malaysia Game News Context" in latest_html, "country news sections should render")
            assert_true("Reviewed announcement note." in latest_html, "reviewed news note should render")
            assert_true("Approved regional announcement." in latest_html, "approved blank-score regional announcement should render")
            assert_true("Game Announcement" in latest_html and "High-score announcement" not in latest_html, "announcement cards should use the neutral Game Announcement label")
            assert_true("Score 0" not in latest_html, "blank-score announcements should not show a score badge")
            for country_code in ("sg", "my", "ph", "id", "th", "vn"):
                panel_start = latest_html.index(f'id="sea-{country_code}"')
                panel_end = latest_html.find('<section class="sea-view-panel', panel_start + 1)
                country_panel = latest_html[panel_start:panel_end if panel_end >= 0 else None]
                assert_true("Regional launch announcement with technical test" in country_panel, f"regional announcement should render in {country_code.upper()}")
            assert_true("Out-of-period announcement" not in latest_html, "out-of-period news should not render")
            assert_true("SG Performance" not in latest_html, "SG performance blocks should not be used in SEA6 country views")
            pc_payload = next(row for row in payload["rows"] if row["Game Title"] == "Pass the Fear")
            pc_export = next(row for row in exported_rows if row["Game Title"] == "Pass the Fear")
            for pc_row in (pc_payload, pc_export):
                assert_true(pc_row["SG Gross Revenue"] == "", "PC-only rows should not export SG revenue")
                assert_true(pc_row["SG Downloads"] == "", "PC-only rows should not export SG downloads")
                assert_true(pc_row["Top 3 Markets"] == "", "PC-only rows should not export SEA markets")
                assert_true(pc_row["SG App Store Ranks"] == "", "PC-only rows should not export app store ranks")
            assert_true(len(payload["rows"]) == 4, "final JSON should use qualifying game layer rows")
            assert_true(len(payload["news_context"]) == 2, "final JSON should use reviewed news rows")
            assert_true(payload["sea_summary"]["ranking_data_as_of"] == "2026-08-03", "SEA summary ranking date should be exported")
            assert_true(payload["sea_games"][0]["game_title"] == "SEA Shared RPG", "SEA games should be exported")
            assert_true(len(exported_rows) == 4, "final CSV export should match qualifying game layer rows")
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
