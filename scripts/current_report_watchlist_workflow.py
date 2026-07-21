import csv
import json
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
LAYER2_CSV = ROOT / "data" / "output" / "layer2_unified_candidates.csv"
REPORT_PERIOD_LAYER2_CSV = ROOT / "data" / "output" / "report_period_layer2_candidates.csv"
LAYER3_CSV = ROOT / "data" / "output" / "layer3_unique_game_metadata.csv"
LAYER3_5_CSV = ROOT / "data" / "output" / "layer3_5_title_normalised_metadata.csv"
REPORT_PERIOD_CANDIDATES_CSV = ROOT / "data" / "output" / "report_period_candidate_metadata.csv"
LAYER3_5_SCRIPT = ROOT / "scripts" / "layer3_5_title_normalise.py"
LAYER4_COUNTRY_CSV = ROOT / "data" / "output" / "layer4_sea6_country_totals.csv"
APP_DIR = ROOT / "data" / "local_app"
WATCHLIST_CSV = APP_DIR / "watchlist.csv"
OUTPUT_DIR = ROOT / "data" / "output"

IOS_DL_CHART = "topfreeapplications"
IOS_REV_CHART = "topgrossingapplications"
ANDROID_DL_CHART = "topselling_free"
ANDROID_REV_CHART = "topgrossing"
WATCH_PERIODS_AFTER_RELEASE = 3
STRONG_SG_GROSS_REVENUE_THRESHOLD = 1000.0

WATCHLIST_FIELDS = [
    "unified_app_id",
    "game_title",
    "publisher",
    "platform",
    "sg_release_date",
    "release_report_start",
    "release_report_end",
    "watch_until_meeting_date",
    "status",
    "first_top_grossing_seen_date",
    "watch_periods_seen",
    "ios_app_ids",
    "android_app_ids",
    "reported_date",
    "notes",
]

FINAL_FIELDS = [
    "Signal Type",
    "Signal Definition",
    "SG Gross Revenue",
    "Inclusion Reason",
    "Game Title",
    "English Display Title",
    "Original Title",
    "Detected Language",
    "Machine English Title",
    "Manual English Title",
    "Translation Source",
    "Translation Confidence",
    "Translation Review Status",
    "Translation Note",
    "Platform",
    "Publisher",
    "Release Date",
    "Genre",
    "Top 3 Markets",
    "SG App Store Ranks",
    "unified_app_id",
    "run_timestamp_utc",
    "report_start_date",
    "report_end_date",
    "ranking_date",
    "sensor_tower_effective_end_date",
]

