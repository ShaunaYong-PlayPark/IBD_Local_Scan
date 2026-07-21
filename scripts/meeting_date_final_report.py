import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
EXTRACTION_METADATA_PATH = ROOT / "data" / "local_app" / "extraction_metadata.json"


STEPS = [
    ("Prepare report-period candidates from local store", "scripts/prepare_report_period_candidates.py"),
    ("Refresh SG Top Free/Top Grossing ranks for stored candidates", "scripts/refresh_report_period_ranks.py"),
    ("Fetch SEA6 revenue/download metrics for stored candidates", "scripts/layer4_fetch_sea6_sales_metrics.py"),
    ("Build dashboard final report CSV", "scripts/current_report_watchlist_workflow.py"),
]


def run_script(label, script):
    print(f"Running {label}...")
    result = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT), text=True)
    if result.returncode:
        raise SystemExit(f"{label} failed.")


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_successful_sensor_tower_refresh_metadata():
    config = load_config()
    EXTRACTION_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if EXTRACTION_METADATA_PATH.exists():
        with EXTRACTION_METADATA_PATH.open("r", encoding="utf-8-sig") as handle:
            metadata = json.load(handle)
    else:
        metadata = {}
    metadata.update({
        "sensor_tower_data_as_of_date": config.get("report_end_date", ""),
        "last_successful_sensor_tower_refresh_at": datetime.now(timezone.utc).isoformat(),
        "last_successful_sensor_tower_report_start_date": config.get("report_start_date", ""),
        "last_successful_sensor_tower_report_end_date": config.get("report_end_date", ""),
        "updated_by": "scripts/meeting_date_final_report.py",
    })
    with EXTRACTION_METADATA_PATH.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)


def main():
    for label, script in STEPS:
        run_script(label, script)
    write_successful_sensor_tower_refresh_metadata()
    print("Meeting-date final report workflow complete.")


if __name__ == "__main__":
    main()
