import argparse
import csv
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from html import escape


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"
FINALIZED = ROOT / "data" / "finalized_briefs"
LOCAL_APP = ROOT / "data" / "local_app"
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
DATA = DOCS / "data"
STATIC = ROOT / "static"
SCHEDULE = ROOT / "config" / "static_report_schedule.json"
FINAL_CSV = OUT / "final_sg_market_scan_current_workflow.csv"
LATEST_FINALIZED_CSV = FINALIZED / "latest_finalized_brief.csv"
DOCS_FINAL_CSV = DATA / "final_sg_market_scan_current_workflow.csv"
DOCS_FINAL_JSON = DATA / "final-report.json"
DOCS_WEEKLY_STAGING_JSON = DATA / "weekly-staging-summary.json"
METADATA = LOCAL_APP / "extraction_metadata.json"
WEEKLY_SUMMARY = OUT / "weekly_candidate_capture_summary.json"
MEETING_PACK_OUTPUT_ROOT = OUT / "meeting_pack"
NEWS_CONTEXT_FILENAME = "news_context_review.csv"
GAME_REPORT_FILENAME = "game_report_layer.csv"
GAME_ENRICHED_FILENAME = "game_enriched_layer.csv"
PROOF_RUNS = DOCS / "proof-runs"


NAV_ITEMS = [
    ("latest-brief.html", "Latest Brief", "Read the current executive market update.", "latest"),
    ("historical-briefs.html", "Brief Archive", "Open past briefs and review meeting schedule.", "historical"),
    ("game-tracker.html", "Game Tracker", "Filter games mentioned across briefs.", "tracker"),
]


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def csv_period(path):
    rows = read_csv(path)
    if not rows:
        return None, None
    return parse_date(rows[0].get("report_start_date")), parse_date(rows[0].get("report_end_date"))


def period_matches_metadata(path, metadata):
    start, end = csv_period(path)
    expected_start = parse_date(metadata.get("last_successful_sensor_tower_report_start_date"))
    expected_end = parse_date(metadata.get("last_successful_sensor_tower_report_end_date"))
    if not expected_start or not expected_end:
        return False
    return start == expected_start and end == expected_end


def source_finalized_csv(metadata=None):
    metadata = metadata or {}
    manual_start, manual_end = csv_period(LATEST_FINALIZED_CSV)
    output_start, output_end = csv_period(FINAL_CSV)

    if FINAL_CSV.exists() and period_matches_metadata(FINAL_CSV, metadata):
        if not manual_end or (output_end and output_end > manual_end):
            return FINAL_CSV
    if LATEST_FINALIZED_CSV.exists():
        return LATEST_FINALIZED_CSV
    if FINAL_CSV.exists() and period_matches_metadata(FINAL_CSV, metadata):
        return FINAL_CSV
    return DOCS_FINAL_CSV


def source_metadata():
    if METADATA.exists():
        return read_json(METADATA, {})
    previous = read_json(DOCS_FINAL_JSON, {})
    return previous.get("metadata", {}) if isinstance(previous, dict) else {}


def source_weekly_summary():
    summary = read_json(WEEKLY_SUMMARY, {})
    return summary if isinstance(summary, dict) else {}


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text[:11], fmt).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def display_date(value):
    parsed = parse_date(value)
    return parsed.strftime("%d %b %Y") if parsed else ""


def money(value):
    try:
        number = float(str(value or "0").replace(",", "").replace("$", ""))
    except ValueError:
        number = 0
    return f"${number:,.0f}"


def number(value):
    try:
        return f"{float(str(value or '0').replace(',', '')):,.0f}"
    except ValueError:
        return str(value or "0")


def normalized_key(value):
    text = str(value or "").lower()
    text = re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


GAME_KEY_DETAIL_OVERRIDES = {
    "star sailors": "Star Sailors is a mobile turn-based collectible RPG built around recruiting characters, forming squads, and resolving battles through team synergy and skill timing. Its USP is a space-fantasy collection loop backed by Com2uS publishing, giving it recognizable RPG progression in a mobile-first format.",
    "cookierun classic": "CookieRun Classic is a mobile endless-runner revival where players jump, slide, collect jellies, pair cookies with pets, and chase higher scores through repeated runs. Its USP is nostalgia-led CookieRun gameplay, bringing a familiar franchise loop back in a simple, accessible mobile format.",
    "qi refining 3000 levels the fallen empress forces me to ascend": "Qi Refining 3000 Levels is a vertical idle xianxia RPG where players grow a cultivation character through automated progression, boss fights, gear upgrades, mounts, and cross-server activities. Its USP is the Chinese cultivation fantasy theme combined with low-friction idle progression for players who want RPG growth without heavy manual play.",
    "once upon a time there was a street": "Once upon a time, there was a street is a mobile management simulation where players rebuild an ancient street by opening shops, attracting residents, and expanding a historical marketplace. Its USP is a cozy heritage-commerce theme, turning town restoration and shop management into a casual mobile loop.",
    "section cloud fantasia": "Section: Cloud Fantasia is a fantasy mobile MMORPG where players explore open zones, build characters, collect companions, run dungeons, and fight alongside pets. Its USP is an anime-style cloud-fantasy world with familiar mobile MMO progression and companion-driven combat.",
    "ragnarok the new world": "Ragnarok: The New World is a mobile open-world MMORPG built around class progression, exploration, monster combat, trading, and social play. Its USP is the Ragnarok IP in a broader open-world mobile format, giving an established SEA franchise a newer exploration-led presentation.",
    "digimon up": "DIGIMON UP is a mobile idle-raising RPG where players collect Digimon, raise them over time, and progress through lightweight battles and upgrades. Its USP is the Digimon IP combined with a low-maintenance mobile raising loop that fits short daily sessions.",
    "ms freedom horizon": "MS: Freedom Horizon is a mobile mecha strategy RPG where players pilot mechs, build battle lineups, and use turn-based tactics against wasteland enemies. Its USP is a mecha-collection fantasy with deck-style combat, giving strategy RPG players a robot-focused alternative to character-only gachas.",
    "oracle of the holy grail": "Oracle of the Holy Grail is a mobile fantasy RPG built around hero progression, party-building, and role-playing combat. Its USP is a fantasy collection-and-growth loop aimed at players who want familiar mobile RPG systems in a compact regional release.",
    "the walking dead aftermath": "The Walking Dead: Aftermath is a mobile roguelite survival RPG where players fight walkers, make survivor choices, upgrade characters, and manage risk across repeated runs. Its USP is the Walking Dead license applied to mobile survival progression, combining recognizable horror IP with roguelite replayability.",
    "hololive dreams": "hololive Dreams is a mobile-led Rhythm RPG where players use hololive talent characters and music-driven battles across iOS, Android, and Steam. Its USP is the hololive fan ecosystem packaged into a cross-platform game, combining idol/music appeal with RPG progression.",
    "cookierun crumble idle rpg": "CookieRun: Crumble - Idle RPG is a mobile idle RPG where Cookie squads battle automatically while players upgrade teams, collect characters, and improve progression efficiency. Its USP is the CookieRun franchise adapted into a hands-off RPG loop, making the brand playable for idle-game audiences.",
    "blade heroes mecha soul": "Blade Heroes: Mecha Soul is a mobile idle RPG built around mecha-themed heroes, automated battles, character upgrades, and long-term power progression. Its USP is the eastern-mecha theme layered onto familiar idle RPG systems, giving players a sci-fi alternative to fantasy idle games.",
    "lordrush": "Lordrush is a mobile strategy and tower-defense game where players rebuild a fortress, gather resources, upgrade defenses, and repel enemy waves. Its USP is a medieval base-building loop that combines casual resource growth with defensive strategy.",
    "palworld": "Palworld is an open-world survival crafting game where players capture creatures, build bases, automate production, fight enemies, and explore with multiplayer support. Its USP is the blend of creature collection with survival crafting and base automation, making it broader than a standard monster-battling game.",
    "spiritvale": "SpiritVale is a PC action MMORPG where players choose classes, build characters, fight monsters, clear dungeons, and chase world-boss progression. Its USP is a classic MMO progression structure delivered as an early-access Steam title with action combat emphasis.",
    "echoes of aincrad": "Echoes of Aincrad is a Sword Art Online action RPG where players progress through quests, real-time combat, and character growth across PC and console platforms. Its USP is the Sword Art Online IP returning to Aincrad-style RPG fantasy with broader platform reach.",
    "pass the fear": "Pass the Fear is a roguelite bullet-hell action RPG where players survive escalating enemy waves, dodge projectile patterns, and build a stronger run through upgrades. Its USP is the mix of survival pressure, bullet-hell movement, and roguelite progression in a compact PC action format.",
    "sephiria": "Sephiria is a top-down pixel-art action roguelite where players descend a tower, fight demons, collect artifacts, and improve with each run. Its USP is a polished 2D action loop with clear roguelite replayability and a distinctive rabbit-hero fantasy premise.",
    "dragonsword awakening": "DragonSword: Awakening is an anime-style open-world action RPG where players explore Orbis, switch through tag-action combat, and progress through fantasy quests and character builds. Its USP is Unreal Engine 5 presentation combined with fast character-switching action, positioning it as a premium-looking anime RPG.",
}


