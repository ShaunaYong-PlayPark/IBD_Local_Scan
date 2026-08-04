import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import build_pc_steamdb_discovery_candidates as pc


ROOT = Path(__file__).resolve().parents[1]
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"
MEETING_DROP_ROOT = ROOT / "data" / "input" / "meeting_drop"
REGISTRY_PATH = ROOT / "data" / "reference" / "game_registry.csv"
PROOF_RUNS_ROOT = ROOT / "docs" / "proof-runs"

CLASS_MOBILE_LED_CROSS_PLATFORM = "mobile_led_cross_platform"
CLASS_MOBILE_ONLY = "mobile_only"
CLASS_PC_ONLY = "pc_only"

PC_LAYER_FIELDS = [
    "pc_title",
    "steam_app_id",
    "steam_url",
    "pc_release_date",
    "steamdb_peak",
    "steamdb_reviews",
    "steamdb_price",
    "pc_report_reason",
]

LEADING_FIELDS = [
    "report_classification",
    "mobile_source_period",
    "pc_source_period",
]

CONTINUITY_FIELDS = [
    "registry_game_id",
    "continuity_note",
    "continuity_brief_href",
    "continuity_first_seen_meeting_date",
]

REGISTRY_FIELDS = [
    "registry_game_id",
    "original_title",
    "english_title",
    "normalized_original_title",
    "normalized_english_title",
    "first_seen_meeting_date",
    "first_seen_report_period",
    "first_seen_platform_classification",
    "first_seen_brief_href",
    "mobile_app_ids",
    "steam_app_ids",
    "known_platforms",
    "publisher",
    "developer",
    "notes",
]


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def read_chart_rows(path):
    raw = Path(path).read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    with Path(path).open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader)


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_registry(path=None):
    path = Path(path or REGISTRY_PATH)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_registry(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalized_title(value):
    return pc.normalize_title(value)


def title_alias_keys(value):
    key = normalized_title(value)
    keys = {key} if key else set()
    mapping_path = ROOT / "data" / "reference" / "master_title_mapping.csv"
    if mapping_path.exists():
        with mapping_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for alias in csv.DictReader(handle):
                original = normalized_title(alias.get("original_title"))
                english = normalized_title(alias.get("english_display_title"))
                if key and key in {original, english}:
                    keys.update(part for part in (original, english) if part)
    return keys


def split_ids(value):
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def steam_id_from_url(value):
    match = re.search(r"/app/(\d+)", str(value or ""))
    return match.group(1) if match else ""


def registry_id(original_title, english_title):
    key = normalized_title(english_title) or normalized_title(original_title)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"game-{digest}"


def proof_rows_before(meeting_date):
    rows = []
    if not PROOF_RUNS_ROOT.exists():
        return rows
    for folder in sorted(PROOF_RUNS_ROOT.iterdir()):
        if not folder.is_dir() or folder.name >= meeting_date:
            continue
        path = folder / "final-report.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.extend((folder.name, row) for row in payload.get("rows") or [])
    return rows


def registry_record_from_row(row, meeting_date, brief_href=None):
    original = row.get("Original Title") or row.get("unified_name") or row.get("pc_title") or row.get("Game Title") or ""
    english = row.get("English Display Title") or row.get("english_report_name") or row.get("Game Title") or original
    classification = row.get("report_classification") or CLASS_MOBILE_ONLY
    default_platforms = {
        CLASS_MOBILE_LED_CROSS_PLATFORM: "iOS, Android, Steam",
        CLASS_MOBILE_ONLY: "iOS, Android",
        CLASS_PC_ONLY: "PC, Steam",
    }
    mobile_ids = [] if classification == CLASS_PC_ONLY else split_ids(row.get("unified_app_id") or row.get("unified_id"))
    steam_ids = split_ids(row.get("steam_app_id")) or [steam_id_from_url(row.get("steam_url"))]
    steam_ids = [value for value in steam_ids if value]
    return {
        "registry_game_id": registry_id(original, english),
        "original_title": original,
        "english_title": english,
        "normalized_original_title": normalized_title(original),
        "normalized_english_title": normalized_title(english),
        "first_seen_meeting_date": meeting_date,
        "first_seen_report_period": date_period(row.get("report_start_date", ""), row.get("report_end_date", "")),
        "first_seen_platform_classification": classification,
        "first_seen_brief_href": brief_href or f"proof-runs/{meeting_date}/latest-brief.html",
        "mobile_app_ids": ";".join(mobile_ids),
        "steam_app_ids": ";".join(steam_ids),
        "known_platforms": row.get("Platform") or row.get("platforms_confirmed") or default_platforms.get(classification, ""),
        "publisher": row.get("Publisher") or row.get("unified_publisher_name") or "",
        "developer": row.get("Developer") or row.get("developer") or "",
        "notes": "",
    }


def seed_registry(meeting_date):
    seeded = []
    for first_seen_date, row in proof_rows_before(meeting_date):
        candidate = registry_record_from_row(row, first_seen_date)
        match = find_registry_match(seeded, row)
        if match:
            continue
        seeded.append(candidate)
    return seeded


def find_registry_match(registry_rows, row):
    row_keys = set()
    for field in ("Original Title", "English Display Title", "unified_name", "english_report_name", "Game Title", "pc_title"):
        row_keys.update(title_alias_keys(row.get(field)))
    row_mobile_ids = set(split_ids(row.get("unified_app_id") or row.get("unified_id")))
    row_steam_ids = set(split_ids(row.get("steam_app_id")))
    steam_id = steam_id_from_url(row.get("steam_url"))
    if steam_id:
        row_steam_ids.add(steam_id)
    for record in registry_rows:
        record_keys = {
            normalized_title(record.get("normalized_original_title")),
            normalized_title(record.get("normalized_english_title")),
        }
        record_mobile_ids = set(split_ids(record.get("mobile_app_ids")))
        record_steam_ids = set(split_ids(record.get("steam_app_ids")))
        if row_keys & record_keys or row_mobile_ids & record_mobile_ids or row_steam_ids & record_steam_ids:
            return record
    return None


def merge_registry_record(existing, current, row):
    if existing is None:
        return current
    merged = dict(existing)
    for field in ("mobile_app_ids", "steam_app_ids"):
        values = set(split_ids(existing.get(field))) | set(split_ids(current.get(field)))
        merged[field] = ";".join(sorted(value for value in values if value))
    for field in ("known_platforms", "publisher", "developer"):
        values = set(part.strip() for part in str(existing.get(field) or "").split(",") if part.strip())
        values.update(part.strip() for part in str(current.get(field) or "").split(",") if part.strip())
        merged[field] = ", ".join(sorted(values))
    if not merged.get("original_title"):
        merged["original_title"] = current.get("original_title", "")
    if not merged.get("english_title"):
        merged["english_title"] = current.get("english_title", "")
    if not merged.get("notes"):
        merged["notes"] = current.get("notes", "")
    return merged


def apply_continuity(rows, meeting_date):
    registry_rows = read_registry()
    if not registry_rows:
        registry_rows = seed_registry(meeting_date)
    output = []
    for row in rows:
        prior = find_registry_match(registry_rows, row)
        row = dict(row)
        row.update({field: "" for field in CONTINUITY_FIELDS})
        current = registry_record_from_row(row, meeting_date)
        if prior and prior.get("first_seen_meeting_date") != meeting_date:
            first_date = prior.get("first_seen_meeting_date", "")
            first_label = display_date_for_note(first_date)
            current_class = row.get("report_classification")
            prior_class = prior.get("first_seen_platform_classification")
            if prior_class == CLASS_MOBILE_ONLY and current_class == CLASS_MOBILE_LED_CROSS_PLATFORM:
                row["continuity_note"] = f"Mobile version was first covered in the {first_label} brief. This report adds the later Steam PC release."
            elif prior_class == CLASS_PC_ONLY and current_class == CLASS_MOBILE_LED_CROSS_PLATFORM:
                row["continuity_note"] = f"PC version was first covered in the {first_label} brief. This report adds the later mobile release/commercial signal."
            if row.get("continuity_note"):
                row["continuity_brief_href"] = prior.get("first_seen_brief_href", "")
                row["continuity_first_seen_meeting_date"] = first_date
                row["registry_game_id"] = prior.get("registry_game_id", "")
        merged = merge_registry_record(prior, current, row)
        if prior:
            index = registry_rows.index(prior)
            registry_rows[index] = merged
        else:
            registry_rows.append(merged)
        output.append(row)
    write_registry(REGISTRY_PATH, registry_rows)
    return output


def display_date_for_note(value):
    try:
        return pc.parse_date(value).strftime("%d %b %Y")
    except (AttributeError, TypeError, ValueError):
        return str(value or "")


def mobile_main_report_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "mobile_main_report.csv"


def pc_meeting_pack_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "pc_meeting_pack.csv"


def output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "game_report_layer.csv"


def mobile_match_keys(row):
    keys = []
    for field in ("english_report_name", "unified_name"):
        key = pc.normalize_title(row.get(field))
        if key:
            keys.append(key)
    return keys


def date_period(start_date, end_date):
    if start_date and end_date:
        return f"{start_date} to {end_date}"
    return ""


def mobile_source_period(mobile_rows):
    periods = {
        date_period(row.get("report_start_date", ""), row.get("report_end_date", ""))
        for row in mobile_rows
    }
    periods.discard("")
    if len(periods) == 1:
        return next(iter(periods))
    if len(periods) > 1:
        return "; ".join(sorted(periods))
    return ""


def pc_source_period(pc_rows):
    for row in pc_rows:
        note = row.get("source_filter_note", "")
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2}) to (20\d{2}-\d{2}-\d{2})\b", note)
        if match:
            return f"{match.group(1)} to {match.group(2)}"
    periods = {
        date_period(row.get("report_start_date", ""), row.get("report_end_date", ""))
        for row in pc_rows
    }
    periods.discard("")
    if len(periods) == 1:
        return next(iter(periods))
    if len(periods) > 1:
        return "; ".join(sorted(periods))
    return ""


