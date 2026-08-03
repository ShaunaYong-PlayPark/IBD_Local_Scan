import argparse
import csv
import re
import sys
from pathlib import Path

import build_pc_steamdb_discovery_candidates as pc


ROOT = Path(__file__).resolve().parents[1]
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"

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


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


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


def index_pc_main_rows(pc_rows, mobile_rows):
    mobile_keys = {}
    for mobile_row in mobile_rows:
        for key in mobile_match_keys(mobile_row):
            mobile_keys[key] = mobile_row

    pc_by_mobile_key = {}
    pc_only = []
    matched_pc_ids = set()
    for pc_row in pc_rows:
        if pc_row.get("pc_main_report_candidate") != "true":
            continue

        match_key = pc.normalize_title(pc_row.get("matched_mobile_main_game"))
        if match_key and match_key in mobile_keys:
            pc_by_mobile_key[match_key] = best_pc(pc_by_mobile_key.get(match_key), pc_row)
            matched_pc_ids.add(pc_row.get("steam_app_id", ""))
            continue

        exact_key = pc.normalize_title(pc_row.get("pc_title"))
        if exact_key and exact_key in mobile_keys:
            pc_by_mobile_key[exact_key] = best_pc(pc_by_mobile_key.get(exact_key), pc_row)
            matched_pc_ids.add(pc_row.get("steam_app_id", ""))
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
    rows = build_rows(mobile_rows, mobile_fields, pc_rows)
    fields = LEADING_FIELDS + mobile_fields + PC_LAYER_FIELDS
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