def meeting_date_from_schedule(schedule):
    meeting = parse_date(schedule.get("upcoming_meeting_date", ""))
    return meeting.isoformat() if meeting else ""


def meeting_pack_dir(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date


def game_report_path(meeting_date):
    return meeting_pack_dir(meeting_date) / GAME_REPORT_FILENAME


def game_enriched_path(meeting_date):
    return meeting_pack_dir(meeting_date) / GAME_ENRICHED_FILENAME


def parse_source_period(value):
    match = re.search(r"\b(20\d{2}[-/]\d{2}[-/]\d{2}) to (20\d{2}[-/]\d{2}[-/]\d{2})\b", str(value or ""))
    if not match:
        return None, None
    return parse_date(match.group(1)), parse_date(match.group(2))


def release_inside_report_period(row, release_date):
    released = parse_date(release_date)
    if not released:
        return False

    start = parse_date(row.get("report_start_date", ""))
    end = parse_date(row.get("report_end_date", ""))
    if not start or not end:
        start, end = parse_source_period(row.get("pc_source_period") or row.get("mobile_source_period"))
    if not start or not end:
        return False
    return start <= released <= end


def mobile_first_commercial_signal(row):
    prior_text = str(row.get("sg_revenue_prior_store") or "").strip().replace(",", "").replace("$", "")
    if not prior_text:
        return False
    try:
        prior_revenue = float(prior_text)
    except ValueError:
        return False
    if prior_revenue != 0:
        return False
    current_revenue = safe_float(row.get("sg_revenue_gross"))
    return current_revenue >= 3000 or (
        str(row.get("chart_rank_match_status") or "").strip().lower() == "matched"
        and current_revenue >= 1000
    )


def release_or_first_signal_inside_report_period(row, release_date):
    if row.get("report_classification") != "pc_only" and mobile_first_commercial_signal(row):
        return True
    return release_inside_report_period(row, release_date)


def game_title(row):
    return row.get("english_report_name") or row.get("unified_name") or row.get("pc_title") or row.get("report_name") or "Untitled"


def game_layer_signal(row):
    classification = row.get("report_classification", "")
    sg_gross = safe_float(row.get("sg_revenue_gross"))
    steam_peak = safe_float(row.get("steamdb_peak"))
    if classification == "pc_only":
        return "Strong Market Signal" if steam_peak >= 10000 else "Emerging Market Signal"
    return "Strong Market Signal" if sg_gross >= 3000 else "Emerging Market Signal"


def game_layer_platform(row, enriched=None):
    if enriched and enriched.get("platforms_confirmed"):
        return enriched.get("platforms_confirmed", "")
    classification = row.get("report_classification", "")
    if classification == "mobile_led_cross_platform":
        return "Mobile + PC"
    if classification == "pc_only":
        return "PC"
    return "Mobile"


def report_classification_label(row):
    labels = {
        "mobile_only": "Mobile game",
        "mobile_led_cross_platform": "Mobile-led game with PC version",
        "pc_only": "PC-only game",
    }
    return labels.get(row.get("report_classification"), "Mobile game")


def game_layer_reason(row, enriched=None):
    if mobile_first_commercial_signal(row):
        return (
            "Included as a new SG commercial signal because prior revenue was $0 "
            "and current SG revenue crossed the report threshold."
        )
    if enriched:
        summary = " ".join(part for part in (enriched.get("summary_sentence_1"), enriched.get("summary_sentence_2")) if part)
        if summary:
            return summary
    classification = row.get("report_classification", "")
    if classification == "pc_only":
        peak = number(row.get("steamdb_peak"))
        return f"PC-only SteamDB signal with peak concurrent users of {peak}."
    if classification == "mobile_led_cross_platform":
        return "Mobile-led cross-platform title selected from Sensor Tower Singapore evidence with matched PC context."
    return "Mobile title selected from Sensor Tower Singapore revenue, download, and rank evidence."


def game_key_details(row, enriched=None):
    title = game_title(row) if "report_classification" in row else title_for(row)
    override = GAME_KEY_DETAIL_OVERRIDES.get(normalized_key(title))
    if override:
        return override
    if enriched:
        summary = " ".join(
            part.strip()
            for part in (enriched.get("summary_sentence_1"), enriched.get("summary_sentence_2"))
            if part and part.strip().lower() != "unconfirmed"
        )
        if summary:
            return summary
    genre = row.get("genre") or row.get("Genre") or "game"
    return f"{title} is a {genre} selected for the report. Gameplay and USP details still need manual enrichment."


def top_markets_text(row):
    parts = []
    for index in range(1, 5):
        country = row.get(f"sea_market_{index}_country", "")
        revenue = safe_float(row.get(f"sea_market_{index}_revenue_gross"))
        downloads = safe_float(row.get(f"sea_market_{index}_downloads"))
        if country and (revenue or downloads):
            parts.append(f"{country} (${revenue:,.0f} / {downloads:,.0f} DL)")
    return "Top Mkts: " + " || ".join(parts) if parts else ""


def sg_ranks_text(row):
    ios = f"iOS (DL #{row.get('ios_top_free_rank') or 'NA'} / Rev #{row.get('ios_top_grossing_rank') or 'NA'})"
    android = f"Android (DL #{row.get('android_top_free_rank') or 'NA'} / Rev #{row.get('android_top_grossing_rank') or 'NA'})"
    return f"SG App Store Ranks: {ios} || {android}"


def game_layer_report_rows(meeting_date):
    game_rows = read_csv(game_report_path(meeting_date))
    if not game_rows:
        return []
    enriched_rows = read_csv(game_enriched_path(meeting_date))
    enriched_by_title = {normalized_key(row.get("report_name")): row for row in enriched_rows if normalized_key(row.get("report_name"))}
    report_rows = []
    for row in game_rows:
        title = game_title(row)
        enriched = enriched_by_title.get(normalized_key(title), {})
        release_date = (
            enriched.get("release_date_used")
            or row.get("sg_release_date_reference")
            or row.get("pc_release_date")
            or ""
        )
        if not release_or_first_signal_inside_report_period(row, release_date):
            continue
        publisher = enriched.get("publisher") or row.get("unified_publisher_name") or "Publisher unavailable"
        is_pc_only = row.get("report_classification") == "pc_only"
        report_rows.append(
            {
                "Signal Type": game_layer_signal(row),
                "Signal Definition": "Game-layer final report row.",
                "SG Gross Revenue": "" if is_pc_only else row.get("sg_revenue_gross") or "0",
                "SG Downloads": "" if is_pc_only else row.get("sg_downloads") or "0",
                "Inclusion Reason": game_layer_reason(row, enriched),
                "Key Details": game_key_details(row, enriched),
                "Game Title": title,
                "English Display Title": title,
                "Original Title": row.get("unified_name") or row.get("pc_title") or title,
                "Detected Language": "",
                "Machine English Title": "",
                "Manual English Title": "",
                "Translation Source": "",
                "Translation Confidence": "",
                "Translation Review Status": "",
                "Translation Note": "",
                "Platform": game_layer_platform(row, enriched),
                "Publisher": publisher,
                "Developer": enriched.get("developer") or row.get("developer") or "",
                "Release Date": release_date,
                "Genre": enriched.get("genre") or "",
                "Top 3 Markets": "" if is_pc_only else top_markets_text(row),
                "SG App Store Ranks": "" if is_pc_only else sg_ranks_text(row),
                "unified_app_id": row.get("unified_id") or row.get("steam_app_id") or normalized_key(title),
                "run_timestamp_utc": "",
                "report_start_date": row.get("report_start_date", ""),
                "report_end_date": row.get("report_end_date", ""),
                "ranking_date": row.get("ranking_date", ""),
                "sensor_tower_effective_end_date": row.get("sensor_tower_effective_end_date", ""),
                "meeting_date": meeting_date,
                "report_classification": row.get("report_classification", ""),
                "steamdb_peak": row.get("steamdb_peak", ""),
                "steamdb_reviews": row.get("steamdb_reviews", ""),
                "steam_url": row.get("steam_url", ""),
                "release_date_source_url": enriched.get("release_date_source_url", ""),
                "source_urls": enriched.get("source_urls", ""),
            }
        )
    return report_rows


def source_report_rows(metadata, schedule):
    meeting_date = meeting_date_from_schedule(schedule)
    if meeting_date:
        rows = game_layer_report_rows(meeting_date)
        if rows:
            return rows
    return read_csv(source_finalized_csv(metadata))


def split_values(value):
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"\s*(?:\|\||;|/)\s*", text)
    return [part.strip() for part in parts if part.strip()]