def pc_fields(row):
    return {
        "pc_title": row.get("pc_title", ""),
        "steam_app_id": row.get("steam_app_id", ""),
        "steam_url": row.get("steam_url", ""),
        "pc_release_date": row.get("release_date", ""),
        "steamdb_peak": row.get("steamdb_peak", ""),
        "steamdb_reviews": row.get("steamdb_reviews", ""),
        "steamdb_price": row.get("steamdb_price", ""),
        "pc_report_reason": row.get("pc_report_reason", ""),
    }


def best_pc(existing, candidate):
    if existing is None:
        return candidate
    if pc.parse_number(candidate.get("steamdb_peak")) > pc.parse_number(existing.get("steamdb_peak")):
        return candidate
    return existing


def numeric(value):
    try:
        return float(str(value or "").replace(",", "").replace("$", "").strip())
    except ValueError:
        return 0.0


def report_period_pc_row(row):
    release = pc.parse_date(row.get("release_date"))
    start = pc.parse_date(row.get("report_start_date"))
    end = pc.parse_date(row.get("report_end_date"))
    return bool(release and start and end and start <= release <= end)


def chart_mobile_rows(meeting_date, mobile_fields, mobile_rows, pc_rows):
    """Create narrow chart-backed mobile rows for matching in-period PC releases."""
    chart_dir = MEETING_DROP_ROOT / meeting_date / "mobile"
    if not chart_dir.exists():
        return []

    existing_keys = {key for row in mobile_rows for key in mobile_match_keys(row)}
    pc_titles = {
        pc.normalize_title(row.get("pc_title")): row
        for row in pc_rows
        if report_period_pc_row(row) and pc.normalize_title(row.get("pc_title"))
    }
    grouped = {}
    for path in sorted(chart_dir.glob("Sensor_Tower_Category_Rankings_*.csv")):
        for source_row in read_chart_rows(path):
            title = str(source_row.get("App name") or "").strip()
            key = pc.normalize_title(title)
            if not key or key not in pc_titles or key in existing_keys:
                continue
            chart = str(source_row.get("Chart") or "").lower()
            platform = "android" if "Android" in path.name else "ios"
            app_id = str(source_row.get("App ID") or "").strip()
            bucket = grouped.setdefault(key, {
                "title": title,
                "publisher": str(source_row.get("Company") or "").strip(),
                "release_date": str(source_row.get("Release date") or "").strip()[:10],
                "source_files": set(),
                "platforms": {},
            })
            bucket["source_files"].add(path.name)
            platform_rows = bucket["platforms"].setdefault(platform, {})
            is_grossing = "grossing" in chart
            if is_grossing or "selected" not in platform_rows:
                platform_rows["selected"] = source_row
                platform_rows["is_grossing"] = is_grossing
            ranking = str(source_row.get("Ranking") or "").strip()
            if ranking and (is_grossing or "rank" not in platform_rows):
                platform_rows["rank"] = ranking
            platform_rows["app_id"] = app_id or platform_rows.get("app_id", "")

    synthetic = []
    for key, bucket in grouped.items():
        revenue = 0.0
        downloads = 0.0
        ranks = {}
        app_ids = []
        for platform, values in bucket["platforms"].items():
            selected = values.get("selected", {})
            revenue += numeric(selected.get("Revenue ($)"))
            revenue += numeric(selected.get("iPhone revenue ($)"))
            revenue += numeric(selected.get("iPad revenue ($)"))
            downloads += numeric(selected.get("Downloads"))
            downloads += numeric(selected.get("iPhone downloads"))
            downloads += numeric(selected.get("iPad downloads"))
            rank = values.get("rank", "")
            if platform == "android":
                chart = str(selected.get("Chart") or "").lower()
                ranks["android_top_grossing_rank" if "grossing" in chart else "android_top_free_rank"] = rank
            else:
                chart = str(selected.get("Chart") or "").lower()
                ranks["ios_top_grossing_rank" if "grossing" in chart else "ios_top_free_rank"] = rank
            if values.get("app_id"):
                app_ids.append(values["app_id"])
        gross = revenue / 0.7 if revenue else 0.0
        if gross < 3000 and not any(
            "grossing" in key_name and numeric(value) > 0 and numeric(value) <= 200
            for key_name, value in ranks.items()
        ):
            continue
        row = {field: "" for field in mobile_fields}
        row.update({
            "meeting_date": meeting_date,
            "report_start_date": pc_titles[key].get("report_start_date", ""),
            "report_end_date": pc_titles[key].get("report_end_date", ""),
            "anchor_country": "SG",
            "unified_name": bucket["title"],
            "english_report_name": bucket["title"],
            "translation_needed": "false",
            "main_report_mobile_candidate": "true",
            "appendix_mobile_candidate": "false",
            "main_report_reason": "chart_matched_and_sg_gross_above_1000",
            "unified_id": ";".join(app_ids),
            "unified_publisher_name": bucket["publisher"],
            "sg_downloads": str(round(downloads, 2)),
            "sg_revenue_store": str(round(revenue, 2)),
            "sg_revenue_gross": str(round(gross, 2)),
            "sg_revenue_prior_store": "0",
            "chart_rank_match_status": "matched",
            "sg_release_date_reference": bucket["release_date"],
            "source_files": " | ".join(sorted(bucket["source_files"])),
            **ranks,
        })
        synthetic.append(row)
    return synthetic


