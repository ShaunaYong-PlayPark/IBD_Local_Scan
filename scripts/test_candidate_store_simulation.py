import candidate_store
from test_temp_utils import repo_temp_dir


TEST_CONFIG = {
    "report_start_date": "2026-07-14",
    "report_end_date": "2026-08-03",
}


def dummy_candidate(uid, title, detected_date, publisher, genre, sg_revenue):
    return {
        "unified_app_id": uid,
        "ios_app_ids": f"ios_{uid}",
        "android_app_ids": f"android.{uid}",
        "title": title,
        "english_display_title": title,
        "original_title": title,
        "publisher": publisher,
        "publisher_id": f"publisher_{uid}",
        "developer": "",
        "genre": genre,
        "category_ids": "",
        "category_labels": genre,
        "platform": "iOS / Android",
        "release_date": "",
        "country_release_date": "",
        "representative_country_release_date": "",
        "release_evidence_date": "",
        "first_detected_date": detected_date,
        "first_detected_timestamp_utc": f"{detected_date}T00:00:00+00:00",
        "latest_extraction_date": detected_date,
        "latest_extraction_timestamp_utc": f"{detected_date}T00:00:00+00:00",
        "latest_ranking_date": detected_date,
        "source_bucket": "Released ~1 week WW",
        "sg_top_grossing_evidence_at_detection": f"{title} appeared in SG Top Grossing during test capture.",
        "sg_chart_matches_at_detection": "SG Top Grossing test evidence",
        "best_sg_rank_at_detection": "10",
        "platforms_seen_in_layer1": "android; ios",
        "all_layer1_app_ids": f"ios_{uid}; android.{uid}",
        "detected_language": "en",
        "machine_english_title": title,
        "manual_english_title": "",
        "display_title": title,
        "translation_source": "test",
        "translation_confidence": "high",
        "translation_review_status": "not_required",
        "translation_note": "",
        "metadata_lookup_status": "test",
        "active": "True",
        "valid_in_sg": "True",
        "raw_app_metadata_json": "{}",
        "raw_unified_app_json": "{}",
        "raw_layer2_rows_json": "[]",
        "detection_history_json": "[]",
        "_test_sg_gross_revenue": str(sg_revenue),
    }


def classify(sg_revenue):
    revenue = float(sg_revenue or 0)
    if revenue > 1000:
        return "Strong Market Signal"
    if revenue > 0:
        return "Watchlist"
    return "Excluded"


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    original_store = candidate_store.CANDIDATE_STORE_CSV

    with repo_temp_dir("ibd_candidate_store_test_") as tmp:
        test_store = tmp / "weekly_candidate_store_test.csv"
        candidate_store.CANDIDATE_STORE_CSV = test_store

        # Duplicate A is intentional: the permanent store should be deduped by unified_app_id.
        rows = [
            dummy_candidate("test_unified_a", "Test Game A", "2026-07-21", "Test Publisher A", "RPG", 1500),
            dummy_candidate("test_unified_a", "Test Game A", "2026-07-21", "Test Publisher A", "RPG", 1500),
            dummy_candidate("test_unified_b", "Test Game B", "2026-07-28", "Test Publisher B", "Strategy", 500),
            dummy_candidate("test_unified_c", "Test Game C", "2026-06-30", "Test Publisher C", "Casual", 2000),
        ]
        deduped = {}
        for row in rows:
            uid = row["unified_app_id"]
            deduped[uid] = candidate_store.merge_candidate(deduped[uid], row) if uid in deduped else row

        candidate_store.write_csv(test_store, sorted(deduped.values(), key=lambda r: r["unified_app_id"]), candidate_store.STORE_FIELDS + ["_test_sg_gross_revenue"])
        selected = candidate_store.select_report_period_candidates(TEST_CONFIG)
        selected_by_id = {row["unified_app_id"]: row for row in selected}

        assert_true(len(deduped) == 3, "Deduped store should contain A, B, C only once each.")
        assert_true(set(selected_by_id) == {"test_unified_a", "test_unified_b"}, "Final period should include A and B only.")
        assert_true("test_unified_c" not in selected_by_id, "C should be excluded because it is outside the report period.")

        a = selected_by_id["test_unified_a"]
        b = selected_by_id["test_unified_b"]
        assert_true(a["publisher"] == "Test Publisher A" and a["genre"] == "RPG", "A metadata should be preserved.")
        assert_true(b["publisher"] == "Test Publisher B" and b["genre"] == "Strategy", "B metadata should be preserved.")
        assert_true(a["ios_app_ids"] and a["android_app_ids"], "A platform IDs should be preserved.")
        assert_true(b["ios_app_ids"] and b["android_app_ids"], "B platform IDs should be preserved.")

        results = {
            "test_file": str(test_store),
            "stored_unique_candidates": len(deduped),
            "selected_for_final_period": sorted(selected_by_id),
            "excluded": ["test_unified_c"],
            "classification": {
                "Test Game A": classify(a["_test_sg_gross_revenue"]),
                "Test Game B": classify(b["_test_sg_gross_revenue"]),
                "Test Game C": classify(deduped["test_unified_c"]["_test_sg_gross_revenue"]),
            },
            "metadata_preserved": {
                "Test Game A": {
                    "publisher": a["publisher"],
                    "genre": a["genre"],
                    "ios_app_ids": a["ios_app_ids"],
                    "android_app_ids": a["android_app_ids"],
                },
                "Test Game B": {
                    "publisher": b["publisher"],
                    "genre": b["genre"],
                    "ios_app_ids": b["ios_app_ids"],
                    "android_app_ids": b["android_app_ids"],
                },
            },
        }
        print("NO_API_CANDIDATE_STORE_SIMULATION_PASS")
        for key, value in results.items():
            print(f"{key}: {value}")

    candidate_store.CANDIDATE_STORE_CSV = original_store
    print(f"production_candidate_store_untouched: {original_store}")


if __name__ == "__main__":
    main()