def parse_top_markets(value):
    text = str(value or "").strip()
    if not text:
        return []
    text = re.sub(r"^Top\s+Mkts?:\s*", "", text, flags=re.I)
    items = []
    for part in re.split(r"\s*\|\|\s*|\s*;\s*", text):
        part = part.strip()
        match = re.match(r"(?P<market>[A-Z]{2})\s*\((?P<revenue>\$?[\d,]+)\s*/\s*(?P<downloads>[\d,]+)\s*DL\)", part)
        if match:
            items.append(match.groupdict())
        elif part:
            items.append({"market": part, "revenue": "", "downloads": ""})
    return items


def parse_rank_pairs(value):
    text = str(value or "").strip()
    if not text:
        return []
    text = re.sub(r"^SG\s+App\s+Store\s+Ranks?:\s*", "", text, flags=re.I)
    items = []
    for part in re.split(r"\s*\|\|\s*|\s*;\s*", text):
        part = part.strip()
        match = re.match(r"(?P<platform>iOS|Android)\s*\((?P<detail>.*)\)", part, flags=re.I)
        if match:
            items.append({"platform": match.group("platform"), "detail": match.group("detail")})
        elif ":" in part:
            platform, detail = part.split(":", 1)
            items.append({"platform": platform.strip(), "detail": detail.strip()})
        elif part:
            items.append({"platform": "Rank", "detail": part})
    return items


def value_chips(value):
    parts = split_values(value)
    if not parts:
        return '<span class="muted-value">N/A</span>'
    return '<div class="chip-list">' + "".join(f'<span class="metric-badge neutral">{escape(part)}</span>' for part in parts) + "</div>"


def status_badge(label):
    text = str(label or "N/A").strip()
    kind = "strong" if "strong" in text.lower() else "emerging"
    return f'<span class="metric-badge {kind}">{escape(text)}</span>'


def performance_block(row):
    return f"""<div class="stat-grid sg-performance">
  <div class="stat-cell"><span>Revenue</span><b>{escape(money(row.get("SG Gross Revenue")))}</b></div>
  <div class="stat-cell"><span>Downloads</span><b>{escape(number(row.get("SG Downloads")))}</b></div>
</div>"""


def top_markets_block(value):
    markets = parse_top_markets(value)
    if not markets:
        return '<span class="muted-value">N/A</span>'
    rows = []
    for index, item in enumerate(markets, 1):
        downloads = item.get("downloads") or ""
        rows.append(
            f'<div class="market-row"><span class="market-rank">#{index}</span><b>{escape(item.get("market", ""))}</b>'
            f'<span>{escape(item.get("revenue") or "N/A")}</span><span>{escape((downloads + " DL") if downloads else "N/A")}</span></div>'
        )
    return '<div class="structured-block top-markets"><h5>Top Markets</h5>' + "".join(rows) + "</div>"


def ranks_block(value):
    ranks = parse_rank_pairs(value)
    if not ranks:
        return '<span class="muted-value">N/A</span>'
    rows = []
    for item in ranks:
        detail = (item.get("detail") or "N/A").replace(" / ", " / ")
        rows.append(f'<div class="rank-row"><b>{escape(item.get("platform", ""))}</b><span>{escape(detail)}</span></div>')
    return '<div class="structured-block ranks-block"><h5>Ranks</h5>' + "".join(rows) + "</div>"


def compact_kv(items):
    return '<div class="compact-kv">' + "".join(
        f'<div><span>{escape(label)}</span><b>{value}</b></div>' for label, value in items
    ) + "</div>"


def report_period(rows, schedule):
    if rows:
        start = rows[0].get("report_start_date", "")
        end = rows[0].get("report_end_date", "")
        if start or end:
            return display_date(start), display_date(end)
    start = schedule.get("last_completed_meeting_date", "")
    meeting = parse_date(schedule.get("upcoming_meeting_date", ""))
    end = (meeting - timedelta(days=1)).isoformat() if meeting else ""
    return display_date(start), display_date(end)


def meeting_date_for(rows, schedule):
    if rows:
        row_meeting = display_date(rows[0].get("meeting_date", ""))
        if row_meeting:
            return row_meeting
        end = parse_date(rows[0].get("report_end_date", ""))
        if end:
            return display_date((end + timedelta(days=1)).isoformat())
    return display_date(schedule.get("upcoming_meeting_date", ""))


def meeting_date_key(rows, schedule):
    if rows:
        row_meeting = parse_date(rows[0].get("meeting_date", ""))
        if row_meeting:
            return row_meeting.isoformat()
        end = parse_date(rows[0].get("report_end_date", ""))
        if end:
            return (end + timedelta(days=1)).isoformat()
    meeting = parse_date(schedule.get("upcoming_meeting_date", ""))
    return meeting.isoformat() if meeting else ""


def source_news_context(rows, schedule):
    meeting_date = meeting_date_key(rows, schedule)
    if not meeting_date:
        return []
    if not rows:
        period_start, period_end, _ranking_date = schedule_report_dates(schedule)
    else:
        period_start = parse_date(rows[0].get("report_start_date", ""))
        period_end = parse_date(rows[0].get("report_end_date", ""))
    review_rows = read_csv(MEETING_PACK_OUTPUT_ROOT / meeting_date / NEWS_CONTEXT_FILENAME)
    output = []
    for row in review_rows:
        context_type = row.get("context_type")
        decision = str(row.get("editor_decision") or "").strip().lower()
        include_value = str(row.get("include_in_final_report") or "").strip().lower()
        if context_type == "industry_trend":
            if decision == "exclude" or include_value == "no":
                continue
        elif include_value != "yes":
            continue
        event_date = parse_date(row.get("event_date")) or parse_date(row.get("published_at"))
        if period_start and period_end and (not event_date or not period_start <= event_date <= period_end):
            continue
        output.append(row)
    return output


def in_progress_period(schedule):
    start = schedule.get("last_completed_meeting_date", "")
    meeting = parse_date(schedule.get("upcoming_meeting_date", ""))
    end = (meeting - timedelta(days=1)).isoformat() if meeting else ""
    return display_date(start), display_date(end)


def schedule_report_dates(schedule):
    start = parse_date(schedule.get("last_completed_meeting_date", ""))
    meeting = parse_date(schedule.get("upcoming_meeting_date", ""))
    end = meeting - timedelta(days=1) if meeting else None
    offset = int(schedule.get("weekly_candidate_capture", {}).get("ranking_date_offset_days", 2))
    ranking = end - timedelta(days=offset) if end else None
    return start, end, ranking


def staging_summary_text(weekly_summary):
    count = weekly_summary.get("new_or_seen_candidates") if isinstance(weekly_summary, dict) else None
    if count == 0:
        return weekly_summary.get("empty_message") or "No weekly candidates found for this extraction window."
    if count:
        return f"{count} candidate(s) are staged for the upcoming meeting-day review."
    return "Weekly extraction data for this window remains staging until the meeting-day final report is generated."


def weekly_staging_payload(weekly_summary, schedule):
    start, end, ranking = schedule_report_dates(schedule)
    candidate_count = weekly_summary.get("new_or_seen_candidates") if isinstance(weekly_summary, dict) else None
    message = staging_summary_text(weekly_summary or {})
    report_start = weekly_summary.get("report_start_date") or (start.isoformat() if start else "")
    report_end = weekly_summary.get("report_end_date") or (end.isoformat() if end else "")
    ranking_date = weekly_summary.get("ranking_date") or ((ranking.isoformat() if ranking else "") if weekly_summary else "")
    return {
        "last_weekly_extraction_run_date": display_date(weekly_summary.get("run_timestamp_utc", "")) if weekly_summary else "",
        "run_timestamp_utc": weekly_summary.get("run_timestamp_utc", "") if weekly_summary else "",
        "report_start_date": report_start,
        "report_end_date": report_end,
        "mode": weekly_summary.get("mode") or ("weekly-capture" if weekly_summary else "not-run"),
        "candidate_count": candidate_count,
        "message": message,
        "sensor_tower_ranking_date": ranking_date,
    }


def data_as_of(metadata, rows=None):
    value = metadata.get("sensor_tower_data_as_of_date") or metadata.get("last_successful_sensor_tower_report_end_date")
    value_date = parse_date(value)
    report_end = parse_date((rows or [{}])[0].get("report_end_date", "")) if rows else None
    if report_end and (not value_date or value_date < report_end):
        value_date = report_end
    return display_date(value_date.isoformat()) if value_date else "N/A"


def normalized_metadata(metadata, rows):
    normalized = dict(metadata)
    if rows:
        report_end = rows[0].get("report_end_date", "")
        value_date = parse_date(normalized.get("sensor_tower_data_as_of_date", ""))
        report_end_date = parse_date(report_end)
        if report_end_date and (not value_date or value_date < report_end_date):
            normalized["sensor_tower_data_as_of_date"] = report_end
            normalized["last_successful_sensor_tower_report_end_date"] = report_end
    return normalized


