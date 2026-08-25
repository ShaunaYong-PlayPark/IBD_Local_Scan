import csv
from pathlib import Path

import build_game_enrichment_layer as enrich
from test_temp_utils import repo_temp_dir


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


GAME_LAYER_FIELDS = [
    "report_classification",
    "mobile_source_period",
    "pc_source_period",
    "meeting_date",
    "report_start_date",
    "report_end_date",
    "unified_name",
    "english_report_name",
    "unified_publisher_name",
    "sg_release_date_reference",
    "pc_title",
    "steam_app_id",
    "steam_url",
    "pc_release_date",
    "steamdb_peak",
    "steamdb_reviews",
    "steamdb_price",
    "pc_report_reason",
]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def mobile_row(name, classification="mobile_only", pc_title=""):
    return {
        "report_classification": classification,
        "mobile_source_period": "2026-07-14 to 2026-07-26",
        "pc_source_period": "2026-07-14 to 2026-07-27",
        "meeting_date": "2026-07-28",
        "report_start_date": "2026-07-14",
        "report_end_date": "2026-07-26",
        "unified_name": name,
        "english_report_name": name,
        "unified_publisher_name": "Mobile Publisher",
        "sg_release_date_reference": "2026/07/17",
        "pc_title": pc_title,
        "steam_app_id": "123" if pc_title else "",
        "steam_url": "https://store.steampowered.com/app/123/" if pc_title else "",
        "pc_release_date": "2026-07-23" if pc_title else "",
        "steamdb_peak": "10000" if pc_title else "",
        "steamdb_reviews": "100" if pc_title else "",
        "steamdb_price": "Free" if pc_title else "",
        "pc_report_reason": "matched_mobile_main_game" if pc_title else "",
    }


def pc_row(name):
    return {
        "report_classification": "pc_only",
        "mobile_source_period": "2026-07-14 to 2026-07-26",
        "pc_source_period": "2026-07-14 to 2026-07-27",
        "meeting_date": "",
        "report_start_date": "",
        "report_end_date": "",
        "unified_name": "",
        "english_report_name": "",
        "unified_publisher_name": "",
        "sg_release_date_reference": "",
        "pc_title": name,
        "steam_app_id": "3561220",
        "steam_url": "https://store.steampowered.com/app/3561220/",
        "pc_release_date": "2026-07-23",
        "steamdb_peak": "25751",
        "steamdb_reviews": "1362",
        "steamdb_price": "S$16.19",
        "pc_report_reason": "steamdb_peak_above_10000_in_report_period",
    }


def with_temp_roots(callback):
    with repo_temp_dir("game_enrich_") as tmp:
        original_output = enrich.MEETING_PACK_OUTPUT_ROOT
        original_drop = enrich.MEETING_DROP_ROOT
        try:
            enrich.MEETING_PACK_OUTPUT_ROOT = Path(tmp) / "meeting_pack"
            enrich.MEETING_DROP_ROOT = Path(tmp) / "meeting_drop"
            return callback(Path(tmp))
        finally:
            enrich.MEETING_PACK_OUTPUT_ROOT = original_output
            enrich.MEETING_DROP_ROOT = original_drop


def write_game_layer_fixture():
    rows = [
        mobile_row("hololive Dreams", "mobile_led_cross_platform", "hololive Dreams"),
        mobile_row("Ragnarok: The New World", "mobile_led_cross_platform", "Ragnarok: The New World"),
        mobile_row("DIGIMON UP"),
        mobile_row("Cars and Corpses - The Football Carnival Season is Here!"),
        mobile_row("Blade Heroes: Mecha Soul"),
        pc_row("Pass the Fear"),
        pc_row("DragonSword : Awakening"),
        pc_row("SpiritVale"),
    ]
    write_csv(enrich.game_report_layer_path("2026-07-28"), rows, GAME_LAYER_FIELDS)


