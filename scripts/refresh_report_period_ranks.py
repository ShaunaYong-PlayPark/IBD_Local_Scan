import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from candidate_store import (
    REPORT_PERIOD_LAYER2_CSV,
    load_config,
    read_csv,
    select_report_period_candidates,
    write_csv,
    write_json,
    ROOT,
)


API_BASE = "https://api.sensortower.com"
RAW_DIR = ROOT / "data" / "raw"
RANK_OUTPUT_JSON = ROOT / "data" / "output" / "report_period_rank_refresh.json"


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


def normalize_id(value):
    return str(value).strip()


def split_ids(value):
    return [part.strip() for part in str(value or "").replace(",", ";").split(";") if part.strip()]


def fetch_chart(platform, platform_config, chart_type, country, ranking_date, auth_token):
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
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"report_period_ranks_{platform}_{country}_{chart_type}_{ranking_date}.json"
    with (RAW_DIR / safe_name).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return {normalize_id(app_id): index for index, app_id in enumerate(payload.get("ranking", []), start=1)}


def main():
    config = load_config()
    token = os.environ.get("SENSORTOWER_AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing SENSORTOWER_AUTH_TOKEN environment variable.")
    config["auth_token"] = token

    country = config.get("country", "SG")
    ranking_date = config["ranking_date"]
    candidates = select_report_period_candidates(config)
    run_timestamp = datetime.now(timezone.utc).isoformat()

    chart_positions = {}
    for platform, platform_config in config["platforms"].items():
        chart_positions[platform] = {}
        for chart_type in platform_config["charts"]:
            print(f"Fetching {platform} {chart_type} for {country} on {ranking_date}...")
            chart_positions[platform][chart_type] = fetch_chart(platform, platform_config, chart_type, country, ranking_date, token)
            time.sleep(0.25)

    rows = []
    for candidate in candidates:
        uid = candidate.get("unified_app_id", "")
        for platform, ids_field in (("ios", "ios_app_ids"), ("android", "android_app_ids")):
            for app_id in split_ids(candidate.get(ids_field, "")):
                details = []
                matches = []
                best_rank = None
                for chart_type, positions in chart_positions.get(platform, {}).items():
                    if app_id not in positions:
                        continue
                    rank = positions[app_id]
                    label = config["platforms"][platform]["charts"][chart_type]
                    details.append({
                        "chart_type": chart_type,
                        "chart_label": label,
                        "rank": rank,
                        "rank_usage": "final_report_rank",
                    })
                    matches.append(f"{label} #{rank}")
                    best_rank = rank if best_rank is None else min(best_rank, rank)
                rows.append({
                    "run_timestamp_utc": run_timestamp,
                    "ranking_date": ranking_date,
                    "country": country,
                    "platform": platform,
                    "app_id": app_id,
                    "released_tag_matches": candidate.get("source_bucket", ""),
                    "sg_chart_matches": "; ".join(matches),
                    "best_sg_rank": best_rank or "",
                    "candidate_reason": "Stored weekly candidate selected for report-period final rank refresh.",
                    "chart_match_details_json": json.dumps(details, ensure_ascii=False),
                    "unified_app_id": uid,
                    "unified_app_name": candidate.get("title", ""),
                    "ios_app_ids": candidate.get("ios_app_ids", ""),
                    "android_app_ids": candidate.get("android_app_ids", ""),
                    "unified_lookup_status": "from_candidate_store",
                })

    existing_fields = list(read_csv(REPORT_PERIOD_LAYER2_CSV)[0].keys()) if read_csv(REPORT_PERIOD_LAYER2_CSV) else []
    fields = list(dict.fromkeys(existing_fields + list(rows[0].keys()) if rows else existing_fields))
    write_csv(REPORT_PERIOD_LAYER2_CSV, rows, fields)
    write_json(RANK_OUTPUT_JSON, rows)
    print("Report-period rank refresh complete.")
    print(f"Stored candidate app IDs checked: {len(candidates)}")
    print(f"Rank evidence rows written: {len(rows)}")
    print(f"Output: {REPORT_PERIOD_LAYER2_CSV}")


if __name__ == "__main__":
    main()
