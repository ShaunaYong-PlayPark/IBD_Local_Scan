import csv
from pathlib import Path

import build_game_news_context_layer as layer
import build_game_news_context_review as review
import export_static_dashboard as exporter
from test_temp_utils import repo_temp_dir


RAW_FIELDS = ["title", "title_en", "url", "context_type"]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
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

            filtered_rows = [
                {
                    "title": "Action figures selling out",
                    "title_en": "Action figures selling out",
                    "url": "https://example.com/toys",
                    "context_type": "high_score_game_announcement",
                    "include_in_final_report": "yes",
                    "editor_decision": "include",
                },
                {
                    "title": "How to play the game in order",
                    "title_en": "How to play the game in order",
                    "url": "https://example.com/guide",
                    "context_type": "high_score_game_announcement",
                    "include_in_final_report": "yes",
                    "editor_decision": "include",
                },
                {
                    "title": "Future game release announced",
                    "title_en": "Future game release announced",
                    "url": "https://example.com/release",
                    "context_type": "high_score_game_announcement",
                    "include_in_final_report": "yes",
                    "editor_decision": "include",
                },
                {
                    "title": "GTA 6 pre-order demand reaches a new record",
                    "title_en": "GTA 6 pre-order demand reaches a new record",
                    "url": "https://example.com/gta6",
                    "context_type": "high_score_game_announcement",
                    "include_in_final_report": "yes",
                    "final_report_section": "Game Announcements",
                    "editor_decision": "include",
                },
            ]
            write_csv(destination, filtered_rows, RAW_FIELDS + review.REVIEW_FIELDS)
            included = exporter.source_news_context([], {"upcoming_meeting_date": "2026-07-28"})
            assert_true(
                len(included) == 2
                and {row["title"] for row in included}
                == {"Future game release announced", "GTA 6 pre-order demand reaches a new record"},
                "banned news categories are excluded even when marked yes",
            )

            regional_candidate = {
                "radar_section": "game_announcements",
                "title": "Three Kingdoms: Throne War opens pre-registration across Southeast Asia",
                "title_en": "Three Kingdoms: Throne War opens pre-registration across Southeast Asia",
                "url": "https://example.com/three-kingdoms",
                "published_at": "2026-08-12T00:00:00+00:00",
                "hot_score": "",
                "region": "SEA6",
            }
            review_candidates = layer.build_rows(
                [],
                {"hot_news": [regional_candidate], "generated_at": "2026-08-24T00:00:00+00:00"},
                "2026-07-28",
                layer.parse_date("2026-07-21"),
                layer.parse_date("2026-08-17"),
            )
            assert_true(len(review_candidates) == 1, "blank-score regional announcement should reach review")
            review_row = dict(review_candidates[0])
            review_row.update({"include_in_final_report": "", "editor_decision": ""})
            write_csv(destination, [review_row], RAW_FIELDS + review.REVIEW_FIELDS)
            assert_true(
                exporter.source_news_context([], {"upcoming_meeting_date": "2026-07-28"}) == [],
                "regional announcement must remain review-only before approval",
            )
            review_row.update(
                {
                    "include_in_final_report": "yes",
                    "final_report_section": "Game Announcements",
                    "editor_decision": "include",
                }
            )
            write_csv(destination, [review_row], RAW_FIELDS + review.REVIEW_FIELDS)
            approved = exporter.source_news_context([], {"upcoming_meeting_date": "2026-07-28"})
            assert_true(len(approved) == 1 and approved[0]["title"].startswith("Three Kingdoms"), "approved regional announcement should render")
        finally:
            review.MEETING_PACK_OUTPUT_ROOT = original_root
            exporter.MEETING_PACK_OUTPUT_ROOT = original_export_root
    print("GAME_NEWS_CONTEXT_REVIEW_TEST_PASS")


if __name__ == "__main__":
    main()