def index_pc_main_rows(pc_rows, mobile_rows):
    mobile_keys = {}
    for mobile_row in mobile_rows:
        for key in mobile_match_keys(mobile_row):
            mobile_keys[key] = mobile_row

    pc_by_mobile_key = {}
    pc_only = []
    matched_pc_ids = set()
    for pc_row in pc_rows:
        match_key = pc.normalize_title(pc_row.get("matched_mobile_main_game"))
        if match_key and match_key in mobile_keys and (
            pc_row.get("pc_main_report_candidate") == "true" or report_period_pc_row(pc_row)
        ):
            pc_by_mobile_key[match_key] = best_pc(pc_by_mobile_key.get(match_key), pc_row)
            matched_pc_ids.add(pc_row.get("steam_app_id", ""))
            continue

        exact_key = pc.normalize_title(pc_row.get("pc_title"))
        if exact_key and exact_key in mobile_keys and (
            pc_row.get("pc_main_report_candidate") == "true" or report_period_pc_row(pc_row)
        ):
            pc_by_mobile_key[exact_key] = best_pc(pc_by_mobile_key.get(exact_key), pc_row)
            matched_pc_ids.add(pc_row.get("steam_app_id", ""))
            continue

        if pc_row.get("pc_main_report_candidate") != "true":
            continue
        pc_only.append(pc_row)

    return pc_by_mobile_key, pc_only, matched_pc_ids


