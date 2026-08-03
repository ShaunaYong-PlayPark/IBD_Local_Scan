import argparse
import csv
import json
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

import resolve_static_automation as schedule_resolver


ROOT = Path(__file__).resolve().parents[1]
RADAR_URL = "https://raw.githubusercontent.com/DarylWong-PlayPark/ai-news-radar/game-data/data/game-news.json"
OUTPUT_CSV = ROOT / "data" / "input" / "radar_sg_manual_check_candidates.csv"
KNOWN_EXISTING_CSV = ROOT / "data" / "reference" / "known_existing_games.csv"
SCHEDULE_PATH = ROOT / "config" / "static_report_schedule.json"

CSV_FIELDS = [
    "radar_generated_at",
    "radar_retention_days",
    "report_start_date",
    "report_end_date",
    "radar_event_date",
    "candidate_region",
    "region_label",
    "region_priority",
    "source",
    "site_id",
    "site_name",
    "source_dedicated",
    "ingestion_path",
    "published_at",
    "first_seen_at",
    "last_seen_at",
    "content_type",
    "title",
    "title_en",
    "candidate_game_name",
    "launch_signal_reason",
    "confidence",
    "url",
    "known_existing_match",
    "duplicate_reason",
    "manual_sg_sensor_tower_status",
    "manual_sg_sensor_tower_notes",
]

REGION_PRIORITY = {
    "SG": 1,
    "MY": 2,
    "ID": 3,
    "TH": 4,
    "PH": 5,
    "VN": 6,
    "TW": 7,
    "CN": 8,
    "GLOBAL": 9,
    "OTHERS": 10,
}

LAUNCH_TERMS = [
    "global launch",
    "sea launch",
    "taiwan launch",
    "soft launch",
    "early access",
    "open beta",
    "closed beta",
    "out now",
    "now available",
    "pre-registration",
    "pre-register",
    "preregistration",
    "launching",
    "launched",
    "launch",
    "releases",
    "released",
    "release",
    "available",
    "opens",
    "cbt",
    "obt",
]

EXCLUDE_PATTERNS = [
    (r"\besports?\b|\be-sports?\b|\bpro league\b|\bchampionship\b", "esports-only"),
    (r"\bpatch\b|\bhotfix\b|\bversion\s+\d|\bupdate\b", "patch/update-only"),
    (r"\bmaintenance\b|\bserver maintenance\b", "maintenance"),
    (r"\bshutdown\b|\bshut down\b|\bend of service\b|\beos\b", "shutdown"),
    (r"\blayoffs?\b|\bjob cuts?\b|\brestructur", "layoffs"),
    (r"\blawsuit\b|\blegal\b|\bcourt\b|\bsettlement\b", "legal"),
    (r"\brevenue\b|\bgrossing\b|\bearnings\b|\bmillion\b", "revenue-only"),
    (r"\btournament\b|\bqualifier\b|\bfinals\b", "tournament-only"),
    (r"\bcosplay\b|\bcosplayer\b", "cosplay"),
    (r"\banime\b|\bmanga\b|\bepisode\b|\bmovie\b|\btrailer\b", "anime-only"),
    (r"\bhardware\b|\bconsole\b|\bgpu\b|\bmonitor\b|\bheadset\b|\bearbuds?\b|\bbuds\b|\bgaming chair\b|\bdrivers?\b|\bsteam machine\b|\bswitch 2\b", "hardware-only"),
    (r"\bwordle\b|\bquordle\b|\bconnections\b|\bstrands\b|\bhints?\b|\banswers?\b", "daily puzzle hints"),
]

HK_KR_PATTERN = re.compile(
    r"\b(HK|Hong Kong|Korea|Korean|KR)\b|香港|韓國|韩国|한국",
    re.IGNORECASE,
)

QUOTE_PATTERNS = [
    r'"([^"]{2,90})"',
    r"'([^']{2,90})'",
    r"《([^》]{2,90})》",
    r"「([^」]{2,90})」",
    r"“([^”]{2,90})”",
]


def normalize_text(value):
    text = str(value or "").lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_cli_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def read_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def report_period(schedule, mode="meeting-day-final-report", today=None):
    start, end, _ranking = schedule_resolver.report_dates(schedule, mode, today)
    return start, end


def radar_event_date(item):
    for field in ("published_at", "last_seen_at", "first_seen_at"):
        parsed = parse_date(item.get(field))
        if parsed:
            return parsed
    return None


