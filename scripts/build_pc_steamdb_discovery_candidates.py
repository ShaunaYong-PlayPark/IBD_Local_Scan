import argparse
import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MEETING_DROP_ROOT = ROOT / "data" / "input" / "meeting_drop"
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"

PC_MEETING_FIELDS = [
    "meeting_date",
    "report_start_date",
    "report_end_date",
    "source_kind",
    "source_filter_note",
    "steamdb_week",
    "source_file",
    "source_url",
    "pc_title",
    "normalized_pc_title",
    "steam_app_id",
    "steam_url",
    "release_date",
    "steamdb_peak",
    "steamdb_reviews",
    "steamdb_price",
    "pc_main_report_candidate",
    "pc_appendix_candidate",
    "pc_report_reason",
    "matched_mobile_main_game",
    "matched_mobile_unified_id",
    "match_method",
    "exclude_reason",
    "needs_internet_enrichment",
    "manual_notes",
]

MOBILE_MAIN_FIELDS = [
    "report_start_date",
    "report_end_date",
    "unified_name",
    "english_report_name",
    "unified_id",
]

JUNK_PATTERNS = [
    ("dlc_only", re.compile(r"\b(dlc|expansion pass|season pass|add[- ]?on)\b", re.I)),
    ("demo_only", re.compile(r"\b(demo|playtest)\b", re.I)),
    ("soundtrack", re.compile(r"\b(soundtrack|ost)\b", re.I)),
    ("software_tool", re.compile(r"\b(editor|sdk|tool|utility|software|server)\b", re.I)),
    ("hardware_peripheral", re.compile(r"\b(controller|keyboard|mouse|headset|peripheral|hardware)\b", re.I)),
    ("adult_spam", re.compile(r"\b(hentai|adult only|nsfw|18\+)\b", re.I)),
    ("old_rerelease_no_clear_launch_angle", re.compile(r"\b(remaster|remastered|anniversary edition|classic edition)\b", re.I)),
]

SOURCE_KIND_WEEKLY = "weekly"
SOURCE_KIND_TOP_RELEASES = "top_releases"
TOP_RELEASES_FILTER_SUFFIX = "game_rpg"


def normalize_title(value):
    text = str(value or "").lower()
    text = re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value):
    text = str(value or "").strip()
    if not text:
        return 0
    text = text.replace(",", "").replace("+", "").replace("$", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0
    return int(float(match.group(0)))


def parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %B, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text[:30], fmt).date()
        except ValueError:
            pass
    match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            return None
    return None


def parse_release_date(value, fallback_year=None):
    parsed = parse_date(value)
    if parsed:
        return parsed

    text = str(value or "").strip()
    if not text or not fallback_year:
        return None
    text = re.sub(r"\s+", " ", text)
    for fmt in ("%d %b", "%d %B", "%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(text[:20], fmt).date()
            return parsed.replace(year=fallback_year)
        except ValueError:
            pass
    return None


def steamdb_week_year(steamdb_week):
    match = re.search(r"\b(20\d{2})W\d{1,2}\b", str(steamdb_week or ""))
    return int(match.group(1)) if match else None


def parse_data_sort_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10}", text):
        return datetime.fromtimestamp(int(text), tz=timezone.utc).date()
    if re.fullmatch(r"\d{13}", text):
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc).date()
    return parse_date(text)


def read_csv(path, required_fields):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in required_fields if field not in (reader.fieldnames or [])]
        if missing:
            raise RuntimeError(f"CSV missing required columns: {', '.join(missing)}")
        return list(reader)