def build_rows(mobile_rows, mobile_fields, pc_rows):
    pc_by_mobile_key, pc_only_rows, _matched_pc_ids = index_pc_main_rows(pc_rows, mobile_rows)
    mobile_period = mobile_source_period(mobile_rows)
    pc_period = pc_source_period(pc_rows)
    output_rows = []

    for mobile_row in mobile_rows:
        matching_pc = None
        for key in mobile_match_keys(mobile_row):
            matching_pc = pc_by_mobile_key.get(key)
            if matching_pc:
                break

        row = {
            "report_classification": CLASS_MOBILE_LED_CROSS_PLATFORM if matching_pc else CLASS_MOBILE_ONLY,
            "mobile_source_period": mobile_period,
            "pc_source_period": pc_period,
            **mobile_row,
        }
        if matching_pc:
            row.update(pc_fields(matching_pc))
        output_rows.append(row)

    for pc_row in pc_only_rows:
        row = {
            "report_classification": CLASS_PC_ONLY,
            "mobile_source_period": mobile_period,
            "pc_source_period": pc_period,
        }
        for field in mobile_fields:
            row[field] = ""
        row.update(pc_fields(pc_row))
        output_rows.append(row)

    return output_rows


def build(meeting_date):
    mobile_rows, mobile_fields = read_csv(mobile_main_report_path(meeting_date))
    pc_rows, _pc_fields = read_csv(pc_meeting_pack_path(meeting_date))
    mobile_rows = mobile_rows + chart_mobile_rows(meeting_date, mobile_fields, mobile_rows, pc_rows)
    rows = build_rows(mobile_rows, mobile_fields, pc_rows)
    rows = apply_continuity(rows, meeting_date)
    fields = LEADING_FIELDS + mobile_fields + PC_LAYER_FIELDS
    fields += [field for field in CONTINUITY_FIELDS if field not in fields]
    out = output_path(meeting_date)
    write_csv(out, rows, fields)
    return out, rows


def main():
    parser = argparse.ArgumentParser(description="Build combined report-ready game layer.")
    parser.add_argument("--meeting-date", required=True)
    args = parser.parse_args()

    path, rows = build(args.meeting_date)
    counts = {}
    for row in rows:
        counts[row["report_classification"]] = counts.get(row["report_classification"], 0) + 1

    print(f"Meeting date: {args.meeting_date}")
    print(f"Game report layer rows: {len(rows)}")
    for key in (CLASS_MOBILE_LED_CROSS_PLATFORM, CLASS_MOBILE_ONLY, CLASS_PC_ONLY):
        print(f"{key}: {counts.get(key, 0)}")
    print(f"Output path: {path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Game report layer failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
