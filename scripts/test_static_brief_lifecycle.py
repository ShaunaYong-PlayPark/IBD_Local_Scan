import csv
import json
import tempfile
from pathlib import Path

import export_static_dashboard as exporter


FIELDS = [
    "Signal Type",
    "Signal Definition",
    "SG Gross Revenue",
    "SG Downloads",
    "Inclusion Reason",
    "Game Title",
    "English Display Title",
    "Original Title",
    "Detected Language",
    "Machine English Title",
    "Manual English Title",
    "Translation Source",
    "Translation Confidence",
    "Translation Review Status",
    "Translation Note",
    "Platform",
    "Publisher",
    "Release Date",
    "Genre",
    "Top 3 Markets",
    "SG App Store Ranks",
    "unified_app_id",
    "run_timestamp_utc",
    "report_start_date",
    "report_end_date",
    "ranking_date",
    "sensor_tower_effective_end_date",
]


def row(title, period_start, period_end, revenue="1000"):
    return {
        "Signal Type": "Strong Market Signal",
        "Signal Definition": "Test signal",
        "SG Gross Revenue": revenue,
        "SG Downloads": "100",
        "Inclusion Reason": "Lifecycle regression fixture.",
        "Game Title": title,
        "English Display Title": title,
        "Original Title": title,
        "Detected Language": "latin",
        "Machine English Title": title,
        "Manual English Title": "",
        "Translation Source": "test",
        "Translation Confidence": "high",
        "Translation Review Status": "not_required",
        "Translation Note": "",
        "Platform": "Mobile",
        "Publisher": "Test Publisher",
        "Release Date": "25-Jun-2026",
        "Genre": "Arcade",
        "Top 3 Markets": "Top Mkts: SG ($1,000 / 100 DL)",
        "SG App Store Ranks": "SG App Store Ranks: iOS (DL #NA / Rev #NA)",
        "unified_app_id": title.lower().replace(" ", "_"),
        "run_timestamp_utc": "2026-07-21T00:00:00+00:00",
        "report_start_date": period_start,
        "report_end_date": period_end,
        "ranking_date": "12-Jul-2026",
        "sensor_tower_effective_end_date": "12-Jul-2026",
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def assert_true(condition, message):
    if not condition:
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
    }

    with tempfile.TemporaryDirectory(prefix="ibd_static_lifecycle_test_") as tmp:
        tmp_path = Path(tmp)
        docs = tmp_path / "docs"
        output = tmp_path / "data" / "output"
        finalized = tmp_path / "data" / "finalized_briefs"
        local_app = tmp_path / "data" / "local_app"
        config = tmp_path / "config"

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

        write_csv(
            exporter.LATEST_FINALIZED_CSV,
            [
                row("Star Sailors", "23-Jun-2026", "13-Jul-2026", "21423.61"),
                row("CookieRun Classic", "23-Jun-2026", "13-Jul-2026", "8166"),
            ],
        )
        write_csv(exporter.FINAL_CSV, [row("Staging Game", "14-Jul-2026", "27-Jul-2026", "0")])
        exporter.METADATA.parent.mkdir(parents=True, exist_ok=True)
        exporter.METADATA.write_text(
            json.dumps(
                {
                    "sensor_tower_data_as_of_date": "2026-07-13",
                    "last_successful_sensor_tower_report_start_date": "2026-06-23",
                    "last_successful_sensor_tower_report_end_date": "2026-07-13",
                }
            ),
            encoding="utf-8",
        )
        exporter.WEEKLY_SUMMARY.write_text(
            json.dumps(
                {
                    "run_timestamp_utc": "2026-07-21T00:00:00+00:00",
                    "mode": "weekly-capture",
                    "report_start_date": "2026-07-14",
                    "report_end_date": "2026-07-27",
                    "ranking_date": "2026-07-19",
                    "new_or_seen_candidates": 0,
                }
            ),
            encoding="utf-8",
        )
        exporter.SCHEDULE.parent.mkdir(parents=True, exist_ok=True)
        exporter.SCHEDULE.write_text(
            json.dumps(
                {
                    "last_completed_meeting_date": "2026-07-14",
                    "upcoming_meeting_date": "2026-07-28",
                    "meeting_time": "16:00",
                }
            ),
            encoding="utf-8",
        )

        exporter.main()

        latest_html = (docs / "latest-brief.html").read_text(encoding="utf-8")
        archive_html = (docs / "historical-briefs.html").read_text(encoding="utf-8")
        payload = json.loads((docs / "data" / "final-report.json").read_text(encoding="utf-8"))
        staging = json.loads((docs / "data" / "weekly-staging-summary.json").read_text(encoding="utf-8"))
        titles = {item["Game Title"] for item in payload["rows"]}

        assert_true("23 Jun 2026 to 13 Jul 2026" in latest_html, "Latest brief should show finalized July period.")
        assert_true("CookieRun Classic" in latest_html, "Latest brief should include CookieRun Classic.")
        assert_true("Star Sailors" in latest_html, "Latest brief should preserve Star Sailors.")
        assert_true("Staging Game" not in latest_html, "Weekly staging output must not replace Latest Brief.")
        assert_true("Current brief" not in archive_html, "Archive must not label staging as Current brief.")
        assert_true("No older finalized briefs yet." in archive_html, "Archive should show empty state without older briefs.")
        assert_true(
            "No weekly candidates found for this extraction window." in archive_html,
            "Staging empty state should appear outside the Latest Brief.",
        )
        assert_true(titles == {"Star Sailors", "CookieRun Classic"}, "Final JSON should contain only finalized brief rows.")
        assert_true(staging["mode"] == "weekly-capture", "Weekly staging summary should keep mode.")
        assert_true(staging["candidate_count"] == 0, "Weekly staging summary should keep candidate count.")
        assert_true(staging["sensor_tower_ranking_date"] == "2026-07-19", "Weekly staging summary should keep ranking date.")

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
    print("STATIC_BRIEF_LIFECYCLE_PASS")


if __name__ == "__main__":
    main()
