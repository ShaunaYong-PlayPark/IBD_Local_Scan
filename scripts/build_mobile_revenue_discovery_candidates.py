import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import resolve_static_automation as schedule_resolver


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input" / "sensor_tower_exports"
CHART_INPUT_DIR = ROOT / "data" / "input" / "sensor_tower_top_charts"
OUTPUT_DIR = ROOT / "data" / "output" / "mobile_discovery"
MEETING_DROP_ROOT = ROOT / "data" / "input" / "meeting_drop"
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"
SCHEDULE_PATH = ROOT / "config" / "static_report_schedule.json"
TITLE_OVERRIDE_PATH = ROOT / "data" / "reference" / "game_title_overrides.csv"
MASTER_TITLE_MAPPING_PATH = ROOT / "data" / "reference" / "master_title_mapping.csv"
SEA6_COUNTRIES = ("SG", "MY", "ID", "TH", "PH", "VN")
CODEX_FALLBACK_TITLES = {
    "我在江湖開後宮": "Building a Harem in Jianghu",
    "天命：六道輪迴": "Destiny: Six Realms of Reincarnation",
    "箭神請息怒": "Archer God, Please Calm Down",
    "怪物之家": "Monster House",
}

REQUIRED_COLUMNS = [
    "Unified Name",
    "Unified ID",
    "Category",
    "Unified Publisher ID",
    "Unified Publisher Name",
    "Date",
    "Platform",
    "Downloads (Absolute)",
    "Downloads (PoP Growth)",
    "Downloads (PoP Growth %)",
    "Revenue (Absolute)",
    "Revenue (PoP Growth)",
    "Revenue (PoP Growth %)",
    "Earliest Release Date",
    "Revenue (Prior, $)",
]

OUTPUT_FIELDS = [
    "report_start_date",
    "report_end_date",
    "country",
    "report_facing_mobile_candidate",
    "report_facing_reason",
    "mobile_discovery_type",
    "unified_name",
    "unified_id",
    "category",
    "unified_publisher_id",
    "unified_publisher_name",
    "platform",
    "chart_rank_date",
    "ios_top_free_rank",
    "ios_top_free_app_id",
    "ios_top_grossing_rank",
    "ios_top_grossing_app_id",
    "android_top_free_rank",
    "android_top_free_app_id",
    "android_top_grossing_rank",
    "android_top_grossing_app_id",
    "chart_rank_match_method",
    "chart_rank_source_files",
    "downloads_absolute",
    "revenue_store_absolute",
    "revenue_gross_estimate",
    "revenue_prior_store",
    "earliest_release_date",
    "sg_release_date",
    "source_file",
    "discovered_at_utc",
]

REPORT_FACING_FIELDS = [
    "report_start_date",
    "report_end_date",
    "country",
    "unified_name",
    "unified_id",
    "unified_publisher_name",
    "downloads_absolute",
    "revenue_store_absolute",
    "revenue_gross_estimate",
    "revenue_prior_store",
    "ios_top_free_rank",
    "ios_top_grossing_rank",
    "android_top_free_rank",
    "android_top_grossing_rank",
    "chart_rank_match_method",
    "chart_rank_match_status",
    "earliest_release_date",
    "sg_release_date",
]

MEETING_PACK_FIELDS = [
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
    "sg_revenue_prior_store",
    "ios_top_free_rank",
    "ios_top_grossing_rank",
    "android_top_free_rank",
    "android_top_grossing_rank",
    "chart_rank_match_status",
    "sg_release_date_reference",
    "sea_market_1_country",
    "sea_market_1_downloads",
    "sea_market_1_revenue_gross",
    "sea_market_2_country",
    "sea_market_2_downloads",
    "sea_market_2_revenue_gross",
    "sea_market_3_country",
    "sea_market_3_downloads",
    "sea_market_3_revenue_gross",
    "sea_market_4_country",
    "sea_market_4_downloads",
    "sea_market_4_revenue_gross",
    "source_files",
]

TITLE_OVERRIDE_FIELDS = [
    "unified_id",
    "unified_name",
    "english_report_name",
    "translation_source",
    "translation_note",
]

MASTER_TITLE_MAPPING_FIELDS = [
    "original_title",
    "unified_id",
    "detected_language_code",
    "english_display_title",
]

TRANSLATION_NEEDED_FIELDS = [
    "meeting_date",
    "unified_id",
    "unified_name",
    "unified_publisher_name",
    "sg_revenue_gross",
    "suggested_english_report_name",
    "translation_needed",
]

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