def fetch_radar_payload(url=RADAR_URL):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def radar_items(payload):
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return items if isinstance(items, list) else []


def read_known_existing_titles(path=KNOWN_EXISTING_CSV):
    if not path.exists():
        return {}
    titles = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            for field in ("unified_name", "app_name"):
                raw = row.get(field, "")
                normalized = normalize_text(raw)
                if normalized:
                    titles.setdefault(normalized, raw)
    return titles


def combined_title(item):
    return " ".join(
        str(item.get(field) or "")
        for field in ("title_en", "title")
    ).strip()


def launch_terms_in(text):
    normalized = normalize_text(text)
    found = []
    for term in LAUNCH_TERMS:
        pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            found.append(term)
    return found


def exclusion_reason(text):
    normalized = normalize_text(text)
    for pattern, reason in EXCLUDE_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return reason
    return ""


def extract_candidate_game_name(item):
    text = str(item.get("title_en") or item.get("title") or "").strip()
    if not text:
        return ""

    for pattern in QUOTE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            candidate = clean_candidate_name(match.group(1))
            if candidate:
                return candidate

    prefix_patterns = [
        r"^(.{2,90}?)\s+(?:global\s+launch|sea\s+launch|taiwan\s+launch|soft\s+launch|launches|launching|launched|launch|releases|released|release|is\s+out\s+now|now\s+available|opens?\s+(?:pre[- ]?registration|registration|early access|beta))\b",
        r"^(.{2,90}?):\s+",
        r"^(.{2,90}?)\s+-\s+",
    ]
    for pattern in prefix_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = clean_candidate_name(match.group(1))
            if candidate:
                return candidate
    return ""


