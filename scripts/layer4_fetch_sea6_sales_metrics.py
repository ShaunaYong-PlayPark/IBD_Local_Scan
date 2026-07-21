import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
LAYER3_CSV = ROOT / "data" / "output" / "layer3_unique_game_metadata.csv"
REPORT_PERIOD_CANDIDATES_CSV = ROOT / "data" / "output" / "report_period_candidate_metadata.csv"
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "data" / "output"
API_BASE = "https://api.sensortower.com"
BATCH_SIZE = 50
STORE_REVENUE_SHARE = 0.70


def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit("Missing config/settings.json.")

    with CONFIG_PATH.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)

    token = os.environ.get("SENSORTOWER_AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing SENSORTOWER_AUTH_TOKEN environment variable.")
    config["auth_token"] = token

    for required in ["report_start_date", "report_end_date", "sensor_tower_lag_days", "sea6_countries"]:
        if required not in config:
            raise SystemExit(f"Missing config setting: {required}")

    return config


def effective_dates(config):
    start = date.fromisoformat(config["report_start_date"])
    report_end = date.fromisoformat(config["report_end_date"])
    lag_days = int(config["sensor_tower_lag_days"])
    effective_end = report_end - timedelta(days=lag_days)

    if start.weekday() != 1:
        raise SystemExit(
            f"Invalid report_start_date: {start.isoformat()}. Run periods must start on a Tuesday."
        )

    if report_end.weekday() != 0:
        raise SystemExit(
            f"Invalid report_end_date: {report_end.isoformat()}. Run periods must end on a Monday."
        )

    if report_end < start:
        raise SystemExit("report_end_date must be after report_start_date.")

    if effective_end < start:
        raise SystemExit("Effective Sensor Tower end date is before the report start date.")

    return start.isoformat(), report_end.isoformat(), effective_end.isoformat(), lag_days


def request_json(path, params):
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
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


def read_layer3_games():
    source = REPORT_PERIOD_CANDIDATES_CSV if REPORT_PERIOD_CANDIDATES_CSV.exists() else LAYER3_CSV
    if not source.exists():
        raise SystemExit("Missing candidate metadata. Run Layer 3 or prepare_report_period_candidates.py first.")

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_api_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def filter_sales_candidates(games):
    # Layer 1 already limits the pool to:
    #   - WW recent-release bucket + SG Top Grossing, or
    #   - active watchlist follow-up still in SG Top Grossing.
    #
    # Do not hard-filter by Sensor Tower country_release_date here. That date is
    # recorded as evidence, but it can be early/late and should not exclude a
    # commercially visible SG Top Grossing game.
    return [game for game in games if game.get("unified_app_id")]


def chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_sales_estimates(app_ids, countries, start_date, effective_end_date, auth_token):
    all_rows = []
    country_param = ",".join(countries)

    for batch_number, batch in enumerate(chunks(app_ids, BATCH_SIZE), start=1):
        payload = request_json(
            "/v1/unified/sales_report_estimates",
            {
                "app_ids": ",".join(batch),
                "countries": country_param,
                "date_granularity": "daily",
                "start_date": start_date,
                "end_date": effective_end_date,
                "auth_token": auth_token,
            },
        )
        save_raw(f"layer4_sales_unified_batch_{batch_number}.json", payload)
        if isinstance(payload, list):
            all_rows.extend(payload)
        else:
            all_rows.extend(payload.get("sales_report_estimates", []))
        time.sleep(0.25)

    return all_rows


def number(value):
    if value in (None, ""):
        return 0
    return float(value)


def cents_to_store_dollars(cents):
    return number(cents) / 100.0


def store_to_gross_dollars(store_dollars):
    return store_dollars / STORE_REVENUE_SHARE if STORE_REVENUE_SHARE else 0


def round_money(value):
    return round(value, 2)


def game_lookup(games):
    return {row["unified_app_id"]: row for row in games}


