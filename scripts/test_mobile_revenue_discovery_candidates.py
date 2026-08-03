import csv
import io
from contextlib import redirect_stdout
from pathlib import Path

import build_mobile_revenue_discovery_candidates as discovery
from test_temp_utils import repo_temp_dir


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_raises(text, callback, message):
    try:
        callback()
    except RuntimeError as exc:
        if text not in str(exc):
            raise AssertionError(f"{message}: expected {text!r}, got {str(exc)!r}") from exc
        return
    raise AssertionError(f"{message}: expected RuntimeError")


def row(**overrides):
    base = {
        "Unified Name": "New Revenue Game",
        "Unified ID": "unified-1",
        "Category": "Games",
        "Unified Publisher ID": "publisher-1",
        "Unified Publisher Name": "Publisher",
        "Date": "Jul 20, 2026",
        "Platform": "Unified",
        "Downloads (Absolute)": "1,234",
        "Downloads (PoP Growth)": "",
        "Downloads (PoP Growth %)": "",
        "Revenue (Absolute)": "$70",
        "Revenue (PoP Growth)": "",
        "Revenue (PoP Growth %)": "",
        "Earliest Release Date": "Jul 18, 2026",
        "Revenue (Prior, $)": "$0",
    }
    base.update(overrides)
    return base


def write_input(path, rows, fields=None):
    fields = fields or discovery.REQUIRED_COLUMNS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def chart_row(**overrides):
    base = {
        "Country": "SG",
        "Category": "Games",
        "Chart": "topgrossingapplications",
        "Date": "2026-07-28",
        "Ranking": "7",
        "App ID": "123456789",
        "App name": "New Revenue Game",
        "Company": "Publisher",
    }
    base.update(overrides)
    return base


def write_unified_export(folder, country, rows, start="Jul 14, 2026", end="Jul 26, 2026"):
    path = folder / f"Unified Top Apps Revenue ({start} - {end}, {country}), Detailed.csv"
    write_input(path, rows)
    return path


def write_chart_export(folder, platform, rows):
    path = folder / f"Sensor_Tower_Category_Rankings_{platform}_SG_Games_2026-07-28.csv"
    write_input(path, rows, discovery.TOP_CHART_REQUIRED_COLUMNS)
    return path


def test_filename_date_country_parsing():
    cases = [
        (
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv",
            "2026-07-14",
            "2026-07-25",
            "SG",
            "exact example filename",
        ),
        (
            "Unified Top Apps Revenue (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv",
            "2026-07-14",
            "2026-07-25",
            "SG",
            "one space before parenthesis",
        ),
        (
            "Unified Top Apps Revenue   (  Jul 14 , 2026   -   Jul 25 , 2026 , SG  )  Detailed.csv",
            "2026-07-14",
            "2026-07-25",
            "SG",
            "extra spaces",
        ),
        (
            "Unified Top Apps Revenue (Jul 14, 2026 - Jul 25, 2026, MY), Detailed.csv",
            "2026-07-14",
            "2026-07-25",
            "MY",
            "different country code",
        ),
        (
            "Unified Top Apps Revenue (Aug 1, 2026 - Aug 10, 2026, ID), Detailed.csv",
            "2026-08-01",
            "2026-08-10",
            "ID",
            "different date range",
        ),
        (
            "anything prefix changed (Sep 2, 2026 - Sep 9, 2026, TH) any suffix.csv",
            "2026-09-02",
            "2026-09-09",
            "TH",
            "changed prefix and suffix",
        ),
    ]
    for filename, expected_start, expected_end, expected_country, message in cases:
        start, end, country = discovery.parse_filename_period(filename)
        assert_equal(start.isoformat(), expected_start, message + " start")
        assert_equal(end.isoformat(), expected_end, message + " end")
        assert_equal(country, expected_country, message + " country")


def test_required_column_validation():
    fields = [field for field in discovery.REQUIRED_COLUMNS if field != "Unified ID"]
    assert_raises(
        "Unified ID",
        lambda: discovery.validate_columns(fields),
        "missing required column fails",
    )


