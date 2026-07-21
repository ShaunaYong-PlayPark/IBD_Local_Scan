import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "output" / "layer3_unique_game_metadata.csv"
OUTPUT = ROOT / "data" / "output" / "layer3_5_title_normalised_metadata.csv"
OUTPUT_JSON = ROOT / "data" / "output" / "layer3_5_title_normalised_metadata.json"
LAYER2_INPUT = ROOT / "data" / "output" / "layer2_unified_candidates.csv"
MAPPING = ROOT / "data" / "reference" / "master_title_mapping.csv"


TITLE_FIELDS = [
    "original_title",
    "unified_id",
    "detected_language_code",
    "english_display_title",
    "title_method",
    "title_needs_review",
]

COMPAT_FIELDS = [
    "detected_language",
    "machine_english_title",
    "manual_english_title",
    "display_title",
    "translation_source",
    "translation_confidence",
    "translation_review_status",
    "translation_note",
]

LAYER3_FIELDS = [
    "layer3_run_timestamp_utc",
    "unified_app_id",
    "unified_app_name",
    "representative_platform",
    "representative_app_id",
    "publisher_name",
    "publisher_id",
    "genre",
    "category_ids",
    "category_labels",
    "ios_app_ids",
    "android_app_ids",
    "all_layer1_app_ids",
    "platforms_seen_in_layer1",
    "best_sg_rank",
    "sg_chart_matches",
    "released_tag_matches",
    "release_date",
    "country_release_date",
    "representative_country_release_date",
    "updated_date",
    "active",
    "valid_in_sg",
    "metadata_lookup_status",
    "raw_app_metadata_json",
]


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def csv_fields(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or [])


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def clean(value):
    return str(value or "").strip()


def is_latin_or_ascii(value):
    if not value:
        return True
    return all(ord(char) < 128 for char in value)


def detect_language_code(value):
    if re.search(r"[\uAC00-\uD7AF]", value or ""):
        return "ko"
    if re.search(r"[\u3040-\u30FF]", value or ""):
        return "ja"
    if re.search(r"[\u4E00-\u9FFF]", value or ""):
        return "zh"
    if re.search(r"[\u0E00-\u0E7F]", value or ""):
        return "th"
    if re.search(r"[\u0400-\u04FF]", value or ""):
        return "ru"
    if is_latin_or_ascii(value):
        return "latin"
    return "unknown"


def first_non_empty(*values):
    for value in values:
        value = clean(value)
        if value:
            return value
    return ""


def load_mapping():
    rows = read_csv(MAPPING)
    by_unified = {}
    by_title = {}
    warnings = []
    seen_titles_by_uid = {}

    for row in rows:
        unified_id = clean(row.get("unified_id"))
        original_title = clean(row.get("original_title"))
        english_title = clean(row.get("english_display_title"))
        language = clean(row.get("detected_language_code"))

        if unified_id:
            seen_titles_by_uid.setdefault(unified_id, set())
            if english_title:
                seen_titles_by_uid[unified_id].add(english_title)
            existing = by_unified.get(unified_id)
            if not existing or (not clean(existing.get("english_display_title")) and english_title):
                by_unified[unified_id] = {
                    "original_title": original_title,
                    "unified_id": unified_id,
                    "detected_language_code": language,
                    "english_display_title": english_title,
                }

        if original_title and original_title not in by_title:
            by_title[original_title] = {
                "original_title": original_title,
                "unified_id": unified_id,
                "detected_language_code": language,
                "english_display_title": english_title,
            }

    for unified_id, titles in sorted(seen_titles_by_uid.items()):
        if len(titles) > 1:
            warnings.append(
                f"WARNING: unified_id {unified_id} has multiple english_display_title values: "
                + " | ".join(sorted(titles))
            )
    return by_unified, by_title, warnings


def source_unified_id(row):
    return first_non_empty(row.get("unified_id"), row.get("unified_app_id"), row.get("Unified App ID"))


def source_original_title(row):
    return first_non_empty(
        row.get("original_title"),
        row.get("unified_app_name"),
        row.get("name"),
        row.get("Game Title"),
    )


