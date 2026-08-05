import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path

import build_mobile_revenue_discovery_candidates as mobile


ROOT = Path(__file__).resolve().parents[1]
MEETING_DROP_ROOT = ROOT / "data" / "input" / "meeting_drop"
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"
SEA6_COUNTRIES = ("SG", "MY", "PH", "ID", "TH", "VN")
PLATFORMS = ("ios", "android")

OUTPUT_FIELDS = [
    "game_title",
    "original_title",
    "publisher",
    "developer",
    "genre",
    "platforms",
    "sea_st_gross_revenue",
    "sea_st_downloads",
    "countries_detected",
    "top_country_by_revenue",
]
for _country in SEA6_COUNTRIES:
    _prefix = _country.lower()
    OUTPUT_FIELDS.extend(
        [
            f"{_prefix}_revenue_gross",
            f"{_prefix}_downloads",
            f"{_prefix}_ios_rank",
            f"{_prefix}_android_rank",
        ]
    )
OUTPUT_FIELDS.extend(
    ["report_start_date", "report_end_date", "ranking_data_as_of", "meeting_date", "source_files"]
)

RANKING_FILE_RE = re.compile(
    r"Sensor_Tower_Category_Rankings_(Android|iPhone)_"
    r"(SG|MY|PH|ID|TH|VN)_Games?_(\d{4}-\d{2}-\d{2})\.csv$",
    re.I,
)


def parse_number(value):
    text = str(value or "").strip().replace(",", "").replace("$", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def format_number(value):
    rounded = round(float(value), 2)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.2f}"


def read_ranking_csv(path):
    return mobile.read_csv(path, mobile.TOP_CHART_REQUIRED_COLUMNS)


def discover_ranking_files(meeting_date, meeting_drop_root=None):
    folder = Path(meeting_drop_root or MEETING_DROP_ROOT) / meeting_date / "mobile"
    if not folder.exists():
        raise RuntimeError(f"Meeting mobile folder not found: {folder}")

    files = {}
    for path in sorted(folder.glob("Sensor_Tower_Category_Rankings_*.csv"), key=lambda item: item.name.lower()):
        match = RANKING_FILE_RE.search(path.name)
        if not match:
            continue
        platform, country, ranking_date = match.groups()
        key = (country.upper(), "ios" if platform.lower() == "iphone" else "android")
        files[key] = {"path": path, "ranking_date": ranking_date}

    missing = [f"{country}/{platform}" for country in SEA6_COUNTRIES for platform in PLATFORMS if (country, platform) not in files]
    if missing:
        raise RuntimeError("Missing SEA6 ranking files: " + ", ".join(missing))
    return files


def ranking_metrics(ranking_files):
    metrics = {}
    ranking_dates = set()
    source_files = set()
    for (country, platform), info in ranking_files.items():
        source_files.add(info["path"].name)
        ranking_dates.add(info["ranking_date"])
        for row in read_ranking_csv(info["path"]):
            title = str(row.get("App name") or "").strip()
            key = mobile.normalize_app_name(title)
            rank = int(parse_number(row.get("Ranking")))
            if not key or rank <= 0:
                continue
            entry = metrics.setdefault((country, key), {"title": title, "publisher": "", "platforms": {}})
            entry["publisher"] = entry["publisher"] or str(row.get("Company") or "").strip()
            platform_values = entry["platforms"].setdefault(platform, {"rank": "", "app_id": ""})
            current = int(platform_values["rank"] or 0)
            if not current or rank < current:
                platform_values["rank"] = str(rank)
                platform_values["app_id"] = str(row.get("App ID") or "").strip()
    return metrics, max(ranking_dates), source_files


def candidate_universe(unified_exports):
    candidates = {}
    for country, export in unified_exports.items():
        rows, _warnings = mobile.filter_rows_by_date(
            export["rows"], export["report_start"], export["report_end"]
        )
        for row in mobile.candidate_rows(
            rows,
            export["report_start"],
            export["report_end"],
            country,
            export["path"].name,
            datetime.now(timezone.utc).isoformat(),
        ):
            key = row["unified_id"]
            current = candidates.get(key)
            if current is None or parse_number(row["revenue_gross_estimate"]) > parse_number(current["candidate"]["revenue_gross_estimate"]):
                candidates[key] = {"candidate": row, "candidate_country": country}
    return candidates


