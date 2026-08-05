import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PROOF_ROOT = DOCS / "proof-runs"


def parse_iso_date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM-DD: {value}") from exc


def run_step(label, script, *args):
    command = [sys.executable, str(ROOT / "scripts" / script), *args]
    print(f"[{label}] {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, check=True)


def display_date(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(value or "N/A")


def latest_meeting_date(current_meeting_date):
    candidates = [current_meeting_date]
    if PROOF_ROOT.exists():
        for folder in PROOF_ROOT.iterdir():
            if folder.is_dir():
                try:
                    date.fromisoformat(folder.name)
                except ValueError:
                    continue
                candidates.append(folder.name)
    return max(candidates)


def rewrite_proof_html(path, meeting_date, latest_date):
    payload_path = path.parent / "final-report.json"
    if not payload_path.exists():
        payload_path = path.parent / "data" / "final-report.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    first = rows[0] if rows else {}
    period = f'{display_date(first.get("report_start_date"))} to {display_date(first.get("report_end_date"))}'
    meeting = display_date(first.get("meeting_date") or meeting_date)
    data_as_of = display_date((payload.get("metadata") or {}).get("sensor_tower_data_as_of_date") or first.get("report_end_date"))
    ranking_data_as_of = display_date((payload.get("sea_summary") or {}).get("ranking_data_as_of")) or "N/A"
    latest = display_date(latest_date)

    html = path.read_text(encoding="utf-8")
    html = html.replace("<title>Latest Brief | IBD Market Intelligence</title>", "<title>Historical Brief | IBD Market Intelligence</title>")
    html = html.replace('<body class="dashboard-page page-latest">', '<body class="dashboard-page page-historical">')
    html = html.replace('href="assets/static-dashboard.css"', 'href="../../assets/static-dashboard.css"')
    html = html.replace('src="assets/static-dashboard.js"', 'src="../../assets/static-dashboard.js"')
    html = re.sub(
        r'<nav class="top-nav" aria-label="Primary navigation">.*?</nav>',
        '<nav class="top-nav" aria-label="Primary navigation"><a class="" href="../../latest-brief.html" data-tooltip="Read the current executive market update." aria-current="false">Latest Brief</a><a class="on" href="../../historical-briefs.html" data-tooltip="Open past briefs and review meeting schedule." aria-current="page">Brief Archive</a><a class="" href="../../game-tracker.html" data-tooltip="Filter games mentioned across briefs." aria-current="false">Game Tracker</a></nav>',
        html,
        flags=re.S,
    )
    html = re.sub(
        r'<div class="inline-context">.*?</div>',
        f'<div class="inline-context">\n          <b title="Historical Brief | Period: {period} | Meeting: {meeting} | Data as of: {data_as_of}">Historical Brief</b>\n          <span>Historical period: {period}</span>\n          <span>Meeting {meeting}</span>\n          <span>Data {data_as_of}</span>\n          <span>Ranking data {ranking_data_as_of}</span>\n          <span>Latest {latest}</span>\n        </div>',
        html,
        flags=re.S,
    )
    html = re.sub(r'<div><em>Market Brief</em><h1[^>]*>.*?</h1><p[^>]*>.*?</p></div>', f'<div><em>Historical Brief</em><h1 id="market-title">SEA6 Gaming Market</h1><p id="market-subtitle">Historical SEA6 regional view for {period}.</p></div>', html, flags=re.S)
    html = html.replace('href="historical-briefs.html"', 'href="../../historical-briefs.html"')
    html = html.replace('href="game-tracker.html"', 'href="../../game-tracker.html"')
    html = html.replace('href="latest-brief.html"', 'href="../../latest-brief.html"')
    html = html.replace('href="index.html"', 'href="../../latest-brief.html"')
    html = html.replace('href="../../latest-brief.html" aria-current="true">Card view', 'href="./latest-brief.html" aria-current="true">Card view')
    html = html.replace('href="latest-brief.html?view=table"', 'href="./latest-brief.html?view=table"')
    html = html.replace('href="../../latest-brief.html?view=table"', 'href="./latest-brief.html?view=table"')
    path.write_text(html, encoding="utf-8")


def copy_outputs(meeting_date):
    destination = PROOF_ROOT / meeting_date
    destination.mkdir(parents=True, exist_ok=True)
    latest_date = latest_meeting_date(meeting_date)
    copies = {
        DOCS / "data" / "final-report.json": destination / "final-report.json",
        DOCS / "data" / "final_sg_market_scan_current_workflow.csv": destination / "final_sg_market_scan_current_workflow.csv",
        DOCS / "latest-brief.html": destination / "latest-brief.html",
        DOCS / "index.html": destination / "index.html",
    }
    for source, target in copies.items():
        if not source.exists():
            raise RuntimeError(f"Expected export output missing: {source}")
        shutil.copy2(source, target)
        if target.suffix == ".html":
            rewrite_proof_html(target, meeting_date, latest_date)
    print(f"Copied proof outputs to {destination}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a local historical IBD game-layer proof workflow.")
    parser.add_argument("--meeting-date", required=True, type=parse_iso_date)
    parser.add_argument("--report-start", required=True, type=parse_iso_date)
    parser.add_argument("--report-end", required=True, type=parse_iso_date)
    parser.add_argument("--use-public-radar", action="store_true")
    args = parser.parse_args(argv)
    if args.report_start > args.report_end:
        parser.error("--report-start must not be after --report-end")
    meeting_date = args.meeting_date.isoformat()
    report_start = args.report_start.isoformat()
    report_end = args.report_end.isoformat()

    run_step("mobile discovery", "build_mobile_revenue_discovery_candidates.py", "--meeting-date", meeting_date)
    run_step("PC discovery", "build_pc_steamdb_discovery_candidates.py", "--meeting-date", meeting_date, "--source-kind", "top-releases")
    run_step("game report layer", "build_game_report_layer.py", "--meeting-date", meeting_date)
    run_step("game enrichment layer", "build_game_enrichment_layer.py", "--meeting-date", meeting_date)
    news_args = [
        "--meeting-date", meeting_date,
        "--report-start", report_start,
        "--report-end", report_end,
    ]
    if args.use_public_radar:
        news_args.append("--use-public-radar")
    run_step("news context layer", "build_game_news_context_layer.py", *news_args)
    run_step("news context review copy", "build_game_news_context_review.py", "--meeting-date", meeting_date)
    run_step("static dashboard export", "export_static_dashboard.py", "--meeting-date", meeting_date)
    copy_outputs(meeting_date)


if __name__ == "__main__":
    main()
