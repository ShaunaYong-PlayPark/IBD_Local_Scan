import argparse
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


def copy_outputs(meeting_date):
    destination = PROOF_ROOT / meeting_date
    destination.mkdir(parents=True, exist_ok=True)
    copies = {
        DOCS / "latest-brief.html": destination / "latest-brief.html",
        DOCS / "index.html": destination / "index.html",
        DOCS / "data" / "final-report.json": destination / "final-report.json",
        DOCS / "data" / "final_sg_market_scan_current_workflow.csv": destination / "final_sg_market_scan_current_workflow.csv",
    }
    for source, target in copies.items():
        if not source.exists():
            raise RuntimeError(f"Expected export output missing: {source}")
        shutil.copy2(source, target)
        if target.suffix == ".html":
            html = target.read_text(encoding="utf-8")
            html = html.replace('href="assets/static-dashboard.css"', 'href="../../assets/static-dashboard.css"')
            html = html.replace('src="assets/static-dashboard.js"', 'src="../../assets/static-dashboard.js"')
            html = html.replace('href="latest-brief.html"', 'href="./latest-brief.html"')
            html = html.replace('href="index.html"', 'href="./index.html"')
            html = html.replace('href="historical-briefs.html"', 'href="../../historical-briefs.html"')
            html = html.replace('href="game-tracker.html"', 'href="../../game-tracker.html"')
            target.write_text(html, encoding="utf-8")
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
