import csv
from pathlib import Path

import build_game_news_context_review as review
import export_static_dashboard as exporter
from test_temp_utils import repo_temp_dir


RAW_FIELDS = ["title", "title_en", "url", "context_type"]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    with repo_temp_dir("game_news_review_") as tmp:
        original_root = review.MEETING_PACK_OUTPUT_ROOT
        original_export_root = exporter.MEETING_PACK_OUTPUT_ROOT
        try:
            root = Path(tmp) / "meeting_pack"
            review.MEETING_PACK_OUTPUT_ROOT = root
            exporter.MEETING_PACK_OUTPUT_ROOT = root
            raw = review.raw_path("2026-07-28")
            write_csv(
                raw,
                [
                    {"title": "Announcement", "title_en": "Announcement", "url": "https://a", "context_type": "high_score_game_announcement"},
                    {"title": "Release", "title_en": "Release", "url": "https://b", "context_type": "selected_game_release_news"},
                ],
                RAW_FIELDS,
            )
            destination, rows = review.build("2026-07-28")
            assert_true(len(rows) == 2, "review copies every raw row")
            assert_true(all(not row[field] for row in rows for field in review.REVIEW_FIELDS), "review defaults are blank")
            assert_true(exporter.source_news_context([], {"upcoming_meeting_date": "2026-07-28"}) == [], "blank review rows are not included")

            rows[0]["include_in_final_report"] = "yes"
            rows[0]["final_report_section"] = "Game Announcements"
            rows[0]["editor_decision"] = "include"
            rows[0]["editor_note"] = "Approved fixture row"
            write_csv(destination, rows, RAW_FIELDS + review.REVIEW_FIELDS)
            _, regenerated = review.build("2026-07-28")
            assert_true(regenerated[0]["include_in_final_report"] == "yes", "regeneration preserves include decision")
            assert_true(regenerated[0]["editor_note"] == "Approved fixture row", "regeneration preserves editor note")
            assert_true(regenerated[1]["include_in_final_report"] == "", "unreviewed row remains blank")
            included = exporter.source_news_context([], {"upcoming_meeting_date": "2026-07-28"})
            assert_true(len(included) == 1 and included[0]["title"] == "Announcement", "only yes rows are included")
        finally:
            review.MEETING_PACK_OUTPUT_ROOT = original_root
            exporter.MEETING_PACK_OUTPUT_ROOT = original_export_root
    print("GAME_NEWS_CONTEXT_REVIEW_TEST_PASS")


if __name__ == "__main__":
    main()