def signal_group(row):
    signal = (row.get("Signal Type") or row.get("Market Relevance") or "").lower()
    return "strong" if "strong" in signal else "emerging"


def signal_label(row):
    return row.get("Signal Type") or ("Strong Market Signal" if signal_group(row) == "strong" else "Emerging Market Signal")


def title_for(row):
    return row.get("Game Title") or row.get("English Display Title") or row.get("Original Title") or "Untitled"


def sort_rows(rows):
    return sorted(rows, key=lambda row: (-safe_float(row.get("SG Gross Revenue")), title_for(row).lower()))


def safe_float(value):
    try:
        return float(str(value or "0").replace(",", "").replace("$", ""))
    except ValueError:
        return 0.0


def page_shell(title, active, body, rows, schedule, metadata):
    start, end = report_period(rows, schedule)
    meeting = meeting_date_for(rows, schedule)
    active_name = next((label for _, label, _, key in NAV_ITEMS if key == active), "Latest Brief")
    nav = "".join(
        f'<a class="{"on" if key == active else ""}" href="{href}" data-tooltip="{escape(desc)}" '
        f'aria-current="{"page" if key == active else "false"}">{escape(label)}</a>'
        for href, label, desc, key in NAV_ITEMS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} | IBD Market Intelligence</title>
  <link rel="stylesheet" href="assets/static-dashboard.css">
  <script defer src="assets/static-dashboard.js"></script>
</head>
<body>
  <div class="app-shell top-nav-shell">
    <header class="site-header">
      <div class="brand top-brand">
        <h1>IBD Market Intelligence</h1>
        <p>Singapore &middot; Mobile Launch Discovery</p>
        <span>Report Dashboard</span>
      </div>
      <nav class="top-nav" aria-label="Primary navigation">{nav}</nav>
    </header>
    <div class="workspace">
      <header class="topbar compact-topbar slim-context-bar" aria-label="Brief context">
        <div class="inline-context">
          <b>{escape(active_name)}</b>
          <span>Period: {escape(start or "N/A")} to {escape(end or "N/A")}</span>
          <span>Meeting: {escape(meeting or "N/A")}</span>
          <span>Data as of: {escape(data_as_of(metadata, rows))}</span>
        </div>
        <div class="top-actions compact-actions">
          <a class="btn ghost" href="historical-briefs.html">Previous Briefs</a>
          <a class="btn primary" href="latest-brief.html">Latest Brief</a>
        </div>
      </header>
      <main id="main-content">{body}</main>
    </div>
  </div>
</body>
</html>"""


def page_header(eyebrow, title, desc="", actions=""):
    action_html = f'\n  <div class="page-actions">{actions}</div>' if actions else ''
    return f"""<section class="page-header">
  <div><em>{escape(eyebrow)}</em><h1>{escape(title)}</h1>{f'<p>{escape(desc)}</p>' if desc else ''}</div>{action_html}
</section>"""


def summary_cards(rows):
    if not rows:
        cards = [
            ("snapshot", "Current snapshot", "0 included launches", "No weekly candidates"),
            ("opportunity", "Top opportunity", "N/A", "No candidate met the extraction criteria"),
            ("action", "SG gross revenue", "$0", "No candidate revenue in this window"),
        ]
        return '<section class="summary-card-grid">' + "".join(
            f'<article class="summary-card {escape(kind)}"><small>{escape(label)}</small><h3>{escape(headline)}</h3><p>{escape(detail)}</p></article>'
            for kind, label, headline, detail in cards
        ) + "</section>"
    strong = [r for r in rows if signal_group(r) == "strong"]
    emerging = [r for r in rows if signal_group(r) != "strong"]
    leader = max(rows, key=lambda r: safe_float(r.get("SG Gross Revenue")), default={})
    total_revenue = sum(safe_float(r.get("SG Gross Revenue")) for r in rows)
    cards = [
        ("snapshot", "Current snapshot", f"{len(rows)} included launches", f"{len(strong)} strong / {len(emerging)} emerging"),
        ("opportunity", "Top opportunity", title_for(leader) if leader else "No title available", money(leader.get("SG Gross Revenue")) if leader else "N/A"),
        ("action", "SG gross revenue", money(total_revenue), "Estimated from available report output"),
    ]
    return '<section class="summary-card-grid">' + "".join(
        f'<article class="summary-card {escape(kind)}"><small>{escape(label)}</small><h3>{escape(headline)}</h3><p>{escape(detail)}</p></article>'
        for kind, label, headline, detail in cards
    ) + "</section>"


def executive_summary(rows):
    if not rows:
        bullets = [
            "No weekly candidates found for this extraction window.",
            "No new released-game item met the configured SG discovery criteria.",
            "Dashboard remains ready for the next weekly capture or meeting-day refresh.",
        ]
        return f"""<section class="brief-section executive-section">
  <div class="section-heading"><div><h2>Executive Summary</h2><p>Level 1 scan: what changed, why it matters, and where to focus.</p></div></div>
  <ul class="executive-bullets">{''.join(f'<li>{escape(item)}</li>' for item in bullets)}</ul>
</section>"""
    strong = [r for r in rows if signal_group(r) == "strong"]
    emerging = [r for r in rows if signal_group(r) != "strong"]
    leader = max(rows, key=lambda r: safe_float(r.get("SG Gross Revenue")), default={})
    bullets = [
        f"{len(rows)} released-game record(s) are included in the current market brief.",
        f"{len(strong)} title(s) are classified as Strong Market Signals and {len(emerging)} are Emerging Market Signals.",
        f"{title_for(leader)} leads available SG revenue at {money(leader.get('SG Gross Revenue'))}." if leader else "No lead title is available in the current output.",
    ]
    return f"""<section class="brief-section executive-section">
  <div class="section-heading"><div><h2>Executive Summary</h2><p>Level 1 scan: what changed, why it matters, and where to focus.</p></div></div>
  <ul class="executive-bullets">{''.join(f'<li>{escape(item)}</li>' for item in bullets)}</ul>
</section>"""


def market_chips(row):
    if row.get("report_classification") == "pc_only":
        return pc_context_block(row)
    pc_context = pc_context_block(row) if row.get("report_classification") == "mobile_led_cross_platform" else ""
    pc_context_line = f"\n  {pc_context}" if pc_context else ""
    return f"""<div class="market-chip-row">
  <span class="market-chip sg-market"><small>SG Performance</small>{performance_block(row)}</span>
  <span class="market-chip structured-market-chip">{top_markets_block(row.get("Top 3 Markets"))}</span>
  <span class="market-chip structured-market-chip">{ranks_block(row.get("SG App Store Ranks"))}</span>{pc_context_line}
</div>"""


def pc_context_block(row):
    stats = []
    if row.get("steamdb_peak"):
        stats.append(f'<div class="stat-cell"><span>Steam peak</span><b>{escape(number(row.get("steamdb_peak")))}</b></div>')
    if row.get("steamdb_reviews"):
        stats.append(f'<div class="stat-cell"><span>Steam reviews</span><b>{escape(number(row.get("steamdb_reviews")))}</b></div>')
    if not stats:
        stats.append('<div class="stat-cell"><span>Steam stats</span><b>Unavailable</b></div>')
    steam_url = row.get("steam_url")
    link = f'<a href="{escape(steam_url)}" target="_blank" rel="noopener">Steam store page</a>' if steam_url else ""
    owners = " / ".join(value for value in (row.get("Publisher"), row.get("Developer")) if value)
    owner_html = f'<p><b>Publisher / developer:</b> {escape(owners)}</p>' if owners else ""
    return '<span class="market-chip structured-market-chip"><h5>PC Context</h5><div class="stat-grid pc-performance">' + "".join(stats) + f'</div>{owner_html}{link}</span>'


def signal_card(row, group):
    title = title_for(row)
    original = row.get("Original Title") or row.get("original_title") or ""
    title_note = f'\n    <p class="original-title"><span>Original title</span>{escape(original)}</p>' if original and original != title else ""
    details = row.get("Key Details") or row.get("Market Overview Reason") or row.get("Inclusion Reason") or "Available in current final report output."
    pill_class = "strong" if group == "strong" else "emerging"
    card_class = "rich-signal-card" if group == "strong" else "rich-signal-card emerging"
    performance_heading = "PC Performance" if row.get("report_classification") == "pc_only" else "Local Performance"
    return f"""<article class="signal-card {card_class}">
  <div class="signal-card-top">
    <span class="signal-pill {pill_class}">{escape(signal_label(row))}</span>
    <span class="view-link">Market brief</span>
  </div>
  <div class="card-overview">
    <h3>{escape(title)}</h3>
    <p class="publisher-line">{escape(row.get("Publisher") or "Publisher unavailable")}</p>
    <div class="meta-chip-row">
      {value_chips(row.get("Platform") or "Platform unavailable")}
      {value_chips(row.get("Genre") or "Genre unavailable")}
      <span class="metric-badge neutral">{escape(report_classification_label(row))}</span>
      <span class="metric-badge neutral">Release {escape(display_date(row.get("Release Date")) or row.get("Release Date") or "N/A")}</span>
    </div>{title_note}
  </div>
  <div class="card-block">
    <h4>{performance_heading}</h4>
    {market_chips(row)}
  </div>
  <div class="card-block card-evidence">
    <h4>Key Details</h4>
    <p>{escape(details)}</p>
  </div>
