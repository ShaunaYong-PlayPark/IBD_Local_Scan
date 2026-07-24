import csv
import json

import layer3_5_title_normalise as title_normalise
import candidate_store
import weekly_candidate_capture
import export_static_dashboard
from test_temp_utils import repo_temp_dir


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def read_header(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle).fieldnames or [])


def main():
    original_paths = {
        "input": title_normalise.INPUT,
        "output": title_normalise.OUTPUT,
        "output_json": title_normalise.OUTPUT_JSON,
        "layer2": title_normalise.LAYER2_INPUT,
        "summary": weekly_candidate_capture.SUMMARY_JSON,
        "candidate_config": candidate_store.CONFIG_PATH,
        "candidate_layer2": candidate_store.LAYER2_CSV,
        "candidate_layer3_5": candidate_store.LAYER3_5_CSV,
        "candidate_layer3": candidate_store.LAYER3_CSV,
        "candidate_store_csv": candidate_store.CANDIDATE_STORE_CSV,
        "candidate_snapshot_dir": candidate_store.SNAPSHOT_DIR,
    }

    with repo_temp_dir("ibd_zero_candidate_test_") as tmp_path:
        layer2 = tmp_path / "layer2_unified_candidates.csv"
        layer3_input = tmp_path / "layer3_unique_game_metadata.csv"
        layer3_output = tmp_path / "layer3_5_title_normalised_metadata.csv"
        layer3_json = tmp_path / "layer3_5_title_normalised_metadata.json"
        summary_json = tmp_path / "weekly_candidate_capture_summary.json"
        config_json = tmp_path / "settings.json"
        candidate_store_csv = tmp_path / "weekly_candidate_store.csv"
        snapshot_dir = tmp_path / "snapshots"

        layer2.write_text("unified_app_id,unified_app_name\n", encoding="utf-8")
        config_json.write_text('{"ranking_date":"2026-07-21"}', encoding="utf-8")

        title_normalise.INPUT = layer3_input
        title_normalise.OUTPUT = layer3_output
        title_normalise.OUTPUT_JSON = layer3_json
        title_normalise.LAYER2_INPUT = layer2
        weekly_candidate_capture.SUMMARY_JSON = summary_json
        candidate_store.CONFIG_PATH = config_json
        candidate_store.LAYER2_CSV = layer2
        candidate_store.LAYER3_5_CSV = layer3_output
        candidate_store.LAYER3_CSV = layer3_input
        candidate_store.CANDIDATE_STORE_CSV = candidate_store_csv
        candidate_store.SNAPSHOT_DIR = snapshot_dir

        title_normalise.main()
        assert_true(layer3_output.exists(), "Layer 3.5 should write an empty CSV.")
        assert_true(layer3_json.exists(), "Layer 3.5 should write an empty JSON file.")
        assert_true(json.loads(layer3_json.read_text(encoding="utf-8")) == [], "Layer 3.5 JSON should be empty list.")
        header = read_header(layer3_output)
        assert_true("english_display_title" in header, "Empty CSV should include title fields.")
        assert_true("title_needs_review" in header, "Empty CSV should include review field.")

        current_rows, store_rows, snapshot = weekly_candidate_capture.upsert_from_current_outputs()
        assert_true(current_rows == [], "Weekly capture upsert should return zero current rows.")
        assert_true(store_rows == [], "Empty permanent store should remain empty.")
        assert_true(candidate_store_csv.exists(), "Weekly capture should create empty candidate store CSV.")
        assert_true(snapshot.exists(), "Weekly capture should create empty snapshot CSV.")

        weekly_candidate_capture.write_summary([], [], tmp_path / "snapshot.csv", "test")
        summary = json.loads(summary_json.read_text(encoding="utf-8"))
        assert_true(summary["new_or_seen_candidates"] == 0, "Summary should record zero candidates.")
        assert_true(
            summary["empty_message"] == "No weekly candidates found for this extraction window.",
            "Summary should include dashboard empty-state text.",
        )

        empty_html = export_static_dashboard.executive_summary([])
        assert_true(
            "No weekly candidates found for this extraction window." in empty_html,
            "Dashboard empty state should be rendered for zero rows.",
        )

    title_normalise.INPUT = original_paths["input"]
    title_normalise.OUTPUT = original_paths["output"]
    title_normalise.OUTPUT_JSON = original_paths["output_json"]
    title_normalise.LAYER2_INPUT = original_paths["layer2"]
    weekly_candidate_capture.SUMMARY_JSON = original_paths["summary"]
    candidate_store.CONFIG_PATH = original_paths["candidate_config"]
    candidate_store.LAYER2_CSV = original_paths["candidate_layer2"]
    candidate_store.LAYER3_5_CSV = original_paths["candidate_layer3_5"]
    candidate_store.LAYER3_CSV = original_paths["candidate_layer3"]
    candidate_store.CANDIDATE_STORE_CSV = original_paths["candidate_store_csv"]
    candidate_store.SNAPSHOT_DIR = original_paths["candidate_snapshot_dir"]
    print("ZERO_CANDIDATE_WEEKLY_CAPTURE_PASS")


if __name__ == "__main__":
    main()
