import csv
import uuid
from pathlib import Path

import build_game_report_layer as layer
import build_pc_steamdb_discovery_candidates as pc


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


MOBILE_FIELDS = [
    "meeting_date",
    "report_start_date",
    "report_end_date",
    "anchor_country",
    "unified_name",
    "english_report_name",
    "translation_needed",
    "main_report_mobile_candidate",
    "appendix_mobile_candidate",
    "main_report_reason",
    "unified_id",
    "unified_publisher_name",
    "sg_downloads",
    "sg_revenue_store",
    "sg_revenue_gross",
]


PC_FIELDS = pc.PC_MEETING_FIELDS


def temp_root():
    path = Path(__file__).resolve().parents[1] / ".tmp" / f"game_layer_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_tsv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def mobile_row(title, unified_id):
    return {
        "meeting_date": "2026-07-28",
        "report_start_date": "2026-07-14",
        "report_end_date": "2026-07-26",
        "anchor_country": "SG",
        "unified_name": title,
        "english_report_name": title,
        "translation_needed": "false",
        "main_report_mobile_candidate": "true",
        "appendix_mobile_candidate": "false",
        "main_report_reason": "sg_gross_above_3000",
        "unified_id": unified_id,
        "unified_publisher_name": "Publisher " + unified_id,
        "sg_downloads": "1000",
        "sg_revenue_store": "5000",
        "sg_revenue_gross": "7142.86",
    }


def pc_row(title, app_id, release_date, peak, main, appendix, reason, matched_mobile=""):
    return {
        "meeting_date": "2026-07-28",
        "report_start_date": "2026-07-14",
        "report_end_date": "2026-07-26",
        "source_kind": "top_releases",
        "source_filter_note": "SteamDB releases 2026-07-14 to 2026-07-27, games only, RPG genre",
        "steamdb_week": "",
        "source_file": "fixture.html",
        "source_url": "",
        "pc_title": title,
        "normalized_pc_title": pc.normalize_title(title),
        "steam_app_id": app_id,
        "steam_url": f"https://store.steampowered.com/app/{app_id}/",
        "release_date": release_date,
        "steamdb_peak": str(peak),
        "steamdb_reviews": "100",
        "steamdb_price": "$9.99",
        "pc_main_report_candidate": "true" if main else "false",
        "pc_appendix_candidate": "true" if appendix else "false",
        "pc_report_reason": reason,
        "matched_mobile_main_game": matched_mobile,
        "matched_mobile_unified_id": "",
        "match_method": "",
        "exclude_reason": "",
        "needs_internet_enrichment": "true",
        "manual_notes": "",
    }


def test_build_game_report_layer_classifications():
    tmp = temp_root()
    original_root = layer.MEETING_PACK_OUTPUT_ROOT
    try:
        layer.MEETING_PACK_OUTPUT_ROOT = tmp / "meeting_pack"
        meeting_dir = layer.MEETING_PACK_OUTPUT_ROOT / "2026-07-28"
        write_csv(
            meeting_dir / "mobile_main_report.csv",
            [
                mobile_row("hololive Dreams", "mobile-1"),
                mobile_row("Ragnarok: The New World", "mobile-2"),
                mobile_row("Mobile Only Quest", "mobile-3"),
            ],
            MOBILE_FIELDS,
        )
        write_csv(
            meeting_dir / "pc_meeting_pack.csv",
            [
                pc_row("hololive Dreams", "4282500", "2026-07-23", 16791, True, False, "matched_mobile_main_game", "hololive Dreams"),
                pc_row("Ragnarok: The New World", "100", "2026-07-15", 500, True, False, "matched_mobile_main_game", "Ragnarok: The New World"),
                pc_row("Pass the Fear", "3561220", "2026-07-23", 25751, True, False, "steamdb_peak_above_10000_in_report_period"),
                pc_row("DragonSword : Awakening", "4570720", "2026-07-23", 23030, True, False, "steamdb_peak_above_10000_in_report_period"),
                pc_row("SpiritVale", "3767850", "2026-07-15", 20253, True, False, "steamdb_peak_above_10000_in_report_period"),
                pc_row("PC Appendix Game", "999", "2026-07-15", 999, False, True, "appendix_global_context_only"),
            ],
            PC_FIELDS,
        )

        path, rows = layer.build("2026-07-28")
        by_mobile = {row["english_report_name"]: row for row in rows if row.get("english_report_name")}
        by_pc = {row["pc_title"]: row for row in rows if row.get("pc_title")}

        assert_true(path.exists(), "game report layer output exists")
        assert_equal(by_mobile["hololive Dreams"]["report_classification"], "mobile_led_cross_platform", "hololive classification")
        assert_equal(by_mobile["Ragnarok: The New World"]["report_classification"], "mobile_led_cross_platform", "Ragnarok classification")
        assert_equal(by_mobile["Mobile Only Quest"]["report_classification"], "mobile_only", "mobile only classification")
        assert_equal(by_pc["Pass the Fear"]["report_classification"], "pc_only", "Pass the Fear classification")
        assert_equal(by_pc["DragonSword : Awakening"]["report_classification"], "pc_only", "DragonSword classification")
        assert_equal(by_pc["SpiritVale"]["report_classification"], "pc_only", "SpiritVale classification")
        assert_true("PC Appendix Game" not in by_pc, "PC appendix excluded")
        assert_equal(by_mobile["hololive Dreams"]["unified_publisher_name"], "Publisher mobile-1", "mobile publisher preserved")
        assert_equal(by_mobile["hololive Dreams"]["steam_app_id"], "4282500", "PC fields attached")
        assert_true(all(row["mobile_source_period"] == "2026-07-14 to 2026-07-26" for row in rows), "mobile source period exists")
        assert_true(all(row["pc_source_period"] == "2026-07-14 to 2026-07-27" for row in rows), "pc source period exists")
    finally:
        layer.MEETING_PACK_OUTPUT_ROOT = original_root


