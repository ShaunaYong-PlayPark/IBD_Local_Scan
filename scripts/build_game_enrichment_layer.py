import argparse
import csv
from pathlib import Path

import build_pc_steamdb_discovery_candidates as pc


ROOT = Path(__file__).resolve().parents[1]
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"
MEETING_DROP_ROOT = ROOT / "data" / "input" / "meeting_drop"
MASTER_TITLE_MAPPING_PATH = ROOT / "data" / "reference" / "master_title_mapping.csv"
GENRE_REFERENCE_PATH = ROOT / "data" / "reference" / "game_genre_sources.csv"

UNKNOWN = "unconfirmed"

ENRICHMENT_FIELDS = [
    "report_name",
    "report_classification",
    "mobile_source_period",
    "pc_source_period",
    "release_date_used",
    "release_date_scope",
    "release_date_source_url",
    "official_site_url",
    "store_url",
    "mobile_storefront_url",
    "developer",
    "publisher",
    "publisher_source_url",
    "genre",
    "genre_source_url",
    "comparable_game",
    "comparison_reason",
    "comparison_source_url",
    "platforms_confirmed",
    "mobile_pc_relationship",
    "registry_game_id",
    "continuity_note",
    "continuity_brief_href",
    "continuity_first_seen_meeting_date",
    "summary_sentence_1",
    "summary_sentence_2",
    "source_urls",
    "enrichment_status",
    "enrichment_notes",
]

RESEARCH_OVERLAY_FIELDS = [
    "report_name",
    "release_date_used",
    "release_date_scope",
    "release_date_source_url",
    "official_site_url",
    "store_url",
    "mobile_storefront_url",
    "developer",
    "publisher",
    "publisher_source_url",
    "genre",
    "genre_source_url",
    "comparable_game",
    "comparison_reason",
    "comparison_source_url",
    "platforms_confirmed",
    "mobile_pc_relationship",
    "registry_game_id",
    "continuity_note",
    "continuity_brief_href",
    "continuity_first_seen_meeting_date",
    "summary_sentence_1",
    "summary_sentence_2",
    "source_urls",
    "enrichment_status",
    "enrichment_notes",
]

SEARCH_ORDER_NOTE = [
    "unified_name",
    "original_title",
    "english_report_name",
    "unified_name + publisher",
    "english_report_name + publisher",
]

PUBLIC_METADATA_OVERRIDES = {
    "ragnarok the new world": {
        "publisher": "GRAVITY",
        "developer": "Gravity Game Vision",
        "genre": "Open World; MMORPG; RPG",
    },
}


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields=ENRICHMENT_FIELDS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def game_report_layer_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "game_report_layer.csv"


def output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "game_enriched_layer.csv"


def default_research_overlay_path(meeting_date):
    return MEETING_DROP_ROOT / meeting_date / "game_enrichment_research.csv"


def title_aliases_from_master_mapping(path=MASTER_TITLE_MAPPING_PATH):
    path = Path(path)
    if not path.exists():
        return {}
    aliases = {}
    for row in read_csv(path):
        original = pc.normalize_title(row.get("original_title"))
        english = pc.normalize_title(row.get("english_display_title"))
        if original and english:
            aliases[original] = english
    return aliases


def genre_references(path=GENRE_REFERENCE_PATH):
    path = Path(path)
    if not path.exists():
        return {}
    return {
        pc.normalize_title(row.get("report_name")): row
        for row in read_csv(path)
        if pc.normalize_title(row.get("report_name"))
    }


def normalize_date(value):
    parsed = pc.parse_date(value)
    return parsed.isoformat() if parsed else str(value or "").strip()


def report_name(row):
    return (
        row.get("english_report_name")
        or row.get("unified_name")
        or row.get("pc_title")
        or UNKNOWN
    )


def release_fields(row):
    classification = row.get("report_classification", "")
    sg_date = normalize_date(row.get("sg_release_date_reference"))
    if classification in {"mobile_led_cross_platform", "mobile_only"} and sg_date:
        return sg_date, "Singapore", UNKNOWN

    pc_date = normalize_date(row.get("pc_release_date"))
    if classification == "pc_only" and pc_date:
        return pc_date, "Steam", row.get("steam_url") or UNKNOWN

    return UNKNOWN, UNKNOWN, UNKNOWN


def relationship(classification):
    if classification == "mobile_led_cross_platform":
        return "mobile-led; PC stats secondary"
    if classification == "mobile_only":
        return "mobile only in report layer"
    if classification == "pc_only":
        return "PC-only report-facing game"
    return UNKNOWN


def platforms(row):
    classification = row.get("report_classification", "")
    if classification == "mobile_led_cross_platform":
        return "iOS, Android, Steam"
    if classification == "mobile_only":
        return "mobile"
    if classification == "pc_only":
        return "PC"
    return UNKNOWN