def test_build_enriched_layer_from_eight_report_rows():
    def run(_tmp):
        write_game_layer_fixture()
        path, rows = enrich.build("2026-07-28")
        headers = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
        by_name = {row["report_name"]: row for row in rows}

        assert_true(path.exists(), "enriched output exists")
        assert_equal(len(read_rows(path)), 8, "writes 8 enriched rows")
        assert_equal(len(rows), 8, "reads 8 game report rows")
        for field in enrich.ENRICHMENT_FIELDS:
            assert_true(field in headers, field + " exists")
        assert_true("source_urls" in headers, "source urls column exists")
        assert_true("summary_sentence_1" in headers, "summary 1 exists")
        assert_true("summary_sentence_2" in headers, "summary 2 exists")
        assert_equal(by_name["hololive Dreams"]["report_classification"], "mobile_led_cross_platform", "mobile-led kept")
        assert_equal(by_name["Ragnarok: The New World"]["publisher"], "GRAVITY", "Ragnarok publisher override")
        assert_equal(by_name["Ragnarok: The New World"]["developer"], "Gravity Game Vision", "Ragnarok developer override")
        assert_equal(by_name["Ragnarok: The New World"]["genre"], "Open World; MMORPG; RPG", "Ragnarok genre override")
        assert_equal(by_name["Pass the Fear"]["report_classification"], "pc_only", "PC-only kept")
        assert_equal(by_name["DIGIMON UP"]["official_site_url"], "unconfirmed", "unknown URL unconfirmed")
        assert_equal(by_name["DIGIMON UP"]["developer"], "unconfirmed", "unknown developer unconfirmed")
        assert_equal(by_name["Pass the Fear"]["release_date_scope"], "Steam", "PC-only uses Steam date")
        assert_equal(by_name["Blade Heroes: Mecha Soul"]["release_date_scope"], "Singapore", "mobile release priority")
    with_temp_roots(run)


def test_appendix_sources_are_not_inputs():
    assert_true("game_report_layer.csv" in str(enrich.game_report_layer_path("2026-07-28")), "only game layer input is used")
    assert_true("appendix" not in str(enrich.game_report_layer_path("2026-07-28")), "appendix files are not read")


def test_research_overlay_can_fill_free_codex_results():
    def run(_tmp):
        write_game_layer_fixture()
        original_genre_references = enrich.genre_references
        reference_rows = {
            "pass the fear": {
                "genre": "Roguelite; Bullet Hell; Shooter",
                "genre_source_url": "https://example.com/pass-the-fear-genre",
                "publisher": "Reference Publisher",
                "publisher_source_url": "https://example.com/pass-the-fear-reference-publisher",
            },
            "dragonsword awakening": {
                "genre": "Open World; Action RPG; Anime RPG",
                "genre_source_url": "https://example.com/dragonsword-genre",
                "publisher": "Reference Publisher",
                "publisher_source_url": "https://example.com/dragonsword-publisher",
            },
        }
        enrich.genre_references = lambda path=enrich.GENRE_REFERENCE_PATH: reference_rows
        overlay_path = enrich.default_research_overlay_path("2026-07-28")
        try:
            write_csv(
                overlay_path,
                [
                    {
                        "report_name": "Pass the Fear",
                        "developer": "Overlay Developer",
                        "publisher": "Overlay Publisher",
                        "publisher_source_url": "https://example.com/pass-the-fear-publisher",
                        "source_urls": "https://example.com/pass-the-fear",
                        "summary_sentence_1": "Overlay summary.",
                    }
                ],
                enrich.RESEARCH_OVERLAY_FIELDS,
            )
            _path, rows = enrich.build("2026-07-28")
            by_name = {row["report_name"]: row for row in rows}
            assert_equal(by_name["Pass the Fear"]["developer"], "Overlay Developer", "overlay developer applied")
            assert_equal(by_name["Pass the Fear"]["publisher"], "Overlay Publisher", "manual publisher wins over genre reference publisher")
            assert_equal(by_name["Pass the Fear"]["genre"], "Roguelite; Bullet Hell; Shooter", "controlled genre remains valid")
            assert_equal(by_name["Pass the Fear"]["publisher_source_url"], "https://example.com/pass-the-fear-publisher", "manual publisher source preserved")
            assert_true(
                "https://example.com/pass-the-fear" in by_name["Pass the Fear"]["source_urls"]
                and "https://example.com/pass-the-fear-genre" in by_name["Pass the Fear"]["source_urls"]
                and "https://example.com/pass-the-fear-reference-publisher" in by_name["Pass the Fear"]["source_urls"],
                "overlay and genre reference source URLs are both preserved",
            )
            assert_equal(by_name["Pass the Fear"]["summary_sentence_1"], "Overlay summary.", "overlay summary applied")
            assert_equal(by_name["DragonSword : Awakening"]["publisher"], "Reference Publisher", "reference publisher fills without manual publisher")
            assert_equal(by_name["DragonSword : Awakening"]["publisher_source_url"], "https://example.com/dragonsword-publisher", "reference publisher source preserved")
        finally:
            enrich.genre_references = original_genre_references
    with_temp_roots(run)


def read_rows(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    test_build_enriched_layer_from_eight_report_rows()
    test_appendix_sources_are_not_inputs()
    test_research_overlay_can_fill_free_codex_results()
    print("GAME_ENRICHMENT_LAYER_TEST_PASS")


if __name__ == "__main__":
    main()
