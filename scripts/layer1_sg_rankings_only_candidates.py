import argparse
import csv
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from candidate_store import known_existing_platform_app_ids, read_known_existing_games


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "data" / "output"
OBSERVATION_LEDGER_CSV = ROOT / "data" / "candidates" / "sg_chart_observations.csv"
API_BASE = "https://api.sensortower.com"
DISCOVERY_SOURCE = "SG Top Grossing first seen"
OBSERVATION_FIELDS = [
    "run_timestamp_utc",
    "ranking_date",
    "country",
    "platform",
    "chart_type",
    "chart_label",
    "app_id",
    "rank",
]


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


def fetch_ranking_ids(
    platform,
    platform_config,
    chart_type,
    country,
    ranking_date,
    auth_token,
    save_raw_response=True,
):
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

    if save_raw_response:
        save_raw(f"layer1_rankings_only_{platform}_{country}_{chart_type}_{ranking_date}.json", payload)

    ranking = payload.get("ranking", [])
    positions = {}
    for index, app_id in enumerate(ranking, start=1):
        positions[normalize_id(app_id)] = index
    return positions


def observation_key(row):
    return (
        row.get("ranking_date", ""),
        row.get("country", ""),
        row.get("platform", ""),
        row.get("chart_type", ""),
        normalize_id(row.get("app_id", "")),
    )


def seen_app_ids(observations, country):
    seen = {"ios": set(), "android": set()}
    for row in observations:
        platform = row.get("platform", "")
        app_id = normalize_id(row.get("app_id", ""))
        chart_type = row.get("chart_type", "")
        if (
            row.get("country", "").upper() == country.upper()
            and platform in seen
            and "gross" in chart_type.lower()
            and app_id
        ):
            seen[platform].add(app_id)
    return seen


def merge_observations(existing_rows, current_rows):
    merged = {observation_key(row): row for row in existing_rows if row.get("app_id")}
    for row in current_rows:
        merged[observation_key(row)] = row
    return sorted(
        merged.values(),
        key=lambda row: (
            row.get("ranking_date", ""),
            row.get("country", ""),
            row.get("platform", ""),
            row.get("chart_type", ""),
            int(row.get("rank") or 999999),
            row.get("app_id", ""),
        ),
    )


def write_observation_ledger(rows, path=OBSERVATION_LEDGER_CSV):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=OBSERVATION_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        raise
    return path


