import argparse
import csv
import json
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

import build_pc_steamdb_discovery_candidates as pc


ROOT = Path(__file__).resolve().parents[1]
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"
DEFAULT_GAME_RADAR_JSON = (
    ROOT.parent / "IBD_Game_News_Radar" / "data" / "game-news.json"
)
PUBLIC_GAME_RADAR_URL = (
    "https://raw.githubusercontent.com/ShaunaYong-PlayPark/ai-news-radar/"
    "game-data/data/game-news.json"
)

DEFAULT_ANNOUNCEMENT_MIN_SCORE = 70
DEFAULT_INDUSTRY_MIN_SCORE = 70
DEFAULT_INDUSTRY_MAX_ROWS = 3

SECTION_GAME_RELEASES = "game_releases"
SECTION_GAME_ANNOUNCEMENTS = "game_announcements"
SECTION_INDUSTRY_REPORTS = "industry_reports"

CSV_FIELDS = [
    "meeting_date",
    "report_start_date",
    "report_end_date",
    "context_type",
    "radar_section",
    "matched_report_game",
    "match_method",
    "event_date",
    "hot_score",
    "hot_reasons",
    "source",
    "source_tier",
    "source_tier_label",
    "region",
    "title",
    "title_en",
    "url",
    "published_at",
    "first_seen_at",
    "last_seen_at",
    "radar_generated_at",
    "inclusion_reason",
    "story_key",
]


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields=CSV_FIELDS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def game_report_layer_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "game_report_layer.csv"


def output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "news_context_layer.csv"


def normalize_title(value):
    return pc.normalize_title(value)


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_report_period_value(value):
    text = str(value or "").strip()
    if " to " not in text:
        return None
    start_raw, end_raw = text.split(" to ", 1)
    start = parse_date(start_raw.strip())
    end = parse_date(end_raw.strip())
    if start and end:
        return start, end
    return None


def infer_report_period(game_rows):
    periods = []
    for row in game_rows:
        start = parse_date(row.get("report_start_date"))
        end = parse_date(row.get("report_end_date"))
        if start and end:
            periods.append((start, end))
            continue
        for field in ("mobile_source_period", "pc_source_period"):
            parsed = parse_report_period_value(row.get(field))
            if parsed:
                periods.append(parsed)
                break
    if not periods:
        return None, None
    return min(start for start, _end in periods), max(end for _start, end in periods)


def item_event_date(item):
    for field in ("published_at", "last_seen_at", "first_seen_at"):
        parsed = parse_date(item.get(field))
        if parsed:
            return parsed
    return None


def in_report_period(item, start, end):
    event_date = item_event_date(item)
    if not event_date or not start or not end:
        return False
    return start <= event_date <= end


def report_game_name(row):
    return (
        row.get("english_report_name")
        or row.get("unified_name")
        or row.get("pc_title")
        or ""
    ).strip()


def selected_game_keys(game_rows):
    rows = []
    for row in game_rows:
        display = report_game_name(row)
        raw_names = [
            display,
            row.get("english_report_name", ""),
            row.get("unified_name", ""),
            row.get("pc_title", ""),
        ]
        keys = []
        for raw in raw_names:
            key = normalize_title(raw)
            if key and key not in keys:
                keys.append(key)
        if display and keys:
            rows.append({"display": display, "keys": keys})
    return rows


def item_text(item):
    return " ".join(
        str(item.get(field) or "")
        for field in ("title_en", "title")
    )


def match_selected_game(item, selected_games):
    text_key = normalize_title(item_text(item))
    if not text_key:
        return "", ""
    for game in selected_games:
        for key in game["keys"]:
            if not key:
                continue
            if key == text_key:
                return game["display"], "exact_title"
            if len(key) >= 5 and key in text_key:
                return game["display"], "selected_game_name_in_article_title"
            if len(text_key) >= 5 and text_key in key:
                return game["display"], "article_title_in_selected_game_name"
    return "", ""


