import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
LAYER2_CSV = ROOT / "data" / "output" / "layer2_unified_candidates.csv"
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "data" / "output"
CACHE_DIR = ROOT / "data" / "cache" / "app_metadata"
API_BASE = "https://api.sensortower.com"
BATCH_SIZE = 50


IOS_CATEGORY_MAP = {
    "0": "Overall",
    "6000": "Business",
    "6001": "Weather",
    "6002": "Utilities",
    "6003": "Travel",
    "6004": "Sports",
    "6005": "Social Networking",
    "6006": "Reference",
    "6007": "Productivity",
    "6008": "Photo & Video",
    "6009": "News",
    "6010": "Navigation",
    "6011": "Music",
    "6012": "Lifestyle",
    "6013": "Health & Fitness",
    "6014": "Games",
    "6015": "Finance",
    "6016": "Entertainment",
    "6017": "Education",
    "6018": "Books",
    "6020": "Medical",
    "6021": "Newsstand",
    "6023": "Food & Drink",
    "6024": "Shopping",
    "6026": "Developer Tools",
    "6027": "Graphics & Design",
    "7001": "Games/Action",
    "7002": "Games/Adventure",
    "7003": "Games/Casual",
    "7004": "Games/Board",
    "7005": "Games/Card",
    "7006": "Games/Casino",
    "7009": "Games/Family",
    "7011": "Games/Music",
    "7012": "Games/Puzzle",
    "7013": "Games/Racing",
    "7014": "Games/Role Playing",
    "7015": "Games/Simulation",
    "7016": "Games/Sports",
    "7017": "Games/Strategy",
    "7018": "Games/Trivia",
    "7019": "Games/Word",
    "9007": "Kids",
    "10000": "Kids/Ages 5 & Under",
    "10001": "Kids/Ages 6-8",
    "10002": "Kids/Ages 9-11",
}


ANDROID_CATEGORY_MAP = {
    "all": "Overall",
    "application": "Application",
    "game": "Game",
    "game_action": "Action",
    "game_adventure": "Adventure",
    "game_arcade": "Arcade",
    "game_board": "Board",
    "game_card": "Card",
    "game_casino": "Casino",
    "game_casual": "Casual",
    "game_educational": "Educational",
    "game_music": "Music",
    "game_puzzle": "Puzzle",
    "game_racing": "Racing",
    "game_role_playing": "Role Playing",
    "game_simulation": "Simulation",
    "game_sports": "Sports",
    "game_strategy": "Strategy",
    "game_trivia": "Trivia",
    "game_word": "Word",
}


def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit("Missing config/settings.json.")

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    token = os.environ.get("SENSORTOWER_AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing SENSORTOWER_AUTH_TOKEN environment variable.")
    config["auth_token"] = token

    return config


def request_json(path, params):
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Sensor Tower returned HTTP {exc.code} for {path}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Sensor Tower for {path}: {exc}") from exc