def build_rows(meeting_date, unified_exports, ranking_files):
    ranking_by_title, ranking_as_of, ranking_sources = ranking_metrics(ranking_files)
    candidates = candidate_universe(unified_exports)
    country_metrics = {
        country: mobile.aggregate_country_metrics(
            export["rows"], export["report_start"], export["report_end"]
        )
        for country, export in unified_exports.items()
    }
    title_overrides = mobile.read_title_overrides()
    master_by_id, master_by_title = mobile.read_master_title_mapping()
    sg_export = unified_exports["SG"]
    rows = []
    for unified_id, selected in candidates.items():
        candidate = selected["candidate"]
        title = candidate.get("unified_name", "")
        title_key = mobile.normalize_app_name(title)
        english_title, _translation_needed, _source = mobile.resolve_english_report_name(
            candidate, title_overrides, master_by_id, master_by_title
        )
        by_country = {}
        countries_detected = []
        platforms = set()
        publisher = candidate.get("unified_publisher_name", "")
        source_files = {candidate.get("source_file", "")}
        for country in SEA6_COUNTRIES:
            metrics = country_metrics.get(country, {}).get(unified_id, {"downloads": 0.0, "gross": 0.0})
            ranking = ranking_by_title.get((country, title_key), {})
            platform_values = ranking.get("platforms", {})
            if ranking.get("publisher"):
                publisher = publisher or ranking["publisher"]
            if platform_values:
                platforms.update("iOS" if value == "ios" else "Android" for value in platform_values)
            revenue = metrics.get("gross", 0.0)
            downloads = metrics.get("downloads", 0.0)
            if revenue or downloads or platform_values:
                countries_detected.append(country)
            by_country[country] = {
                "revenue": revenue,
                "downloads": downloads,
                "ios_rank": platform_values.get("ios", {}).get("rank", ""),
                "android_rank": platform_values.get("android", {}).get("rank", ""),
            }
            source_files.update(
                unified_exports[country]["path"].name
                for country in SEA6_COUNTRIES
                if unified_id in country_metrics.get(country, {})
            )

        total_revenue = sum(item["revenue"] for item in by_country.values())
        total_downloads = sum(item["downloads"] for item in by_country.values())
        top_country = max(SEA6_COUNTRIES, key=lambda country: (by_country[country]["revenue"], country))
        output = {
            "game_title": english_title,
            "original_title": title,
            "publisher": publisher,
            "developer": "",
            "genre": candidate.get("category", ""),
            "platforms": ", ".join(sorted(platforms, key=("iOS", "Android").index)),
            "sea_st_gross_revenue": format_number(total_revenue),
            "sea_st_downloads": format_number(total_downloads),
            "countries_detected": ", ".join(countries_detected),
            "top_country_by_revenue": top_country if total_revenue else "",
            "report_start_date": sg_export["report_start"].isoformat(),
            "report_end_date": sg_export["report_end"].isoformat(),
            "ranking_data_as_of": ranking_as_of,
            "meeting_date": meeting_date,
            "source_files": " | ".join(sorted(source_files | ranking_sources)),
        }
        for country in SEA6_COUNTRIES:
            prefix = country.lower()
            output[f"{prefix}_revenue_gross"] = format_number(by_country[country]["revenue"])
            output[f"{prefix}_downloads"] = format_number(by_country[country]["downloads"])
            output[f"{prefix}_ios_rank"] = by_country[country]["ios_rank"]
            output[f"{prefix}_android_rank"] = by_country[country]["android_rank"]
        rows.append(output)
    return sorted(rows, key=lambda row: (-parse_number(row["sea_st_gross_revenue"]), row["game_title"]))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def output_path(meeting_date, output_root=None):
    return Path(output_root or MEETING_PACK_OUTPUT_ROOT) / meeting_date / "sea_game_layer.csv"


def build(meeting_date, meeting_drop_root=None, output_root=None):
    original_mobile_root = mobile.MEETING_DROP_ROOT
    if meeting_drop_root is not None:
        mobile.MEETING_DROP_ROOT = Path(meeting_drop_root)
    try:
        folder, unified_exports, _chart_paths, warnings = mobile.discover_meeting_inputs(
            meeting_date
        )
    finally:
        mobile.MEETING_DROP_ROOT = original_mobile_root
    ranking_files = discover_ranking_files(meeting_date, meeting_drop_root)
    rows = build_rows(meeting_date, unified_exports, ranking_files)
    path = output_path(meeting_date, output_root)
    write_csv(path, rows)
    return path, rows, warnings


def main():
    parser = argparse.ArgumentParser(description="Build one combined SEA6 game layer from Sensor Tower exports.")
    parser.add_argument("--meeting-date", action="append", help="Meeting date; may be repeated.")
    args = parser.parse_args()
    meeting_dates = args.meeting_date or ["2026-07-07", "2026-07-21", "2026-08-04"]
    for meeting_date in meeting_dates:
        path, rows, warnings = build(meeting_date)
        print(f"Meeting date: {meeting_date}")
        print(f"SEA6 game rows: {len(rows)}")
        print(f"Output path: {path}")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
