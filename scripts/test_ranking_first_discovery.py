import csv
import urllib.request
from datetime import date

import candidate_store
import layer1_sg_rankings_only_candidates as discovery
import layer2_enrich_unified_apps as layer2
from test_temp_utils import repo_temp_dir


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_raises(expected_text, callback, message):
    try:
        callback()
    except RuntimeError as exc:
        if expected_text not in str(exc):
            raise AssertionError(
                f"{message}: expected error containing {expected_text!r}, got {str(exc)!r}"
            ) from exc
        return
    raise AssertionError(f"{message}: expected RuntimeError")


def fixture_config():
    return {
        "auth_token": "offline-test-token",
        "country": "SG",
        "ranking_date": "2026-07-22",
        "sensor_tower_lag_days": 2,
        "platforms": {
            "ios": {
                "category": "6014",
                "charts": {
                    "topfreeapplications": "Top Free iPhone Apps",
                    "topgrossingapplications": "Top Grossing iPhone Apps",
                },
            },
            "android": {
                "category": "game",
                "charts": {
                    "topselling_free": "Top Free Android Apps",
                    "topgrossing": "Top Grossing Android Apps",
                },
            },
        },
    }


def fixture_known_existing_rows():
    return [
        {
            "platform": "ios",
            "app_id": "ios-known",
            "unified_app_id": "known-unified-ios",
            "unified_name": "Known iOS Game",
            "app_name": "Known iOS Game",
            "first_known_date": "2019-01-01",
            "last_known_date": "2026-01-01",
            "source_file_count": "3",
        },
        {
            "platform": "android",
            "app_id": "android-historical",
            "unified_app_id": "known-cross-platform-unified",
            "unified_name": "Known Cross Platform Game",
            "app_name": "Known Cross Platform Game",
            "first_known_date": "2020-01-01",
            "last_known_date": "2025-01-01",
            "source_file_count": "2",
        },
    ]