</article>"""


def empty_state(title, desc):
    return f'<article class="empty-state polished-empty"><h3>{escape(title)}</h3><p>{escape(desc)}</p></article>'


def report_table(rows, released=False):
    fields = [
        "Game Title",
        "Signal Type",
        "Publisher",
        "Developer",
        "Platform",
        "Release Date",
        "Genre",
    ]
    classification = rows[0].get("report_classification") if rows else ""
    if classification == "pc_only":
        fields += ["Steam Peak", "Steam Reviews", "Steam URL"]
    else:
        fields += ["SG Gross Revenue", "SG Downloads", "Top 3 Markets", "SG App Store Ranks"]
        if classification == "mobile_led_cross_platform":
            fields += ["Steam Peak", "Steam Reviews", "Steam URL"]
    head = "".join(f"<th>{escape(field)}</th>" for field in fields)
    body = "".join(
        "<tr>" + "".join(table_cell(row, field) for field in fields) + "</tr>"
        for row in rows
    )
    empty = f'<tr><td colspan="{len(fields)}">No report rows available.</td></tr>'
    cls = "data-table released-table" if released else "data-table"
    return f'<div class="{cls}"><table><thead><tr>{head}</tr></thead><tbody>{body or empty}</tbody></table></div>'


def tracker_table(rows):
    fields = [
        "Game Title",
        "Signal Type",
        "Publisher",
        "Developer",
        "Platform",
        "Release Date",
        "Genre",
        "SG Gross Revenue",
        "SG Downloads",
        "Top 3 Markets",
        "SG App Store Ranks",
        "Steam Peak",
        "Steam Reviews",
        "Steam URL",
        "Related Brief",
    ]
    head = "".join(f"<th>{escape(field)}</th>" for field in fields)
    body = "".join(
        "<tr>" + "".join(table_cell(row, field) for field in fields) + "</tr>"
        for row in rows
    )
    empty = f'<tr><td colspan="{len(fields)}">No tracker rows available.</td></tr>'
    return f'<div class="data-table released-table"><table><thead><tr>{head}</tr></thead><tbody>{body or empty}</tbody></table></div>'


def table_cell(row, field):
    value = row.get(field, "")
    if field == "Game Title":
        original = row.get("Original Title") or ""
        return f"<td><b>{escape(title_for(row))}</b>{f'<small>{escape(original)}</small>' if original and original != title_for(row) else ''}</td>"
    if field == "SG Gross Revenue":
        return f'<td class="num">{escape(money(value))}</td>'
    if field == "SG Downloads":
        return f'<td class="num">{escape(number(value))}</td>'
    if field == "Signal Type":
        return f"<td>{status_badge(value)}</td>"
    if field in ("Platform", "Genre"):
        return f"<td>{value_chips(value)}</td>"
    if field == "Top 3 Markets":
        return f"<td>{top_markets_block(value)}</td>"
    if field == "SG App Store Ranks":
        return f"<td>{ranks_block(value)}</td>"
    if field == "Steam Peak":
        return f'<td class="num">{escape(number(row.get("steamdb_peak")))}</td>'
    if field == "Steam Reviews":
        return f'<td class="num">{escape(number(row.get("steamdb_reviews")))}</td>'
    if field == "Steam URL":
        url = row.get("steam_url")
        link = f'<a href="{escape(url)}" target="_blank" rel="noopener">Steam</a>' if url else ""
        return f"<td>{link}</td>"
    if field == "Release Date":
        return f'<td><span class="metric-badge neutral">{escape(display_date(value) or str(value or ""))}</span></td>'
    if field == "Related Brief":
        href = row.get("_brief_href", "")
        text = value or row.get("_brief_label", "")
        if href:
            return f'<td><a href="{escape(href)}">{escape(text)}</a></td>'
        return f"<td>{escape(str(text or ''))}</td>"
    return f"<td>{escape(str(value or ''))}</td>"


def released_games_section(strong, emerging, view):
    active_cards = "active" if view != "table" else ""
    active_table = "active" if view == "table" else ""
    toggle = f"""<div class="view-toggle" aria-label="Released games view">
  <a class="{active_cards}" href="latest-brief.html" aria-current="{"true" if view != "table" else "false"}">Card view</a>
  <a class="{active_table}" href="latest-brief.html?view=table" aria-current="{"true" if view == "table" else "false"}">Compact table</a>
</div>"""
    rows = strong + emerging
    groups = [
        ("mobile_only", "Mobile Games", "Mobile game", "No mobile-only games were released in this reporting period."),
        ("mobile_led_cross_platform", "Mobile + PC Games", "Mobile-led game with PC version", "No mobile-led cross-platform games were released in this reporting period."),
        ("pc_only", "PC-only Games", "PC-only game", "No PC-only games were released in this reporting period."),
    ]
    card_sections = []
    table_sections = []
    for classification, heading, label, empty_desc in groups:
        group_rows = sorted(
            [
                row for row in rows
                if row.get("report_classification") == classification
                or (classification == "mobile_only" and not row.get("report_classification"))
            ],
            key=lambda row: (0 if signal_group(row) == "strong" else 1, title_for(row).lower()),
        )
        cards = "".join(signal_card(row, signal_group(row)) for row in group_rows) or empty_state(f"No {heading.lower()} in this brief", empty_desc)
        card_sections.append(f'<section class="release-group"><h3 class="signal-heading">{heading} <span>{label}</span></h3><div class="signal-grid">{cards}</div></section>')
        table_content = report_table(group_rows, released=True) if group_rows else empty_state(f"No {heading.lower()} in this brief", empty_desc)
        table_sections.append(f'<section class="release-group"><h3 class="signal-heading">{heading} <span>{label}</span></h3>{table_content}</section>')
    return f"""<section class="brief-section released-games-section">
  <div class="section-heading"><div><h2>Released Games</h2><p>Games released inside the report period, grouped by mobile and PC classification.</p></div>{toggle}</div>
  <div class="cards-view" data-view="cards">
    {"".join(card_sections)}
  </div>
  <div class="table-view" data-view="table">
    {"".join(table_sections)}
  </div>
</section>"""


def news_context_card(row, label):
    title = row.get("title_en") or row.get("title") or "Untitled news item"
    source = row.get("source") or "Unknown source"
    score = row.get("hot_score") or "0"
    event_date = display_date(row.get("event_date")) or display_date(row.get("published_at")) or "Date unavailable"
    matched = row.get("matched_report_game")
    reason = row.get("editor_note") or row.get("inclusion_reason") or "Qualified through Game News Radar context rules."
    url = row.get("url") or "#"
    matched_html = f'<p><b>Matched game:</b> {escape(matched)}</p>' if matched else ""
    link_html = f'<a href="{escape(url)}" target="_blank" rel="noopener">View source</a>' if url != "#" else ""
    parts = [
        '<article class="news-context-card">',
        f'  <div class="meta-chip-row"><span class="metric-badge neutral">{escape(label)}</span><span class="metric-badge strong">Score {escape(str(score))}</span><span class="metric-badge neutral">{escape(event_date)}</span></div>',
        f"  <h3>{escape(title)}</h3>",
        f"  <p><b>Source:</b> {escape(source)}</p>",
    ]
    if matched_html:
        parts.append(f"  {matched_html}")
    parts.extend([f"  <p>{escape(reason)}</p>", f"  {link_html}" if link_html else "", "</article>"])
    return "\n".join(part for part in parts if part)


def news_context_section(news_context):
    release_rows = [r for r in news_context if r.get("context_type") == "selected_game_release_news"]
    announcement_rows = [r for r in news_context if r.get("context_type") == "high_score_game_announcement"]
    industry_rows = [r for r in news_context if r.get("context_type") == "industry_trend"]
    industry_cards = "".join(news_context_card(row, "Industry trend") for row in industry_rows) or empty_state(
        "No industry trends for this report period",
        "No high-signal, non-repeated Game News Radar industry trend qualified for this brief.",
    )
    release_cards = "".join(news_context_card(row, "Release support") for row in release_rows) or empty_state(
        "No release-support news matched selected games",
        "Game Release radar items only appear here when they match a Sensor Tower or SteamDB selected game.",
    )
    announcement_cards = "".join(news_context_card(row, "High-score announcement") for row in announcement_rows) or empty_state(
        "No high-score announcements for this report period",
        "Game Announcements only appear here when the radar score is high and the event date is inside the report period.",
    )
    return f"""<section class="brief-section news-context-section">
  <div class="section-heading"><div><h2>Game News Context</h2><p>Game News Radar items used as supporting context for the final brief. Releases support selected games only; announcements are ranked news signals for the report period.</p></div></div>
  <h3 class="signal-heading">Industry Trends <span>High-signal, non-repeated trends affecting the games market.</span></h3>
  <div class="news-context-grid">{industry_cards}</div>
  <h3 class="signal-heading">Game Announcements <span>High-score future-release or major game news items.</span></h3>
  <div class="news-context-grid">{announcement_cards}</div>
  <h3 class="signal-heading">Release Support <span>Release articles matched to games already selected by Sensor Tower or SteamDB.</span></h3>
  <div class="news-context-grid">{release_cards}</div>
