import csv
import json
from pathlib import Path

import build_game_news_context_layer as news
from test_temp_utils import repo_temp_dir


GAME_LAYER_FIELDS = [
    "report_classification",
    "mobile_source_period",
    "pc_source_period",
    "report_start_date",
    "report_end_date",
    "unified_name",
    "english_report_name",
    "pc_title",
]


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def game_row(name, classification="mobile_only", pc_title=""):
    return {
        "report_classification": classification,
        "mobile_source_period": "2026-07-14 to 2026-07-26",
        "pc_source_period": "2026-07-14 to 2026-07-27",
        "report_start_date": "2026-07-14",
        "report_end_date": "2026-07-26",
        "unified_name": name,
        "english_report_name": name,
        "pc_title": pc_title,
    }


def radar_item(title, section, score, event_date, url_suffix):
    return {
        "id": url_suffix,
        "source": "Radar Source",
        "site_id": "radar",
        "site_name": "Radar Source",
        "source_tier": "major_gaming_media",
        "source_tier_label": "Major gaming media",
        "region": "GLOBAL",
        "title": title,
        "title_en": title,
        "url": f"https://example.com/{url_suffix}",
        "published_at": f"{event_date}T00:00:00+00:00",
        "first_seen_at": f"{event_date}T01:00:00+00:00",
        "last_seen_at": f"{event_date}T01:00:00+00:00",
        "radar_section": section,
        "hot_score": score,
        "hot_reasons": ["game_lifecycle"],
    }


def fixture_payload():
    return {
        "generated_at": "2026-08-03T00:00:00+00:00",
        "hot_news": [
            radar_item("Ragnarok: The New World officially launches in SEA", "game_releases", 105, "2026-07-20", "matched-release"),
            radar_item("Unselected Game is out now on Steam", "game_releases", 105, "2026-07-20", "unmatched-release"),
            radar_item("Call of Duty: Modern Warfare 4 release date and platforms", "game_announcements", 74, "2026-07-21", "high-announcement"),
            radar_item("Low Score RPG release date announced", "game_announcements", 49, "2026-07-21", "low-announcement"),
            radar_item("Future RPG release date announced", "game_announcements", 90, "2026-07-30", "after-period"),
            radar_item("Platform revenue rises 20 percent", "industry_reports", 120, "2026-07-21", "industry"),
        ],
    }


def with_temp_roots(callback):
    with repo_temp_dir("game_news_context_") as tmp:
        original_output = news.MEETING_PACK_OUTPUT_ROOT
        try:
            news.MEETING_PACK_OUTPUT_ROOT = Path(tmp) / "meeting_pack"
            return callback(Path(tmp))
        finally:
            news.MEETING_PACK_OUTPUT_ROOT = original_output


def write_game_layer_fixture(meeting_date):
    write_csv(
        news.game_report_layer_path(meeting_date),
        [
            game_row("Ragnarok: The New World", "mobile_led_cross_platform", "Ragnarok: The New World"),
            game_row("Pass the Fear", "pc_only", "Pass the Fear"),
        ],
        GAME_LAYER_FIELDS,
    )


def write_payload(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def test_news_context_layer_uses_locked_ibd_rules():
    def run(tmp):
        meeting_date = "2026-07-28"
        write_game_layer_fixture(meeting_date)
        payload_path = tmp / "game-news.json"
        write_payload(payload_path, fixture_payload())

        out, rows = news.build(meeting_date, payload_path, announcement_min_score=70)
        written = read_rows(out)
        by_url = {row["url"]: row for row in rows}

        assert_true(out.exists(), "news context output exists")
        assert_equal(len(rows), 4, "matched release, high-score announcement, low-score qualifying announcement, and industry trend included")
        assert_equal(len(written), 4, "writes four rows")
        assert_true("https://example.com/matched-release" in by_url, "matched release included")
        assert_true("https://example.com/high-announcement" in by_url, "high-score announcement included")
        assert_true("https://example.com/unmatched-release" not in by_url, "unmatched release excluded")
        assert_true("https://example.com/low-announcement" in by_url, "low-score release-date announcement included as a review candidate")
        assert_true("https://example.com/after-period" not in by_url, "after-period announcement excluded")
        assert_true("https://example.com/industry" in by_url, "industry trend included")
        assert_equal(
            by_url["https://example.com/matched-release"]["matched_report_game"],
            "Ragnarok: The New World",
            "release matched selected report game",
        )
        assert_equal(
            by_url["https://example.com/high-announcement"]["context_type"],
            "high_score_game_announcement",
            "announcement context type",
        )
        assert_equal(
            by_url["https://example.com/low-announcement"]["context_type"],
            "high_score_game_announcement",
            "low-score announcement remains a review-candidate context type",
        )
        assert_true(
            "qualifying regional launch or release announcement marker" in by_url["https://example.com/low-announcement"]["inclusion_reason"],
            "low-score announcement is included because of its qualifying marker",
        )
        assert_true(
            by_url["https://example.com/low-announcement"].get("include_in_final_report", "") == "",
            "review candidate does not imply automatic final-report inclusion",
        )
        assert_equal(
            by_url["https://example.com/industry"]["context_type"],
            "industry_trend",
            "industry context type",
        )
    with_temp_roots(run)


def test_csv_headers_exact():
    with repo_temp_dir("game_news_context_headers_") as tmp:
        path = Path(tmp) / "news_context_layer.csv"
        news.write_csv(path, [])
        headers = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")).fieldnames or [])
    assert_equal(headers, news.CSV_FIELDS, "CSV headers")


def main():
    test_news_context_layer_uses_locked_ibd_rules()
    test_csv_headers_exact()
    print("GAME_NEWS_CONTEXT_LAYER_TEST_PASS")


if __name__ == "__main__":
    main()