def base_enrichment_row(row):
    name = report_name(row)
    genre_reference = genre_references().get(pc.normalize_title(name), {})
    classification = row.get("report_classification", UNKNOWN) or UNKNOWN
    release_date, release_scope, release_source_url = release_fields(row)
    store_url = row.get("steam_url") if row.get("steam_url") else UNKNOWN
    source_urls = store_url if store_url != UNKNOWN else UNKNOWN
    result = {
        "report_name": name,
        "report_classification": classification,
        "mobile_source_period": row.get("mobile_source_period") or UNKNOWN,
        "pc_source_period": row.get("pc_source_period") or UNKNOWN,
        "release_date_used": release_date or UNKNOWN,
        "release_date_scope": release_scope or UNKNOWN,
        "release_date_source_url": release_source_url or UNKNOWN,
        "official_site_url": UNKNOWN,
        "store_url": store_url,
        "mobile_storefront_url": genre_reference.get("mobile_storefront_url") or "",
        "developer": UNKNOWN,
        "publisher": genre_reference.get("publisher") or row.get("unified_publisher_name") or UNKNOWN,
        "publisher_source_url": genre_reference.get("publisher_source_url") or "",
        "genre": genre_reference.get("genre") or UNKNOWN,
        "genre_source_url": genre_reference.get("genre_source_url") or "",
        "comparable_game": genre_reference.get("comparable_game") or "",
        "comparison_reason": genre_reference.get("comparison_reason") or "",
        "comparison_source_url": genre_reference.get("comparison_source_url") or "",
        "platforms_confirmed": platforms(row),
        "mobile_pc_relationship": relationship(classification),
        "registry_game_id": row.get("registry_game_id") or UNKNOWN,
        "continuity_note": row.get("continuity_note") or "",
        "continuity_brief_href": row.get("continuity_brief_href") or "",
        "continuity_first_seen_meeting_date": row.get("continuity_first_seen_meeting_date") or "",
        "summary_sentence_1": UNKNOWN,
        "summary_sentence_2": UNKNOWN,
        "source_urls": genre_reference.get("genre_source_url") or source_urls,
        "enrichment_status": "needs_research",
        "enrichment_notes": "Base row generated from game_report_layer.csv; unknown internet research fields left unconfirmed.",
    }
    result.update(PUBLIC_METADATA_OVERRIDES.get(pc.normalize_title(name), {}))
    return result


def read_research_overlay(path):
    path = Path(path)
    if not path.exists():
        return {}
    rows = read_csv(path)
    overlay = {}
    aliases = title_aliases_from_master_mapping()
    for row in rows:
        key = pc.normalize_title(row.get("report_name"))
        if key:
            overlay[key] = row
            if key in aliases:
                overlay[aliases[key]] = row
    return overlay


def is_blank_or_unconfirmed(value):
    return str(value or "").strip().lower() in {"", UNKNOWN}


def append_source_urls(existing, *urls):
    sources = [part.strip() for part in str(existing or "").split("|") if part.strip()]
    for url in urls:
        url = str(url or "").strip()
        if url and url not in sources:
            sources.append(url)
    return " | ".join(sources)


def apply_overlay(row, overlay):
    values = overlay.get(pc.normalize_title(row.get("report_name")), {})
    if not values:
        return row
    updated = dict(row)
    for field in RESEARCH_OVERLAY_FIELDS:
        value = str(values.get(field, "")).strip()
        if field != "report_name" and value:
            updated[field] = value
    reference = genre_references().get(pc.normalize_title(row.get("report_name")), {})
    if reference.get("genre"):
        updated["genre"] = reference["genre"]
        updated["genre_source_url"] = reference.get("genre_source_url", "")
    if reference.get("mobile_storefront_url") and is_blank_or_unconfirmed(updated.get("mobile_storefront_url")):
        updated["mobile_storefront_url"] = reference["mobile_storefront_url"]
    for field in ("publisher", "publisher_source_url", "comparable_game", "comparison_reason", "comparison_source_url"):
        if reference.get(field) and is_blank_or_unconfirmed(updated.get(field)):
            updated[field] = reference[field]
    updated["source_urls"] = append_source_urls(
        updated.get("source_urls"),
        reference.get("genre_source_url"),
        reference.get("publisher_source_url"),
        reference.get("comparison_source_url"),
        reference.get("mobile_storefront_url"),
    )
    if updated["enrichment_status"] == "needs_research":
        updated["enrichment_status"] = "research_overlay_applied"
    return updated


def build(meeting_date, research_overlay_path=None):
    game_rows = read_csv(game_report_layer_path(meeting_date))
    overlay_path = research_overlay_path or default_research_overlay_path(meeting_date)
    overlay = read_research_overlay(overlay_path)
    rows = [apply_overlay(base_enrichment_row(row), overlay) for row in game_rows]
    out = output_path(meeting_date)
    write_csv(out, rows)
    return out, rows


def main():
    parser = argparse.ArgumentParser(description="Build report-facing game enrichment layer.")
    parser.add_argument("--meeting-date", required=True)
    parser.add_argument("--research-overlay")
    args = parser.parse_args()

    path, rows = build(args.meeting_date, args.research_overlay)
    print(f"Meeting date: {args.meeting_date}")
    print(f"Game enriched layer rows: {len(rows)}")
    print(f"Output path: {path}")


if __name__ == "__main__":
    main()