def build_daily_rows(api_rows, games_by_id, report_start, report_end, effective_end, lag_days):
    run_timestamp = datetime.now(timezone.utc).isoformat()
    daily_rows = []

    for item in api_rows:
        unified_app_id = str(item.get("app_id", "")).strip()
        game = games_by_id.get(unified_app_id, {})

        android_downloads = number(item.get("android_units"))
        ipad_downloads = number(item.get("ipad_units"))
        iphone_downloads = number(item.get("iphone_units"))
        total_downloads = android_downloads + ipad_downloads + iphone_downloads

        android_revenue_cents = number(item.get("android_revenue"))
        ipad_revenue_cents = number(item.get("ipad_revenue"))
        iphone_revenue_cents = number(item.get("iphone_revenue"))
        store_revenue_cents = android_revenue_cents + ipad_revenue_cents + iphone_revenue_cents
        store_revenue_dollars = cents_to_store_dollars(store_revenue_cents)
        gross_revenue_dollars = store_to_gross_dollars(store_revenue_dollars)

        daily_rows.append(
            {
                "layer4_run_timestamp_utc": run_timestamp,
                "report_start_date": report_start,
                "report_end_date": report_end,
                "sensor_tower_effective_end_date": effective_end,
                "sensor_tower_lag_days": lag_days,
                "date_granularity": "daily",
                "unified_app_id": unified_app_id,
                "unified_app_name": game.get("unified_app_name", ""),
                "publisher_name": game.get("publisher_name", ""),
                "genre": game.get("genre", ""),
                "country": item.get("country", ""),
                "date": item.get("date", ""),
                "android_downloads": int(android_downloads),
                "ipad_downloads": int(ipad_downloads),
                "iphone_downloads": int(iphone_downloads),
                "total_downloads": int(total_downloads),
                "android_revenue_cents": int(android_revenue_cents),
                "ipad_revenue_cents": int(ipad_revenue_cents),
                "iphone_revenue_cents": int(iphone_revenue_cents),
                "store_revenue_cents": int(store_revenue_cents),
                "store_revenue_dollars": round_money(store_revenue_dollars),
                "gross_revenue_dollars": round_money(gross_revenue_dollars),
                "raw_sales_row_json": json.dumps(item, ensure_ascii=False),
            }
        )

    return daily_rows


def build_country_totals(daily_rows):
    totals = {}

    for row in daily_rows:
        key = (row["unified_app_id"], row["country"])
        if key not in totals:
            totals[key] = {
                "layer4_run_timestamp_utc": row["layer4_run_timestamp_utc"],
                "report_start_date": row["report_start_date"],
                "report_end_date": row["report_end_date"],
                "sensor_tower_effective_end_date": row["sensor_tower_effective_end_date"],
                "sensor_tower_lag_days": row["sensor_tower_lag_days"],
                "unified_app_id": row["unified_app_id"],
                "unified_app_name": row["unified_app_name"],
                "publisher_name": row["publisher_name"],
                "genre": row["genre"],
                "country": row["country"],
                "days_returned": 0,
                "android_downloads": 0,
                "ipad_downloads": 0,
                "iphone_downloads": 0,
                "total_downloads": 0,
                "android_revenue_cents": 0,
                "ipad_revenue_cents": 0,
                "iphone_revenue_cents": 0,
                "store_revenue_cents": 0,
                "store_revenue_dollars": 0,
                "gross_revenue_dollars": 0,
            }

        total = totals[key]
        total["days_returned"] += 1
        for field in [
            "android_downloads",
            "ipad_downloads",
            "iphone_downloads",
            "total_downloads",
            "android_revenue_cents",
            "ipad_revenue_cents",
            "iphone_revenue_cents",
            "store_revenue_cents",
        ]:
            total[field] += int(row[field])

    for total in totals.values():
        total["store_revenue_dollars"] = round_money(cents_to_store_dollars(total["store_revenue_cents"]))
        total["gross_revenue_dollars"] = round_money(store_to_gross_dollars(total["store_revenue_dollars"]))

    return sorted(totals.values(), key=lambda row: (row["unified_app_name"], row["country"]))


def build_game_totals(country_totals):
    totals = {}

    for row in country_totals:
        key = row["unified_app_id"]
        if key not in totals:
            totals[key] = {
                "layer4_run_timestamp_utc": row["layer4_run_timestamp_utc"],
                "report_start_date": row["report_start_date"],
                "report_end_date": row["report_end_date"],
                "sensor_tower_effective_end_date": row["sensor_tower_effective_end_date"],
                "sensor_tower_lag_days": row["sensor_tower_lag_days"],
                "unified_app_id": row["unified_app_id"],
                "unified_app_name": row["unified_app_name"],
                "publisher_name": row["publisher_name"],
                "genre": row["genre"],
                "countries_with_rows": [],
                "total_downloads": 0,
                "store_revenue_cents": 0,
                "store_revenue_dollars": 0,
                "gross_revenue_dollars": 0,
            }

        total = totals[key]
        total["countries_with_rows"].append(row["country"])
        total["total_downloads"] += int(row["total_downloads"])
        total["store_revenue_cents"] += int(row["store_revenue_cents"])

    for total in totals.values():
        total["countries_with_rows"] = "; ".join(total["countries_with_rows"])
        total["store_revenue_dollars"] = round_money(cents_to_store_dollars(total["store_revenue_cents"]))
        total["gross_revenue_dollars"] = round_money(store_to_gross_dollars(total["store_revenue_dollars"]))

    return sorted(totals.values(), key=lambda row: row["gross_revenue_dollars"], reverse=True)


