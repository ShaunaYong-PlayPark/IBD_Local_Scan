import csv
import json
import re
import shutil
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
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
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
        end = parse_date(rows[0].get("report_end_date", ""))
        if end:
            return display_date((end + timedelta(days=1)).isoformat())
    return display_date(schedule.get("upcoming_meeting_date", ""))


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


def data_as_of(metadata):
    value = metadata.get("sensor_tower_data_as_of_date") or metadata.get("last_successful_sensor_tower_report_end_date")
    return display_date(value) or "N/A"


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
          <span>Data as of: {escape(data_as_of(metadata))}</span>
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
            ("risk", "Watchlist focus", "0 monitoring item(s)", "Nothing new to review"),
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
        ("risk", "Watchlist focus", f"{len(emerging)} monitoring item(s)", "Review rank and revenue signals"),
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
        f"{len(strong)} title(s) are classified as Strong Market Signals and {len(emerging)} remain in monitoring.",
        f"{title_for(leader)} leads available SG revenue at {money(leader.get('SG Gross Revenue'))}." if leader else "No lead title is available in the current output.",
    ]
    return f"""<section class="brief-section executive-section">
  <div class="section-heading"><div><h2>Executive Summary</h2><p>Level 1 scan: what changed, why it matters, and where to focus.</p></div></div>
  <ul class="executive-bullets">{''.join(f'<li>{escape(item)}</li>' for item in bullets)}</ul>
</section>"""


def market_chips(row):
    return f"""<div class="market-chip-row">
  <span class="market-chip sg-market"><small>SG Performance</small>{performance_block(row)}</span>
  <span class="market-chip structured-market-chip">{top_markets_block(row.get("Top 3 Markets"))}</span>
  <span class="market-chip structured-market-chip">{ranks_block(row.get("SG App Store Ranks"))}</span>
</div>"""


def signal_card(row, group):
    title = title_for(row)
    original = row.get("Original Title") or row.get("original_title") or ""
    title_note = f'\n    <p class="original-title"><span>Original title</span>{escape(original)}</p>' if original and original != title else ""
    reason = row.get("Market Overview Reason") or row.get("Inclusion Reason") or row.get("Key Details") or "Available in current final report output."
    pill_class = "strong" if group == "strong" else "emerging"
    card_class = "rich-signal-card" if group == "strong" else "rich-signal-card emerging"
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
      <span class="metric-badge neutral">Release {escape(display_date(row.get("Release Date")) or row.get("Release Date") or "N/A")}</span>
    </div>{title_note}
  </div>
  <div class="card-block">
    <h4>Local Performance</h4>
    {market_chips(row)}
  </div>
  <div class="card-block card-evidence">
    <h4>Key Details</h4>
    <p>{escape(reason)}</p>
  </div>
</article>"""


def empty_state(title, desc):
    return f'<article class="empty-state polished-empty"><h3>{escape(title)}</h3><p>{escape(desc)}</p></article>'


def report_table(rows, released=False):
    fields = [
        "Game Title",
        "English Display Title",
        "Original Title",
        "Signal Type",
        "Publisher",
        "Platform",
        "Release Date",
        "Genre",
        "SG Gross Revenue",
        "SG Downloads",
        "Top 3 Markets",
        "SG App Store Ranks",
    ]
    head = "".join(f"<th>{escape(field)}</th>" for field in fields)
    body = "".join(
        "<tr>" + "".join(table_cell(row, field) for field in fields) + "</tr>"
        for row in rows
    )
    empty = f'<tr><td colspan="{len(fields)}">No report rows available.</td></tr>'
    cls = "data-table released-table" if released else "data-table"
    return f'<div class="{cls}"><table><thead><tr>{head}</tr></thead><tbody>{body or empty}</tbody></table></div>'


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
    if field == "Release Date":
        return f'<td><span class="metric-badge neutral">{escape(display_date(value) or str(value or ""))}</span></td>'
    return f"<td>{escape(str(value or ''))}</td>"


def released_games_section(strong, emerging, view):
    active_cards = "active" if view != "table" else ""
    active_table = "active" if view == "table" else ""
    toggle = f"""<div class="view-toggle" aria-label="Released games view">
  <a class="{active_cards}" href="latest-brief.html" aria-current="{"true" if view != "table" else "false"}">Card view</a>
  <a class="{active_table}" href="latest-brief.html?view=table" aria-current="{"true" if view == "table" else "false"}">Compact table</a>
</div>"""
    strong_html = "".join(signal_card(row, "strong") for row in strong) or empty_state("No Strong releases in this brief", "No released-game item currently exceeds the Strong signal threshold for Singapore.")
    emerging_html = "".join(signal_card(row, "emerging") for row in emerging) or empty_state("No Emerging releases in this brief", "No Emerging released-game items are available for this reporting period.")
    return f"""<section class="brief-section released-games-section">
  <div class="section-heading"><div><h2>SG Top Grossing Signals</h2><p>First-observed SG Top Grossing evidence with Sensor Tower-supported revenue, downloads, ranks, and SEA6 market context.</p></div>{toggle}</div>
  <div class="cards-view" data-view="cards">
    <h3 class="signal-heading strong-heading">Strong Market Signals <span>Commercial traction is already visible.</span></h3>
    <div class="signal-grid strong-grid">{strong_html}</div>
    <h3 class="signal-heading emerging-heading">Emerging Market Signals <span>New SG launches worth monitoring.</span></h3>
    <div class="signal-grid emerging-grid">{emerging_html}</div>
  </div>
  <div class="table-view" data-view="table">
    {report_table(strong + emerging, released=True)}
  </div>
