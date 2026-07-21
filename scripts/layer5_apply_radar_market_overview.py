import csv
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "output"
FINAL_CSV = OUTPUT_DIR / "final_sg_market_scan_current_workflow.csv"
JUDGEMENT_CSV = OUTPUT_DIR / "layer5_market_overview_judgement.csv"
RADAR_URL = "https://raw.githubusercontent.com/DarylWong-PlayPark/ai-news-radar/game-data/data/game-news.json"

STRONG_SG_REVENUE_THRESHOLD = 1000.0

ADDED_FIELDS = [
    "Market Overview Status",
    "Market Overview Reason",
    "Radar Status",
    "Radar Match Quality",
    "Radar Score",
    "Radar Matched Title",
    "Radar Source",
    "Radar URL",
    "Radar Checked At UTC",
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


def safe_float(value):
    try:
        return float(str(value or "0").replace(",", "").replace("$", ""))
    except ValueError:
        return 0.0


def normalize_title(value):
    text = str(value or "").lower()
    text = re.sub(r"[™®©:：!！?？,，.。\\\-–—_()\[\]{}]", " ", text)
    text = re.sub(r"\b(mobile|global|sea|sg|android|ios|game|games)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def radar_score(item):
    score = 0.0
    content_type = str(item.get("content_type") or "").lower()
    if content_type == "launch":
        score += 0.7
    elif content_type in ("business", "monetization"):
        score += 0.45
    elif content_type in ("update", "event", "esports"):
        score += 0.25

    source = str(item.get("site_id") or item.get("source") or "").lower()
    if any(
        key in source
        for key in (
            "pocket",
            "siliconera",
            "polygon",
            "pcgamer",
            "gamerant",
            "gamesradar",
            "gaming",
        )
    ):
        score += 0.4

    title = str(item.get("title_en") or item.get("title") or "").lower()
    if any(key in title for key in ("launch", "released", "pre-register", "opens", "available", "debut")):
        score += 0.4
    if any(key in title for key in ("revenue", "gross", "top grossing", "download", "million", "record")):
        score += 0.4
    return round(score, 2)


def fetch_radar_items():
    with urllib.request.urlopen(RADAR_URL, timeout=30) as response:
        data = response.read().decode("utf-8-sig")
    payload = json.loads(data)
    if isinstance(payload, dict):
        return payload.get("items") or payload.get("data") or []
    return payload


def build_radar_index(items):
    indexed = []
    for item in items:
        title = item.get("title_en") or item.get("title") or ""
        normalized = normalize_title(title)
        if normalized:
            indexed.append((normalized, item, radar_score(item)))
    return indexed


def best_phrase_match(game_title, radar_index):
    normalized_game = normalize_title(game_title)
    if len(normalized_game) < 5:
        return None

    matches = []
    for normalized_radar, item, score in radar_index:
        if normalized_game in normalized_radar or normalized_radar in normalized_game:
            matches.append((score, item))

    if not matches:
        return None
    matches.sort(key=lambda pair: pair[0], reverse=True)
    return matches[0]


def classify_row(row, radar_index, checked_at):
    title = row.get("Game Title") or row.get("English Display Title") or ""
    sg_revenue = safe_float(row.get("SG Gross Revenue"))
    match = best_phrase_match(title, radar_index)

    radar_status = "No exact Radar match"
    radar_quality = "none"
    radar_score_value = ""
    radar_title = ""
    radar_source = ""
    radar_url = ""

    if match:
        radar_score_value, item = match
        radar_quality = "exact_or_phrase_title_match"
        radar_status = "Radar supported" if radar_score_value >= 0.7 else "Weak Radar support"
        radar_title = item.get("title_en") or item.get("title") or ""
        radar_source = item.get("source") or item.get("site_name") or item.get("site_id") or ""
        radar_url = item.get("url", "")

    if row.get("Signal Type") == "Strong Market Signal" or sg_revenue > STRONG_SG_REVENUE_THRESHOLD:
        overview_status = "Include in Market Overview"
        overview_reason = "Strong SG revenue threshold met"
    elif match and radar_score_value >= 0.7:
        overview_status = "Needs Analyst Review"
        overview_reason = "Emerging title has exact Game News Radar support"
    elif sg_revenue > 0:
        overview_status = "Needs Analyst Review"
        overview_reason = "Has some SG revenue but below Strong threshold"
    else:
        overview_status = "Filter from Market Overview"
        overview_reason = "No SG revenue above threshold and no exact Game News Radar support"

    row.update(
        {
            "Market Overview Status": overview_status,
            "Market Overview Reason": overview_reason,
            "Radar Status": radar_status,
            "Radar Match Quality": radar_quality,
            "Radar Score": radar_score_value,
            "Radar Matched Title": radar_title,
            "Radar Source": radar_source,
            "Radar URL": radar_url,
            "Radar Checked At UTC": checked_at,
        }
    )
    return row


def main():
    rows = read_csv(FINAL_CSV)
    if not rows:
        raise SystemExit(f"No final report rows found at {FINAL_CSV}")

    checked_at = datetime.now(timezone.utc).isoformat()
    radar_items = fetch_radar_items()
    radar_index = build_radar_index(radar_items)
    updated = [classify_row(dict(row), radar_index, checked_at) for row in rows]

    base_fields = list(rows[0].keys())
    fields = base_fields + [field for field in ADDED_FIELDS if field not in base_fields]
    write_csv(FINAL_CSV, updated, fields)
    write_csv(JUDGEMENT_CSV, updated, fields)

    counts = {}
    for row in updated:
        counts[row["Market Overview Status"]] = counts.get(row["Market Overview Status"], 0) + 1

    print(f"Radar judgement complete using {len(radar_items)} Radar items.")
    print(f"Updated: {FINAL_CSV}")
    print(f"Judgement layer: {JUDGEMENT_CSV}")
    print(counts)


if __name__ == "__main__":
    main()