def save_raw(name, payload):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def read_layer2_candidates():
    if not LAYER2_CSV.exists():
        raise SystemExit("Missing data/output/layer2_unified_candidates.csv. Run Layer 2 first.")

    with LAYER2_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def to_rank(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999999


def group_by_unified_app(rows):
    groups = {}
    for row in rows:
        group_key = row.get("unified_app_id") or f"{row['platform']}:{row['app_id']}"
        groups.setdefault(group_key, []).append(row)
    return groups


def choose_representative(rows):
    # Prefer iOS metadata when a unified game has both iOS and Android. This keeps the
    # final report release date aligned to the iOS SG country release date when available.
    return sorted(rows, key=lambda row: (0 if row["platform"] == "ios" else 1, to_rank(row.get("best_sg_rank"))))[0]


def chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def cache_path(platform, app_id, country):
    safe_app_id = urllib.parse.quote(str(app_id), safe="")
    return CACHE_DIR / country / platform / f"{safe_app_id}.json"


def read_cached_metadata(platform, app_id, country):
    path = cache_path(platform, app_id, country)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None


def write_cached_metadata(platform, app):
    app_id = str(app.get("app_id", "")).strip()
    country = str(app.get("metadata_country", "SG")).strip() or "SG"
    if not app_id:
        return
    path = cache_path(platform, app_id, country)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(app, handle, ensure_ascii=False)


def fetch_metadata(platform, app_ids, auth_token, country):
    apps = []
    for batch_number, batch in enumerate(chunks(app_ids, BATCH_SIZE), start=1):
        payload = request_json(
            f"/v1/{platform}/apps",
            {
                "app_ids": ",".join(batch),
                "country": country,
                "auth_token": auth_token,
            },
        )
        save_raw(f"layer3_metadata_{platform}_batch_{batch_number}.json", payload)
        for app in payload.get("apps", []):
            app["metadata_country"] = country
            apps.append(app)
            write_cached_metadata(platform, app)
        time.sleep(0.25)
    return apps


def build_metadata_lookup(config, representatives):
    lookup = {}
    country = config.get("country", "SG")
    for platform in ["ios", "android"]:
        app_ids = sorted({rep["app_id"] for rep in representatives if rep["platform"] == platform})
        if not app_ids:
            continue

        cached_count = 0
        missing_app_ids = []
        for app_id in app_ids:
            cached = read_cached_metadata(platform, app_id, country)
            if cached:
                lookup[(platform, str(app_id).strip())] = cached
                cached_count += 1
            else:
                missing_app_ids.append(app_id)

        print(
            f"Metadata cache for {platform}: {cached_count} cached, "
            f"{len(missing_app_ids)} to fetch from Sensor Tower."
        )
        if missing_app_ids:
            apps = fetch_metadata(platform, missing_app_ids, config["auth_token"], country)
            for app in apps:
                lookup[(platform, str(app.get("app_id", "")).strip())] = app
    return lookup


def category_labels(platform, categories):
    if not isinstance(categories, list):
        return []

    mapping = IOS_CATEGORY_MAP if platform == "ios" else ANDROID_CATEGORY_MAP
    labels = []
    for category in categories:
        key = str(category)
        labels.append(mapping.get(key, key))
    return labels


def genre_from_categories(platform, categories):
    labels = category_labels(platform, categories)

    if platform == "ios":
        genres = [label.split("/", 1)[1] for label in labels if label.startswith("Games/")]
        if genres:
            return "; ".join(dict.fromkeys(genres))
        if "Games" in labels:
            return "Games"
        return "; ".join(labels)

    category_keys = [str(category) for category in categories] if isinstance(categories, list) else []
    genres = [ANDROID_CATEGORY_MAP[key] for key in category_keys if key.startswith("game_") and key != "game" and key in ANDROID_CATEGORY_MAP]
    if genres:
        return "; ".join(dict.fromkeys(genres))
    if "game" in category_keys:
        return "Game"
    return "; ".join(labels)


def unique_join(values):
    cleaned = []
    for value in values:
        if not value:
            continue
        for part in str(value).split("; "):
            part = part.strip()
            if part and part not in cleaned:
                cleaned.append(part)
    return "; ".join(cleaned)



def split_ids(value):
    if not value:
        return []
    return [part.strip() for part in str(value).split("; ") if part.strip()]


def parse_api_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def latest_date_value(values):
    parsed = []
    for value in values:
        parsed_date = parse_api_date(value)
        if parsed_date:
            parsed.append((parsed_date, value))
    if not parsed:
        return ""
    return max(parsed, key=lambda item: item[0])[1]


def metadata_for_ids(metadata_lookup, platform, ids):
    return [metadata_lookup.get((platform, app_id), {}) for app_id in ids if metadata_lookup.get((platform, app_id), {})]

def build_rows(groups, metadata_lookup):
    output_rows = []
    run_timestamp = datetime.now(timezone.utc).isoformat()

    for group_key, rows in groups.items():
        representative = choose_representative(rows)
        platform = representative["platform"]
        app_id = representative["app_id"]
        metadata = metadata_lookup.get((platform, app_id), {})
        categories = metadata.get("categories", [])
        ios_app_ids = unique_join(row.get("ios_app_ids", "") for row in rows)
        android_app_ids = unique_join(row.get("android_app_ids", "") for row in rows)
        ios_metadata = metadata_for_ids(metadata_lookup, "ios", split_ids(ios_app_ids))
        android_metadata = metadata_for_ids(metadata_lookup, "android", split_ids(android_app_ids))
        platform_metadata = ios_metadata + android_metadata
        official_release_date = latest_date_value(
            [item.get("country_release_date", "") for item in platform_metadata]
        ) or metadata.get("country_release_date", "") or metadata.get("release_date", "")

        output_rows.append(
            {
                "layer3_run_timestamp_utc": run_timestamp,
                "unified_app_id": representative.get("unified_app_id") or group_key,
                "unified_app_name": representative.get("unified_app_name", ""),
                "representative_platform": platform,
                "representative_app_id": app_id,
                "publisher_name": metadata.get("publisher_name", ""),
                "publisher_id": metadata.get("publisher_id", ""),
                "genre": genre_from_categories(platform, categories),
                "category_ids": "; ".join(str(category) for category in categories) if isinstance(categories, list) else "",
                "category_labels": "; ".join(category_labels(platform, categories)),
                "ios_app_ids": ios_app_ids,
                "android_app_ids": android_app_ids,
                "all_layer1_app_ids": unique_join(row.get("app_id", "") for row in rows),
                "platforms_seen_in_layer1": "; ".join(sorted({row["platform"] for row in rows})),
                "best_sg_rank": min(to_rank(row.get("best_sg_rank")) for row in rows),
                "sg_chart_matches": unique_join(row.get("sg_chart_matches", "") for row in rows),
                "released_tag_matches": unique_join(row.get("released_tag_matches", "") for row in rows),
                "release_date": metadata.get("release_date", ""),
                "country_release_date": official_release_date,
                "representative_country_release_date": metadata.get("country_release_date", ""),
                "updated_date": metadata.get("updated_date", ""),
                "active": metadata.get("active", ""),
                "valid_in_sg": "SG" in (metadata.get("valid_countries", []) or []),
                "metadata_lookup_status": "matched" if metadata else "not_found",
                "raw_app_metadata_json": json.dumps(metadata, ensure_ascii=False) if metadata else "",
            }
        )

    return sorted(output_rows, key=lambda row: (to_rank(row["best_sg_rank"]), row["unified_app_name"]))


def write_outputs(rows):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "layer3_unique_game_metadata.csv"
    json_path = OUTPUT_DIR / "layer3_unique_game_metadata.json"

    fieldnames = [
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

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=False)

    return csv_path, json_path


def main():
    config = load_config()
    layer2_rows = read_layer2_candidates()
    groups = group_by_unified_app(layer2_rows)
    representatives = [choose_representative(rows) for rows in groups.values()]
    metadata_seed_rows = list(representatives)
    for rows in groups.values():
        representative = choose_representative(rows)
        for row in rows:
            for ios_id in split_ids(row.get("ios_app_ids", "")):
                metadata_seed_rows.append({**representative, "platform": "ios", "app_id": ios_id})
            for android_id in split_ids(row.get("android_app_ids", "")):
                metadata_seed_rows.append({**representative, "platform": "android", "app_id": android_id})
    metadata_lookup = build_metadata_lookup(config, metadata_seed_rows)
    output_rows = build_rows(groups, metadata_lookup)
    csv_path, json_path = write_outputs(output_rows)

    matched_count = sum(1 for row in output_rows if row["metadata_lookup_status"] == "matched")
    print("")
    print(f"Done. Created {len(output_rows)} unique unified game rows from {len(layer2_rows)} Layer 2 rows.")
    print(f"Metadata matched for {matched_count} unique games.")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Layer 3 failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