def write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(daily_rows, country_totals, game_totals):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    daily_path = OUTPUT_DIR / "layer4_sea6_daily_metrics.csv"
    country_path = OUTPUT_DIR / "layer4_sea6_country_totals.csv"
    game_path = OUTPUT_DIR / "layer4_sea6_game_totals.csv"
    json_path = OUTPUT_DIR / "layer4_sea6_metrics.json"

    daily_fields = [
        "layer4_run_timestamp_utc",
        "report_start_date",
        "report_end_date",
        "sensor_tower_effective_end_date",
        "sensor_tower_lag_days",
        "date_granularity",
        "unified_app_id",
        "unified_app_name",
        "publisher_name",
        "genre",
        "country",
        "date",
        "android_downloads",
        "ipad_downloads",
        "iphone_downloads",
        "total_downloads",
        "android_revenue_cents",
        "ipad_revenue_cents",
        "iphone_revenue_cents",
        "store_revenue_cents",
        "store_revenue_dollars",
        "gross_revenue_dollars",
        "raw_sales_row_json",
    ]

    country_fields = [
        "layer4_run_timestamp_utc",
        "report_start_date",
        "report_end_date",
        "sensor_tower_effective_end_date",
        "sensor_tower_lag_days",
        "unified_app_id",
        "unified_app_name",
        "publisher_name",
        "genre",
        "country",
        "days_returned",
        "android_downloads",
        "ipad_downloads",
        "iphone_downloads",
        "total_downloads",
        "android_revenue_cents",
        "ipad_revenue_cents",
        "iphone_revenue_cents",
        "store_revenue_cents",
        "store_revenue_dollars",
        "gross_revenue_dollars",
    ]

    game_fields = [
        "layer4_run_timestamp_utc",
        "report_start_date",
        "report_end_date",
        "sensor_tower_effective_end_date",
        "sensor_tower_lag_days",
        "unified_app_id",
        "unified_app_name",
        "publisher_name",
        "genre",
        "countries_with_rows",
        "total_downloads",
        "store_revenue_cents",
        "store_revenue_dollars",
        "gross_revenue_dollars",
    ]

    write_csv(daily_path, daily_rows, daily_fields)
    write_csv(country_path, country_totals, country_fields)
    write_csv(game_path, game_totals, game_fields)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "daily_rows": daily_rows,
                "country_totals": country_totals,
                "game_totals": game_totals,
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )

    return daily_path, country_path, game_path, json_path


def main():
    config = load_config()
    report_start, report_end, effective_end, lag_days = effective_dates(config)
    countries = config["sea6_countries"]
    all_games = read_layer3_games()
    games = filter_sales_candidates(all_games)
    games_by_id = game_lookup(games)
    unified_app_ids = sorted(games_by_id.keys())

    print(f"Layer 4 candidate prefilter: {len(games)} of {len(all_games)} Layer 3 games selected for SEA6 sales.")
    print(f"Fetching unified daily SEA6 sales estimates for {len(unified_app_ids)} apps...")
    print(f"Report period: {report_start} to {report_end}; Sensor Tower effective end: {effective_end}")

    api_rows = fetch_sales_estimates(
        app_ids=unified_app_ids,
        countries=countries,
        start_date=report_start,
        effective_end_date=effective_end,
        auth_token=config["auth_token"],
    )

    daily_rows = build_daily_rows(api_rows, games_by_id, report_start, report_end, effective_end, lag_days)
    country_totals = build_country_totals(daily_rows)
    game_totals = build_game_totals(country_totals)
    daily_path, country_path, game_path, json_path = write_outputs(daily_rows, country_totals, game_totals)

    print("")
    print(f"Done. API returned {len(api_rows)} daily country rows.")
    print(f"Daily CSV: {daily_path}")
    print(f"Country totals CSV: {country_path}")
    print(f"Game totals CSV: {game_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Layer 4 failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