TOP_CHART_REQUIRED_COLUMNS = [
    "Country",
    "Category",
    "Chart",
    "Date",
    "Ranking",
    "App ID",
    "App name",
    "Company",
]

CHART_RANK_FIELDS = [
    "chart_rank_date",
    "ios_top_free_rank",
    "ios_top_free_app_id",
    "ios_top_grossing_rank",
    "ios_top_grossing_app_id",
    "android_top_free_rank",
    "android_top_free_app_id",
    "android_top_grossing_rank",
    "android_top_grossing_app_id",
    "chart_rank_match_method",
    "chart_rank_source_files",
]


def parse_filename_period(path):
    name = Path(path).name
    match = re.search(
        r"\(\s*([A-Za-z]{3,4})\s+(\d{1,2})\s*,\s*(\d{4})\s*-\s*"
        r"([A-Za-z]{3,4})\s+(\d{1,2})\s*,\s*(\d{4})\s*,\s*([A-Za-z]{2})\s*\)",
        name,
    )
    if not match:
        raise RuntimeError(
            "Could not parse date range and country from Sensor Tower filename: "
            + name
        )
    start_month, start_day, start_year, end_month, end_day, end_year, country = match.groups()
    try:
        start = datetime(
            int(start_year),
            MONTHS[start_month.lower()],
            int(start_day),
        ).date()
        end = datetime(
            int(end_year),
            MONTHS[end_month.lower()],
            int(end_day),
        ).date()
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Filename contains an invalid date range: " + name) from exc
    if end < start:
        raise RuntimeError("Filename end date is before start date: " + name)
    return start, end, country.upper()


def resolve_export_period(path):
    try:
        start, end, country = parse_filename_period(path)
        return start, end, country, warn_if_schedule_mismatch(start, end)
    except RuntimeError as exc:
        schedule_start, schedule_end = schedule_report_period()
        if not schedule_start or not schedule_end:
            raise RuntimeError(
                f"{exc}; no configured report period available for fallback."
            ) from exc
        return (
            schedule_start,
            schedule_end,
            "SG",
            [
                "WARNING: Could not parse date range/country from filename "
                f"{Path(path).name!r}; using configured report period "
                f"{schedule_start.isoformat()} to {schedule_end.isoformat()} and default country SG."
            ],
        )


def parse_number(value):
    text = str(value or "").strip()
    if not text:
        return 0.0
    text = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return 0.0


def format_number(value):
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}"


def parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text[:30], fmt).date()
        except ValueError:
            pass
    return None


def read_csv(path, required_columns=None):
    last_error = None
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            with Path(path).open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
                reader = csv.DictReader(handle, delimiter=delimiter)
                fieldnames = [str(field or "").lstrip("\ufeff") for field in (reader.fieldnames or [])]
                validate_columns(fieldnames, required_columns or REQUIRED_COLUMNS)
                rows = []
                for row in reader:
                    rows.append(
                        {
                            str(key or "").lstrip("\ufeff"): value
                            for key, value in row.items()
                        }
                    )
                return rows
        except UnicodeError as exc:
            last_error = exc
    raise RuntimeError(f"Could not decode Sensor Tower CSV: {last_error}")


def validate_columns(fieldnames, required_columns=None):
    required_columns = required_columns or REQUIRED_COLUMNS
    missing = [field for field in required_columns if field not in fieldnames]
    if missing:
        raise RuntimeError("Sensor Tower CSV is missing required columns: " + ", ".join(missing))
    return True


