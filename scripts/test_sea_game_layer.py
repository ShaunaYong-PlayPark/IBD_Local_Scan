import csv
import tempfile
from pathlib import Path

import build_sea_game_layer as layer
import build_mobile_revenue_discovery_candidates as mobile


def write_csv(path, rows, fields, delimiter=","):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def revenue_row(title, unified_id, publisher, revenue, downloads, date="2026-07-21"):
    return {
        "Unified Name": title,
        "Unified ID": unified_id,
        "Category": "Games",
        "Unified Publisher ID": "publisher-id",
        "Unified Publisher Name": publisher,
        "Date": date,
        "Platform": "Unified",
        "Downloads (Absolute)": str(downloads),
        "Downloads (PoP Growth)": "",
        "Downloads (PoP Growth %)": "",
        "Revenue (Absolute)": str(revenue),
        "Revenue (PoP Growth)": "",
        "Revenue (PoP Growth %)": "",
        "Earliest Release Date": "2026/07/01",
        "Revenue (Prior, $)": "0",
    }


def ranking_row(country, app_name, platform, rank):
    return {
        "Country": country,
        "Category": "Game",
        "Chart": "topgrossingapplications",
        "Date": "2026-08-03",
        "Ranking": str(rank),
        "App ID": f"app-{country.lower()}-{platform.lower()}",
        "App name": app_name,
        "Company": "Test Publisher",
    }


def test_sea6_layer_combines_country_rows_and_accepts_lagged_ranking_date():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        meeting = root / "meeting_drop" / "2026-08-04" / "mobile"
        period = "Jul 21, 2026 - Aug 1, 2026"
        revenue_fields = mobile.REQUIRED_COLUMNS
        for country in layer.SEA6_COUNTRIES:
            rows = [revenue_row("Shared SEA RPG", "shared-1", "Shared Publisher", 100 if country == "MY" else 50, 1000)]
            if country == "PH":
                rows.append(revenue_row("PH Only Game", "ph-1", "PH Publisher", 200, 2000))
            write_csv(meeting / f"Unified Top Apps Revenue ({period}, {country}), Detailed.csv", rows, revenue_fields)
            for platform, suffix in (("Android", "Game"), ("iPhone", "Games")):
                name = f"Sensor_Tower_Category_Rankings_{platform}_{country}_{suffix}_2026-08-03.csv"
                write_csv(meeting / name, [ranking_row(country, "Shared SEA RPG", platform, 10)], mobile.TOP_CHART_REQUIRED_COLUMNS, delimiter="\t")

        ranking_files = layer.discover_ranking_files("2026-08-04", root / "meeting_drop")
        assert len(ranking_files) == 12
        assert max(item["ranking_date"] for item in ranking_files.values()) == "2026-08-03"
        original_drop = layer.MEETING_DROP_ROOT
        try:
            layer.MEETING_DROP_ROOT = root / "meeting_drop"
            _path, rows, _warnings = layer.build(
                "2026-08-04",
                meeting_drop_root=root / "meeting_drop",
                output_root=root / "output",
            )
        finally:
            layer.MEETING_DROP_ROOT = original_drop

        shared = next(row for row in rows if row["original_title"] == "Shared SEA RPG")
        assert len([row for row in rows if row["original_title"] == "Shared SEA RPG"]) == 1
        assert shared["countries_detected"] == "SG, MY, PH, ID, TH, VN"
        assert shared["top_country_by_revenue"] == "MY"
        assert shared["my_revenue_gross"] == "142.86"
        assert shared["sg_revenue_gross"] == "71.43"
        assert shared["my_ios_rank"] == "10"
        assert shared["my_android_rank"] == "10"
        assert shared["ranking_data_as_of"] == "2026-08-03"
        assert shared["meeting_date"] == "2026-08-04"


def test_sg_logic_remains_the_anchor_for_report_period():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        meeting = root / "meeting_drop" / "2026-07-07" / "mobile"
        period = "Jun 23, 2026 - Jul 6, 2026"
        row = revenue_row("SG Anchor Game", "sg-1", "SG Publisher", 3000, 5000, date="2026-06-30")
        for country in layer.SEA6_COUNTRIES:
            write_csv(meeting / f"Unified Top Apps Revenue ({period}, {country}), Detailed.csv", [row], mobile.REQUIRED_COLUMNS)
            for platform, suffix in (("Android", "Game"), ("iPhone", "Games")):
                write_csv(meeting / f"Sensor_Tower_Category_Rankings_{platform}_{country}_{suffix}_2026-07-06.csv", [ranking_row(country, "SG Anchor Game", platform, 1)], mobile.TOP_CHART_REQUIRED_COLUMNS, delimiter="\t")
        _path, rows, _warnings = layer.build("2026-07-07", meeting_drop_root=root / "meeting_drop", output_root=root / "output")
        assert len(rows) == 1
        assert rows[0]["report_start_date"] == "2026-06-23"
        assert rows[0]["report_end_date"] == "2026-07-06"


if __name__ == "__main__":
    test_sea6_layer_combines_country_rows_and_accepts_lagged_ranking_date()
    test_sg_logic_remains_the_anchor_for_report_period()
    print("SEA6 game layer tests passed")
