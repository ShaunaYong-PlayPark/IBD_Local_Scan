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
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "data" / "output"
WATCHLIST_CSV = ROOT / "data" / "local_app" / "watchlist.csv"
API_BASE = "https://api.sensortower.com"


def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit("Missing config/settings.json.")

    with CONFIG_PATH.open("r", encoding="utf-8-sig") as handle:
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


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_id(value):
    return str(value).strip()


def split_ids(value):
    if not value:
        return []
    return [part.strip() for part in str(value).replace(",", ";").split(";") if part.strip()]


def active_watchlist_ids_by_platform():
    rows = read_csv(WATCHLIST_CSV)
    ids_by_platform = {"ios": set(), "android": set()}
    for row in rows:
        if row.get("status") != "Watching":
            continue
        for app_id in split_ids(row.get("ios_app_ids", "")):
            ids_by_platform["ios"].add(normalize_id(app_id))
        for app_id in split_ids(row.get("android_app_ids", "")):
            ids_by_platform["android"].add(normalize_id(app_id))
    return ids_by_platform


def fetch_ranking_ids(platform, platform_config, chart_type, country, ranking_date, auth_token):
    payload = request_json(
        f"/v1/{platform}/ranking",
        {
            "category": platform_config["category"],
            "chart_type": chart_type,
            "country": country,
            "date": ranking_date,
            "auth_token": auth_token,
        },
    )

    save_raw(f"layer1_rankings_only_{platform}_{country}_{chart_type}_{ranking_date}.json", payload)

    ranking = payload.get("ranking", [])
    positions = {}
    for index, app_id in enumerate(ranking, start=1):
        positions[normalize_id(app_id)] = index
    return positions


def fetch_released_tag_ids(platform, platform_config, tag_name, tag_value, auth_token):
    payload = request_json(
        "/v1/app_tag/apps",
        {
            "app_id_type": platform_config["app_id_type"],
            "name": tag_name,
            "value": tag_value,
            "global": "true",
            "auth_token": auth_token,
        },
    )

    safe_value = tag_value.replace(" ", "_").replace("~", "approx").replace(">", "gt")
    save_raw(f"layer1_released_days_ww_{platform}_{safe_value}.json", payload)

    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = (
            payload.get("apps")
            or payload.get("app_ids")
            or payload.get("ids")
            or payload.get("data")
            or []
        )
    else:
        values = []

    ids = set()
    for item in values:
        if isinstance(item, dict):
            app_id = (
                item.get("app_id")
                or item.get("itunes_app_id")
                or item.get("android_app_id")
                or item.get("id")
            )
        else:
            app_id = item
        if app_id:
            ids.add(normalize_id(app_id))
    return ids


def build_candidates(config):
    auth_token = config["auth_token"]
    country = config["country"]
    ranking_date = config["ranking_date"]
    released_tag_name = config.get("released_tag_name", "Released Days Ago (WW)")
    released_tag_values = config.get("released_tag_values", ["~ 1 week", "~ 2 weeks"])
    watchlist_ids = active_watchlist_ids_by_platform()
    candidates_by_key = {}
    run_timestamp = datetime.now(timezone.utc).isoformat()

    for platform, platform_config in config["platforms"].items():
        print(f"Fetching SG rankings for {platform}...")
        chart_positions = {}
        for chart_type, chart_label in platform_config["charts"].items():
            chart_positions[chart_type] = fetch_ranking_ids(
                platform, platform_config, chart_type, country, ranking_date, auth_token
            )
            time.sleep(0.25)

        print(f"Fetching WW recent-release buckets for {platform}...")
        released_ids = {}
        recent_release_ids = set()
        for tag_value in released_tag_values:
            ids = fetch_released_tag_ids(
                platform, platform_config, released_tag_name, tag_value, auth_token
            )
            released_ids[tag_value] = ids
            recent_release_ids.update(ids)
            time.sleep(0.25)

        top_grossing_chart_types = [
            chart_type
            for chart_type in platform_config["charts"]
            if "gross" in chart_type.lower()
        ]
        top_grossing_ids = set()
        for chart_type in top_grossing_chart_types:
            top_grossing_ids.update(chart_positions.get(chart_type, {}).keys())

        # Discovery rule:
        #   Recently released globally + currently visible in SG Top Grossing.
        # Top Free is still fetched and recorded later, but it does not create candidates.
        discovered_ids = top_grossing_ids & recent_release_ids
        watchlist_followup_ids = top_grossing_ids & watchlist_ids.get(platform, set())
        all_candidate_ids = discovered_ids | watchlist_followup_ids
        print(
            f"{platform}: {len(discovered_ids)} new recent candidates and "
            f"{len(watchlist_followup_ids)} watchlist follow-ups in SG Top Grossing."
        )

        for app_id in all_candidate_ids:
            key = (platform, app_id)
            matched_tags = [
                tag_value
                for tag_value, ids in released_ids.items()
                if app_id in ids
            ]
            candidate_reason = (
                "Recently released globally and appeared in SG Games Top Grossing; "
                "Top Free rank recorded only if present"
            )
            if app_id in watchlist_followup_ids and app_id not in discovered_ids:
                candidate_reason = (
                    "Active watchlist follow-up still appearing in SG Games Top Grossing; "
                    "Top Free rank recorded only if present"
                )
            chart_details = []
            chart_matches = []
            best_rank = None

            for chart_type, positions in chart_positions.items():
                if app_id not in positions:
                    continue
                rank = positions[app_id]
                chart_label = platform_config["charts"][chart_type]
                best_rank = rank if best_rank is None else min(best_rank, rank)
                chart_matches.append(f"{chart_label} #{rank}")
                chart_details.append(
                    {
                        "chart_type": chart_type,
                        "chart_label": chart_label,
                        "rank": rank,
                        "rank_usage": "discovery" if chart_type in top_grossing_chart_types else "record_only",
                    }
                )

            candidates_by_key[key] = {
                "run_timestamp_utc": run_timestamp,
                "ranking_date": ranking_date,
                "country": country,
                "platform": platform,
                "app_id": app_id,
                "released_tag_matches": "; ".join(matched_tags),
                "sg_chart_matches": "; ".join(chart_matches),
                "best_sg_rank": best_rank or "",
                "candidate_reason": candidate_reason,
                "chart_match_details": chart_details,
            }

    rows = []
    for row in candidates_by_key.values():
        output_row = {key: value for key, value in row.items() if key != "chart_match_details"}
        output_row["chart_match_details_json"] = json.dumps(row["chart_match_details"], ensure_ascii=False)
        rows.append(output_row)

    return sorted(rows, key=lambda row: (row["platform"], int(row["best_sg_rank"] or 999999), row["app_id"]))


def write_outputs(candidates):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "layer1_candidates.csv"
    json_path = OUTPUT_DIR / "layer1_candidates.json"

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
    ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(candidates, handle, indent=2, ensure_ascii=False)

    return csv_path, json_path


def main():
    config = load_config()
    candidates = build_candidates(config)
    csv_path, json_path = write_outputs(candidates)

    print("")
    print(f"Done. Found {len(candidates)} recent WW-release app IDs in SG Top Grossing.")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"SG rankings-only Layer 1 failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