def read_baseline_ledger(path=OBSERVATION_LEDGER_CSV):
    if not path.exists():
        raise RuntimeError(f"Baseline ledger does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != OBSERVATION_FIELDS:
            raise RuntimeError("Baseline ledger header does not match the SG observation schema.")
        return list(reader)


def read_required_discovery_ledger(path=OBSERVATION_LEDGER_CSV):
    rows = read_baseline_ledger(path)
    if not rows:
        raise RuntimeError(
            "Normal discovery refused: SG chart observation ledger has no baseline rows. "
            "Run --baseline-only as the separately approved seeding step first."
        )
    return rows


def validate_baseline_ranking_date(config, today=None):
    try:
        lag_days = int(config.get("sensor_tower_lag_days", 2))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("sensor_tower_lag_days must be an integer of at least 2.") from exc
    if lag_days < 2:
        raise RuntimeError("Baseline requires at least two full days of Sensor Tower lag.")

    try:
        ranking_date = date.fromisoformat(str(config["ranking_date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Baseline requires a valid configured ranking_date.") from exc

    singapore_today = today or datetime.now(timezone(timedelta(hours=8))).date()
    latest_allowed = singapore_today - timedelta(days=lag_days)
    if ranking_date > latest_allowed:
        raise RuntimeError(
            f"Configured ranking_date {ranking_date.isoformat()} is too recent; "
            f"latest allowed is {latest_allowed.isoformat()} for a {lag_days}-day lag."
        )
    return ranking_date.isoformat()


def baseline_top_grossing_chart(platform, platform_config):
    matches = [
        (chart_type, chart_label)
        for chart_type, chart_label in platform_config.get("charts", {}).items()
        if "gross" in chart_type.lower()
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Baseline requires exactly one configured Top Grossing chart for {platform}."
        )
    return matches[0]


def run_baseline_only(
    config,
    ranking_fetcher=None,
    ledger_path=OBSERVATION_LEDGER_CSV,
    today=None,
):
    existing_rows = read_baseline_ledger(ledger_path)
    if existing_rows:
        raise RuntimeError("Baseline refused: SG chart observation ledger already has data rows.")

    country = str(config.get("country", "")).upper()
    if country != "SG":
        raise RuntimeError("Baseline-only mode supports SG only.")
    ranking_date = validate_baseline_ranking_date(config, today=today)
    if ranking_fetcher is None:
        def ranking_fetcher(
            platform,
            platform_config,
            chart_type,
            country,
            ranking_date,
            auth_token,
        ):
            return fetch_ranking_ids(
                platform,
                platform_config,
                chart_type,
                country,
                ranking_date,
                auth_token,
                save_raw_response=False,
            )
    auth_token = config["auth_token"]
    run_timestamp = datetime.now(timezone.utc).isoformat()
    observations = []

    # Fetch both complete platform baselines before writing the ledger.
    for platform in ("ios", "android"):
        platform_config = config.get("platforms", {}).get(platform)
        if not platform_config:
            raise RuntimeError(f"Baseline requires {platform} platform configuration.")
        chart_type, chart_label = baseline_top_grossing_chart(platform, platform_config)
        positions = ranking_fetcher(
            platform,
            platform_config,
            chart_type,
            country,
            ranking_date,
            auth_token,
        )
        if not positions:
            raise RuntimeError(
                f"Baseline refused: {platform} SG Top Grossing response was empty."
            )
        for app_id, rank in positions.items():
            observations.append(
                {
                    "run_timestamp_utc": run_timestamp,
                    "ranking_date": ranking_date,
                    "country": country,
                    "platform": platform,
                    "chart_type": chart_type,
                    "chart_label": chart_label,
                    "app_id": normalize_id(app_id),
                    "rank": rank,
                }
            )

    write_observation_ledger(observations, ledger_path)
    return [], observations, ledger_path


def build_candidates(
    config,
    ranking_fetcher=None,
    existing_observations=None,
    known_existing_rows=None,
):
    ranking_fetcher = ranking_fetcher or fetch_ranking_ids
    auth_token = config["auth_token"]
    country = config["country"]
    if country.upper() != "SG":
        raise ValueError("Ranking-first discovery Phase 1 supports SG only.")
    ranking_date = config["ranking_date"]
    prior_observations = (
        list(existing_observations)
        if existing_observations is not None
        else read_required_discovery_ledger(OBSERVATION_LEDGER_CSV)
    )
    seen_before = seen_app_ids(prior_observations, country)
    known_existing_rows = (
        list(known_existing_rows)
        if known_existing_rows is not None
        else read_known_existing_games()
    )
    known_platform_app_ids = known_existing_platform_app_ids(known_existing_rows)
    current_observations = []
    candidates_by_key = {}
    run_timestamp = datetime.now(timezone.utc).isoformat()

    for platform, platform_config in config["platforms"].items():
        print(f"Fetching SG rankings for {platform}...")
        chart_positions = {}
        for chart_type, chart_label in platform_config["charts"].items():
            chart_positions[chart_type] = ranking_fetcher(
                platform, platform_config, chart_type, country, ranking_date, auth_token
            )
            time.sleep(0.25)

        top_grossing_chart_types = [
            chart_type
            for chart_type in platform_config["charts"]
            if "gross" in chart_type.lower()
        ]
        top_grossing_ids = set()
        for chart_type in top_grossing_chart_types:
            chart_label = platform_config["charts"][chart_type]
            positions = chart_positions.get(chart_type, {})
            top_grossing_ids.update(positions.keys())
            for app_id, rank in positions.items():
                current_observations.append(
                    {
                        "run_timestamp_utc": run_timestamp,
                        "ranking_date": ranking_date,
                        "country": country,
                        "platform": platform,
                        "chart_type": chart_type,
                        "chart_label": chart_label,
                        "app_id": app_id,
                        "rank": rank,
                    }
                )

        # Discovery rule:
        #   First appearance in the local SG Top Grossing observation history.
        # Sensor Tower release dates and worldwide release tags are not gates.
        # Top Free is still fetched and recorded later, but it does not create candidates.
        known_platform_ids = {
            app_id
            for known_platform, app_id in known_platform_app_ids
            if known_platform == platform
        }
        discovered_ids = (
            top_grossing_ids
            - seen_before.get(platform, set())
            - known_platform_ids
        )
        print(
            f"{platform}: {len(discovered_ids)} app IDs first seen in local "
            "SG Top Grossing history."
        )

        for app_id in discovered_ids:
            key = (platform, app_id)
            candidate_reason = (
                f"{DISCOVERY_SOURCE}; "
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
                "released_tag_matches": "",
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

    candidates = sorted(
        rows,
        key=lambda row: (row["platform"], int(row["best_sg_rank"] or 999999), row["app_id"]),
    )
    return candidates, merge_observations(prior_observations, current_observations)


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="SG ranking-first Layer 1 discovery.")
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Seed an empty SG Top Grossing observation ledger without creating candidates.",
    )
    args = parser.parse_args(argv)
    config = load_config()
    if args.baseline_only:
        candidates, observations, ledger_path = run_baseline_only(config)
        print("")
        print("SG Top Grossing baseline complete.")
        print(f"Candidates created: {len(candidates)}")
        print(f"Observations written: {len(observations)}")
        print(f"Observation ledger: {ledger_path}")
        return

    candidates, observations = build_candidates(config)
    csv_path, json_path = write_outputs(candidates)
    ledger_path = write_observation_ledger(observations)

    print("")
    print(f"Done. Found {len(candidates)} app IDs first seen in SG Top Grossing history.")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Observation ledger: {ledger_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"SG rankings-only Layer 1 failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