def main():
    network_attempts = []
    original_urlopen = urllib.request.urlopen
    original_request_json = discovery.request_json
    original_save_raw = discovery.save_raw
    original_discovery_known_reader = discovery.read_known_existing_games

    def block_urlopen(*args, **kwargs):
        network_attempts.append(("urlopen", args, kwargs))
        raise AssertionError("Network call attempted during offline test.")

    def block_request_json(*args, **kwargs):
        network_attempts.append(("request_json", args, kwargs))
        raise AssertionError("Sensor Tower request attempted during offline test.")

    fixture_rankings = {
        ("ios", "topfreeapplications"): {"ios-new": 4, "ios-seen": 8, "ios-known": 12},
        ("ios", "topgrossingapplications"): {"ios-seen": 10, "ios-known": 15, "ios-new": 20},
        ("android", "topselling_free"): {"android-new": 6},
        ("android", "topgrossing"): {"android-new": 30},
    }
    fetch_calls = []

    def fixture_fetcher(platform, platform_config, chart_type, country, ranking_date, auth_token):
        fetch_calls.append((platform, chart_type, country, ranking_date))
        return fixture_rankings[(platform, chart_type)]

    existing = [
        {
            "run_timestamp_utc": "2026-07-15T00:00:00+00:00",
            "ranking_date": "2026-07-13",
            "country": "SG",
            "platform": "ios",
            "chart_type": "topgrossingapplications",
            "chart_label": "Top Grossing iPhone Apps",
            "app_id": "ios-seen",
            "rank": "12",
        }
    ]

    urllib.request.urlopen = block_urlopen
    discovery.request_json = block_request_json
    try:
        candidates, observations = discovery.build_candidates(
            fixture_config(),
            ranking_fetcher=fixture_fetcher,
            existing_observations=existing,
            known_existing_rows=fixture_known_existing_rows(),
        )

        assert_equal(
            {(row["platform"], row["app_id"]) for row in candidates},
            {("ios", "ios-new"), ("android", "android-new")},
            "Only SG Top Grossing app IDs absent from history should be candidates",
        )
        assert_true(
            ("ios", "ios-known") not in {(row["platform"], row["app_id"]) for row in candidates},
            "Known platform app IDs must be excluded before Layer 2",
        )
        assert_true(
            ("ios", "ios-known") in {(row["platform"], row["app_id"]) for row in observations},
            "Known platform app IDs must still be recorded in SG chart observations",
        )
        assert_true(
            all(row["released_tag_matches"] == "" for row in candidates),
            "Legacy released_tag_matches must remain present and blank",
        )
        assert_true(
            all(discovery.DISCOVERY_SOURCE in row["candidate_reason"] for row in candidates),
            "Candidate reason must identify ranking-first discovery",
        )
        assert_true(
            all("gross" in row["chart_type"].lower() for row in observations),
            "The ledger must contain only Top Grossing observations",
        )
        assert_equal(len(fetch_calls), 4, "Offline fixture should cover configured ranking calls")

        second_candidates, second_observations = discovery.build_candidates(
            fixture_config(),
            ranking_fetcher=fixture_fetcher,
            existing_observations=observations,
            known_existing_rows=fixture_known_existing_rows(),
        )
        assert_equal(second_candidates, [], "A repeated observation must not rediscover candidates")
        assert_equal(
            len(second_observations),
            len(observations),
            "Repeated same-date observations must be idempotent",
        )

        with repo_temp_dir("ibd_ranking_first_test_") as tmp:
            ledger_path = tmp / "sg_chart_observations.csv"
            discovery.write_observation_ledger(observations, ledger_path)
            with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
                persisted = list(csv.DictReader(handle))
            assert_equal(len(persisted), len(observations), "Ledger should persist every unique observation")
            assert_equal(
                set(persisted[0].keys()),
                set(discovery.OBSERVATION_FIELDS),
                "Ledger should use the documented single-file schema",
            )

        layer2_candidate = {
            "run_timestamp_utc": "2026-07-22T00:00:00+00:00",
            "ranking_date": "2026-07-22",
            "country": "SG",
            "platform": "ios",
            "app_id": "ios-cross-platform-new",
            "released_tag_matches": "",
            "sg_chart_matches": "Top Grossing iPhone Apps #9",
            "best_sg_rank": "9",
            "candidate_reason": discovery.DISCOVERY_SOURCE,
            "chart_match_details_json": "[]",
        }
        lookup = {
            ("ios", "ios-cross-platform-new"): {
                "unified_app_id": "known-cross-platform-unified",
                "name": "Known Cross Platform Game",
                "canonical_app_id": "ios-cross-platform-new",
                "itunes_apps": [{"app_id": "ios-cross-platform-new"}],
                "android_apps": [{"app_id": "android-historical"}],
            }
        }
        enriched = layer2.enrich_rows([layer2_candidate], lookup)
        filtered = layer2.filter_known_existing_unified_rows(
            enriched,
            known_existing_rows=fixture_known_existing_rows(),
        )
        assert_equal(
            filtered,
            [],
            "Layer 2 must drop candidates whose unified_app_id is historically known",
        )

        with repo_temp_dir("ibd_missing_ledger_test_") as tmp:
            original_ledger = discovery.OBSERVATION_LEDGER_CSV
            discovery.OBSERVATION_LEDGER_CSV = tmp / "missing_sg_chart_observations.csv"
            calls_before_refusal = len(fetch_calls)
            try:
                assert_raises(
                    "Baseline ledger does not exist",
                    lambda: discovery.build_candidates(
                        fixture_config(),
                        ranking_fetcher=fixture_fetcher,
                    ),
                    "Normal discovery must refuse a missing observation ledger",
                )
            finally:
                discovery.OBSERVATION_LEDGER_CSV = original_ledger
            assert_equal(
                len(fetch_calls),
                calls_before_refusal,
                "Missing-ledger refusal must happen before any ranking fetch",
            )

        with repo_temp_dir("ibd_empty_ledger_test_") as tmp:
            ledger_path = tmp / "sg_chart_observations.csv"
            discovery.write_observation_ledger([], ledger_path)
            original_ledger = discovery.OBSERVATION_LEDGER_CSV
            discovery.OBSERVATION_LEDGER_CSV = ledger_path
            calls_before_refusal = len(fetch_calls)
            try:
                assert_raises(
                    "no baseline rows",
                    lambda: discovery.build_candidates(
                        fixture_config(),
                        ranking_fetcher=fixture_fetcher,
                    ),
                    "Normal discovery must refuse a header-only observation ledger",
                )
            finally:
                discovery.OBSERVATION_LEDGER_CSV = original_ledger
            assert_equal(
                len(fetch_calls),
                calls_before_refusal,
                "Empty-ledger refusal must happen before any ranking fetch",
            )

        def raise_missing_known_db():
            raise RuntimeError("Known-existing games database does not exist: test")

        discovery.read_known_existing_games = raise_missing_known_db
        calls_before_refusal = len(fetch_calls)
        try:
            assert_raises(
                "Known-existing games database does not exist",
                lambda: discovery.build_candidates(
                    fixture_config(),
                    ranking_fetcher=fixture_fetcher,
                    existing_observations=existing,
                ),
                "Normal discovery must refuse a missing known-existing database",
            )
        finally:
            discovery.read_known_existing_games = original_discovery_known_reader
        assert_equal(
            len(fetch_calls),
            calls_before_refusal,
            "Missing known-existing database refusal must happen before any ranking fetch",
        )

        with repo_temp_dir("ibd_known_db_validation_test_") as tmp:
            empty_known = tmp / "empty_known_existing_games.csv"
            malformed_known = tmp / "malformed_known_existing_games.csv"
            empty_known.write_text(
                ",".join(candidate_store.KNOWN_EXISTING_FIELDS) + "\n",
                encoding="utf-8",
            )
            malformed_known.write_text("platform,app_id\nios,123\n", encoding="utf-8")
            assert_raises(
                "no usable rows",
                lambda: candidate_store.read_known_existing_games(empty_known),
                "Known-existing database must fail closed when empty",
            )
            assert_raises(
                "malformed",
                lambda: candidate_store.read_known_existing_games(malformed_known),
                "Known-existing database must fail closed when malformed",
            )

        baseline_fetch_calls = []

        def baseline_fixture_fetcher(
            platform,
            platform_config,
            chart_type,
            country,
            ranking_date,
            auth_token,
        ):
            baseline_fetch_calls.append((platform, chart_type, country, ranking_date))
            return fixture_rankings[(platform, chart_type)]

        with repo_temp_dir("ibd_baseline_success_test_") as tmp:
            ledger_path = tmp / "sg_chart_observations.csv"
            discovery.write_observation_ledger([], ledger_path)
            candidates, baseline_rows, written_path = discovery.run_baseline_only(
                fixture_config(),
                ranking_fetcher=baseline_fixture_fetcher,
                ledger_path=ledger_path,
                today=date(2026, 7, 24),
            )
            assert_equal(candidates, [], "Baseline must create zero Layer 1 candidates")
            assert_equal(written_path, ledger_path, "Baseline should write only the requested ledger")
            assert_equal(
                {(row["platform"], row["app_id"]) for row in baseline_rows},
                {
                    ("ios", "ios-seen"),
                    ("ios", "ios-known"),
                    ("ios", "ios-new"),
                    ("android", "android-new"),
                },
                "Baseline should retain both non-empty Top Grossing responses",
            )
            assert_equal(
                baseline_fetch_calls,
                [
                    ("ios", "topgrossingapplications", "SG", "2026-07-22"),
                    ("android", "topgrossing", "SG", "2026-07-22"),
                ],
                "Baseline must fetch only iOS and Android SG Top Grossing",
            )
            persisted = discovery.read_baseline_ledger(ledger_path)
            assert_equal(len(persisted), 4, "Baseline observations should be persisted")

            calls_before_refusal = len(baseline_fetch_calls)
            assert_raises(
                "already has data rows",
                lambda: discovery.run_baseline_only(
                    fixture_config(),
                    ranking_fetcher=baseline_fixture_fetcher,
                    ledger_path=ledger_path,
                    today=date(2026, 7, 24),
                ),
                "A populated baseline ledger must refuse a second baseline",
            )
            assert_equal(
                len(baseline_fetch_calls),
                calls_before_refusal,
                "Repeat baseline refusal must happen before any ranking fetch",
            )

        baseline_api_requests = []
        raw_write_attempts = []

        def offline_baseline_request_json(path, params):
            baseline_api_requests.append((path, dict(params)))
            if path == "/v1/ios/ranking":
                return {"ranking": ["ios-baseline-a", "ios-baseline-b"]}
            if path == "/v1/android/ranking":
                return {"ranking": ["android-baseline-a"]}
            raise AssertionError(f"Unexpected baseline endpoint: {path}")

        def block_save_raw(*args, **kwargs):
            raw_write_attempts.append((args, kwargs))
            raise AssertionError("Baseline attempted to write a raw response file.")

        with repo_temp_dir("ibd_baseline_no_raw_test_") as tmp:
            ledger_path = tmp / "sg_chart_observations.csv"
            discovery.write_observation_ledger([], ledger_path)
            discovery.request_json = offline_baseline_request_json
            discovery.save_raw = block_save_raw
            try:
                candidates, baseline_rows, _ = discovery.run_baseline_only(
                    fixture_config(),
                    ledger_path=ledger_path,
                    today=date(2026, 7, 24),
                )
            finally:
                discovery.request_json = block_request_json
                discovery.save_raw = original_save_raw

            assert_equal(candidates, [], "Default baseline fetch path must create zero candidates")
            assert_equal(len(baseline_rows), 3, "Default baseline fetch path should write observations")
            assert_equal(raw_write_attempts, [], "Baseline must suppress all raw response writes")
            assert_equal(
                [(path, params["chart_type"]) for path, params in baseline_api_requests],
                [
                    ("/v1/ios/ranking", "topgrossingapplications"),
                    ("/v1/android/ranking", "topgrossing"),
                ],
                "Default baseline path must make only the two Top Grossing requests",
            )
            assert_equal(
                {path.name for path in tmp.iterdir()},
                {"sg_chart_observations.csv"},
                "Baseline test directory must contain only the observation ledger",
            )

        partial_fetch_calls = []

        def partial_fixture_fetcher(
            platform,
            platform_config,
            chart_type,
            country,
            ranking_date,
            auth_token,
        ):
            partial_fetch_calls.append((platform, chart_type))
            return {"ios-only": 1} if platform == "ios" else {}

        with repo_temp_dir("ibd_baseline_partial_test_") as tmp:
            ledger_path = tmp / "sg_chart_observations.csv"
            discovery.write_observation_ledger([], ledger_path)
            ledger_before = ledger_path.read_bytes()
            assert_raises(
                "android SG Top Grossing response was empty",
                lambda: discovery.run_baseline_only(
                    fixture_config(),
                    ranking_fetcher=partial_fixture_fetcher,
                    ledger_path=ledger_path,
                    today=date(2026, 7, 24),
                ),
                "A partial platform baseline must fail",
            )
            assert_equal(
                partial_fetch_calls,
                [("ios", "topgrossingapplications"), ("android", "topgrossing")],
                "Partial baseline should stop after the required platform responses",
            )
            assert_equal(
                ledger_path.read_bytes(),
                ledger_before,
                "Partial baseline failure must not modify the ledger",
            )

        with repo_temp_dir("ibd_baseline_lag_test_") as tmp:
            ledger_path = tmp / "sg_chart_observations.csv"
            discovery.write_observation_ledger([], ledger_path)
            too_recent_config = fixture_config()
            too_recent_config["ranking_date"] = "2026-07-23"
            calls_before_lag_refusal = len(baseline_fetch_calls)
            assert_raises(
                "too recent",
                lambda: discovery.run_baseline_only(
                    too_recent_config,
                    ranking_fetcher=baseline_fixture_fetcher,
                    ledger_path=ledger_path,
                    today=date(2026, 7, 24),
                ),
                "Baseline must enforce two full days of Sensor Tower lag",
            )
            assert_equal(
                len(baseline_fetch_calls),
                calls_before_lag_refusal,
                "Lag validation must fail before any ranking fetch",
            )
            assert_equal(
                discovery.read_baseline_ledger(ledger_path),
                [],
                "Lag validation failure must leave the ledger empty",
            )

        assert_equal(network_attempts, [], "Offline test must make zero network or Sensor Tower calls")
    finally:
        urllib.request.urlopen = original_urlopen
        discovery.request_json = original_request_json
        discovery.save_raw = original_save_raw
        discovery.read_known_existing_games = original_discovery_known_reader

    print("RANKING_FIRST_DISCOVERY_OFFLINE_PASS")
    print("NETWORK_CALLS=0")
    print("SENSOR_TOWER_API_CALLS=0")


if __name__ == "__main__":
    main()
