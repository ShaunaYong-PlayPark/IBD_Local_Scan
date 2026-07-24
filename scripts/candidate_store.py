import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
OUTPUT_DIR = ROOT / "data" / "output"
CANDIDATE_DIR = ROOT / "data" / "candidates"
SNAPSHOT_DIR = CANDIDATE_DIR / "snapshots"
CANDIDATE_STORE_CSV = CANDIDATE_DIR / "weekly_candidate_store.csv"
KNOWN_EXISTING_GAMES_CSV = ROOT / "data" / "reference" / "known_existing_games.csv"
REPORT_PERIOD_METADATA_CSV = OUTPUT_DIR / "report_period_candidate_metadata.csv"
REPORT_PERIOD_METADATA_JSON = OUTPUT_DIR / "report_period_candidate_metadata.json"
REPORT_PERIOD_LAYER2_CSV = OUTPUT_DIR / "report_period_layer2_candidates.csv"

LAYER2_CSV = OUTPUT_DIR / "layer2_unified_candidates.csv"
LAYER3_CSV = OUTPUT_DIR / "layer3_unique_game_metadata.csv"
LAYER3_5_CSV = OUTPUT_DIR / "layer3_5_title_normalised_metadata.csv"
RANKING_FIRST_SOURCE = "SG Top Grossing first seen"
KNOWN_EXISTING_FIELDS = [
    "platform",
    "app_id",
    "unified_app_id",
    "unified_name",
    "app_name",
    "first_known_date",
    "last_known_date",
    "source_file_count",
]


