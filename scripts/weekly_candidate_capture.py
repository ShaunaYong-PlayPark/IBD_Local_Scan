import argparse
import subprocess
import sys
from pathlib import Path

from candidate_store import upsert_from_current_outputs


ROOT = Path(__file__).resolve().parents[1]


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
    print("Weekly candidate capture complete.")
    print(f"New/seen candidates in this capture: {len(current_rows)}")
    print(f"Permanent candidate store rows: {len(store_rows)}")
    print(f"Snapshot: {snapshot}")


if __name__ == "__main__":
    main()