def test_mobile_appendix_rows_are_not_inputs_to_layer():
    assert_true("mobile_appendix.csv" not in str(layer.mobile_main_report_path("2026-07-28")), "mobile appendix is not read")


def test_chart_backed_pc_match_promotes_ragnarok():
    tmp = temp_root()
    original_root = layer.MEETING_PACK_OUTPUT_ROOT
    original_drop = layer.MEETING_DROP_ROOT
    try:
        layer.MEETING_PACK_OUTPUT_ROOT = tmp / "meeting_pack"
        layer.MEETING_DROP_ROOT = tmp / "meeting_drop"
        meeting_dir = layer.MEETING_PACK_OUTPUT_ROOT / "2026-08-04"
        write_csv(meeting_dir / "mobile_main_report.csv", [], MOBILE_FIELDS)
        ragnarok_pc = pc_row("Ragnarok: The New World", "4212480", "2026-07-27", 4914, False, True, "appendix_global_context_only")
        ragnarok_pc["report_start_date"] = "2026-07-21"
        ragnarok_pc["report_end_date"] = "2026-08-01"
        write_csv(meeting_dir / "pc_meeting_pack.csv", [ragnarok_pc], PC_FIELDS)
        chart_fields = [
            "Country", "Category", "Chart", "Date", "Ranking", "App ID", "App name", "Company",
            "Release date", "Downloads", "Revenue ($)", "iPhone downloads", "iPhone revenue ($)",
            "iPad downloads", "iPad revenue ($)",
        ]
        write_tsv(
            layer.MEETING_DROP_ROOT / "2026-08-04" / "mobile" / "Sensor_Tower_Category_Rankings_Android_SG_Game_2026-08-03.csv",
            [{
                "Country": "SG", "Category": "Game", "Chart": "topgrossing", "Date": "2026-08-03",
                "Ranking": "26", "App ID": "com.ggv.roworldsea.aos", "App name": "Ragnarok: The New World",
                "Company": "Gravity Game Vision", "Release date": "2026-07-14 00:00:00 UTC",
                "Downloads": "122", "Revenue ($)": "1796.49",
            }],
            chart_fields,
        )
        write_tsv(
            layer.MEETING_DROP_ROOT / "2026-08-04" / "mobile" / "Sensor_Tower_Category_Rankings_iPhone_SG_Games_2026-08-03.csv",
            [{
                "Country": "SG", "Category": "Games", "Chart": "topgrossingapplications", "Date": "2026-08-03",
                "Ranking": "17", "App ID": "6754275005", "App name": "Ragnarok: The New World",
                "Company": "Gravity Game Vision Limited", "Release date": "2026-07-15 00:00:00 UTC",
                "iPhone downloads": "188", "iPhone revenue ($)": "4074.85",
                "iPad downloads": "19", "iPad revenue ($)": "238.98",
            }],
            chart_fields,
        )
        _path, rows = layer.build("2026-08-04")
        ragnarok = [row for row in rows if row.get("english_report_name") == "Ragnarok: The New World"]
        assert_equal(len(ragnarok), 1, "chart-backed Ragnarok is not duplicated")
        assert_equal(ragnarok[0]["report_classification"], "mobile_led_cross_platform", "chart-backed Ragnarok classification")
        assert_equal(ragnarok[0]["steam_app_id"], "4212480", "Ragnarok Steam match")
        assert_equal(ragnarok[0]["steamdb_peak"], "4914", "Ragnarok Steam peak")
        assert_equal(ragnarok[0]["steamdb_reviews"], "100", "Ragnarok Steam reviews fixture")
        assert_equal(ragnarok[0]["chart_rank_match_status"], "matched", "Ragnarok chart match")
    finally:
        layer.MEETING_PACK_OUTPUT_ROOT = original_root
        layer.MEETING_DROP_ROOT = original_drop


def main():
    test_build_game_report_layer_classifications()
    test_mobile_appendix_rows_are_not_inputs_to_layer()
    test_chart_backed_pc_match_promotes_ragnarok()
    print("GAME_REPORT_LAYER_TEST_PASS")


if __name__ == "__main__":
    main()