def load_radar_payload(source):
    source_text = str(source)
    if source_text.startswith(("http://", "https://")):
        request = urllib.request.Request(source_text, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8-sig"))
    path = Path(source)
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def radar_candidates(payload):
    hot = payload.get("hot_news", []) if isinstance(payload, dict) else []
    return hot if isinstance(hot, list) else []


def hot_score(item):
    try:
        return int(float(item.get("hot_score") or 0))
    except (TypeError, ValueError):
        return 0


def story_key(item):
    text = normalize_title(item_text(item))
    if not text:
        return normalize_title(item.get("url", ""))
    theme_keywords = [
        (
            "physical_media_shift",
            [
                "physical",
                "disc",
                "discs",
                "digital only",
                "digital sales",
                "digital playstation sales",
                "digital pulling",
                "halting physical",
                "download code",
            ],
        ),
        ("xbox_restructure", ["xbox", "layoffs", "revenue plunges", "game pass", "zenimax", "bethesda"]),
        ("steam_market_revenue", ["steam revenue", "steam", "top grossing", "new ip"]),
        ("mobile_iap_ads", ["mobile iap", "iap revenue", "ad spend", "mobile gaming"]),
        ("publisher_financial_results", ["q2 results", "q2 revenue", "revenue rises", "revenue up"]),
        ("publisher_mna", ["acquisition", "merger", "pif", "regulatory"]),
        ("ai_game_tools", ["generative ai", "ai agents", "spatial reasoning", "on device"]),
        ("creator_marketing", ["creators", "viewership", "influencer"]),
        ("funding", ["funding", "raised", "prototype funding"]),
        ("layoffs", ["layoff", "layoffs", "cut workforce", "liquidate"]),
    ]
    for key, keywords in theme_keywords:
        if any(keyword in text for keyword in keywords):
            return key
    words = [word for word in text.split() if len(word) > 3]
    return " ".join(words[:8]) if words else text


def prior_context_keys(meeting_date):
    prior = {"urls": set(), "titles": set(), "stories": set()}
    current = parse_date(meeting_date)
    if not current or not MEETING_PACK_OUTPUT_ROOT.exists():
        return prior
    for folder in MEETING_PACK_OUTPUT_ROOT.iterdir():
        if not folder.is_dir():
            continue
        folder_date = parse_date(folder.name)
        if not folder_date or folder_date >= current:
            continue
        for filename in ("news_context_review.csv", "news_context_layer.csv"):
            path = folder / filename
            if not path.exists():
                continue
            for row in read_csv(path):
                if row.get("url"):
                    prior["urls"].add(row["url"])
                title_key = normalize_title(row.get("title_en") or row.get("title"))
                if title_key:
                    prior["titles"].add(title_key)
                if row.get("story_key"):
                    prior["stories"].add(row["story_key"])
            break
    return prior


def repeated_context(item, prior, key=""):
    url = item.get("url", "")
    title_key = normalize_title(item.get("title_en") or item.get("title"))
    return bool(
        (url and url in prior["urls"])
        or (title_key and title_key in prior["titles"])
        or (key and key in prior["stories"])
    )


def context_row(item, payload, meeting_date, start, end, context_type, matched_game="", match_method="", reason=""):
    event_date = item_event_date(item)
    return {
        "meeting_date": meeting_date,
        "report_start_date": start.isoformat() if start else "",
        "report_end_date": end.isoformat() if end else "",
        "context_type": context_type,
        "radar_section": item.get("radar_section", ""),
        "matched_report_game": matched_game,
        "match_method": match_method,
        "event_date": event_date.isoformat() if event_date else "",
        "hot_score": str(hot_score(item)),
        "hot_reasons": "; ".join(item.get("hot_reasons") or []),
        "source": item.get("source", ""),
        "source_tier": item.get("source_tier", ""),
        "source_tier_label": item.get("source_tier_label", ""),
        "region": item.get("region", ""),
        "title": item.get("title", ""),
        "title_en": item.get("title_en", ""),
        "url": item.get("url", ""),
        "published_at": item.get("published_at", ""),
        "first_seen_at": item.get("first_seen_at", ""),
        "last_seen_at": item.get("last_seen_at", ""),
        "radar_generated_at": payload.get("generated_at", "") if isinstance(payload, dict) else "",
        "inclusion_reason": reason,
        "story_key": story_key(item),
    }


def build_rows(
    game_rows,
    payload,
    meeting_date,
    start,
    end,
    announcement_min_score=DEFAULT_ANNOUNCEMENT_MIN_SCORE,
    industry_min_score=DEFAULT_INDUSTRY_MIN_SCORE,
    industry_max_rows=DEFAULT_INDUSTRY_MAX_ROWS,
):
    selected_games = selected_game_keys(game_rows)
    rows = []
    seen_urls = set()
    seen_stories = set()
    industry_rows = []
    prior = prior_context_keys(meeting_date)

    for item in radar_candidates(payload):
        if not in_report_period(item, start, end):
            continue

        section = item.get("radar_section")
        score = hot_score(item)
        url = item.get("url", "")
        if url and url in seen_urls:
            continue
        key = story_key(item)
        if repeated_context(item, prior, key):
            continue

        if section == SECTION_GAME_RELEASES:
            matched_game, match_method = match_selected_game(item, selected_games)
            if not matched_game:
                continue
            rows.append(
                context_row(
                    item,
                    payload,
                    meeting_date,
                    start,
                    end,
                    "selected_game_release_news",
                    matched_game,
                    match_method,
                    "Game Release article matched to Sensor Tower/SteamDB selected game.",
                )
            )
            if url:
                seen_urls.add(url)
            continue

        if section == SECTION_GAME_ANNOUNCEMENTS and score >= announcement_min_score:
            rows.append(
                context_row(
                    item,
                    payload,
                    meeting_date,
                    start,
                    end,
                    "high_score_game_announcement",
                    "",
                    "",
                    f"Game Announcement hot_score >= {announcement_min_score} and inside report period.",
                )
            )
            if url:
                seen_urls.add(url)
            continue

        if section == SECTION_INDUSTRY_REPORTS and score >= industry_min_score:
            if key and key in seen_stories:
                continue
            industry_rows.append(
                context_row(
                    item,
                    payload,
                    meeting_date,
                    start,
                    end,
                    "industry_trend",
                    "",
                    "industry_story_theme",
                    "Industry trend selected from high-score radar item; repeated story themes from earlier briefs are suppressed.",
                )
            )
            if url:
                seen_urls.add(url)
            if key:
                seen_stories.add(key)

    industry_rows.sort(key=lambda row: (-int(row["hot_score"] or 0), row["event_date"], row["source"]))
    rows.extend(industry_rows[:industry_max_rows])
    rows.sort(
        key=lambda row: (
            row["context_type"] != "industry_trend",
            row["context_type"] != "high_score_game_announcement",
            -int(row["hot_score"] or 0),
            row["event_date"],
            row["source"],
        )
    )
    return rows


def build(meeting_date, radar_source=DEFAULT_GAME_RADAR_JSON, report_start=None, report_end=None, announcement_min_score=DEFAULT_ANNOUNCEMENT_MIN_SCORE):
    game_rows = read_csv(game_report_layer_path(meeting_date))
    inferred_start, inferred_end = infer_report_period(game_rows)
    start = parse_date(report_start) if report_start else inferred_start
    end = parse_date(report_end) if report_end else inferred_end
    if not start or not end:
        raise ValueError("Could not infer report period. Pass --report-start and --report-end.")
    payload = load_radar_payload(radar_source)
    rows = build_rows(game_rows, payload, meeting_date, start, end, announcement_min_score)
    out = output_path(meeting_date)
    write_csv(out, rows)
    return out, rows


def main():
    parser = argparse.ArgumentParser(description="Build IBD news context layer from Game News Radar output.")
    parser.add_argument("--meeting-date", required=True)
    parser.add_argument("--radar-json", default=str(DEFAULT_GAME_RADAR_JSON))
    parser.add_argument("--use-public-radar", action="store_true")
    parser.add_argument("--report-start")
    parser.add_argument("--report-end")
    parser.add_argument("--announcement-min-score", type=int, default=DEFAULT_ANNOUNCEMENT_MIN_SCORE)
    args = parser.parse_args()

    radar_source = PUBLIC_GAME_RADAR_URL if args.use_public_radar else args.radar_json
    path, rows = build(args.meeting_date, radar_source, args.report_start, args.report_end, args.announcement_min_score)
    counts = {}
    for row in rows:
        counts[row["context_type"]] = counts.get(row["context_type"], 0) + 1
    print(f"Meeting date: {args.meeting_date}")
    print(f"News context rows: {len(rows)}")
    for key in ("selected_game_release_news", "high_score_game_announcement"):
        print(f"{key}: {counts.get(key, 0)}")
    print(f"Output path: {path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Game news context layer failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
