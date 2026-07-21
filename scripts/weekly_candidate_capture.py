import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from candidate_store import upsert_from_current_outputs


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_JSON = ROOT / "data" / "output" / "weekly_candidate_capture_summary.json"


LAYER_COMMANDS = [
    ("Layer 1 candidate discovery", "scripts/layer1_sg_rankings_only_candidates.py"),
    ("Layer 2 unified app mapping", "scripts/layer2_enrich_unified_apps.py"),
    ("Layer 3 metadata cache/fetch", "scripts/layer3_fetch_app_metadata.py"),
    ("Layer 3.5 title normalisation", "scripts/layer3_5_title_normalise.py"),
]


def run_script(label, script):
    print(f"Running {label}...")
    result = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
        text=True,
    )
    if result.returncode:
        raise SystemExit(f"{label} failed.")


def write_summary(current_rows, store_rows, snapshot, source):
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "new_or_seen_candidates": len(current_rows),
        "permanent_candidate_store_rows": len(store_rows),
        "snapshot": str(snapshot),
        "empty_message": "No weekly candidates found for this extraction window." if not current_rows else "",
    }
    with SUMMARY_JSON.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return SUMMARY_JSON


def main():
    parser = argparse.ArgumentParser(
        description="Capture weekly SG Top Grossing x Released Days Ago WW candidates into the permanent local store."
    )
    parser.add_argument(
        "--from-existing-outputs",
        action="store_true",
        help="Do not call Sensor Tower. Upsert the candidate store from current Layer 2/3.5 output files only.",
    )
    args = parser.parse_args()

    if not args.from_existing_outputs:
        for label, script in LAYER_COMMANDS:
            run_script(label, script)

    current_rows, store_rows, snapshot = upsert_from_current_outputs()
    summary = write_summary(
        current_rows,
        store_rows,
        snapshot,
        "existing_outputs" if args.from_existing_outputs else "live_weekly_capture",
    )
    print("Weekly candidate capture complete.")
    print(f"New/seen candidates in this capture: {len(current_rows)}")
    print(f"Permanent candidate store rows: {len(store_rows)}")
    print(f"Snapshot: {snapshot}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