def test_new_revenue_rule_includes():
    candidates = discovery.candidate_rows(
        [row()],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(len(candidates), 1, "new revenue row included")


def test_release_date_inside_period_is_new_release_candidate():
    candidates = discovery.candidate_rows(
        [row(**{"Earliest Release Date": "2026/07/18", "Revenue (Absolute)": "$500"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["mobile_discovery_type"], "new_release_candidate", "new release type")


def test_old_release_date_is_first_revenue_candidate():
    candidates = discovery.candidate_rows(
        [row(**{"Earliest Release Date": "Jul 13, 2026", "Revenue (Absolute)": "$500"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["mobile_discovery_type"], "first_revenue_candidate", "first revenue type")


def test_old_low_revenue_is_noise():
    candidates = discovery.candidate_rows(
        [row(**{"Earliest Release Date": "Jan 1, 2020", "Revenue (Absolute)": "$99.99"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["mobile_discovery_type"], "low_revenue_noise", "low revenue noise type")


def test_new_release_below_threshold_is_low_revenue_noise():
    candidates = discovery.candidate_rows(
        [row(**{"Earliest Release Date": "Jul 15, 2026", "Revenue (Absolute)": "$1"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["mobile_discovery_type"], "low_revenue_noise", "low revenue new release type")


def test_missing_release_date_is_first_revenue_candidate():
    candidates = discovery.candidate_rows(
        [row(**{"Earliest Release Date": "", "Revenue (Absolute)": "$500"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["mobile_discovery_type"], "first_revenue_candidate", "missing release date type")


def test_old_release_above_threshold_is_report_facing_true():
    candidates = discovery.candidate_rows(
        [row(**{"Earliest Release Date": "Jan 1, 2020", "Revenue (Absolute)": "$351"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["report_facing_mobile_candidate"], "true", "old release report-facing true")
    assert_equal(candidates[0]["report_facing_reason"], "first_period_revenue_above_threshold", "above threshold reason")


def test_digimon_up_style_row_is_report_facing_true():
    candidates = discovery.candidate_rows(
        [
            row(
                **{
                    "Unified Name": "DIGIMON UP!",
                    "Earliest Release Date": "Jan 1, 2025",
                    "Revenue (Absolute)": "$1000",
                }
            )
        ],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["report_facing_mobile_candidate"], "true", "DIGIMON UP style row")


def test_hololive_dreams_style_row_is_report_facing_true():
    candidates = discovery.candidate_rows(
        [
            row(
                **{
                    "Unified Name": "hololive Dreams",
                    "Earliest Release Date": "Jul 18, 2026",
                    "Revenue (Absolute)": "$500",
                }
            )
        ],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["report_facing_mobile_candidate"], "true", "hololive Dreams style row")


def test_below_threshold_is_audit_row_not_report_facing():
    candidates = discovery.candidate_rows(
        [row(**{"Earliest Release Date": "Jul 18, 2026", "Revenue (Absolute)": "$349"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(len(candidates), 1, "below threshold kept as audit row")
    assert_equal(candidates[0]["report_facing_mobile_candidate"], "false", "below threshold report-facing false")
    assert_equal(candidates[0]["report_facing_reason"], "first_period_revenue_below_threshold", "below threshold reason")


def test_release_date_does_not_control_report_facing_inclusion():
    candidates = discovery.candidate_rows(
        [
            row(
                **{
                    "Earliest Release Date": "Jan 1, 2011",
                    "Revenue (Absolute)": "$1000",
                }
            )
        ],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["report_facing_mobile_candidate"], "true", "old release date can be report-facing")


def test_prior_revenue_excluded():
    candidates = discovery.candidate_rows(
        [row(**{"Revenue (Prior, $)": "$1"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates, [], "prior revenue row excluded")


def test_zero_absolute_revenue_excluded():
    candidates = discovery.candidate_rows(
        [row(**{"Revenue (Absolute)": "$0", "Downloads (Absolute)": "999"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates, [], "zero revenue row excluded")


def test_gross_revenue_conversion():
    candidates = discovery.candidate_rows(
        [row(**{"Revenue (Absolute)": "$70"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(candidates[0]["revenue_store_absolute"], "70", "store revenue")
    assert_equal(candidates[0]["revenue_gross_estimate"], "100", "gross revenue")


def test_output_sorted_by_type_then_revenue_descending():
    candidates = discovery.candidate_rows(
        [
            row(
                **{
                    "Unified Name": "Old High Revenue",
                    "Unified ID": "old-high",
                    "Earliest Release Date": "Jan 1, 2020",
                    "Revenue (Absolute)": "$1000",
                }
            ),
            row(
                **{
                    "Unified Name": "New Low Revenue",
                    "Unified ID": "new-low",
                    "Earliest Release Date": "Jul 18, 2026",
                    "Revenue (Absolute)": "$1",
                }
            ),
            row(
                **{
                    "Unified Name": "New High Revenue",
                    "Unified ID": "new-high",
                    "Earliest Release Date": "Jul 19, 2026",
                    "Revenue (Absolute)": "$500",
                }
            ),
            row(
                **{
                    "Unified Name": "Old Low Noise",
                    "Unified ID": "old-low",
                    "Earliest Release Date": "Jan 1, 2020",
                    "Revenue (Absolute)": "$10",
                }
            ),
        ],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    assert_equal(
        [candidate["unified_name"] for candidate in candidates],
        ["Old High Revenue", "New High Revenue", "Old Low Noise", "New Low Revenue"],
        "sorted by report-facing then gross revenue",
    )


def test_chart_rank_enrichment_for_report_facing_only():
    candidates = discovery.candidate_rows(
        [
            row(
                **{
                    "Unified Name": "New Revenue Game",
                    "Unified ID": "report-facing",
                    "Revenue (Absolute)": "$500",
                }
            ),
            row(
                **{
                    "Unified Name": "Below Threshold Game",
                    "Unified ID": "audit-only",
                    "Revenue (Absolute)": "$1",
                }
            ),
        ],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    chart_index = {
        discovery.normalize_app_name("New Revenue Game"): {
            field: "" for field in discovery.CHART_RANK_FIELDS
        },
        discovery.normalize_app_name("Below Threshold Game"): {
            field: "" for field in discovery.CHART_RANK_FIELDS
        },
    }
    chart_index[discovery.normalize_app_name("New Revenue Game")]["ios_top_grossing_rank"] = "7"
    chart_index[discovery.normalize_app_name("New Revenue Game")]["ios_top_grossing_app_id"] = "123456789"
    chart_index[discovery.normalize_app_name("Below Threshold Game")]["ios_top_grossing_rank"] = "8"
    chart_index[discovery.normalize_app_name("Below Threshold Game")]["ios_top_grossing_app_id"] = "987654321"

    enriched = discovery.apply_chart_rank_enrichment(candidates, chart_index)
    by_id = {candidate["unified_id"]: candidate for candidate in enriched}
    assert_equal(by_id["report-facing"]["ios_top_grossing_rank"], "7", "report-facing chart rank")
    assert_equal(by_id["report-facing"]["chart_rank_match_method"], "normalized_name_exact", "match method")
    assert_equal(by_id["audit-only"]["ios_top_grossing_rank"], "", "audit-only rank left blank")


def test_report_facing_only_csv_creation():
    rows = discovery.candidate_rows(
        [
            row(
                **{
                    "Unified Name": "Report Facing Game",
                    "Unified ID": "report-facing",
                    "Revenue (Absolute)": "$500",
                }
            ),
            row(
                **{
                    "Unified Name": "Audit Only Game",
                    "Unified ID": "audit-only",
                    "Revenue (Absolute)": "$1",
                }
            ),
        ],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    clean = discovery.report_facing_rows(rows)
    assert_equal(len(clean), 1, "only report-facing row exported")
    assert_equal(clean[0]["unified_name"], "Report Facing Game", "report-facing row name")


def test_chart_rank_match_status_matched_when_any_rank_exists():
    rows = discovery.candidate_rows(
        [row(**{"Revenue (Absolute)": "$500"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    rows[0]["android_top_grossing_rank"] = "6"
    clean = discovery.report_facing_rows(rows)
    assert_equal(clean[0]["chart_rank_match_status"], "matched", "rank match status")


def test_chart_rank_match_status_unmatched_without_rank():
    rows = discovery.candidate_rows(
        [row(**{"Revenue (Absolute)": "$500"})],
        *discovery.parse_filename_period(
            "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        ),
        "source.csv",
        "2026-07-27T00:00:00+00:00",
    )
    clean = discovery.report_facing_rows(rows)
    assert_equal(clean[0]["chart_rank_match_status"], "unmatched", "rank unmatched status")


def test_build_chart_rank_index_maps_ios_and_android_charts():
    with repo_temp_dir("mobile_chart_rank_") as tmp:
        ios_path = Path(tmp) / "Sensor_Tower_Category_Rankings_iPhone_SG_Games_2026-07-28.csv"
        android_path = Path(tmp) / "Sensor_Tower_Category_Rankings_Android_SG_Game_2026-07-28.csv"
        write_input(
            ios_path,
            [
                chart_row(**{"Chart": "topfreeapplications", "Ranking": "3", "App ID": "ios-free"}),
                chart_row(**{"Chart": "topgrossingapplications", "Ranking": "9", "App ID": "ios-gross"}),
                chart_row(**{"Chart": "toppaidapplications", "Ranking": "1", "App ID": "ignored-paid"}),
            ],
            discovery.TOP_CHART_REQUIRED_COLUMNS,
        )
        write_input(
            android_path,
            [
                chart_row(**{"Chart": "topselling_free", "Ranking": "4", "App ID": "android-free"}),
                chart_row(**{"Chart": "topgrossing", "Ranking": "6", "App ID": "android-gross"}),
            ],
            discovery.TOP_CHART_REQUIRED_COLUMNS,
        )
        index, warnings = discovery.build_chart_rank_index([ios_path, android_path])
        assert_equal(warnings, [], "chart warnings")
        entry = index[discovery.normalize_app_name("New Revenue Game")]
        assert_equal(entry["ios_top_free_rank"], "3", "ios free rank")
        assert_equal(entry["ios_top_grossing_rank"], "9", "ios grossing rank")
        assert_equal(entry["android_top_free_rank"], "4", "android free rank")
        assert_equal(entry["android_top_grossing_rank"], "6", "android grossing rank")
        assert_equal(entry["ios_top_free_app_id"], "ios-free", "ios free app id")
        assert_equal(entry["android_top_grossing_app_id"], "android-gross", "android gross app id")


def test_config_date_mismatch_warns_not_fail():
    with repo_temp_dir("mobile_revenue_discovery_") as tmp:
        input_path = (
            Path(tmp)
            / "Unified Top Apps Revenue  (Jul 14, 2026 - Jul 25, 2026, SG), Detailed.csv"
        )
        output_dir = Path(tmp) / "out"
        original_output = discovery.OUTPUT_DIR
        try:
            discovery.OUTPUT_DIR = output_dir
            write_input(input_path, [row()])
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                path, candidates, warnings, _count, clean_path, clean_rows = discovery.build(input_path)
            text = buffer.getvalue()
            assert_true(path.exists(), "output file created")
            assert_true(clean_path.exists(), "clean output file created")
            assert_equal(len(candidates), 1, "candidate still produced")
            assert_equal(len(clean_rows), 0, "below threshold row not report-facing")
            assert_true(any("WARNING: Filename period" in warning for warning in warnings), "warning returned")
            assert_equal(text, "", "build does not print directly")
        finally:
            discovery.OUTPUT_DIR = original_output


def test_unparseable_filename_falls_back_with_warning():
    with repo_temp_dir("mobile_revenue_fallback_") as tmp:
        input_path = Path(tmp) / "manual_export_without_period.csv"
        output_dir = Path(tmp) / "out"
        original_output = discovery.OUTPUT_DIR
        try:
            discovery.OUTPUT_DIR = output_dir
            write_input(input_path, [row(**{"Date": "Jul 20, 2026"})])
            path, candidates, warnings, _count, clean_path, _clean_rows = discovery.build(input_path)
            assert_true(path.exists(), "fallback output file created")
            assert_true(clean_path.exists(), "fallback clean output file created")
            assert_equal(path.name, "mobile_revenue_discovery_candidates_2026-07-14_to_2026-07-27_SG.csv", "fallback output filename")
            assert_equal(candidates[0]["report_start_date"], "2026-07-14", "fallback report start")
            assert_equal(candidates[0]["report_end_date"], "2026-07-27", "fallback report end")
            assert_equal(candidates[0]["country"], "SG", "fallback country")
            assert_true(any("Could not parse date range/country" in warning for warning in warnings), "fallback warning")
        finally:
            discovery.OUTPUT_DIR = original_output


def test_output_headers_exact():
    with repo_temp_dir("mobile_revenue_headers_") as tmp:
        path = Path(tmp) / "out.csv"
        discovery.write_csv(path, [])
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
    assert_equal(headers, discovery.OUTPUT_FIELDS, "output headers")


def test_report_facing_headers_exact():
    with repo_temp_dir("mobile_report_facing_headers_") as tmp:
        path = Path(tmp) / "out.csv"
        discovery.write_csv(path, [], discovery.REPORT_FACING_FIELDS)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
    assert_equal(headers, discovery.REPORT_FACING_FIELDS, "report-facing headers")


def test_meeting_pack_builds_from_meeting_date_folder():
    with repo_temp_dir("mobile_meeting_pack_") as tmp:
        tmp = Path(tmp)
        original_drop_root = discovery.MEETING_DROP_ROOT
        original_output_root = discovery.MEETING_PACK_OUTPUT_ROOT
        try:
            discovery.MEETING_DROP_ROOT = tmp / "meeting_drop"
            discovery.MEETING_PACK_OUTPUT_ROOT = tmp / "meeting_pack"
            original_title_override = discovery.TITLE_OVERRIDE_PATH
            discovery.TITLE_OVERRIDE_PATH = tmp / "reference" / "game_title_overrides.csv"
            folder = discovery.MEETING_DROP_ROOT / "2026-07-28" / "mobile"
            folder.mkdir(parents=True)

            write_unified_export(
                folder,
                "SG",
                [
                    row(
                        **{
                            "Unified Name": "Report Game",
                            "Unified ID": "uid-report",
                            "Revenue (Absolute)": "$700",
                            "Downloads (Absolute)": "70",
                        }
                    ),
                    row(
                        **{
                            "Unified Name": "低收入遊戲",
                            "Unified ID": "uid-low",
                            "Revenue (Absolute)": "$70",
                            "Downloads (Absolute)": "7",
                        }
                    ),
                    row(
                        **{
                            "Unified Name": "Old Revenue Game",
                            "Unified ID": "uid-old",
                            "Revenue (Absolute)": "$700",
                            "Revenue (Prior, $)": "$1",
                        }
                    ),
                ],
            )
            write_unified_export(
                folder,
                "MY",
                [row(**{"Unified Name": "Report Game", "Unified ID": "uid-report", "Revenue (Absolute)": "$1400", "Downloads (Absolute)": "140"})],
            )
            write_unified_export(
                folder,
                "ID",
                [row(**{"Unified Name": "Report Game", "Unified ID": "uid-report", "Revenue (Absolute)": "$1200", "Downloads (Absolute)": "120"})],
            )
            write_unified_export(
                folder,
                "TH",
                [row(**{"Unified Name": "Report Game", "Unified ID": "uid-report", "Revenue (Absolute)": "$1000", "Downloads (Absolute)": "100"})],
            )
            write_unified_export(
                folder,
                "PH",
                [row(**{"Unified Name": "Report Game", "Unified ID": "uid-report", "Revenue (Absolute)": "$0", "Downloads (Absolute)": "99"})],
            )
            write_chart_export(
                folder,
                "iPhone",
                [
                    chart_row(**{"App name": "Report Game", "Chart": "topgrossingapplications", "Ranking": "8"}),
                    chart_row(**{"App name": "Report Game", "Chart": "topfreeapplications", "Ranking": "3"}),
                ],
            )

            (
                path,
                rows,
                warnings,
                input_folder,
                chart_paths,
                translation_path,
                translation_rows,
                override_created,
                main_path,
                main_rows,
                appendix_path,
                appendix,
                resolution_sources,
                fallback_overrides,
            ) = discovery.build_meeting_pack("2026-07-28")
            assert_equal(input_folder, folder, "meeting-date folder detection")
            assert_true(path.exists(), "meeting pack output exists")
            assert_true(translation_path.exists(), "translation-needed output exists")
            assert_true(main_path.exists(), "main report output exists")
            assert_true(appendix_path.exists(), "appendix output exists")
            assert_true(override_created, "title override file created")
            assert_equal(len(rows), 1, "SG report-facing extraction")
            assert_equal(len(main_rows), 1, "chart matched report game qualifies for main")
            assert_equal(len(appendix), 0, "chart matched report game not in appendix")
            assert_equal(translation_rows, [], "no translation rows for English title")
            assert_equal(fallback_overrides, [], "no fallback overrides for English title")
            assert_equal(resolution_sources["uid-report"], "mostly_english", "English title source")
            output = rows[0]
            assert_equal(output["unified_id"], "uid-report", "report-facing unified id")
            assert_equal(output["sea_market_1_country"], "MY", "top SEA market 1")
            assert_equal(output["sea_market_2_country"], "ID", "top SEA market 2")
            assert_equal(output["sea_market_3_country"], "TH", "top SEA market 3")
            assert_equal(output["sea_market_4_country"], "SG", "SG appears as market 4")
            assert_true("PH" not in [output[f"sea_market_{index}_country"] for index in range(1, 5)], "zero-revenue country hidden")
            assert_equal(output["chart_rank_match_status"], "matched", "chart rank matched")
            assert_equal(output["ios_top_grossing_rank"], "8", "iOS gross rank")
            assert_equal(output["english_report_name"], "Report Game", "English title kept")
            assert_equal(output["translation_needed"], "false", "English title no translation")
            assert_true(any("VN unified revenue export missing" in warning for warning in warnings), "missing VN warns")
            assert_true(chart_paths, "chart file discovered")
        finally:
            discovery.MEETING_DROP_ROOT = original_drop_root
            discovery.MEETING_PACK_OUTPUT_ROOT = original_output_root
            discovery.TITLE_OVERRIDE_PATH = original_title_override


def test_missing_chart_files_warn_and_rank_na():
    with repo_temp_dir("mobile_meeting_no_charts_") as tmp:
        tmp = Path(tmp)
        original_drop_root = discovery.MEETING_DROP_ROOT
        original_output_root = discovery.MEETING_PACK_OUTPUT_ROOT
        try:
            discovery.MEETING_DROP_ROOT = tmp / "meeting_drop"
            discovery.MEETING_PACK_OUTPUT_ROOT = tmp / "meeting_pack"
            original_title_override = discovery.TITLE_OVERRIDE_PATH
            discovery.TITLE_OVERRIDE_PATH = tmp / "reference" / "game_title_overrides.csv"
            folder = discovery.MEETING_DROP_ROOT / "2026-07-28" / "mobile"
            folder.mkdir(parents=True)
            write_unified_export(
                folder,
                "SG",
                [row(**{"Unified Name": "天命：六道輪迴", "Unified ID": "uid-cn", "Revenue (Absolute)": "$700"})],
            )

            _path, rows, warnings, _folder, chart_paths, _translation_path, translation_rows, _created, _main_path, _main_rows, _appendix_path, _appendix, _sources, _fallback = discovery.build_meeting_pack("2026-07-28")
            assert_equal(chart_paths, [], "no chart files")
            assert_true(any("No SG Top Charts CSV files found" in warning for warning in warnings), "missing chart warning")
            assert_equal(rows[0]["ios_top_free_rank"], "N/A", "missing ios free rank as N/A")
            assert_equal(rows[0]["android_top_grossing_rank"], "N/A", "missing android gross rank as N/A")
            assert_equal(rows[0]["english_report_name"], "Destiny: Six Realms of Reincarnation", "fallback title applied")
            assert_equal(rows[0]["translation_needed"], "false", "fallback title clears translation flag")
            assert_equal(len(translation_rows), 0, "fallback row not exported for translation")
            assert_equal(rows[0]["sea_market_2_country"], "", "unused market 2 country blank")
            assert_equal(rows[0]["sea_market_2_downloads"], "", "unused market 2 downloads blank")
            assert_equal(rows[0]["sea_market_2_revenue_gross"], "", "unused market 2 revenue blank")
        finally:
            discovery.MEETING_DROP_ROOT = original_drop_root
            discovery.MEETING_PACK_OUTPUT_ROOT = original_output_root
            discovery.TITLE_OVERRIDE_PATH = original_title_override


def test_title_override_reuses_english_report_name():
    with repo_temp_dir("mobile_meeting_override_") as tmp:
        tmp = Path(tmp)
        original_drop_root = discovery.MEETING_DROP_ROOT
        original_output_root = discovery.MEETING_PACK_OUTPUT_ROOT
        original_title_override = discovery.TITLE_OVERRIDE_PATH
        try:
            discovery.MEETING_DROP_ROOT = tmp / "meeting_drop"
            discovery.MEETING_PACK_OUTPUT_ROOT = tmp / "meeting_pack"
            discovery.TITLE_OVERRIDE_PATH = tmp / "reference" / "game_title_overrides.csv"
            folder = discovery.MEETING_DROP_ROOT / "2026-07-28" / "mobile"
            folder.mkdir(parents=True)
            write_unified_export(
                folder,
                "SG",
                [row(**{"Unified Name": "我在江湖開後宮", "Unified ID": "uid-override", "Revenue (Absolute)": "$700"})],
            )
            write_input(
                discovery.TITLE_OVERRIDE_PATH,
                [
                    {
                        "unified_id": "uid-override",
                        "unified_name": "我在江湖開後宮",
                        "english_report_name": "Palace Life",
                        "translation_source": "manual",
                        "translation_note": "",
                    }
                ],
                discovery.TITLE_OVERRIDE_FIELDS,
            )

            _path, rows, _warnings, _folder, _chart_paths, _translation_path, translation_rows, override_created, _main_path, _main_rows, _appendix_path, _appendix, _sources, _fallback = discovery.build_meeting_pack("2026-07-28")
            assert_equal(override_created, False, "existing override file not created")
            assert_equal(rows[0]["english_report_name"], "Palace Life", "override title applied")
            assert_equal(rows[0]["translation_needed"], "false", "override clears translation flag")
            assert_equal(translation_rows, [], "override row not exported for translation")
        finally:
            discovery.MEETING_DROP_ROOT = original_drop_root
            discovery.MEETING_PACK_OUTPUT_ROOT = original_output_root
            discovery.TITLE_OVERRIDE_PATH = original_title_override


def test_override_lookup_by_unified_id_wins():
    candidate = {"unified_id": "uid-1", "unified_name": "Original"}
    english, needed, source = discovery.resolve_english_report_name(
        candidate,
        {"uid-1": "Override Name"},
        {"uid-1": "Master ID Name"},
        {discovery.normalize_app_name("Original"): "Master Title Name"},
    )
    assert_equal(english, "Override Name", "override by unified id wins")
    assert_equal(needed, "false", "override clears translation flag")
    assert_equal(source, "override", "override source")


def test_master_title_mapping_lookup_by_unified_id():
    candidate = {"unified_id": "uid-1", "unified_name": "Original"}
    english, needed, source = discovery.resolve_english_report_name(
        candidate,
        {},
        {"uid-1": "Master ID Name"},
        {discovery.normalize_app_name("Original"): "Master Title Name"},
    )
    assert_equal(english, "Master ID Name", "master unified id lookup")
    assert_equal(needed, "false", "master id clears translation flag")
    assert_equal(source, "master_unified_id", "master id source")


def test_master_title_mapping_lookup_by_normalized_original_title():
    candidate = {"unified_id": "uid-missing", "unified_name": "Original: Title!"}
    english, needed, source = discovery.resolve_english_report_name(
        candidate,
        {},
        {},
        {discovery.normalize_app_name("Original Title"): "Master Title Name"},
    )
    assert_equal(english, "Master Title Name", "master normalized original title lookup")
    assert_equal(needed, "false", "master title clears translation flag")
    assert_equal(source, "master_original_title", "master title source")


def test_codex_fallback_dictionary_fills_missing_title():
    candidate = {"unified_id": "uid-fallback", "unified_name": "我在江湖開後宮"}
    english, needed, source = discovery.resolve_english_report_name(candidate, {}, {}, {})
    assert_equal(english, "Building a Harem in Jianghu", "fallback title")
    assert_equal(needed, "false", "fallback clears translation flag")
    assert_equal(source, "codex_fallback", "fallback source")


def test_meeting_pack_headers_exact():
    with repo_temp_dir("mobile_meeting_headers_") as tmp:
        path = Path(tmp) / "out.csv"
        discovery.write_csv(path, [], discovery.MEETING_PACK_FIELDS)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
    assert_equal(headers, discovery.MEETING_PACK_FIELDS, "meeting pack headers")


def test_main_report_rows_have_no_blank_english_report_name():
    rows = [
        {"main_report_mobile_candidate": "true", "english_report_name": "Name"},
        {"main_report_mobile_candidate": "false", "english_report_name": ""},
    ]
    assert_true(
        all(row["english_report_name"] for row in discovery.main_report_rows(rows)),
        "main report names are nonblank",
    )


def test_translation_needed_count_decreases_after_lookup():
    candidates = [
        {
            "unified_id": "uid-fallback",
            "unified_name": "我在江湖開後宮",
            "report_facing_mobile_candidate": "true",
        },
        {
            "unified_id": "uid-unresolved",
            "unified_name": "未知標題",
            "report_facing_mobile_candidate": "true",
        },
    ]
    resolved = [
        discovery.resolve_english_report_name(candidate, {}, {}, {})[1]
        for candidate in candidates
    ]
    unresolved_without_lookup = [
        "true" if not discovery.mostly_english_name(candidate["unified_name"]) else "false"
        for candidate in candidates
    ]
    assert_true(
        resolved.count("true") < unresolved_without_lookup.count("true"),
        "fallback lookup reduces translation-needed count",
    )


def test_main_report_rule_sg_gross_above_3000():
    result = discovery.main_report_classification(
        {
            "sg_revenue_gross": "3000",
            "sg_downloads": "1",
            "chart_rank_match_status": "unmatched",
            "sg_release_date_reference": "2026/07/20",
        }
    )
    assert_equal(result, ("true", "false", "sg_gross_above_3000"), "SG gross threshold main")


def test_main_report_rule_chart_matched_and_sg_gross_above_1000():
    result = discovery.main_report_classification(
        {
            "sg_revenue_gross": "1000",
            "sg_downloads": "1",
            "chart_rank_match_status": "matched",
            "sg_release_date_reference": "2025/01/01",
        }
    )
    assert_equal(
        result,
        ("true", "false", "chart_matched_and_sg_gross_above_1000"),
        "chart matched plus SG gross threshold main",
    )


def test_main_report_rule_old_unmatched_overrides_high_sg_gross():
    result = discovery.main_report_classification(
        {
            "sg_revenue_gross": "9999",
            "sg_downloads": "1",
            "chart_rank_match_status": "unmatched",
            "sg_release_date_reference": "2025/12/31",
        }
    )
    assert_equal(
        result,
        ("false", "true", "appendix_old_unmatched_release"),
        "old unmatched release stays appendix",
    )


def test_main_report_rule_zero_download_unmatched_overrides_high_sg_gross():
    result = discovery.main_report_classification(
        {
            "sg_revenue_gross": "9999",
            "sg_downloads": "0",
            "chart_rank_match_status": "unmatched",
            "sg_release_date_reference": "2026/07/20",
        }
    )
    assert_equal(
        result,
        ("false", "true", "appendix_zero_download_unmatched"),
        "zero download unmatched stays appendix",
    )


def test_sea6_revenue_does_not_affect_main_inclusion():
    result = discovery.main_report_classification(
        {
            "sg_revenue_gross": "999",
            "sg_downloads": "10",
            "chart_rank_match_status": "unmatched",
            "sg_release_date_reference": "2026/07/20",
            "sea_market_1_revenue_gross": "1000000",
        }
    )
    assert_equal(
        result,
        ("false", "true", "appendix_below_main_threshold"),
        "SEA revenue cannot promote main inclusion",
    )


def test_expected_current_split_is_5_main_17_appendix_when_fixture_available():
    if not discovery.meeting_mobile_dir("2026-07-28").exists():
        return
    with repo_temp_dir("mobile_current_split_") as tmp:
        tmp = Path(tmp)
        original_output_root = discovery.MEETING_PACK_OUTPUT_ROOT
        original_title_override = discovery.TITLE_OVERRIDE_PATH
        try:
            discovery.MEETING_PACK_OUTPUT_ROOT = tmp / "meeting_pack"
            discovery.TITLE_OVERRIDE_PATH = tmp / "reference" / "game_title_overrides.csv"
            _path, rows, _warnings, _folder, _chart_paths, _translation_path, _translation_rows, _created, _main_path, main_rows, _appendix_path, appendix, _sources, _fallback = discovery.build_meeting_pack("2026-07-28")
            assert_equal(len(rows), 22, "current meeting pack rows")
            assert_equal(len(main_rows), 5, "current main split")
            assert_equal(len(appendix), 17, "current appendix split")
            assert_equal(
                [row["unified_name"] for row in main_rows],
                [
                    "Ragnarok: The New World",
                    "DIGIMON UP",
                    "hololive Dreams",
                    "車車屍搭普 - 足球狂歡季來臨！",
                    "Blade Heroes: Mecha Soul",
                ],
                "current main report games",
            )
        finally:
            discovery.MEETING_PACK_OUTPUT_ROOT = original_output_root
            discovery.TITLE_OVERRIDE_PATH = original_title_override


def main():
    test_filename_date_country_parsing()
    test_required_column_validation()
    test_new_revenue_rule_includes()
    test_release_date_inside_period_is_new_release_candidate()
    test_old_release_date_is_first_revenue_candidate()
    test_old_low_revenue_is_noise()
    test_new_release_below_threshold_is_low_revenue_noise()
    test_missing_release_date_is_first_revenue_candidate()
    test_old_release_above_threshold_is_report_facing_true()
    test_digimon_up_style_row_is_report_facing_true()
    test_hololive_dreams_style_row_is_report_facing_true()
    test_below_threshold_is_audit_row_not_report_facing()
    test_release_date_does_not_control_report_facing_inclusion()
    test_prior_revenue_excluded()
    test_zero_absolute_revenue_excluded()
    test_gross_revenue_conversion()
    test_output_sorted_by_type_then_revenue_descending()
    test_chart_rank_enrichment_for_report_facing_only()
    test_report_facing_only_csv_creation()
    test_chart_rank_match_status_matched_when_any_rank_exists()
    test_chart_rank_match_status_unmatched_without_rank()
    test_build_chart_rank_index_maps_ios_and_android_charts()
    test_config_date_mismatch_warns_not_fail()
    test_unparseable_filename_falls_back_with_warning()
    test_output_headers_exact()
    test_report_facing_headers_exact()
    test_meeting_pack_builds_from_meeting_date_folder()
    test_missing_chart_files_warn_and_rank_na()
    test_title_override_reuses_english_report_name()
    test_override_lookup_by_unified_id_wins()
    test_master_title_mapping_lookup_by_unified_id()
    test_master_title_mapping_lookup_by_normalized_original_title()
    test_codex_fallback_dictionary_fills_missing_title()
    test_meeting_pack_headers_exact()
    test_main_report_rows_have_no_blank_english_report_name()
    test_translation_needed_count_decreases_after_lookup()
    test_main_report_rule_sg_gross_above_3000()
    test_main_report_rule_chart_matched_and_sg_gross_above_1000()
    test_main_report_rule_old_unmatched_overrides_high_sg_gross()
    test_main_report_rule_zero_download_unmatched_overrides_high_sg_gross()
    test_sea6_revenue_does_not_affect_main_inclusion()
    test_expected_current_split_is_5_main_17_appendix_when_fixture_available()
    print("MOBILE_REVENUE_DISCOVERY_CANDIDATES_TEST_PASS")


if __name__ == "__main__":
    main()