def write_csv(path, rows, fields=PC_MEETING_FIELDS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


class SteamDBTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = None
        self.current_cell = None
        self.in_cell = False
        self.current_link = None
        self.current_link_info = None
        self.current_row_app_id = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.current_row = []
            self.current_row_app_id = attrs.get("data-appid", "")
        elif tag in {"td", "th"} and self.current_row is not None:
            self.in_cell = True
            self.current_cell = {
                "text": [],
                "attrs": " ".join(str(value) for value in attrs.values() if value),
                "data_sort": attrs.get("data-sort", ""),
                "is_header": tag == "th",
                "app_id": self.current_row_app_id,
                "app_title": "",
                "links": [],
            }
        elif tag == "a" and self.in_cell and self.current_cell is not None:
            href = attrs.get("href", "")
            match = re.search(r"/app/(\d+)", href)
            if match:
                self.current_link = []
                self.current_link_info = {
                    "app_id": match.group(1),
                    "class": attrs.get("class", ""),
                    "href": href,
                    "text": "",
                }
                if not self.current_cell["app_id"]:
                    self.current_cell["app_id"] = match.group(1)

    def handle_data(self, data):
        if self.in_cell and self.current_cell is not None:
            self.current_cell["text"].append(data)
            if self.current_link is not None:
                self.current_link.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None and self.current_cell is not None:
            link_text = clean_text("".join(self.current_link))
            self.current_link_info["text"] = link_text
            self.current_cell["links"].append(self.current_link_info)
            if "b" in self.current_link_info["class"].split():
                self.current_cell["app_title"] = link_text
                self.current_cell["app_id"] = self.current_link_info["app_id"]
            self.current_link = None
            self.current_link_info = None
        elif tag in {"td", "th"} and self.current_row is not None and self.current_cell is not None:
            self.current_cell["text"] = clean_text(" ".join(self.current_cell["text"]))
            self.current_row.append(self.current_cell)
            self.current_cell = None
            self.in_cell = False
        elif tag == "tr" and self.current_row is not None:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = None
            self.current_row_app_id = ""


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def header_index(headers, patterns):
    for index, header in enumerate(headers):
        value = header.lower()
        if any(pattern in value for pattern in patterns):
            return index
    return None


def cell_value(cells, index):
    if index is None or index >= len(cells):
        return ""
    cell = cells[index]
    return clean_text(f"{cell.get('text', '')} {cell.get('attrs', '')}")


def preferred_app_cell(cells):
    fallback = None
    for cell in cells:
        for link in cell.get("links", []):
            if re.search(r"(^|\s)b(\s|$)", link.get("class", "")) and link.get("text"):
                return {
                    "app_id": cell.get("app_id") or link.get("app_id", ""),
                    "app_title": link.get("text", ""),
                    "text": cell.get("text", ""),
                }
            if link.get("app_id") and fallback is None:
                fallback = {
                    "app_id": cell.get("app_id") or link.get("app_id", ""),
                    "app_title": link.get("text", ""),
                    "text": cell.get("text", ""),
                }
        if cell.get("app_id") and fallback is None:
            fallback = cell
    return fallback


def parse_steamdb_table(html, steamdb_week=None):
    parser = SteamDBTableParser()
    parser.feed(html)

    headers = []
    parsed = []
    fallback_year = steamdb_week_year(steamdb_week)
    for cells in parser.rows:
        app_cell = preferred_app_cell(cells)
        if not app_cell:
            if not headers and any(cell.get("is_header") for cell in cells):
                headers = [cell["text"] for cell in cells]
            continue

        title = app_cell.get("app_title") or app_cell.get("text")
        release_index = header_index(headers, ["release", "date"])
        peak_index = header_index(headers, ["peak", "players"])
        reviews_index = header_index(headers, ["review"])
        price_index = header_index(headers, ["price"])

        release_cell = cells[release_index] if release_index is not None and release_index < len(cells) else {}
        release_date = parse_data_sort_date(release_cell.get("data_sort"))
        date_source = cell_value(cells, release_index) or " ".join(
            f"{cell.get('text', '')} {cell.get('attrs', '')}" for cell in cells
        )
        if not release_date:
            release_date = parse_release_date(date_source, fallback_year)
        numeric_values = [parse_number(cell.get("text")) for cell in cells]
        numeric_values = [value for value in numeric_values if value > 0]
        peak = parse_number(cell_value(cells, peak_index))
        if not peak and numeric_values:
            peak = max(numeric_values)

        parsed.append(
            {
                "pc_title": title,
                "steam_app_id": app_cell["app_id"],
                "steam_url": f"https://store.steampowered.com/app/{app_cell['app_id']}/",
                "release_date": release_date.isoformat() if release_date else "",
                "steamdb_peak": str(peak),
                "steamdb_reviews": str(parse_number(cell_value(cells, reviews_index)) or ""),
                "steamdb_price": clean_text(cells[price_index]["text"]) if price_index is not None and price_index < len(cells) else "",
            }
        )
    return parsed


def pc_input_dir(meeting_date):
    return MEETING_DROP_ROOT / meeting_date / "pc"


def source_url_path(meeting_date, steamdb_week):
    return pc_input_dir(meeting_date) / f"steamdb_upcoming_{steamdb_week}_source_url.txt"


def fallback_html_path(meeting_date, steamdb_week):
    return pc_input_dir(meeting_date) / f"steamdb_upcoming_{steamdb_week}.html"


def top_releases_source_stem(report_start, report_end):
    filter_end = report_end + timedelta(days=1)
    return f"steamdb_top_releases_{report_start.isoformat()}_to_{filter_end.isoformat()}_{TOP_RELEASES_FILTER_SUFFIX}"


def top_releases_html_path(meeting_date, report_start, report_end):
    return pc_input_dir(meeting_date) / f"{top_releases_source_stem(report_start, report_end)}.html"


def top_releases_source_url_path(meeting_date, report_start, report_end):
    return pc_input_dir(meeting_date) / f"{top_releases_source_stem(report_start, report_end)}_source_url.txt"


def top_releases_filter_note(report_start, report_end):
    filter_end = report_end + timedelta(days=1)
    return f"SteamDB releases {report_start.isoformat()} to {filter_end.isoformat()}, games only, RPG genre"


def output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "pc_meeting_pack.csv"


def appendix_output_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "pc_appendix.csv"


def mobile_main_report_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / "mobile_main_report.csv"


def read_source_url(meeting_date, steamdb_week):
    path = source_url_path(meeting_date, steamdb_week)
    if not path.exists():
        raise RuntimeError(f"SteamDB source URL file missing: {path}")
    url = path.read_text(encoding="utf-8").strip()
    if not url:
        raise RuntimeError(f"SteamDB source URL file is blank: {path}")
    return url


def fetch_live_html(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def load_steamdb_html(meeting_date, steamdb_week):
    url = read_source_url(meeting_date, steamdb_week)
    try:
        return fetch_live_html(url), url, "live"
    except (OSError, URLError) as exc:
        fallback = fallback_html_path(meeting_date, steamdb_week)
        if fallback.exists():
            return fallback.read_text(encoding="utf-8", errors="replace"), url, fallback.name
        raise RuntimeError(
            f"Live SteamDB fetch failed and fallback HTML is missing. "
            f"URL: {url}; fallback: {fallback}; error: {exc}"
        ) from exc


def load_top_releases_html(meeting_date, report_start, report_end):
    path = top_releases_html_path(meeting_date, report_start, report_end)
    if not path.exists():
        raise RuntimeError(f"SteamDB top releases HTML file missing: {path}")
    source_url_path = top_releases_source_url_path(meeting_date, report_start, report_end)
    source_url = source_url_path.read_text(encoding="utf-8").strip() if source_url_path.exists() else ""
    return path.read_text(encoding="utf-8", errors="replace"), source_url, path.name


def normalize_steamdb_weeks(steamdb_week=None, steamdb_weeks=None):
    values = []
    if steamdb_weeks:
        values.extend(part.strip() for part in str(steamdb_weeks).split(","))
    elif steamdb_week:
        values.append(str(steamdb_week).strip())
    weeks = [value for value in values if value]
    if not weeks:
        raise RuntimeError("Provide --steamdb-week or --steamdb-weeks")
    return weeks


def mobile_title_index(meeting_date):
    rows = read_csv(mobile_main_report_path(meeting_date), MOBILE_MAIN_FIELDS)
    index = {}
    for row in rows:
        for field, method in (
            ("english_report_name", "exact_normalized_english_report_name"),
            ("unified_name", "exact_normalized_unified_name"),
        ):
            key = normalize_title(row.get(field))
            if key:
                index.setdefault(
                    key,
                    {
                        "matched_mobile_main_game": row.get("english_report_name") or row.get("unified_name", ""),
                        "matched_mobile_unified_id": row.get("unified_id", ""),
                        "match_method": method,
                    },
                )
    if not rows:
        raise RuntimeError(f"Mobile main report has no rows: {mobile_main_report_path(meeting_date)}")
    return rows[0]["report_start_date"], rows[0]["report_end_date"], index


def junk_reason(title):
    for reason, pattern in JUNK_PATTERNS:
        if pattern.search(title):
            return reason
    return ""


def classify_pc_row(row, report_start, report_end, mobile_index):
    title_key = normalize_title(row["pc_title"])
    match = mobile_index.get(title_key, {})
    exclude_reason = junk_reason(row["pc_title"])
    release_date = parse_date(row.get("release_date"))
    in_period = bool(release_date and report_start <= release_date <= report_end)
    peak = parse_number(row.get("steamdb_peak"))

    base = {
        "matched_mobile_main_game": match.get("matched_mobile_main_game", ""),
        "matched_mobile_unified_id": match.get("matched_mobile_unified_id", ""),
        "match_method": match.get("match_method", ""),
        "exclude_reason": exclude_reason,
        "needs_internet_enrichment": "true",
        "manual_notes": "",
    }
    if exclude_reason:
        base.update(
            {
                "pc_main_report_candidate": "false",
                "pc_appendix_candidate": "false",
                "pc_report_reason": f"excluded_{exclude_reason}",
            }
        )
    elif match:
        base.update(
            {
                "pc_main_report_candidate": "true",
                "pc_appendix_candidate": "false",
                "pc_report_reason": "matched_mobile_main_game",
            }
        )
    elif in_period and peak >= 10000:
        base.update(
            {
                "pc_main_report_candidate": "true",
                "pc_appendix_candidate": "false",
                "pc_report_reason": "steamdb_peak_above_10000_in_report_period",
            }
        )
    else:
        base.update(
            {
                "pc_main_report_candidate": "false",
                "pc_appendix_candidate": "true",
                "pc_report_reason": "appendix_global_context_only",
            }
        )
    return base


def dedupe_pc_items(items):
    by_app_id = {}
    for item in items:
        app_id = item.get("steam_app_id", "")
        if not app_id:
            continue
        existing = by_app_id.get(app_id)
        if existing is None or parse_number(item.get("steamdb_peak")) > parse_number(existing.get("steamdb_peak")):
            by_app_id[app_id] = item
    return list(by_app_id.values())


def build(meeting_date, steamdb_week=None, steamdb_weeks=None, source_kind=SOURCE_KIND_WEEKLY):
    report_start_text, report_end_text, mobile_index = mobile_title_index(meeting_date)
    report_start = parse_date(report_start_text)
    report_end = parse_date(report_end_text)
    if not report_start or not report_end:
        raise RuntimeError("Could not parse report period from mobile_main_report.csv")

    parsed_items = []
    source_files = []
    source_filter_note = ""
    if source_kind == SOURCE_KIND_TOP_RELEASES:
        html, source_url, source_file = load_top_releases_html(meeting_date, report_start, report_end)
        source_files.append(source_file)
        source_filter_note = top_releases_filter_note(report_start, report_end)
        for item in parse_steamdb_table(html):
            parsed_items.append(
                {
                    "source_kind": source_kind,
                    "source_filter_note": source_filter_note,
                    "steamdb_week": "",
                    "source_file": source_file,
                    "source_url": source_url,
                    **item,
                }
            )
    elif source_kind == SOURCE_KIND_WEEKLY:
        weeks = normalize_steamdb_weeks(steamdb_week, steamdb_weeks)
        for week in weeks:
            html, source_url, source_file = load_steamdb_html(meeting_date, week)
            source_files.append(source_file)
            for item in parse_steamdb_table(html, week):
                parsed_items.append(
                    {
                        "source_kind": source_kind,
                        "source_filter_note": "",
                        "steamdb_week": week,
                        "source_file": source_file,
                        "source_url": source_url,
                        **item,
                    }
                )
    else:
        raise RuntimeError(f"Unsupported source kind: {source_kind}")

    rows = []
    for item in dedupe_pc_items(parsed_items):
        classified = classify_pc_row(item, report_start, report_end, mobile_index)
        if classified["exclude_reason"]:
            continue
        row = {
            "meeting_date": meeting_date,
            "report_start_date": report_start.isoformat(),
            "report_end_date": report_end.isoformat(),
            "normalized_pc_title": normalize_title(item["pc_title"]),
            **item,
            **classified,
        }
        rows.append(row)

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row["pc_main_report_candidate"] == "true" else 1,
            -parse_number(row["steamdb_peak"]),
            row["pc_title"],
        ),
    )
    out = output_path(meeting_date)
    write_csv(out, rows)
    appendix = [row for row in rows if row["pc_appendix_candidate"] == "true"]
    appendix_out = appendix_output_path(meeting_date)
    write_csv(appendix_out, appendix)
    return out, rows, appendix_out, appendix, ", ".join(source_files)