def mapped_result(original_title, unified_id, mapping_row, method):
    english = first_non_empty(mapping_row.get("english_display_title"), original_title)
    language = first_non_empty(mapping_row.get("detected_language_code"), detect_language_code(original_title))
    return {
        "original_title": original_title,
        "unified_id": unified_id,
        "detected_language_code": language,
        "english_display_title": english,
        "title_method": method,
        "title_needs_review": "false",
    }


def resolve_title(row, by_unified, by_title):
    original_title = source_original_title(row)
    unified_id = source_unified_id(row)

    if unified_id and unified_id in by_unified:
        return mapped_result(original_title, unified_id, by_unified[unified_id], "unified_id_mapping")

    if original_title and original_title in by_title:
        return mapped_result(original_title, unified_id, by_title[original_title], "title_mapping")

    if is_latin_or_ascii(original_title):
        return {
            "original_title": original_title,
            "unified_id": unified_id,
            "detected_language_code": "latin",
            "english_display_title": original_title,
            "title_method": "already_latin",
            "title_needs_review": "false",
        }

    return {
        "original_title": original_title,
        "unified_id": unified_id,
        "detected_language_code": detect_language_code(original_title),
        "english_display_title": original_title,
        "title_method": "unmapped_original",
        "title_needs_review": "true",
    }


def apply_compatibility_fields(row, result):
    row.update(result)
    row["unified_app_id"] = row.get("unified_app_id") or result["unified_id"]
    row["detected_language"] = result["detected_language_code"]
    row["machine_english_title"] = result["english_display_title"]
    row["manual_english_title"] = row.get("manual_english_title", "")
    row["display_title"] = row.get("manual_english_title") or result["english_display_title"]
    row["translation_source"] = result["title_method"]
    row["translation_confidence"] = "high" if result["title_method"] in {"unified_id_mapping", "title_mapping"} else "not_applicable"
    row["translation_review_status"] = "needs_review" if result["title_needs_review"] == "true" else "not_required"
    row["translation_note"] = (
        "Mapped from local master title mapping."
        if result["title_method"] in {"unified_id_mapping", "title_mapping"}
        else "No translation performed; original title preserved."
    )
    return row


def output_fields(rows):
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    for field in TITLE_FIELDS + COMPAT_FIELDS:
        if field not in fields:
            fields.append(field)
    return fields


def empty_output_fields():
    fields = csv_fields(INPUT) or LAYER3_FIELDS
    for field in TITLE_FIELDS + COMPAT_FIELDS:
        if field not in fields:
            fields.append(field)
    return fields


def zero_candidate_input():
    return len(read_csv(LAYER2_INPUT)) == 0


def main():
    source_rows = read_csv(INPUT)
    if not source_rows:
        if INPUT.exists() or zero_candidate_input():
            fields = empty_output_fields()
            write_csv(OUTPUT, [], fields)
            write_json(OUTPUT_JSON, [])
            print("No Layer 3 metadata rows to normalise. Wrote empty title-normalised outputs.")
            print(f"Output: {OUTPUT}")
            print(f"JSON: {OUTPUT_JSON}")
            return
        raise SystemExit(f"Missing input file and Layer 2 candidates exist: {INPUT}")
    by_unified, by_title, warnings = load_mapping()
    for warning in warnings:
        print(warning)
    normalised = [
        apply_compatibility_fields(dict(row), resolve_title(row, by_unified, by_title))
        for row in source_rows
    ]
    write_csv(OUTPUT, normalised, output_fields(normalised))
    write_json(OUTPUT_JSON, normalised)
    needs_review = sum(1 for row in normalised if row.get("title_needs_review") == "true")
    mapped = sum(1 for row in normalised if row.get("title_method") in {"unified_id_mapping", "title_mapping"})
    print(f"Title mapping complete: {len(normalised)} titles, {mapped} mapped, {needs_review} need review.")
    print(f"Mapping: {MAPPING}")
    print(f"Output: {OUTPUT}")
    print(f"JSON: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