</section>"""


def latest_page(rows, schedule, metadata, view="cards"):
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
        + """<details class="methodology"><summary>Methodology and data notes</summary><p>Discovery uses app IDs first observed in SG Games Top Grossing history. Release dates are evidence only and are not discovery gates. Revenue is shown as estimated gross revenue from Sensor Tower where available.</p></details>"""
    )
    return page_shell("Latest Brief", "latest", body, rows, schedule, metadata)


def historical_page(rows, schedule, metadata, weekly_summary=None):
    in_progress_start, in_progress_end = in_progress_period(schedule)
    staging_note = staging_summary_text(weekly_summary or {})
    archive_empty = empty_state(
        "No older finalized briefs yet.",
        "Finalized reports will move here after a newer meeting-day brief replaces them.",
    )
    body = (
        page_header("Historical Briefs", "Brief archive", "Open past market briefs by reporting period.")
        + '<section class="archive-toolbar"><a class="btn primary" href="latest-brief.html">Latest</a><input type="search" id="archiveSearch" placeholder="Search briefs"></section>'
        + f'<div class="combined-archive-grid"><section><h2>Briefs</h2><div class="archive-grid">{archive_empty}</div></section>'
        + f'<aside class="combined-timeline"><h2>Upcoming / In progress</h2><div class="timeline-list compact"><article class="timeline-item"><div class="timeline-date"><span>Next meeting</span><b>{escape(display_date(schedule.get("upcoming_meeting_date", "")) or "N/A")}</b></div><div class="timeline-detail"><h3>{escape(in_progress_start or "N/A")} to {escape(in_progress_end or "N/A")}</h3><p>{escape(staging_note)}</p></div></article></div></aside></div>'
    )
    return page_shell("Historical Briefs", "historical", body, rows, schedule, metadata)


def tracker_page(rows, schedule, metadata):
    body = (
        page_header("Game Tracker", "Games mentioned across briefs", "A structured working view for games, publishers, status, and related brief evidence.")
        + """<section class="tracker-filters control-panel">
  <label>Search <input id="trackerSearch" placeholder="Game, publisher, genre"></label>
  <label>Signal <select id="signalFilter"><option value="">All signals</option><option>Strong Market Signal</option><option>Emerging Market Signal</option></select></label>
  <button type="button" id="clearTrackerFilters">Clear</button>
</section>
<div class="filter-chips"><span>Filters</span><a class="filter-chip" href="latest-brief.html"><span>Open</span>Latest brief</a></div>"""
        + report_table(rows)
    )
    return page_shell("Game Tracker", "tracker", body, rows, schedule, metadata)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def same_path(left, right):
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def write_data(rows, metadata, schedule, weekly_summary=None):
    DATA.mkdir(parents=True, exist_ok=True)
    write_text(DATA / "final-report.json", json.dumps({"rows": rows, "metadata": metadata, "schedule": schedule, "staging": weekly_summary or {}}, ensure_ascii=False, indent=2))
    write_text(DOCS_WEEKLY_STAGING_JSON, json.dumps(weekly_staging_payload(weekly_summary or {}, schedule), ensure_ascii=False, indent=2))
    source = source_finalized_csv(metadata)
    destination = DATA / "final_sg_market_scan_current_workflow.csv"
    if source.exists() and not same_path(source, destination):
        shutil.copy2(source, destination)


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
.combined-archive-grid{display:grid!important;grid-template-columns:minmax(0,1fr) minmax(280px,360px)!important;gap:16px!important;align-items:start!important}
.archive-grid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr))!important;gap:14px!important}
.archive-card{border-radius:15px!important;padding:16px!important}
.archive-card.reading-card{grid-template-columns:minmax(0,1fr) auto!important;align-items:center!important}
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


def main():
    weekly_summary = source_weekly_summary()
    metadata = source_metadata()
    rows = read_csv(source_finalized_csv(metadata))
    schedule = read_json(SCHEDULE, {})
    DOCS.mkdir(parents=True, exist_ok=True)
    write_assets()
    write_data(rows, metadata, schedule, weekly_summary)
    latest_cards = latest_page(rows, schedule, metadata, "cards")
    write_text(DOCS / "index.html", latest_cards)
    write_text(DOCS / "latest-brief.html", latest_cards)
    write_text(DOCS / "historical-briefs.html", historical_page(rows, schedule, metadata, weekly_summary))
    write_text(DOCS / "game-tracker.html", tracker_page(rows, schedule, metadata))
    print(f"Static dashboard exported to {DOCS}")


if __name__ == "__main__":
    main()