</section>"""


def latest_page(rows, schedule, metadata, view="cards", news_context=None):
    news_context = news_context or []
    strong = sort_rows([r for r in rows if signal_group(r) == "strong"])
    emerging = sort_rows([r for r in rows if signal_group(r) != "strong"])
    body = (
        page_header(
            "Market Brief",
            "Singapore Gaming Market",
            "Executive view of the latest Singapore market scan.",
        )
        + summary_cards(rows)
        + executive_summary(rows)
        + released_games_section(strong, emerging, view)
        + news_context_section(news_context)
        + """<details class="methodology"><summary>Methodology and data notes</summary><p>Discovery uses app IDs first observed in SG Games Top Grossing history. Release dates are evidence only and are not discovery gates. Revenue is shown as estimated gross revenue from Sensor Tower where available.</p></details>"""
    )
    return page_shell("Latest Brief", "latest", body, rows, schedule, metadata)


def proof_run_records():
    records = []
    if not PROOF_RUNS.exists():
        return records
    for folder in sorted(PROOF_RUNS.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        payload_path = folder / "final-report.json"
        brief_path = folder / "latest-brief.html"
        if not payload_path.exists() or not brief_path.exists():
            continue
        payload = read_json(payload_path, {})
        proof_rows = payload.get("rows") or []
        proof_metadata = payload.get("metadata") or {}
        proof_schedule = payload.get("schedule") or {}
        start, end = report_period(proof_rows, proof_schedule)
        meeting = meeting_date_for(proof_rows, proof_schedule) or display_date(folder.name)
        records.append(
            {
                "folder": folder.name,
                "href": f"proof-runs/{folder.name}/latest-brief.html",
                "period": f"{start} to {end}" if start or end else "N/A",
                "meeting": meeting or "N/A",
                "data_as_of": data_as_of(proof_metadata, proof_rows),
                "row_count": len(proof_rows),
                "news_count": len(payload.get("news_context") or []),
                "meeting_key": folder.name,
            }
        )
    return records


def proof_archive_cards(records):
    if not records:
        return empty_state(
            "No proof reports yet.",
            "Historical proof reports will appear here after the proof-run exporter saves them.",
        )
    cards = []
    for record in records:
        cards.append(
            f"""<article class="archive-card reading-card">
  <div class="archive-main">
    <span class="status-chip neutral">Proof run</span>
    <h3>{escape(record["meeting"])} mock report</h3>
    <p>{escape(record["period"])}</p>
  </div>
  <div class="archive-meta">
    <span>Data as of: {escape(record["data_as_of"])}</span>
    <span>{record["row_count"]} games &middot; {record["news_count"]} news items</span>
    <a class="btn primary" href="{escape(record["href"])}">Open brief</a>
  </div>
</article>"""
        )
    return "".join(cards)


def tracker_rows_across_briefs(fallback_rows):
    records = proof_run_records()
    if not records:
        return fallback_rows
    tracker_rows = []
    seen_titles = set()
    for record in records:
        payload_path = PROOF_RUNS / record["meeting_key"] / "final-report.json"
        payload = read_json(payload_path, {})
        for row in payload.get("rows") or []:
            title_key = normalized_key(title_for(row))
            if title_key and title_key in seen_titles:
                continue
            if title_key:
                seen_titles.add(title_key)
            tracker_row = dict(row)
            label = f'{record["meeting"]} mock report'
            tracker_row["Related Brief"] = f'{label} | {record["period"]}'
            tracker_row["_brief_label"] = label
            tracker_row["_brief_href"] = record["href"]
            tracker_rows.append(tracker_row)
    return tracker_rows


def historical_page(rows, schedule, metadata, weekly_summary=None):
    in_progress_start, in_progress_end = in_progress_period(schedule)
    staging_note = staging_summary_text(weekly_summary or {})
    proof_records = proof_run_records()
    latest_proof = proof_records[0] if proof_records else None
    historical_records = proof_records[1:] if len(proof_records) > 1 else []
    archive_cards = proof_archive_cards(historical_records)
    latest_callout = ""
    if latest_proof:
        latest_callout = (
            f'<section class="latest-archive-callout"><div><span class="status-chip strong">Current latest brief</span>'
            f'<h2>{escape(latest_proof["meeting"])} latest report</h2>'
            f'<p>{escape(latest_proof["period"])} &middot; Data as of: {escape(latest_proof["data_as_of"])}</p></div>'
            f'<a class="btn primary" href="latest-brief.html">Open latest brief</a></section>'
        )
    body = (
        page_header("Historical Briefs", "Brief archive", "Open past market briefs by reporting period. The current latest brief stays separate.")
        + latest_callout
        + '<section class="archive-toolbar"><a class="btn primary" href="latest-brief.html">Latest</a><input type="search" id="archiveSearch" placeholder="Search briefs"></section>'
        + f'<div class="combined-archive-grid"><section><h2>Historical reports</h2><div class="archive-grid">{archive_cards}</div></section>'
        + f'<aside class="combined-timeline"><h2>Upcoming / In progress</h2><div class="timeline-list compact"><article class="timeline-item"><div class="timeline-date"><span>Next meeting</span><b>{escape(display_date(schedule.get("upcoming_meeting_date", "")) or "N/A")}</b></div><div class="timeline-detail"><h3>{escape(in_progress_start or "N/A")} to {escape(in_progress_end or "N/A")}</h3><p>{escape(staging_note)}</p></div></article></div></aside></div>'
    )
    return page_shell("Historical Briefs", "historical", body, rows, schedule, metadata)


def tracker_page(rows, schedule, metadata):
    tracker_rows = tracker_rows_across_briefs(rows)
    body = (
        page_header("Game Tracker", "Games mentioned across briefs", "A structured working view for games, publishers, status, and related brief evidence.")
        + """<section class="tracker-filters control-panel">
  <label>Search <input id="trackerSearch" placeholder="Game, publisher, genre"></label>
  <label>Signal <select id="signalFilter"><option value="">All signals</option><option>Strong Market Signal</option><option>Emerging Market Signal</option></select></label>
  <button type="button" id="clearTrackerFilters">Clear</button>
</section>
<div class="filter-chips"><span>Filters</span><a class="filter-chip" href="latest-brief.html"><span>Open</span>Latest brief</a></div>"""
        + tracker_table(tracker_rows)
    )
    return page_shell("Game Tracker", "tracker", body, rows, schedule, metadata)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_rows_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_data(rows, metadata, schedule, weekly_summary=None, news_context=None):
    DATA.mkdir(parents=True, exist_ok=True)
    metadata = normalized_metadata(metadata, rows)
    write_text(
        DATA / "final-report.json",
        json.dumps(
            {"rows": rows, "metadata": metadata, "schedule": schedule, "staging": weekly_summary or {}, "news_context": news_context or []},
            ensure_ascii=False,
            indent=2,
        ),
    )
    write_text(DOCS_WEEKLY_STAGING_JSON, json.dumps(weekly_staging_payload(weekly_summary or {}, schedule), ensure_ascii=False, indent=2))
    destination = DATA / "final_sg_market_scan_current_workflow.csv"
    write_rows_csv(destination, rows)


def write_assets():
    ASSETS.mkdir(parents=True, exist_ok=True)
    css = ""
    if (STATIC / "dashboard.css").exists():
        css += (STATIC / "dashboard.css").read_text(encoding="utf-8", errors="ignore")
    css += """