def newest_input_csv(input_dir=INPUT_DIR):
    input_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(
        input_dir.glob("*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise RuntimeError(f"No Sensor Tower CSV files found in {input_dir}")
    return files[0]


def schedule_report_period():
    if not SCHEDULE_PATH.exists():
        return None, None
    schedule = schedule_resolver.read_json(SCHEDULE_PATH)
    start, end, _ranking = schedule_resolver.report_dates(schedule, "meeting-day-final-report")
    return start, end


def warn_if_schedule_mismatch(filename_start, filename_end):
    schedule_start, schedule_end = schedule_report_period()
    if not schedule_start or not schedule_end:
        return []
    if schedule_start != filename_start or schedule_end != filename_end:
        return [
            "WARNING: Filename period "
            f"{filename_start.isoformat()} to {filename_end.isoformat()} differs from "
            f"configured report period {schedule_start.isoformat()} to {schedule_end.isoformat()}; "
            "using filename period."
        ]
    return []


def filter_rows_by_date(rows, report_start, report_end):
    dated_rows = []
    aggregate_rows = []
    outside_count = 0

    for row in rows:
        parsed = parse_date(row.get("Date"))
        if not parsed:
            aggregate_rows.append(row)
            continue
        if report_start <= parsed <= report_end:
            dated_rows.append(row)
        else:
            outside_count += 1

    if dated_rows:
        warnings = []
        if outside_count:
            warnings.append(
                f"WARNING: Excluded {outside_count} row(s) with Date outside filename period."
            )
        return dated_rows + aggregate_rows, warnings

    if outside_count and not aggregate_rows:
        raise RuntimeError("All CSV Date values are outside the filename period.")

    return aggregate_rows, []


def mobile_discovery_type(row, report_start, report_end, revenue_absolute):
    gross = revenue_absolute / 0.7
    if gross <= 500:
        return "low_revenue_noise"
    release_date = parse_date(row.get("Earliest Release Date"))
    if release_date and report_start <= release_date <= report_end:
        return "new_release_candidate"
    return "first_revenue_candidate"


def report_facing_fields(gross):
    if gross > 500:
        return "true", "first_period_revenue_above_threshold"
    return "false", "first_period_revenue_below_threshold"


def normalize_app_name(value):
    text = str(value or "").lower()
    text = re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def chart_platform_from_path(path):
    name = Path(path).name.lower()
    if "iphone" in name or "ios" in name or "app_store" in name:
        return "ios"
    if "android" in name or "google" in name:
        return "android"
    return ""


def normalized_chart_kind(chart):
    value = str(chart or "").strip().lower()
    if value in {"topfreeapplications", "topselling_free"}:
        return "top_free"
    if value in {"topgrossingapplications", "topgrossing"}:
        return "top_grossing"
    return ""


def chart_rank_field(platform, chart_kind):
    if platform == "ios" and chart_kind == "top_free":
        return "ios_top_free_rank", "ios_top_free_app_id"
    if platform == "ios" and chart_kind == "top_grossing":
        return "ios_top_grossing_rank", "ios_top_grossing_app_id"
    if platform == "android" and chart_kind == "top_free":
        return "android_top_free_rank", "android_top_free_app_id"
    if platform == "android" and chart_kind == "top_grossing":
        return "android_top_grossing_rank", "android_top_grossing_app_id"
    return "", ""


def top_chart_files(charts_dir=CHART_INPUT_DIR):
    charts_dir.mkdir(parents=True, exist_ok=True)
    return sorted(charts_dir.glob("*.csv"), key=lambda path: path.name.lower())


def build_chart_rank_index(chart_paths):
    index = {}
    warnings = []
    for path in chart_paths:
        platform = chart_platform_from_path(path)
        if not platform:
            warnings.append(f"WARNING: Could not infer chart platform from {Path(path).name}; skipped.")
            continue
        rows = read_csv(path, TOP_CHART_REQUIRED_COLUMNS)
        for row in rows:
            chart_kind = normalized_chart_kind(row.get("Chart"))
            rank_field, app_id_field = chart_rank_field(platform, chart_kind)
            if not rank_field:
                continue
            name_key = normalize_app_name(row.get("App name"))
            rank = int(parse_number(row.get("Ranking")))
            if not name_key or rank <= 0:
                continue
            entry = index.setdefault(name_key, {field: "" for field in CHART_RANK_FIELDS})
            current_rank = parse_number(entry.get(rank_field))
            if not current_rank or rank < current_rank:
                entry[rank_field] = str(rank)
                entry[app_id_field] = str(row.get("App ID") or "").strip()
            chart_date = str(row.get("Date") or "").strip()
            if chart_date and not entry["chart_rank_date"]:
                entry["chart_rank_date"] = chart_date
            sources = set(filter(None, entry["chart_rank_source_files"].split(" | ")))
            sources.add(Path(path).name)
            entry["chart_rank_source_files"] = " | ".join(sorted(sources))
    return index, warnings


def apply_chart_rank_enrichment(rows, chart_index):
    for row in rows:
        for field in CHART_RANK_FIELDS:
            row.setdefault(field, "")
        if row.get("report_facing_mobile_candidate") != "true":
            continue
        key = normalize_app_name(row.get("unified_name"))
        match = chart_index.get(key)
        if not match:
            continue
        for field in CHART_RANK_FIELDS:
            row[field] = match.get(field, "")
        row["chart_rank_match_method"] = "normalized_name_exact"
    return rows


def candidate_sort_key(row):
    return (
        0 if row.get("report_facing_mobile_candidate") == "true" else 1,
        -parse_number(row.get("revenue_gross_estimate")),
        row.get("unified_name", ""),
    )


def candidate_rows(rows, report_start, report_end, country, source_file, discovered_at):
    output = []
    for row in rows:
        revenue_prior = parse_number(row.get("Revenue (Prior, $)"))
        revenue_absolute = parse_number(row.get("Revenue (Absolute)"))
        if revenue_prior != 0 or revenue_absolute <= 0:
            continue
        unified_id = str(row.get("Unified ID") or "").strip()
        if not unified_id:
            raise RuntimeError("Candidate row has blank Unified ID.")
        gross = revenue_absolute / 0.7
        report_facing, report_reason = report_facing_fields(gross)
        earliest_release = str(row.get("Earliest Release Date") or "").strip()
        output.append(
            {
                "report_start_date": report_start.isoformat(),
                "report_end_date": report_end.isoformat(),
                "country": country,
                "report_facing_mobile_candidate": report_facing,
                "report_facing_reason": report_reason,
                "mobile_discovery_type": mobile_discovery_type(
                    row,
                    report_start,
                    report_end,
                    revenue_absolute,
                ),
                "unified_name": row.get("Unified Name", ""),
                "unified_id": unified_id,
                "category": row.get("Category", ""),
                "unified_publisher_id": row.get("Unified Publisher ID", ""),
                "unified_publisher_name": row.get("Unified Publisher Name", ""),
                "platform": row.get("Platform", ""),
                "downloads_absolute": format_number(parse_number(row.get("Downloads (Absolute)"))),
                "revenue_store_absolute": format_number(revenue_absolute),
                "revenue_gross_estimate": format_number(gross),
                "revenue_prior_store": format_number(revenue_prior),
                "earliest_release_date": earliest_release,
                "sg_release_date": earliest_release,
                "source_file": source_file,
                "discovered_at_utc": discovered_at,
            }
        )
    return sorted(output, key=candidate_sort_key)


def output_path(report_start, report_end, country):
    return (
        OUTPUT_DIR
        / f"mobile_revenue_discovery_candidates_{report_start.isoformat()}_to_{report_end.isoformat()}_{country}.csv"
    )


def report_facing_output_path(report_start, report_end, country):
    return (
        OUTPUT_DIR
        / f"report_facing_mobile_candidates_{report_start.isoformat()}_to_{report_end.isoformat()}_{country}.csv"
    )


def write_csv(path, rows, fields=None):
    fields = fields or OUTPUT_FIELDS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def has_any_chart_rank(row):
    return any(
        row.get(field)
        for field in (
            "ios_top_free_rank",
            "ios_top_grossing_rank",
            "android_top_free_rank",
            "android_top_grossing_rank",
        )
    )


def report_facing_rows(rows):
    clean_rows = []
    for row in rows:
        if row.get("report_facing_mobile_candidate") != "true":
            continue
        clean = {field: row.get(field, "") for field in REPORT_FACING_FIELDS}
        clean["chart_rank_match_status"] = "matched" if has_any_chart_rank(row) else "unmatched"
        clean_rows.append(clean)
    return clean_rows


def meeting_mobile_dir(meeting_date):
    return MEETING_DROP_ROOT / meeting_date / "mobile"


def meeting_pack_output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "mobile_meeting_pack.csv"


def translation_needed_output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "mobile_translation_needed.csv"


def mobile_main_report_output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "mobile_main_report.csv"


def mobile_appendix_output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "mobile_appendix.csv"


def ensure_title_override_file(path=None):
    path = Path(path or TITLE_OVERRIDE_PATH)
    if path.exists():
        return False
    write_csv(path, [], TITLE_OVERRIDE_FIELDS)
    return True


def read_title_overrides(path=None):
    path = Path(path or TITLE_OVERRIDE_PATH)
    ensure_title_override_file(path)
    overrides = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_columns(reader.fieldnames or [], TITLE_OVERRIDE_FIELDS)
        for row in reader:
            unified_id = str(row.get("unified_id") or "").strip()
            english_name = str(row.get("english_report_name") or "").strip()
            if unified_id and english_name:
                overrides[unified_id] = english_name
    return overrides


def read_master_title_mapping(path=None):
    path = Path(path or MASTER_TITLE_MAPPING_PATH)
    by_id = {}
    by_title = {}
    if not path.exists():
        return by_id, by_title
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_columns(reader.fieldnames or [], MASTER_TITLE_MAPPING_FIELDS)
        for row in reader:
            english_name = str(row.get("english_display_title") or "").strip()
            if not english_name:
                continue
            unified_id = str(row.get("unified_id") or "").strip()
            original_title = str(row.get("original_title") or "").strip()
            if unified_id:
                by_id[unified_id] = english_name
            title_key = normalize_app_name(original_title)
            if title_key:
                by_title[title_key] = english_name
    return by_id, by_title


def append_title_overrides(rows, path=None):
    if not rows:
        return
    path = Path(path or TITLE_OVERRIDE_PATH)
    ensure_title_override_file(path)
    existing_ids = set(read_title_overrides(path).keys())
    new_rows = [row for row in rows if row["unified_id"] not in existing_ids]
    if not new_rows:
        return
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TITLE_OVERRIDE_FIELDS, extrasaction="ignore")
        writer.writerows(new_rows)


def read_unified_export(path):
    rows = read_csv(path, REQUIRED_COLUMNS)
    start, end, country = parse_filename_period(path)
    return {
        "path": Path(path),
        "rows": rows,
        "report_start": start,
        "report_end": end,
        "country": country,
    }


def discover_meeting_inputs(meeting_date):
    folder = meeting_mobile_dir(meeting_date)
    if not folder.exists():
        raise RuntimeError(f"Meeting mobile folder not found: {folder}")

    unified_exports = {}
    chart_paths = []
    warnings = []

    for path in sorted(folder.glob("*.csv"), key=lambda item: item.name.lower()):
        try:
            export = read_unified_export(path)
        except RuntimeError as unified_error:
            try:
                read_csv(path, TOP_CHART_REQUIRED_COLUMNS)
            except RuntimeError:
                warnings.append(
                    f"WARNING: Skipped unrecognized CSV {path.name}: {unified_error}"
                )
                continue
            chart_paths.append(path)
            continue

        country = export["country"]
        if country in unified_exports:
            current = unified_exports[country]["path"]
            chosen = max(current, path, key=lambda item: item.stat().st_mtime)
            skipped = path if chosen == current else current
            warnings.append(
                f"WARNING: Multiple {country} unified revenue exports found; "
                f"using {chosen.name} and skipping {skipped.name}."
            )
            if chosen == current:
                continue
        unified_exports[country] = export

    if "SG" not in unified_exports:
        raise RuntimeError(f"SG unified revenue export missing from {folder}")

    for country in SEA6_COUNTRIES:
        if country == "SG":
            continue
        if country not in unified_exports:
            warnings.append(
                f"WARNING: {country} unified revenue export missing; SEA6 fields use zero/blank values."
            )

    if not chart_paths:
        warnings.append("WARNING: No SG Top Charts CSV files found; chart ranks set to N/A.")

    sg_export = unified_exports["SG"]
    for country, export in sorted(unified_exports.items()):
        if country == "SG":
            continue
        if (
            export["report_start"] != sg_export["report_start"]
            or export["report_end"] != sg_export["report_end"]
        ):
            warnings.append(
                f"WARNING: {country} filename period "
                f"{export['report_start'].isoformat()} to {export['report_end'].isoformat()} "
                f"differs from SG period {sg_export['report_start'].isoformat()} to "
                f"{sg_export['report_end'].isoformat()}."
            )

    return folder, unified_exports, chart_paths, warnings


def aggregate_country_metrics(rows, report_start, report_end):
    filtered_rows, _warnings = filter_rows_by_date(rows, report_start, report_end)
    metrics = {}
    for row in filtered_rows:
        unified_id = str(row.get("Unified ID") or "").strip()
        if not unified_id:
            continue
        entry = metrics.setdefault(unified_id, {"downloads": 0.0, "store": 0.0, "gross": 0.0})
        downloads = parse_number(row.get("Downloads (Absolute)"))
        revenue = parse_number(row.get("Revenue (Absolute)"))
        entry["downloads"] += downloads
        entry["store"] += revenue
        entry["gross"] += revenue / 0.7
    return metrics


def mostly_english_name(value):
    text = str(value or "").strip()
    if not text:
        return False
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return True
    latin_letters = [char for char in letters if "A" <= char.upper() <= "Z"]
    return len(latin_letters) / len(letters) >= 0.7


def display_rank(value):
    text = str(value or "").strip()
    return text if text else "N/A"


def main_report_classification(row):
    sg_gross = parse_number(row.get("sg_revenue_gross"))
    downloads = parse_number(row.get("sg_downloads"))
    matched = row.get("chart_rank_match_status") == "matched"
    release_date = parse_date(row.get("sg_release_date_reference"))
    old_unmatched = bool(release_date and release_date.year < 2026 and not matched)
    zero_download_unmatched = downloads == 0 and not matched

    if old_unmatched:
        return "false", "true", "appendix_old_unmatched_release"
    if zero_download_unmatched:
        return "false", "true", "appendix_zero_download_unmatched"
    if sg_gross > 3000:
        return "true", "false", "sg_gross_above_3000"
    return "false", "true", "appendix_below_main_threshold"


def meeting_source_files(row, unified_exports):
    sources = {row.get("source_file", "")}
    sources.update(row.get("chart_rank_source_files", "").split(" | "))
    unified_id = row.get("unified_id", "")
    for export in unified_exports.values():
        metrics = aggregate_country_metrics(
            export["rows"],
            export["report_start"],
            export["report_end"],
        )
        if unified_id in metrics:
            sources.add(export["path"].name)
    return " | ".join(sorted(source for source in sources if source))


def sea_market_slots(unified_id, country_metrics):
    markets = []
    for country in SEA6_COUNTRIES:
        metrics = country_metrics.get(country, {}).get(
            unified_id,
            {"downloads": 0.0, "gross": 0.0},
        )
        markets.append(
            {
                "country": country,
                "downloads": metrics.get("downloads", 0.0),
                "gross": metrics.get("gross", 0.0),
            }
        )

    positive_markets = [market for market in markets if market["gross"] > 0]
    ranked = sorted(positive_markets, key=lambda item: (-item["gross"], item["country"]))
    selected = ranked[:3]
    if "SG" not in {item["country"] for item in selected}:
        selected.append(next(item for item in markets if item["country"] == "SG"))
    while len(selected) < 4:
        selected.append({"country": "", "downloads": "", "gross": ""})
    return selected[:4]


def resolve_english_report_name(candidate, title_overrides, master_by_id, master_by_title):
    unified_id = candidate.get("unified_id", "")
    unified_name = candidate.get("unified_name", "")
    if unified_id in title_overrides:
        return title_overrides[unified_id], "false", "override"
    if unified_id in master_by_id:
        return master_by_id[unified_id], "false", "master_unified_id"
    title_key = normalize_app_name(unified_name)
    if title_key in master_by_title:
        return master_by_title[title_key], "false", "master_original_title"
    if unified_name in CODEX_FALLBACK_TITLES:
        return CODEX_FALLBACK_TITLES[unified_name], "false", "codex_fallback"
    if mostly_english_name(unified_name):
        return unified_name, "false", "mostly_english"
    return unified_name, "true", "unresolved"


def meeting_pack_rows(
    meeting_date,
    sg_candidates,
    unified_exports,
    title_overrides=None,
    master_by_id=None,
    master_by_title=None,
):
    title_overrides = title_overrides or {}
    master_by_id = master_by_id or {}
    master_by_title = master_by_title or {}
    country_metrics = {
        country: aggregate_country_metrics(
            export["rows"],
            export["report_start"],
            export["report_end"],
        )
        for country, export in unified_exports.items()
    }
    rows = []
    fallback_overrides = []
    resolution_sources = {}
    for candidate in sg_candidates:
        if candidate.get("report_facing_mobile_candidate") != "true":
            continue
        english_name, translation_needed, resolution_source = resolve_english_report_name(
            candidate,
            title_overrides,
            master_by_id,
            master_by_title,
        )
        resolution_sources[candidate["unified_id"]] = resolution_source
        if resolution_source == "codex_fallback":
            fallback_overrides.append(
                {
                    "unified_id": candidate["unified_id"],
                    "unified_name": candidate["unified_name"],
                    "english_report_name": english_name,
                    "translation_source": "codex_auto",
                    "translation_note": "Auto-translated for report display.",
                }
            )
        markets = sea_market_slots(candidate["unified_id"], country_metrics)
        chart_rank_match_status = "matched" if has_any_chart_rank(candidate) else "unmatched"
        row = {
            "meeting_date": meeting_date,
            "report_start_date": candidate["report_start_date"],
            "report_end_date": candidate["report_end_date"],
            "anchor_country": "SG",
            "unified_name": candidate["unified_name"],
            "english_report_name": english_name,
            "translation_needed": translation_needed,
            "unified_id": candidate["unified_id"],
            "unified_publisher_name": candidate["unified_publisher_name"],
            "sg_downloads": candidate["downloads_absolute"],
            "sg_revenue_store": candidate["revenue_store_absolute"],
            "sg_revenue_gross": candidate["revenue_gross_estimate"],
            "sg_revenue_prior_store": candidate["revenue_prior_store"],
            "ios_top_free_rank": display_rank(candidate.get("ios_top_free_rank")),
            "ios_top_grossing_rank": display_rank(candidate.get("ios_top_grossing_rank")),
            "android_top_free_rank": display_rank(candidate.get("android_top_free_rank")),
            "android_top_grossing_rank": display_rank(candidate.get("android_top_grossing_rank")),
            "chart_rank_match_status": chart_rank_match_status,
            "sg_release_date_reference": candidate["sg_release_date"],
            "source_files": meeting_source_files(candidate, unified_exports),
        }
        (
            row["main_report_mobile_candidate"],
            row["appendix_mobile_candidate"],
            row["main_report_reason"],
        ) = main_report_classification(row)
        for index, market in enumerate(markets, start=1):
            row[f"sea_market_{index}_country"] = market["country"]
            row[f"sea_market_{index}_downloads"] = (
                format_number(market["downloads"]) if market["country"] else ""
            )
            row[f"sea_market_{index}_revenue_gross"] = (
                format_number(market["gross"]) if market["country"] else ""
            )
        rows.append(row)
    return (
        sorted(rows, key=lambda row: (-parse_number(row["sg_revenue_gross"]), row["unified_name"])),
        fallback_overrides,
        resolution_sources,
    )


def translation_needed_rows(meeting_date, rows):
    output = []
    for row in rows:
        if row.get("translation_needed") != "true":
            continue
        output.append(
            {
                "meeting_date": meeting_date,
                "unified_id": row.get("unified_id", ""),
                "unified_name": row.get("unified_name", ""),
                "unified_publisher_name": row.get("unified_publisher_name", ""),
                "sg_revenue_gross": row.get("sg_revenue_gross", ""),
                "suggested_english_report_name": "",
                "translation_needed": "true",
            }
        )
    return output


def main_report_rows(rows):
    return [row for row in rows if row.get("main_report_mobile_candidate") == "true"]


def appendix_rows(rows):
    return [row for row in rows if row.get("appendix_mobile_candidate") == "true"]


def build_meeting_pack(meeting_date):
    folder, unified_exports, chart_paths, warnings = discover_meeting_inputs(meeting_date)
    override_created = ensure_title_override_file()
    title_overrides = read_title_overrides()
    master_by_id, master_by_title = read_master_title_mapping()
    sg_export = unified_exports["SG"]
    report_start = sg_export["report_start"]
    report_end = sg_export["report_end"]
    sg_rows, date_warnings = filter_rows_by_date(sg_export["rows"], report_start, report_end)
    warnings.extend(date_warnings)
    discovered_at = datetime.now(timezone.utc).isoformat()
    sg_candidates = candidate_rows(
        sg_rows,
        report_start,
        report_end,
        "SG",
        sg_export["path"].name,
        discovered_at,
    )
    if chart_paths:
        chart_index, chart_warnings = build_chart_rank_index(chart_paths)
        warnings.extend(chart_warnings)
        sg_candidates = apply_chart_rank_enrichment(sg_candidates, chart_index)
    rows, fallback_overrides, resolution_sources = meeting_pack_rows(
        meeting_date,
        sg_candidates,
        unified_exports,
        title_overrides,
        master_by_id,
        master_by_title,
    )
    append_title_overrides(fallback_overrides)
    path = meeting_pack_output_path(meeting_date)
    write_csv(path, rows, MEETING_PACK_FIELDS)
    translation_path = translation_needed_output_path(meeting_date)
    translation_rows = translation_needed_rows(meeting_date, rows)
    write_csv(translation_path, translation_rows, TRANSLATION_NEEDED_FIELDS)
    main_path = mobile_main_report_output_path(meeting_date)
    main_rows = main_report_rows(rows)
    write_csv(main_path, main_rows, MEETING_PACK_FIELDS)
    appendix_path = mobile_appendix_output_path(meeting_date)
    appendix = appendix_rows(rows)
    write_csv(appendix_path, appendix, MEETING_PACK_FIELDS)
    return (
        path,
        rows,
        warnings,
        folder,
        chart_paths,
        translation_path,
        translation_rows,
        override_created,
        main_path,
        main_rows,
        appendix_path,
        appendix,
        resolution_sources,
        fallback_overrides,
    )


def build(input_path, chart_paths=None):
    input_path = Path(input_path)
    report_start, report_end, country, warnings = resolve_export_period(input_path)
    rows = read_csv(input_path)
    rows, date_warnings = filter_rows_by_date(rows, report_start, report_end)
    warnings.extend(date_warnings)
    discovered_at = datetime.now(timezone.utc).isoformat()
    candidates = candidate_rows(
        rows,
        report_start,
        report_end,
        country,
        input_path.name,
        discovered_at,
    )
    if chart_paths is None:
        chart_paths = top_chart_files()
    if chart_paths:
        chart_index, chart_warnings = build_chart_rank_index(chart_paths)
        warnings.extend(chart_warnings)
        candidates = apply_chart_rank_enrichment(candidates, chart_index)
    else:
        warnings.append("WARNING: No Sensor Tower Top Charts CSV files found; chart rank fields left blank.")
    path = output_path(report_start, report_end, country)
    write_csv(path, candidates)
    clean_path = report_facing_output_path(report_start, report_end, country)
    clean_rows = report_facing_rows(candidates)
    write_csv(clean_path, clean_rows, REPORT_FACING_FIELDS)
    return path, candidates, warnings, len(rows), clean_path, clean_rows


def counts_by_discovery_type(rows):
    counts = {}
    for row in rows:
        key = row.get("mobile_discovery_type", "")
        counts[key] = counts.get(key, 0) + 1
    order = ("new_release_candidate", "first_revenue_candidate", "low_revenue_noise")
    return {key: counts[key] for key in order if key in counts}


def counts_by_report_facing(rows):
    counts = {"true": 0, "false": 0}
    for row in rows:
        key = row.get("report_facing_mobile_candidate", "false")
        counts[key] = counts.get(key, 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Build mobile revenue discovery candidates from a manual Sensor Tower export."
    )
    parser.add_argument("--input", help="Path to a manually downloaded Sensor Tower CSV.")
    parser.add_argument(
        "--meeting-date",
        help="Meeting date folder to build, for example 2026-07-28.",
    )
    parser.add_argument(
        "--charts-dir",
        default=str(CHART_INPUT_DIR),
        help="Folder containing Sensor Tower Top Charts CSV files for rank enrichment.",
    )
    args = parser.parse_args()

    if args.meeting_date:
        (
            path,
            rows,
            warnings,
            folder,
            chart_paths,
            translation_path,
            translation_rows,
            override_created,
            main_path,
            main_rows,
            appendix_path,
            appendix,
            resolution_sources,
            fallback_overrides,
        ) = build_meeting_pack(args.meeting_date)
        for warning in warnings:
            print(warning)
        matched = [row for row in rows if row["chart_rank_match_status"] == "matched"]
        print(f"Meeting date: {args.meeting_date}")
        print(f"Input folder: {folder}")
        print(f"SG Top chart files: {[str(path) for path in chart_paths]}")
        print(f"Report-facing row count: {len(rows)}")
        print(f"Main report row count: {len(main_rows)}")
        print(f"Appendix row count: {len(appendix)}")
        print(f"Chart-rank matched rows: {len(matched)} / {len(rows)}")
        print(f"Translation-needed rows: {len(translation_rows)}")
        print(f"Title override file created: {override_created}")
        print(
            "Titles resolved from master_title_mapping.csv: "
            f"{sum(1 for source in resolution_sources.values() if source.startswith('master_'))}"
        )
        print(f"Titles resolved from Codex fallback dictionary: {len(fallback_overrides)}")
        print(f"Output path: {path}")
        print(f"Translation-needed output path: {translation_path}")
        print(f"Main report output path: {main_path}")
        print(f"Appendix output path: {appendix_path}")
        return

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHART_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = newest_input_csv()
        print(f"Selected newest input CSV: {input_path}")
    chart_paths = top_chart_files(Path(args.charts_dir))
    path, candidates, warnings, considered_count, clean_path, clean_rows = build(input_path, chart_paths)
    for warning in warnings:
        print(warning)
    report_facing = [row for row in candidates if row.get("report_facing_mobile_candidate") == "true"]
    rank_matched = [
        row for row in report_facing
        if any(row.get(field) for field in (
            "ios_top_free_rank",
            "ios_top_grossing_rank",
            "android_top_free_rank",
            "android_top_grossing_rank",
        ))
    ]
    print(f"Input path: {input_path}")
    print(f"Top chart files: {[str(path) for path in chart_paths]}")
    print(f"Rows considered: {considered_count}")
    print(f"Candidate count: {len(candidates)}")
    print(f"Counts by report_facing_mobile_candidate: {counts_by_report_facing(candidates)}")
    print(f"Counts by mobile_discovery_type: {counts_by_discovery_type(candidates)}")
    print(f"Report-facing candidates with chart rank match: {len(rank_matched)} / {len(report_facing)}")
    print(f"Output path: {path}")
    print(f"Clean report-facing output path: {clean_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Mobile revenue discovery failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