def main():
    parser = argparse.ArgumentParser(description="Build PC SteamDB discovery candidates.")
    parser.add_argument("--meeting-date", required=True)
    parser.add_argument("--source-kind", choices=[SOURCE_KIND_WEEKLY, "top-releases", SOURCE_KIND_TOP_RELEASES], default=SOURCE_KIND_WEEKLY)
    parser.add_argument("--steamdb-week")
    parser.add_argument("--steamdb-weeks")
    args = parser.parse_args()

    source_kind = SOURCE_KIND_TOP_RELEASES if args.source_kind == "top-releases" else args.source_kind
    if source_kind == SOURCE_KIND_WEEKLY:
        weeks = normalize_steamdb_weeks(args.steamdb_week, args.steamdb_weeks)
        path, rows, appendix_path, appendix, source_file = build(
            args.meeting_date,
            steamdb_weeks=",".join(weeks),
            source_kind=source_kind,
        )
    else:
        weeks = []
        path, rows, appendix_path, appendix, source_file = build(args.meeting_date, source_kind=source_kind)
    main_rows = [row for row in rows if row["pc_main_report_candidate"] == "true"]
    print(f"Meeting date: {args.meeting_date}")
    print(f"Source kind: {source_kind}")
    if weeks:
        print(f"SteamDB weeks: {', '.join(weeks)}")
    print(f"Source used: {source_file}")
    print(f"PC meeting pack rows: {len(rows)}")
    print(f"PC main report rows: {len(main_rows)}")
    print(f"PC appendix rows: {len(appendix)}")
    print(f"Output path: {path}")
    print(f"Appendix output path: {appendix_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PC SteamDB discovery failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