/* Static GitHub Pages compatibility layer. Keep generated pages on the legacy dashboard visual system. */
.top-brand span{display:inline-flex}
.top-nav a[aria-current="false"]{background:transparent}
.summary-card.snapshot{border-top:4px solid var(--blue-600)}
.released-games-section .data-table{margin-top:8px}
.news-context-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:14px;margin:10px 0 18px}
.news-context-card{border:1px solid var(--line);background:#FFFFFF;border-radius:14px;padding:16px;display:grid;gap:10px;box-shadow:0 10px 22px rgba(9,30,66,.06)}
.news-context-card h3{margin:0;color:var(--blue-900);font-size:19px;line-height:1.2;overflow-wrap:anywhere}
.news-context-card p{margin:0;color:var(--ink-2);line-height:1.45}
.news-context-card a{font-weight:900;color:var(--blue-600)}
.tracker-filters label{display:grid;gap:6px;color:var(--muted);font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:.05em}
.tracker-filters input,.tracker-filters select{min-width:min(320px,100%)}
.original-title{font-size:13px;color:var(--ink-2)}
.original-title span{display:block}
.methodology a{color:var(--blue-600);font-weight:900}
.chip-list,.meta-chip-row{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.metric-badge{display:inline-flex;align-items:center;min-height:28px;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:900;line-height:1.2;border:1px solid #D9E2EC;background:#F7FAFC;color:var(--ink-2)}
.metric-badge.strong{background:#EAF1FF;border-color:#BCD4F6;color:var(--blue-900)}
.metric-badge.emerging{background:var(--amber-bg);border-color:#F5C26B;color:#925600}
.metric-badge.neutral{background:#F5F7FA;color:var(--ink-2)}
.muted-value{color:var(--muted);font-size:13px}
.structured-market-chip{display:block}
.structured-block{display:grid;gap:7px;width:100%}
.structured-block h5{margin:0;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.market-row{display:grid;grid-template-columns:34px 34px minmax(76px,1fr) minmax(82px,1fr);gap:7px;align-items:center;font-size:12.5px;line-height:1.25}
.market-row span,.rank-row span{min-width:0}
.market-rank{display:inline-flex;align-items:center;justify-content:center;width:28px;height:24px;border-radius:8px;background:#EAF1FF;color:var(--blue-900);font-weight:900}
.rank-row{display:grid;grid-template-columns:70px minmax(0,1fr);gap:8px;align-items:start;font-size:12.5px;line-height:1.35}
.rank-row b,.market-row b{color:var(--blue-900)}
.stat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;width:100%}
.stat-cell{border:1px solid #D9E2EC;background:#F7FAFC;border-radius:10px;padding:8px;min-width:0}
.stat-cell span,.compact-kv span{display:block;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;font-weight:900}
.stat-cell b{display:block;color:var(--blue-900);font-size:17px;font-variant-numeric:tabular-nums}
.compact-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:10px}
.compact-kv div{border:1px solid var(--line);background:#FAFCFF;border-radius:12px;padding:10px}
.compact-kv b{display:block;color:var(--ink);margin-top:3px;overflow-wrap:anywhere}
.released-table .structured-block{min-width:210px}
.released-table .chip-list{min-width:130px}
.table-view{display:none}
body.table-mode .cards-view{display:none}
body.table-mode .table-view{display:block}
@media(max-width:520px){.market-row{grid-template-columns:32px 34px 1fr}.market-row span:last-child{grid-column:3}.stat-grid{grid-template-columns:1fr}}

/* Professional dashboard responsive pass */
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:hidden}
body{background:var(--bg);color:var(--ink);text-rendering:optimizeLegibility}
.top-nav-shell{display:block!important;min-height:100vh;background:var(--bg)}
.site-header{position:sticky!important;top:0!important;z-index:50!important;display:grid!important;grid-template-columns:minmax(210px,280px) minmax(0,1fr)!important;gap:18px!important;align-items:center!important;min-height:60px!important;padding:10px clamp(16px,2vw,28px)!important;background:var(--blue-900)!important;box-shadow:0 8px 22px rgba(9,30,66,.14)!important;overflow:visible!important}
.top-brand{min-width:0!important;display:grid!important;gap:2px!important}
.top-brand h1{font-size:clamp(15px,1.2vw,18px)!important;line-height:1.05!important;margin:0!important}
.top-brand p{font-size:12px!important;line-height:1.2!important;margin:0!important;color:#DCE8F7!important}
.top-brand span{display:none!important}
.top-nav{display:flex!important;justify-content:flex-end!important;align-items:center!important;gap:7px!important;flex-wrap:wrap!important;overflow:visible!important;padding:0!important;white-space:normal!important;scrollbar-width:none!important}
.top-nav a{flex:0 0 auto!important;min-height:34px!important;max-width:100%!important;padding:8px 11px!important;border-radius:999px!important;font-size:12.5px!important;line-height:1!important;white-space:nowrap!important}
.workspace{min-width:0!important;width:100%!important}
.slim-context-bar,.compact-topbar{position:sticky!important;top:60px!important;z-index:40!important;display:flex!important;justify-content:space-between!important;align-items:center!important;gap:12px!important;min-height:46px!important;padding:8px clamp(16px,2vw,28px)!important;background:#FFFFFFF7!important;backdrop-filter:blur(8px)!important}
.inline-context{display:flex!important;align-items:center!important;gap:8px!important;flex-wrap:wrap!important;min-width:0!important;font-size:13px!important;line-height:1.3!important}
.inline-context b{font-size:13.5px!important;color:var(--blue-900)!important}
.inline-context span{white-space:nowrap!important;color:var(--ink-2)!important}
.compact-actions{display:flex!important;gap:7px!important;flex:0 0 auto!important}
.compact-actions .btn{min-height:32px!important;padding:6px 10px!important;border-radius:9px!important;font-size:12.5px!important}
main#main-content{width:100%!important;max-width:1480px!important;margin:0 auto!important;padding:clamp(16px,2vw,28px)!important}
.page-header{display:flex!important;align-items:flex-end!important;justify-content:space-between!important;gap:18px!important;margin:0 0 16px!important}
.page-header>div:first-child{flex:1 1 620px!important;min-width:0!important}
.page-header em{font-size:11px!important;letter-spacing:.08em!important}
.page-header h1{font-size:clamp(28px,2.5vw,36px)!important;line-height:1.08!important;margin:4px 0 6px!important}
.page-header p{font-size:clamp(14px,1.15vw,16px)!important;line-height:1.45!important;max-width:820px!important}
.page-actions{display:flex!important;justify-content:flex-end!important;align-items:center!important;gap:8px!important;flex-wrap:wrap!important}
.summary-card-grid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(210px,1fr))!important;gap:12px!important;margin:14px 0 16px!important;align-items:stretch!important}
.summary-card{min-height:118px!important;border-radius:14px!important;padding:15px!important}
.summary-card h3{font-size:clamp(18px,1.4vw,21px)!important;line-height:1.2!important;margin:8px 0 6px!important;overflow-wrap:anywhere!important}
.summary-card p{font-size:13.5px!important;line-height:1.35!important}
.brief-section{border-radius:16px!important;padding:clamp(16px,1.6vw,22px)!important;margin:16px 0!important}
.section-heading{display:flex!important;justify-content:space-between!important;align-items:center!important;gap:16px!important;margin-bottom:16px!important;padding-bottom:13px!important}
.section-heading>div{min-width:0!important;flex:1 1 520px!important}
.section-heading h2{font-size:clamp(21px,1.7vw,25px)!important;line-height:1.15!important}
.section-heading p{font-size:14px!important;line-height:1.45!important}
.view-toggle{flex:0 0 auto!important;align-self:center!important}
.view-toggle a{white-space:nowrap!important}
.executive-bullets{font-size:15px!important;line-height:1.55!important;display:grid!important;gap:8px!important}
.signal-grid,.signal-grid.emerging-grid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr))!important;gap:14px!important;align-items:stretch!important}
.signal-heading{display:flex!important;justify-content:space-between!important;gap:10px!important;align-items:flex-end!important;margin:18px 0 10px!important}
.signal-heading span{font-size:13px!important;line-height:1.35!important;text-align:right!important}
.signal-card{height:auto!important;min-height:0!important;border-radius:15px!important;padding:16px!important;gap:13px!important;box-shadow:0 10px 22px rgba(9,30,66,.07)!important}
.signal-card h3{font-size:clamp(20px,1.5vw,23px)!important;line-height:1.15!important}
.publisher-line{font-size:14.5px!important;line-height:1.3!important}
.meta-chip-row{margin-top:10px!important}
.card-block{padding-top:11px!important}
.card-block h4{font-size:11px!important;margin-bottom:8px!important}
.market-chip-row{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(230px,1fr))!important;gap:10px!important;align-items:stretch!important}
.market-chip{display:block!important;min-height:0!important;border-radius:12px!important;padding:11px!important;overflow:hidden!important}
.market-chip small{margin-bottom:7px!important}
.market-row{grid-template-columns:34px 34px minmax(72px,1fr) minmax(86px,1fr)!important;gap:6px!important;font-size:12px!important}
.rank-row{grid-template-columns:64px minmax(0,1fr)!important;font-size:12px!important}
.stat-cell{padding:8px!important}
.stat-cell b{font-size:16px!important}
.data-table{width:100%!important;max-width:100%!important;overflow-x:auto!important;overflow-y:visible!important;border-radius:14px!important;margin-top:10px!important}
.data-table table{width:100%!important;min-width:1080px!important;border-collapse:separate!important;border-spacing:0!important}
.released-table table{min-width:1180px!important}
.data-table th{position:sticky!important;top:0!important;z-index:2!important;white-space:nowrap!important;font-size:11px!important;padding:10px 11px!important}
.data-table td{font-size:13px!important;line-height:1.4!important;padding:11px!important}
.data-table td:first-child{min-width:180px!important}
.data-table th:nth-child(4),.data-table td:nth-child(4){min-width:142px!important}
.data-table th:nth-child(5),.data-table td:nth-child(5){min-width:142px!important}
.data-table th:nth-child(11),.data-table td:nth-child(11){min-width:240px!important}
.data-table th:nth-child(12),.data-table td:nth-child(12){min-width:210px!important}
.data-table td:nth-child(4) .metric-badge{white-space:nowrap!important}
.released-table .structured-block{min-width:190px!important}
.released-table .market-row{grid-template-columns:30px 30px minmax(68px,1fr) minmax(76px,1fr)!important}
.archive-toolbar,.tracker-filters{display:flex!important;align-items:end!important;gap:10px!important;flex-wrap:wrap!important;border-radius:14px!important;padding:12px!important;margin-bottom:16px!important}
.tracker-filters input,.tracker-filters select,.archive-toolbar input{min-width:min(280px,100%)!important}
.latest-archive-callout{display:flex!important;justify-content:space-between!important;align-items:center!important;gap:16px!important;background:#fff!important;border:1px solid var(--line)!important;border-left:5px solid var(--magenta)!important;border-radius:16px!important;padding:18px!important;box-shadow:var(--shadow)!important;margin:0 0 16px!important}
.latest-archive-callout h2{margin:8px 0 4px!important;color:var(--blue-900)!important;font-size:22px!important;line-height:1.2!important}
.latest-archive-callout p{margin:0!important;color:var(--muted)!important;line-height:1.4!important}
.combined-archive-grid{display:grid!important;grid-template-columns:minmax(0,1fr) minmax(280px,360px)!important;gap:16px!important;align-items:start!important}
.archive-grid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr))!important;gap:14px!important}
.archive-card{border-radius:15px!important;padding:18px!important;min-width:0!important}
.archive-card.reading-card{display:grid!important;grid-template-columns:minmax(0,1fr)!important;align-items:start!important;gap:14px!important}
.archive-card .archive-main{min-width:0!important}
.archive-card .archive-main h3{font-size:21px!important;line-height:1.2!important;margin:8px 0 6px!important;overflow-wrap:anywhere!important}
.archive-card .archive-main p{font-size:15px!important;line-height:1.45!important;margin:0!important;color:var(--muted)!important}
.archive-card .archive-meta{display:flex!important;flex-wrap:wrap!important;align-items:center!important;gap:9px!important;min-width:0!important;color:var(--muted)!important}
.archive-card .archive-meta span{display:inline-flex!important;white-space:normal!important;line-height:1.35!important;min-width:0!important}
.archive-card .archive-meta .btn{margin-top:2px!important;white-space:nowrap!important}
.combined-timeline{position:sticky!important;top:122px!important;border-radius:15px!important}
.compact-kv{grid-template-columns:repeat(auto-fit,minmax(120px,1fr))!important}
.filter-chips{margin:8px 0 12px!important}
@media(max-width:1366px){
  main#main-content{max-width:1240px!important}
  .site-header{grid-template-columns:minmax(180px,230px) minmax(0,1fr)!important;gap:12px!important}
  .top-nav{gap:5px!important}
  .top-nav a{font-size:11.8px!important;padding:7px 8px!important}
  .summary-card-grid{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))!important}
  .market-chip-row{grid-template-columns:repeat(auto-fit,minmax(210px,1fr))!important}
}
@media(max-width:1100px){
  .site-header{grid-template-columns:1fr!important;gap:9px!important}
  .top-nav{justify-content:flex-start!important;overflow-x:auto!important;flex-wrap:nowrap!important;padding-bottom:2px!important}
  .slim-context-bar,.compact-topbar{top:104px!important;align-items:flex-start!important}
  .combined-archive-grid{grid-template-columns:1fr!important}
  .combined-timeline{position:relative!important;top:auto!important}
}
@media(max-width:820px){
  .site-header{position:relative!important}
  .top-nav{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;overflow:visible!important;white-space:normal!important}
  .top-nav a{width:100%!important;white-space:normal!important;line-height:1.15!important;text-align:center!important;min-height:40px!important}
  .slim-context-bar,.compact-topbar{position:relative!important;top:auto!important;display:grid!important;grid-template-columns:1fr!important}
  .inline-context{display:block!important}
  .inline-context b,.inline-context span{display:inline!important;white-space:normal!important}
  .latest-archive-callout{display:grid!important;grid-template-columns:1fr!important}
  .compact-actions{display:grid!important;grid-template-columns:1fr 1fr!important;width:100%!important}
  main#main-content{padding:14px!important}
  .page-header{display:block!important}
  .page-actions{justify-content:flex-start!important;margin-top:12px!important}
  .section-heading{display:block!important}
  .section-heading .view-toggle{margin-top:12px!important}
  .signal-heading{display:block!important}
  .signal-heading span{text-align:left!important;display:block!important;margin-top:4px!important}
  .market-chip-row,.summary-card-grid{grid-template-columns:1fr!important}
  .archive-card.reading-card{grid-template-columns:1fr!important}
  .data-table{margin-left:0!important;margin-right:0!important}
  .archive-toolbar .btn,.archive-toolbar input{width:100%!important}
}
@media(max-width:520px){
  .top-nav{grid-template-columns:1fr!important}
  .compact-actions{grid-template-columns:1fr!important}
  .page-header h1{font-size:25px!important}
  .brief-section{padding:13px!important;border-radius:14px!important}
  .market-row{grid-template-columns:30px 34px minmax(0,1fr)!important}
  .market-row span:last-child{grid-column:3!important}
  .stat-grid{grid-template-columns:1fr!important}
  .view-toggle{display:grid!important;grid-template-columns:1fr 1fr!important;width:100%!important}
}
"""
    write_text(ASSETS / "static-dashboard.css", css)
    write_text(
        ASSETS / "static-dashboard.js",
        """document.addEventListener('DOMContentLoaded',()=>{const params=new URLSearchParams(location.search);const current=params.get('view')==='table'?'table':'cards';if(current==='table'){document.body.classList.add('table-mode')}document.querySelectorAll('.view-toggle a').forEach(link=>{const url=new URL(link.href,location.href);const mode=url.searchParams.get('view')==='table'?'table':'cards';if(mode===current){link.classList.add('active');link.setAttribute('aria-current','true')}else{link.classList.remove('active');link.setAttribute('aria-current','false')}});const search=document.getElementById('trackerSearch');const signal=document.getElementById('signalFilter');const clear=document.getElementById('clearTrackerFilters');function filterRows(){const q=(search&&search.value||'').toLowerCase();const sig=(signal&&signal.value||'').toLowerCase();document.querySelectorAll('.data-table tbody tr').forEach(row=>{const text=row.textContent.toLowerCase();const okText=!q||text.includes(q);const okSig=!sig||text.includes(sig);row.style.display=okText&&okSig?'':'none'})}if(search)search.addEventListener('input',filterRows);if(signal)signal.addEventListener('change',filterRows);if(clear)clear.addEventListener('click',()=>{if(search)search.value='';if(signal)signal.value='';filterRows()})});""",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export the static IBD dashboard.")
    parser.add_argument("--meeting-date", help="Use a specific meeting_pack date, for example 2026-08-04.")
    args = parser.parse_args(argv)

    weekly_summary = source_weekly_summary()
    metadata = source_metadata()
    schedule = read_json(SCHEDULE, {})
    if args.meeting_date:
        schedule = dict(schedule)
        schedule["upcoming_meeting_date"] = args.meeting_date
    rows = source_report_rows(metadata, schedule)
    news_context = source_news_context(rows, schedule)
    DOCS.mkdir(parents=True, exist_ok=True)
    write_assets()
    write_data(rows, metadata, schedule, weekly_summary, news_context)
    latest_cards = latest_page(rows, schedule, metadata, "cards", news_context)
    write_text(DOCS / "index.html", latest_cards)
    write_text(DOCS / "latest-brief.html", latest_cards)
    write_text(DOCS / "historical-briefs.html", historical_page(rows, schedule, metadata, weekly_summary))
    write_text(DOCS / "game-tracker.html", tracker_page(rows, schedule, metadata))
    print(f"Static dashboard exported to {DOCS}")


if __name__ == "__main__":
    main()
