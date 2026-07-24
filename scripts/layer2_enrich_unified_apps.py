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

from candidate_store import known_existing_unified_ids, read_known_existing_games


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
LAYER1_CSV = ROOT / "data" / "output" / "layer1_candidates.csv"
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "data" / "output"
API_BASE = "https://api.sensortower.com"
BATCH_SIZE = 50


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


def read_layer1_candidates():
    if not LAYER1_CSV.exists():
        raise SystemExit("Missing data/output/layer1_candidates.csv. Run Layer 1 first.")

    with LAYER1_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_unified_apps(platform, app_ids, app_id_type, auth_token):
    apps = []
    for batch_number, batch in enumerate(chunks(app_ids, BATCH_SIZE), start=1):
        payload = request_json(
            "/v1/unified/apps",
            {
                "app_id_type": app_id_type,
                "app_ids": ",".join(batch),
                "auth_token": auth_token,
            },
        )
        save_raw(f"layer2_unified_{platform}_batch_{batch_number}.json", payload)
        apps.extend(payload.get("apps", []))
        time.sleep(0.25)
    return apps


def json_join(values):
    if values is None:
        return ""
    return json.dumps(values, ensure_ascii=False)


def build_unified_lookup(config, layer1_rows):
    lookup = {}

    for platform, platform_config in config["platforms"].items():
        app_ids = sorted({row["app_id"] for row in layer1_rows if row["platform"] == platform})
        if not app_ids:
            continue

        print(f"Fetching unified app details for {len(app_ids)} {platform} app IDs...")
        apps = fetch_unified_apps(
            platform=platform,
            app_ids=app_ids,
            app_id_type=platform_config["app_id_type"],
            auth_token=config["auth_token"],
        )

        for app in apps:
            canonical_app_id = str(app.get("canonical_app_id", "")).strip()
            if canonical_app_id:
                lookup[(platform, canonical_app_id)] = app

            for ios_app in app.get("itunes_apps", []) or []:
                ios_id = str(ios_app.get("app_id", "")).strip()
                if ios_id:
                    lookup[("ios", ios_id)] = app

            for android_app in app.get("android_apps", []) or []:
                android_id = str(android_app.get("app_id", "")).strip()
                if android_id:
                    lookup[("android", android_id)] = app

    return lookup


def enrich_rows(layer1_rows, lookup):
    enriched = []
    run_timestamp = datetime.now(timezone.utc).isoformat()

    for row in layer1_rows:
        platform = row["platform"]
        app_id = row["app_id"]
        app = lookup.get((platform, app_id), {})

        ios_ids = [str(item.get("app_id", "")) for item in app.get("itunes_apps", []) or []]
        android_ids = [str(item.get("app_id", "")) for item in app.get("android_apps", []) or []]

        enriched.append(
            {
                **row,
                "layer2_run_timestamp_utc": run_timestamp,
                "unified_app_id": app.get("unified_app_id", ""),
                "unified_app_name": app.get("name", ""),
                "canonical_app_id": app.get("canonical_app_id", ""),
                "cohort_id": app.get("cohort_id", ""),
                "ios_app_ids": "; ".join(ios_ids),
                "android_app_ids": "; ".join(android_ids),
                "unified_publisher_ids": "; ".join(app.get("unified_publisher_ids", []) or []),
                "itunes_publisher_ids": "; ".join(str(value) for value in app.get("itunes_publisher_ids", []) or []),
                "android_publisher_ids": "; ".join(str(value) for value in app.get("android_publisher_ids", []) or []),
                "unified_lookup_status": "matched" if app else "not_found",
                "raw_unified_app_json": json_join(app) if app else "",
            }
        )

    return enriched


def filter_known_existing_unified_rows(rows, known_existing_rows=None):
    known_existing_rows = (
        list(known_existing_rows)
        if known_existing_rows is not None
        else read_known_existing_games()
    )
    known_unified_ids = known_existing_unified_ids(known_existing_rows)
    return [
        row
        for row in rows
        if not row.get("unified_app_id") or row.get("unified_app_id") not in known_unified_ids
    ]


def write_outputs(rows):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "layer2_unified_candidates.csv"
    json_path = OUTPUT_DIR / "layer2_unified_candidates.json"

    fieldnames = [
        "run_timestamp_utc",
        "ranking_date",
        "country",
        "platform",
        "app_id",
        "released_tag_matches",
        "sg_chart_matches",
        "best_sg_rank",
        "candidate_reason",
        "chart_match_details_json",
        "layer2_run_timestamp_utc",
        "unified_app_id",
        "unified_app_name",
        "canonical_app_id",
        "cohort_id",
        "ios_app_ids",
        "android_app_ids",
        "unified_publisher_ids",
        "itunes_publisher_ids",
        "android_publisher_ids",
        "unified_lookup_status",
        "raw_unified_app_json",
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
    layer1_rows = read_layer1_candidates()
    known_existing_rows = read_known_existing_games()
    lookup = build_unified_lookup(config, layer1_rows)
    enriched = filter_known_existing_unified_rows(
        enrich_rows(layer1_rows, lookup),
        known_existing_rows=known_existing_rows,
    )
    csv_path, json_path = write_outputs(enriched)

    matched_count = sum(1 for row in enriched if row["unified_lookup_status"] == "matched")
    print("")
    print(f"Done. Enriched {matched_count} of {len(enriched)} Layer 1 candidates.")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Layer 2 failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