AUDIT_FIELDS = [
    "unified_app_id",
    "game_title",
    "release_date",
    "has_top_free",
    "has_top_grossing",
    "sg_gross_revenue_dollars",
    "decision",
    "reason",
    "signal_type",
]


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def run_title_normalisation():
    if not LAYER3_CSV.exists():
        raise SystemExit(f"Missing Layer 3 metadata before title normalisation: {LAYER3_CSV}")
    result = subprocess.run(
        [sys.executable, str(LAYER3_5_SCRIPT)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=180,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "Layer 3.5 title normalisation failed."
        raise SystemExit(message)
    if result.stdout.strip():
        print(result.stdout.strip())

def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def nice_date(value):
    parsed = parse_date(value)
    return parsed.strftime("%d-%b-%Y") if parsed else (value or "")


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def money(value):
    return "$" + format(round(safe_float(value)), ",")


def downloads(value):
    return format(safe_int(value), ",") + " DL"


def rank_text(value):
    rank = safe_int(value)
    return f"#{rank}" if rank else "#NA"


def parse_chart_matches(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def min_rank(existing, incoming):
    incoming_int = safe_int(incoming)
    if incoming_int == 0:
        return existing
    if existing in (None, 0):
        return incoming_int
    return min(existing, incoming_int)


def build_chart_lookup(layer2_rows):
    lookup = defaultdict(lambda: {
        "has_top_free": False,
        "has_top_grossing": False,
        "ios_dl_rank": None,
        "ios_rev_rank": None,
        "android_dl_rank": None,
        "android_rev_rank": None,
        "first_top_grossing_seen_date": "",
    })

    for row in layer2_rows:
        uid = row.get("unified_app_id", "")
        platform = row.get("platform", "")
        ranking_date = row.get("ranking_date", "")
        if not uid:
            continue
        for chart in parse_chart_matches(row.get("chart_match_details_json")):
            chart_type = chart.get("chart_type")
            rank = chart.get("rank")
            if chart_type in (IOS_DL_CHART, ANDROID_DL_CHART):
                lookup[uid]["has_top_free"] = True
            if chart_type in (IOS_REV_CHART, ANDROID_REV_CHART):
                lookup[uid]["has_top_grossing"] = True
                if not lookup[uid]["first_top_grossing_seen_date"]:
                    lookup[uid]["first_top_grossing_seen_date"] = ranking_date
            if platform == "ios" and chart_type == IOS_DL_CHART:
                lookup[uid]["ios_dl_rank"] = min_rank(lookup[uid]["ios_dl_rank"], rank)
            elif platform == "ios" and chart_type == IOS_REV_CHART:
                lookup[uid]["ios_rev_rank"] = min_rank(lookup[uid]["ios_rev_rank"], rank)
            elif platform == "android" and chart_type == ANDROID_DL_CHART:
                lookup[uid]["android_dl_rank"] = min_rank(lookup[uid]["android_dl_rank"], rank)
            elif platform == "android" and chart_type == ANDROID_REV_CHART:
                lookup[uid]["android_rev_rank"] = min_rank(lookup[uid]["android_rev_rank"], rank)
    return lookup


def build_country_lookup(country_rows):
    lookup = defaultdict(list)
    for row in country_rows:
        lookup[row.get("unified_app_id", "")].append(row)
    return lookup


def sg_gross_revenue(country_rows):
    return sum(safe_float(row.get("gross_revenue_dollars")) for row in country_rows if row.get("country") == "SG")


def format_top_markets(country_rows):
    if not country_rows:
        return "Top Mkts: No SEA6 revenue/download data"
    sorted_rows = sorted(country_rows, key=lambda row: safe_float(row.get("gross_revenue_dollars")), reverse=True)
    selected = sorted_rows[:3]
    if "SG" not in {row.get("country") for row in selected}:
        sg = next((row for row in sorted_rows if row.get("country") == "SG"), None)
        if sg:
            selected.append(sg)
    parts = [f"{row.get('country')} ({money(row.get('gross_revenue_dollars'))} / {downloads(row.get('total_downloads'))})" for row in selected]
    return "Top Mkts: " + " || ".join(parts)


def format_sg_ranks(chart):
    return (
        f"SG App Store Ranks: iOS (DL {rank_text(chart.get('ios_dl_rank'))} / Rev {rank_text(chart.get('ios_rev_rank'))}) "
        f"|| Android (DL {rank_text(chart.get('android_dl_rank'))} / Rev {rank_text(chart.get('android_rev_rank'))})"
    )


def platform_label(row):
    has_ios = bool(row.get("ios_app_ids", "").strip())
    has_android = bool(row.get("android_app_ids", "").strip())
    if has_ios and has_android:
        return "iOS / Android"
    if has_ios:
        return "iOS"
    if has_android:
        return "Android"
    return row.get("platforms_seen_in_layer1", "")


def release_value(row):
    return row.get("country_release_date") or row.get("release_date") or ""


def title_value(game, key, fallback=""):
    return game.get(key, "") or fallback

def display_title(game):
    return title_value(game, "display_title", game.get("unified_app_name", ""))

def final_row(game, chart, countries, config, run_timestamp, signal_type, inclusion_reason):
    definition = (
        "Clear SG commercial traction: SG gross revenue exceeded $1,000 during the release/report period."
        if signal_type == "Strong Market Signal"
        else "SG Top Grossing watchlist item: commercial relevance is below the Strong threshold."
    )
    return {
        "Signal Type": signal_type,
        "Signal Definition": definition,
        "SG Gross Revenue": round(sg_gross_revenue(countries), 2),
        "Inclusion Reason": inclusion_reason,
        "Game Title": display_title(game),
        "English Display Title": display_title(game),
        "Original Title": title_value(game, "original_title", game.get("unified_app_name", "")),
        "Detected Language": game.get("detected_language", ""),
        "Machine English Title": game.get("machine_english_title", ""),
        "Manual English Title": game.get("manual_english_title", ""),
        "Translation Source": game.get("translation_source", ""),
        "Translation Confidence": game.get("translation_confidence", ""),
        "Translation Review Status": game.get("translation_review_status", ""),
        "Translation Note": game.get("translation_note", ""),
        "Platform": platform_label(game),
        "Publisher": game.get("publisher_name", ""),
        "Release Date": nice_date(release_value(game)),
        "Genre": game.get("genre", ""),
        "Top 3 Markets": format_top_markets(countries),
        "SG App Store Ranks": format_sg_ranks(chart),
        "unified_app_id": game.get("unified_app_id", ""),
        "run_timestamp_utc": run_timestamp,
        "report_start_date": nice_date(config.get("report_start_date")),
        "report_end_date": nice_date(config.get("report_end_date")),
        "ranking_date": nice_date(config.get("ranking_date")),
        "sensor_tower_effective_end_date": nice_date(config.get("ranking_date")),
    }


def watch_until_meeting(report_end):
    meeting = report_end + timedelta(days=1)
    return (meeting + timedelta(days=14 * WATCH_PERIODS_AFTER_RELEASE)).isoformat()


def make_watchlist_row(game, config, reason, chart):
    report_end = parse_date(config.get("report_end_date"))
    return {
        "unified_app_id": game.get("unified_app_id", ""),
        "game_title": display_title(game),
        "publisher": game.get("publisher_name", ""),
        "platform": platform_label(game),
        "sg_release_date": nice_date(release_value(game)),
        "release_report_start": nice_date(config.get("report_start_date")),
        "release_report_end": nice_date(config.get("report_end_date")),
        "watch_until_meeting_date": watch_until_meeting(report_end),
        "status": "Watching",
        "first_top_grossing_seen_date": chart.get("first_top_grossing_seen_date", ""),
        "watch_periods_seen": "1",
        "ios_app_ids": game.get("ios_app_ids", ""),
        "android_app_ids": game.get("android_app_ids", ""),
        "reported_date": "",
        "notes": reason,
    }


def merge_watchlist(existing_rows, new_rows, reported_ids, expired_ids, seen_ids):
    by_id = {row.get("unified_app_id", ""): row for row in existing_rows if row.get("unified_app_id")}
    for uid in reported_ids:
        if uid in by_id:
            by_id[uid]["status"] = "Reported"
            by_id[uid]["reported_date"] = datetime.now().date().isoformat()
            by_id[uid]["notes"] = "Moved to final report after SG gross revenue exceeded the Strong threshold."
    for uid in expired_ids:
        if uid in by_id and by_id[uid].get("status") == "Watching":
            by_id[uid]["status"] = "Expired"
            by_id[uid]["notes"] = "Watch window ended without exceeding the SG gross revenue Strong threshold."
    for row in new_rows:
        uid = row.get("unified_app_id", "")
        if uid not in by_id:
            by_id[uid] = row
        elif by_id[uid].get("status") == "Watching":
            prior_seen = safe_int(by_id[uid].get("watch_periods_seen")) or 1
            if uid in seen_ids:
                by_id[uid]["watch_periods_seen"] = str(min(WATCH_PERIODS_AFTER_RELEASE, prior_seen + 1))
            by_id[uid]["notes"] = row.get("notes", by_id[uid].get("notes", ""))
            by_id[uid]["ios_app_ids"] = row.get("ios_app_ids") or by_id[uid].get("ios_app_ids", "")
            by_id[uid]["android_app_ids"] = row.get("android_app_ids") or by_id[uid].get("android_app_ids", "")
    return sorted(by_id.values(), key=lambda row: (row.get("status", ""), row.get("game_title", "")))


def main():
    config = load_config()
    start = parse_date(config.get("report_start_date"))
    end = parse_date(config.get("report_end_date"))
    if not start or not end:
        raise SystemExit("Missing report_start_date or report_end_date in config/settings.json")

    run_title_normalisation()

    layer2_source = REPORT_PERIOD_LAYER2_CSV if REPORT_PERIOD_LAYER2_CSV.exists() else LAYER2_CSV
    layer3_source = REPORT_PERIOD_CANDIDATES_CSV if REPORT_PERIOD_CANDIDATES_CSV.exists() else (LAYER3_5_CSV if LAYER3_5_CSV.exists() else LAYER3_CSV)
    layer2 = read_csv(layer2_source)
    layer3 = read_csv(layer3_source)
    countries_by_game = build_country_lookup(read_csv(LAYER4_COUNTRY_CSV))
    charts = build_chart_lookup(layer2)
    existing_watchlist = read_csv(WATCHLIST_CSV)
    game_by_id = {row.get("unified_app_id", ""): row for row in layer3}

    run_timestamp = datetime.now(timezone.utc).isoformat()
    final_rows = []
    new_watchlist_rows = []
    audit_rows = []
    reported_ids = set()
    expired_ids = set()

    # Meeting-date report logic:
    #   - Do not rediscover releases from the current Released Days Ago bucket.
    #   - Use the stored weekly candidate pool captured during the report period.
    #   - Refresh performance stats/ranks for those stored candidates.
    #
    # Top Free/Grossing ranks are recorded for display. Missing ranks do not
    # exclude a stored candidate. Sensor Tower SG release date is evidence only.
    for game in layer3:
        uid = game.get("unified_app_id", "")
        if not uid:
            continue
        chart = charts[uid]
        country_rows = countries_by_game.get(uid, [])
        sg_rev = sg_gross_revenue(country_rows)
        if sg_rev > STRONG_SG_GROSS_REVENUE_THRESHOLD:
            final_rows.append(final_row(game, chart, country_rows, config, run_timestamp, "Strong Market Signal", "Stored weekly candidate with SG gross revenue > $1,000 during the report period"))
            reported_ids.add(uid)
            decision = "Final Report"
            reason = "Stored weekly candidate with SG gross revenue > $1,000 during the report period."
        elif sg_rev > 0:
            reason = "Stored weekly candidate with SG gross revenue > $0 but at or below the $1,000 Strong threshold."
            final_rows.append(final_row(game, chart, country_rows, config, run_timestamp, "Watchlist", reason))
            new_watchlist_rows.append(make_watchlist_row(game, config, reason, chart))
            decision = "Market Brief Watchlist"
        else:
            reason = "Stored weekly candidate, but SG gross revenue is $0 or unavailable during the report period."
            decision = "Excluded"
        audit_rows.append({
            "unified_app_id": uid,
            "game_title": display_title(game),
            "release_date": nice_date(release_value(game)),
            "has_top_free": chart["has_top_free"],
            "has_top_grossing": chart["has_top_grossing"],
            "sg_gross_revenue_dollars": round(sg_rev, 2),
            "decision": decision,
            "reason": reason,
            "signal_type": "Strong Market Signal" if sg_rev > STRONG_SG_GROSS_REVENUE_THRESHOLD else ("Watchlist" if sg_rev > 0 else "Excluded"),
        })

    current_seen_ids = {row.get("unified_app_id", "") for row in new_watchlist_rows if row.get("unified_app_id")}
    merged_watchlist = merge_watchlist(existing_watchlist, new_watchlist_rows, reported_ids, expired_ids, current_seen_ids)
    signal_order = {"Strong Market Signal": 0, "Watchlist": 1}
    final_rows = sorted(final_rows, key=lambda row: (signal_order.get(row.get("Signal Type", ""), 9), -safe_float(row.get("SG Gross Revenue")), row.get("Game Title", "")))

    write_csv(OUTPUT_DIR / "final_sg_market_scan_current_workflow.csv", final_rows, FINAL_FIELDS)
    write_csv(OUTPUT_DIR / "current_workflow_decisions.csv", audit_rows, AUDIT_FIELDS)
    write_csv(WATCHLIST_CSV, merged_watchlist, WATCHLIST_FIELDS)

    print(f"Current workflow complete.")
    print(f"Final report rows: {len(final_rows)}")
    print(f"New watchlist candidates: {len(new_watchlist_rows)}")
    print(f"Reported from watchlist/current: {len(reported_ids)}")
    print(f"Expired watchlist items: {len(expired_ids)}")
    print(f"Final CSV: {OUTPUT_DIR / 'final_sg_market_scan_current_workflow.csv'}")
    print(f"Watchlist CSV: {WATCHLIST_CSV}")
    print(f"Audit CSV: {OUTPUT_DIR / 'current_workflow_decisions.csv'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Current workflow failed: {exc}", file=sys.stderr)
        raise SystemExit(1)