STORE_FIELDS = [
    "unified_app_id",
    "ios_app_ids",
    "android_app_ids",
    "title",
    "english_display_title",
    "original_title",
    "publisher",
    "publisher_id",
    "developer",
    "genre",
    "category_ids",
    "category_labels",
    "platform",
    "release_date",
    "country_release_date",
    "representative_country_release_date",
    "release_evidence_date",
    "first_detected_date",
    "first_detected_timestamp_utc",
    "latest_extraction_date",
    "latest_extraction_timestamp_utc",
    "latest_ranking_date",
    "source_bucket",
    "sg_top_grossing_evidence_at_detection",
    "sg_chart_matches_at_detection",
    "best_sg_rank_at_detection",
    "platforms_seen_in_layer1",
    "all_layer1_app_ids",
    "detected_language",
    "machine_english_title",
    "manual_english_title",
    "display_title",
    "translation_source",
    "translation_confidence",
    "translation_review_status",
    "translation_note",
    "metadata_lookup_status",
    "active",
    "valid_in_sg",
    "raw_app_metadata_json",
    "raw_unified_app_json",
    "raw_layer2_rows_json",
    "detection_history_json",
]


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def today_iso():
    return datetime.now(timezone.utc).date().isoformat()


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_known_existing_games(path=None):
    path = path or KNOWN_EXISTING_GAMES_CSV
    if not path.exists():
        raise RuntimeError(f"Known-existing games database does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        missing = [field for field in KNOWN_EXISTING_FIELDS if field not in fieldnames]
        if missing:
            raise RuntimeError(
                "Known-existing games database is malformed; missing columns: "
                + ", ".join(missing)
            )
        rows = [
            row
            for row in reader
            if row.get("platform") and row.get("app_id") and row.get("unified_app_id")
        ]
    if not rows:
        raise RuntimeError("Known-existing games database has no usable rows.")
    return rows


def known_existing_platform_app_ids(rows=None):
    rows = rows if rows is not None else read_known_existing_games()
    return {
        (row.get("platform", "").strip(), row.get("app_id", "").strip())
        for row in rows
        if row.get("platform") and row.get("app_id")
    }


def known_existing_unified_ids(rows=None):
    rows = rows if rows is not None else read_known_existing_games()
    return {
        row.get("unified_app_id", "").strip()
        for row in rows
        if row.get("unified_app_id")
    }


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def unique_join(values):
    seen = []
    for value in values:
        if not value:
            continue
        for part in str(value).replace(",", ";").split(";"):
            cleaned = part.strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
    return "; ".join(seen)


def safe_json_loads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def layer2_by_unified_id(layer2_rows):
    grouped = {}
    for row in layer2_rows:
        uid = row.get("unified_app_id", "")
        if uid:
            grouped.setdefault(uid, []).append(row)
    return grouped


def has_top_grossing(row):
    for chart in safe_json_loads(row.get("chart_match_details_json"), []):
        if "gross" in str(chart.get("chart_type", "")).lower():
            return True
    return False


def top_grossing_evidence(rows):
    parts = []
    for row in rows:
        platform = row.get("platform", "")
        app_id = row.get("app_id", "")
        for chart in safe_json_loads(row.get("chart_match_details_json"), []):
            if "gross" in str(chart.get("chart_type", "")).lower():
                parts.append(
                    f"{platform} {app_id} {chart.get('chart_label') or chart.get('chart_type')} #{chart.get('rank')}"
                )
    return " || ".join(parts)


def best_value(rows, field):
    for row in rows:
        value = row.get(field, "")
        if value not in (None, ""):
            return value
    return ""


def store_row_from_outputs(metadata_row, layer2_rows, config, timestamp):
    uid = metadata_row.get("unified_app_id", "")
    source_bucket = unique_join(row.get("released_tag_matches", "") for row in layer2_rows) or RANKING_FIRST_SOURCE
    ranking_date = best_value(layer2_rows, "ranking_date") or config.get("ranking_date", "")
    extraction_date = ranking_date or today_iso()
    detection_event = {
        "captured_at": timestamp,
        "extraction_date": extraction_date,
        "ranking_date": ranking_date,
        "source_bucket": source_bucket,
        "sg_top_grossing_evidence": top_grossing_evidence(layer2_rows),
        "sg_chart_matches": unique_join(row.get("sg_chart_matches", "") for row in layer2_rows),
    }
    display_title = (
        metadata_row.get("display_title")
        or metadata_row.get("unified_app_name")
        or metadata_row.get("original_title")
        or ""
    )
    return {
        "unified_app_id": uid,
        "ios_app_ids": metadata_row.get("ios_app_ids", ""),
        "android_app_ids": metadata_row.get("android_app_ids", ""),
        "title": metadata_row.get("unified_app_name", "") or display_title,
        "english_display_title": display_title,
        "original_title": metadata_row.get("original_title", "") or metadata_row.get("unified_app_name", ""),
        "publisher": metadata_row.get("publisher_name", ""),
        "publisher_id": metadata_row.get("publisher_id", ""),
        "developer": metadata_row.get("developer", ""),
        "genre": metadata_row.get("genre", ""),
        "category_ids": metadata_row.get("category_ids", ""),
        "category_labels": metadata_row.get("category_labels", ""),
        "platform": "iOS / Android" if metadata_row.get("ios_app_ids") and metadata_row.get("android_app_ids") else metadata_row.get("platforms_seen_in_layer1", ""),
        "release_date": metadata_row.get("release_date", ""),
        "country_release_date": metadata_row.get("country_release_date", ""),
        "representative_country_release_date": metadata_row.get("representative_country_release_date", ""),
        "release_evidence_date": metadata_row.get("country_release_date", "") or metadata_row.get("release_date", ""),
        "first_detected_date": extraction_date,
        "first_detected_timestamp_utc": timestamp,
        "latest_extraction_date": extraction_date,
        "latest_extraction_timestamp_utc": timestamp,
        "latest_ranking_date": ranking_date,
        "source_bucket": source_bucket,
        "sg_top_grossing_evidence_at_detection": top_grossing_evidence(layer2_rows),
        "sg_chart_matches_at_detection": unique_join(row.get("sg_chart_matches", "") for row in layer2_rows),
        "best_sg_rank_at_detection": metadata_row.get("best_sg_rank", ""),
        "platforms_seen_in_layer1": metadata_row.get("platforms_seen_in_layer1", ""),
        "all_layer1_app_ids": metadata_row.get("all_layer1_app_ids", ""),
        "detected_language": metadata_row.get("detected_language", ""),
        "machine_english_title": metadata_row.get("machine_english_title", ""),
        "manual_english_title": metadata_row.get("manual_english_title", ""),
        "display_title": display_title,
        "translation_source": metadata_row.get("translation_source", ""),
        "translation_confidence": metadata_row.get("translation_confidence", ""),
        "translation_review_status": metadata_row.get("translation_review_status", ""),
        "translation_note": metadata_row.get("translation_note", ""),
        "metadata_lookup_status": metadata_row.get("metadata_lookup_status", ""),
        "active": metadata_row.get("active", ""),
        "valid_in_sg": metadata_row.get("valid_in_sg", ""),
        "raw_app_metadata_json": metadata_row.get("raw_app_metadata_json", ""),
        "raw_unified_app_json": best_value(layer2_rows, "raw_unified_app_json"),
        "raw_layer2_rows_json": json.dumps(layer2_rows, ensure_ascii=False),
        "detection_history_json": json.dumps([detection_event], ensure_ascii=False),
    }


def merge_candidate(existing, incoming):
    merged = dict(existing)
    for field, value in incoming.items():
        if field.startswith("first_") and existing.get(field):
            continue
        if value not in (None, ""):
            merged[field] = value
    history = safe_json_loads(existing.get("detection_history_json"), [])
    history.extend(safe_json_loads(incoming.get("detection_history_json"), []))
    merged["detection_history_json"] = json.dumps(history, ensure_ascii=False)
    merged["first_detected_date"] = existing.get("first_detected_date") or incoming.get("first_detected_date", "")
    merged["first_detected_timestamp_utc"] = existing.get("first_detected_timestamp_utc") or incoming.get("first_detected_timestamp_utc", "")
    return merged


def upsert_from_current_outputs():
    config = load_config()
    layer2_rows = read_csv(LAYER2_CSV)
    metadata_rows = read_csv(LAYER3_5_CSV if LAYER3_5_CSV.exists() else LAYER3_CSV)
    grouped_layer2 = layer2_by_unified_id(layer2_rows)
    timestamp = now_utc()

    current_rows = []
    for metadata_row in metadata_rows:
        uid = metadata_row.get("unified_app_id", "")
        if not uid:
            continue
        related_layer2 = grouped_layer2.get(uid, [])
        if not any(has_top_grossing(row) for row in related_layer2):
            continue
        current_rows.append(store_row_from_outputs(metadata_row, related_layer2, config, timestamp))

    existing = {row.get("unified_app_id", ""): row for row in read_csv(CANDIDATE_STORE_CSV) if row.get("unified_app_id")}
    for row in current_rows:
        uid = row["unified_app_id"]
        existing[uid] = merge_candidate(existing[uid], row) if uid in existing else row

    store_rows = sorted(existing.values(), key=lambda row: (row.get("first_detected_date", ""), row.get("display_title", "")))
    write_csv(CANDIDATE_STORE_CSV, store_rows, STORE_FIELDS)
    snapshot = SNAPSHOT_DIR / f"weekly_candidates_{config.get('ranking_date') or today_iso()}.csv"
    write_csv(snapshot, current_rows, STORE_FIELDS)
    return current_rows, store_rows, snapshot


def select_report_period_candidates(config=None):
    config = config or load_config()
    start = parse_date(config.get("report_start_date"))
    end = parse_date(config.get("report_end_date"))
    selected = []
    for row in read_csv(CANDIDATE_STORE_CSV):
        detected = parse_date(row.get("first_detected_date") or row.get("latest_extraction_date"))
        if start and end and detected and start <= detected <= end:
            selected.append(row)
    return selected


def candidate_to_metadata_row(row):
    return {
        "layer3_run_timestamp_utc": row.get("first_detected_timestamp_utc", ""),
        "unified_app_id": row.get("unified_app_id", ""),
        "unified_app_name": row.get("title", "") or row.get("display_title", ""),
        "representative_platform": "ios" if row.get("ios_app_ids") else ("android" if row.get("android_app_ids") else ""),
        "representative_app_id": (row.get("ios_app_ids", "").split(";")[0].strip() or row.get("android_app_ids", "").split(";")[0].strip()),
        "publisher_name": row.get("publisher", ""),
        "publisher_id": row.get("publisher_id", ""),
        "developer": row.get("developer", ""),
        "genre": row.get("genre", ""),
        "category_ids": row.get("category_ids", ""),
        "category_labels": row.get("category_labels", ""),
        "ios_app_ids": row.get("ios_app_ids", ""),
        "android_app_ids": row.get("android_app_ids", ""),
        "all_layer1_app_ids": row.get("all_layer1_app_ids", ""),
        "platforms_seen_in_layer1": row.get("platforms_seen_in_layer1", ""),
        "best_sg_rank": row.get("best_sg_rank_at_detection", ""),
        "sg_chart_matches": row.get("sg_chart_matches_at_detection", ""),
        "released_tag_matches": row.get("source_bucket", ""),
        "release_date": row.get("release_date", ""),
        "country_release_date": row.get("country_release_date", ""),
        "representative_country_release_date": row.get("representative_country_release_date", ""),
        "updated_date": "",
        "active": row.get("active", ""),
        "valid_in_sg": row.get("valid_in_sg", ""),
        "metadata_lookup_status": row.get("metadata_lookup_status", ""),
        "raw_app_metadata_json": row.get("raw_app_metadata_json", ""),
        "original_title": row.get("original_title", ""),
        "detected_language": row.get("detected_language", ""),
        "machine_english_title": row.get("machine_english_title", ""),
        "manual_english_title": row.get("manual_english_title", ""),
        "display_title": row.get("display_title", "") or row.get("english_display_title", "") or row.get("title", ""),
        "translation_source": row.get("translation_source", ""),
        "translation_confidence": row.get("translation_confidence", ""),
        "translation_review_status": row.get("translation_review_status", ""),
        "translation_note": row.get("translation_note", ""),
    }


def candidate_to_layer2_rows(row):
    raw_rows = safe_json_loads(row.get("raw_layer2_rows_json"), [])
    if raw_rows:
        return raw_rows
    output = []
    for platform, ids_field in (("ios", "ios_app_ids"), ("android", "android_app_ids")):
        for app_id in [part.strip() for part in row.get(ids_field, "").split(";") if part.strip()]:
            output.append({
                "run_timestamp_utc": row.get("first_detected_timestamp_utc", ""),
                "ranking_date": row.get("latest_ranking_date", ""),
                "country": "SG",
                "platform": platform,
                "app_id": app_id,
                "released_tag_matches": row.get("source_bucket", ""),
                "sg_chart_matches": row.get("sg_chart_matches_at_detection", ""),
                "best_sg_rank": row.get("best_sg_rank_at_detection", ""),
                "candidate_reason": "Stored weekly candidate selected for report period.",
                "chart_match_details_json": "[]",
                "unified_app_id": row.get("unified_app_id", ""),
                "unified_app_name": row.get("title", ""),
                "ios_app_ids": row.get("ios_app_ids", ""),
                "android_app_ids": row.get("android_app_ids", ""),
                "unified_lookup_status": "from_candidate_store",
            })
    return output


def write_report_period_outputs():
    config = load_config()
    selected = select_report_period_candidates(config)
    metadata_rows = [candidate_to_metadata_row(row) for row in selected]
    layer2_rows = []
    for row in selected:
        layer2_rows.extend(candidate_to_layer2_rows(row))

    existing_metadata_rows = read_csv(LAYER3_5_CSV if LAYER3_5_CSV.exists() else LAYER3_CSV)
    metadata_fields = []
    if existing_metadata_rows:
        metadata_fields.extend(existing_metadata_rows[0].keys())
    if metadata_rows:
        metadata_fields.extend(metadata_rows[0].keys())
    metadata_fields = list(dict.fromkeys(metadata_fields))

    existing_layer2_rows = read_csv(LAYER2_CSV)
    layer2_fields = []
    if existing_layer2_rows:
        layer2_fields.extend(existing_layer2_rows[0].keys())
    if layer2_rows:
        layer2_fields.extend(layer2_rows[0].keys())
    layer2_fields = list(dict.fromkeys(layer2_fields))

    write_csv(REPORT_PERIOD_METADATA_CSV, metadata_rows, metadata_fields or list(candidate_to_metadata_row({}).keys()))
    write_json(REPORT_PERIOD_METADATA_JSON, metadata_rows)
    write_csv(REPORT_PERIOD_LAYER2_CSV, layer2_rows, layer2_fields or [])
    return selected, REPORT_PERIOD_METADATA_CSV, REPORT_PERIOD_LAYER2_CSV