def clean_candidate_name(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -:|.,!?()[]{}")
    if not text:
        return ""
    if len(text) > 80:
        return ""
    lowered = text.lower()
    bad_starts = ("new ", "this ", "the ", "how ", "why ", "top ", "best ", "a year since ")
    if lowered.startswith(bad_starts):
        return ""
    if lowered in {"game", "games", "mobile game", "new game"}:
        return ""
    return text


def known_existing_match(row, known_titles):
    checks = [
        normalize_text(row.get("candidate_game_name")),
        normalize_text(row.get("title_en")),
        normalize_text(row.get("title")),
    ]
    for key in checks:
        if key and key in known_titles:
            return known_titles[key]
    return ""


def classify_confidence(content_type, terms, candidate_name, hk_kr_mentioned):
    if content_type == "launch" and terms and candidate_name:
        confidence = "high"
    elif terms or (content_type == "launch" and candidate_name):
        confidence = "medium"
    else:
        confidence = "low"
    if hk_kr_mentioned and confidence == "high":
        return "medium"
    return confidence


def candidate_from_item(item, payload, known_titles, report_start=None, report_end=None):
    event_date = radar_event_date(item)
    if report_start and report_end:
        if not event_date or event_date < report_start or event_date > report_end:
            return None

    region = str(item.get("region") or "").upper()
    if region == "MISC" or region not in REGION_PRIORITY:
        return None

    text = combined_title(item)
    content_type = str(item.get("content_type") or "").lower()
    terms = launch_terms_in(text)
    is_launch = content_type == "launch"
    if not is_launch and not terms:
        return None
    if region == "OTHERS" and not terms:
        return None

    excluded = exclusion_reason(text)
    if excluded:
        return None

    candidate_name = extract_candidate_game_name(item)
    hk_kr_mentioned = bool(HK_KR_PATTERN.search(text))
    reasons = []
    if is_launch:
        reasons.append("content_type=launch")
    if terms:
        reasons.append("launch_terms=" + "|".join(terms))
    if hk_kr_mentioned:
        reasons.append("HK/KR inferable from title only; not first-class radar region")

    row = {
        "radar_generated_at": payload.get("generated_at", ""),
        "radar_retention_days": payload.get("retention_days", ""),
        "report_start_date": report_start.isoformat() if report_start else "",
        "report_end_date": report_end.isoformat() if report_end else "",
        "radar_event_date": event_date.isoformat() if event_date else "",
        "candidate_region": region,
        "region_label": item.get("region_label", ""),
        "region_priority": REGION_PRIORITY[region],
        "source": item.get("source", ""),
        "site_id": item.get("site_id", ""),
        "site_name": item.get("site_name", ""),
        "source_dedicated": item.get("source_dedicated", ""),
        "ingestion_path": item.get("ingestion_path", ""),
        "published_at": item.get("published_at", ""),
        "first_seen_at": item.get("first_seen_at", ""),
        "last_seen_at": item.get("last_seen_at", ""),
        "content_type": content_type,
        "title": item.get("title", ""),
        "title_en": item.get("title_en", ""),
        "candidate_game_name": candidate_name,
        "launch_signal_reason": "; ".join(reasons),
        "confidence": classify_confidence(content_type, terms, candidate_name, hk_kr_mentioned),
        "url": item.get("url", ""),
        "known_existing_match": "",
        "duplicate_reason": "",
        "manual_sg_sensor_tower_status": "",
        "manual_sg_sensor_tower_notes": "",
    }
    row["known_existing_match"] = known_existing_match(row, known_titles)
    return row


def sort_key(row):
    parsed = parse_date(row.get("published_at")) or date.min
    return (
        int(row.get("region_priority") or 999),
        -parsed.toordinal(),
        str(row.get("candidate_game_name") or row.get("title_en") or row.get("title")),
    )


def dedupe_rows(rows):
    kept = []
    by_url = set()
    by_title = set()
    close_groups = {}

    for row in sorted(rows, key=sort_key):
        url = str(row.get("url") or "").strip()
        if url and url in by_url:
            continue
        if url:
            by_url.add(url)

        title_key = normalize_text(row.get("title_en") or row.get("title"))
        if title_key and title_key in by_title:
            continue
        if title_key:
            by_title.add(title_key)

        candidate_key = normalize_text(row.get("candidate_game_name"))
        row_date = parse_date(row.get("published_at"))
        if candidate_key and row_date:
            group_key = (candidate_key, row.get("candidate_region", ""))
            existing_index = close_groups.get(group_key)
            if existing_index is not None:
                existing = kept[existing_index]
                existing_date = parse_date(existing.get("published_at"))
                if existing_date and abs((row_date - existing_date).days) <= 3:
                    existing["duplicate_reason"] = "merged_same_candidate_region_close_date"
                    continue
            close_groups[group_key] = len(kept)

        kept.append(row)
    return kept


def apply_global_cap(rows, cap=50):
    capped = []
    global_count = 0
    for row in rows:
        if row.get("candidate_region") == "GLOBAL":
            if global_count >= cap:
                continue
            global_count += 1
        capped.append(row)
    return capped


def build_candidates(payload, known_titles, report_start=None, report_end=None):
    rows = []
    for item in radar_items(payload):
        row = candidate_from_item(item, payload, known_titles, report_start, report_end)
        if row:
            rows.append(row)
    rows = dedupe_rows(rows)
    rows = sorted(rows, key=sort_key)
    return apply_global_cap(rows)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def by_region_counts(rows):
    counts = {}
    for row in rows:
        region = row.get("candidate_region") or ""
        counts[region] = counts.get(region, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: REGION_PRIORITY.get(pair[0], 999)))


def main():
    parser = argparse.ArgumentParser(
        description="Export public Game News Radar items for manual SG Sensor Tower checks."
    )
    parser.add_argument(
        "--mode",
        choices=("meeting-day-final-report", "weekly-capture"),
        default="meeting-day-final-report",
    )
    parser.add_argument("--today", help="Override today's date for schedule resolution, YYYY-MM-DD.")
    args = parser.parse_args()

    schedule = read_json(SCHEDULE_PATH)
    report_start, report_end = report_period(
        schedule,
        mode=args.mode,
        today=parse_cli_date(args.today),
    )
    payload = fetch_radar_payload()
    known_titles = read_known_existing_titles()
    rows = build_candidates(payload, known_titles, report_start, report_end)
    write_csv(OUTPUT_CSV, rows)

    known_count = sum(1 for row in rows if row.get("known_existing_match"))
    print(f"Report period: {report_start.isoformat()} to {report_end.isoformat()}")
    print(f"Input item count: {len(radar_items(payload))}")
    print(f"Kept candidate count: {len(rows)}")
    print(f"By-region counts: {by_region_counts(rows)}")
    print(f"Known-existing match count: {known_count}")
    print(f"Output path: {OUTPUT_CSV}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Radar manual-check candidate export failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
