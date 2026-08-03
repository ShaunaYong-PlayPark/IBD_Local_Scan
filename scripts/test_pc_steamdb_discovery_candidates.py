import csv
from pathlib import Path

import build_pc_steamdb_discovery_candidates as pc
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


FIXTURE_HTML = """
<table>
  <thead>
    <tr>
      <th>Name</th><th>Release Date</th><th>Peak Players</th><th>Reviews</th><th>Price</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="/app/100/Ragnarok: The New World/">Ragnarok: The New World</a></td>
      <td data-sort="2026-07-15">Jul 15, 2026</td><td>500</td><td>1,000</td><td>Free</td>
    </tr>
    <tr>
      <td><a href="/app/200/Global Hit/">Global Hit</a></td>
      <td>Jul 20, 2026</td><td>12,345</td><td>700</td><td>$19.99</td>
    </tr>
    <tr>
      <td><a href="/app/300/Weak Game/">Weak Game</a></td>
      <td>Jul 21, 2026</td><td>999</td><td>600</td><td>$9.99</td>
    </tr>
    <tr>
      <td><a href="/app/400/Global Hit Soundtrack/">Global Hit Soundtrack</a></td>
      <td>Jul 20, 2026</td><td>50,000</td><td>900</td><td>$4.99</td>
    </tr>
    <tr>
      <td><a href="/app/500/Tool App/">Tool App</a></td>
      <td>Jul 20, 2026</td><td>50,000</td><td>900</td><td>$4.99</td>
    </tr>
  </tbody>
</table>
"""

STEAMDB_SAVED_ROW_HTML = """
<table>
  <thead>
    <tr>
      <th>Name</th><th>Release Date</th><th>Peak Players</th><th>Reviews</th><th>Price</th>
    </tr>
  </thead>
  <tbody>
    <tr class="app" data-appid="3561220">
      <td>
        <a target="_blank" href="https://store.steampowered.com/app/3561220/pass_the_fear/" class="info-icon" title="Store"></a>
        <a href="/app/3561220/" tabindex="-1" aria-hidden="true">ignored art text</a>
        <a class="b" href="/app/3561220/">Pass the Fear</a>
      </td>
      <td data-sort="1784764800">23 Jul</td><td>10,500</td><td>800</td><td>$9.99</td>
    </tr>
  </tbody>
</table>
"""

W29_FIXTURE_HTML = """
<table>
  <thead>
    <tr>
      <th>Name</th><th>Release Date</th><th>Peak Players</th><th>Reviews</th><th>Price</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a class="b" href="/app/900/SpiritVale/">SpiritVale</a></td>
      <td data-sort="1784073600">15 Jul</td><td>20,253</td><td>1,200</td><td>$14.99</td>
    </tr>
    <tr>
      <td><a class="b" href="/app/200/Global Hit/">Global Hit</a></td>
      <td>Jul 20, 2026</td><td>13,000</td><td>700</td><td>$19.99</td>
    </tr>
  </tbody>
</table>
"""

W30_DUPLICATE_FIXTURE_HTML = """
<table>
  <thead>
    <tr>
      <th>Name</th><th>Release Date</th><th>Peak Players</th><th>Reviews</th><th>Price</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a class="b" href="/app/200/Global Hit/">Global Hit</a></td>
      <td>Jul 20, 2026</td><td>12,345</td><td>700</td><td>$19.99</td>
    </tr>
    <tr>
      <td><a class="b" href="/app/300/Weak Game/">Weak Game</a></td>
      <td>Jul 21, 2026</td><td>999</td><td>600</td><td>$9.99</td>
    </tr>
  </tbody>
</table>
"""

TOP_RELEASES_FIXTURE_HTML = """
<table>
  <thead>
    <tr>
      <th>Name</th><th>Release Date</th><th>Peak Players</th><th>Reviews</th><th>Price</th>
    </tr>
  </thead>
  <tbody>
    <tr class="app" data-appid="910">
      <td>
        <a target="_blank" href="https://store.steampowered.com/app/910/spiritvale/" class="info-icon" title="Store"></a>
        <a href="/app/910/" tabindex="-1" aria-hidden="true">ignored</a>
        <a class="b" href="/app/910/">SpiritVale</a>
      </td>
      <td data-sort="1784073600">15 Jul</td><td>20,253</td><td>1,200</td><td>$14.99</td>
    </tr>
    <tr class="app" data-appid="920">
      <td><a class="b" href="/app/920/Ragnarok/">Ragnarok: The New World</a></td>
      <td data-sort="1779235200">20 May</td><td>500</td><td>1,000</td><td>Free</td>
    </tr>
    <tr class="app" data-appid="930">
      <td><a class="b" href="/app/930/Old Peak/">Old Peak</a></td>
      <td data-sort="1778803200">15 May</td><td>50,000</td><td>600</td><td>$9.99</td>
    </tr>
    <tr class="app" data-appid="940">
      <td><a class="b" href="/app/940/Junk DLC/">Junk DLC</a></td>
      <td data-sort="1784073600">15 Jul</td><td>50,000</td><td>600</td><td>$9.99</td>
    </tr>
  </tbody>
</table>
"""


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_mobile_main(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pc.MOBILE_MAIN_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "report_start_date": "2026-07-14",
                "report_end_date": "2026-07-26",
                "unified_name": "Ragnarok: The New World",
                "english_report_name": "Ragnarok: The New World",
                "unified_id": "mobile-1",
            }
        )


def with_temp_roots(callback):
    with repo_temp_dir("pc_steamdb_") as tmp:
        original_drop = pc.MEETING_DROP_ROOT
        original_output = pc.MEETING_PACK_OUTPUT_ROOT
        original_fetch = pc.fetch_live_html
        try:
            pc.MEETING_DROP_ROOT = Path(tmp) / "meeting_drop"
            pc.MEETING_PACK_OUTPUT_ROOT = Path(tmp) / "meeting_pack"
            write_mobile_main(pc.mobile_main_report_path("2026-07-28"))
            return callback(Path(tmp))
        finally:
            pc.MEETING_DROP_ROOT = original_drop
            pc.MEETING_PACK_OUTPUT_ROOT = original_output
            pc.fetch_live_html = original_fetch


def setup_url_file():
    write_text(
        pc.source_url_path("2026-07-28", "2026W30"),
        "https://steamdb.info/upcoming/?min_reviews=500&sort=peak_desc&week=2026W30",
    )


def setup_url_file_for_week(week):
    write_text(
        pc.source_url_path("2026-07-28", week),
        f"https://steamdb.info/upcoming/?min_reviews=500&sort=peak_desc&week={week}",
    )


def test_live_url_input_path_works_using_mocked_fixture():
    def run(_tmp):
        setup_url_file()
        pc.fetch_live_html = lambda url: FIXTURE_HTML
        path, rows, appendix_path, appendix, source_file = pc.build("2026-07-28", "2026W30")
        assert_true(path.exists(), "pc output created")
        assert_true(appendix_path.exists(), "pc appendix created")
        assert_equal(source_file, "live", "live source used")
        assert_equal(len(rows), 3, "junk rows excluded")
        assert_equal(len(appendix), 1, "appendix rows")
    with_temp_roots(run)


def test_fallback_saved_html_works():
    def run(_tmp):
        setup_url_file()
        write_text(pc.fallback_html_path("2026-07-28", "2026W30"), FIXTURE_HTML)
        pc.fetch_live_html = lambda url: (_ for _ in ()).throw(OSError("offline"))
        _path, rows, _appendix_path, _appendix, source_file = pc.build("2026-07-28", "2026W30")
        assert_equal(source_file, "steamdb_upcoming_2026W30.html", "fallback source used")
        assert_equal(len(rows), 3, "fallback parsed rows")
    with_temp_roots(run)


def test_multiple_weeks_combine_and_dedupe_by_higher_peak():
    def run(_tmp):
        setup_url_file_for_week("2026W29")
        setup_url_file_for_week("2026W30")
        write_text(pc.fallback_html_path("2026-07-28", "2026W29"), W29_FIXTURE_HTML)
        write_text(pc.fallback_html_path("2026-07-28", "2026W30"), W30_DUPLICATE_FIXTURE_HTML)
        pc.fetch_live_html = lambda url: (_ for _ in ()).throw(OSError("offline"))
        path, rows, appendix_path, appendix, source_file = pc.build("2026-07-28", steamdb_weeks="2026W29,2026W30")
        by_id = {row["steam_app_id"]: row for row in rows}
        assert_true(path.exists(), "combined pc output created")
        assert_true(appendix_path.exists(), "combined appendix output created")
        assert_equal(source_file, "steamdb_upcoming_2026W29.html, steamdb_upcoming_2026W30.html", "combined source files")
        assert_equal(len(rows), 3, "combined rows deduped")
        assert_equal(by_id["200"]["steamdb_peak"], "13000", "higher duplicate peak kept")
        assert_equal(by_id["200"]["steamdb_week"], "2026W29", "duplicate source week preserved")
        assert_equal(by_id["900"]["pc_title"], "SpiritVale", "SpiritVale included")
        assert_equal(by_id["900"]["release_date"], "2026-07-15", "SpiritVale release date parsed")
        assert_equal(by_id["900"]["steamdb_peak"], "20253", "SpiritVale peak parsed")
        assert_equal(by_id["900"]["pc_main_report_candidate"], "true", "SpiritVale main candidate")
        assert_equal(
            by_id["900"]["pc_report_reason"],
            "steamdb_peak_above_10000_in_report_period",
            "SpiritVale main reason",
        )
        assert_true(appendix, "combined appendix has rows")
    with_temp_roots(run)


def test_top_releases_saved_html_builds_with_source_metadata_and_rules():
    def run(_tmp):
        report_start = pc.parse_date("2026-07-14")
        report_end = pc.parse_date("2026-07-26")
        write_text(pc.top_releases_html_path("2026-07-28", report_start, report_end), TOP_RELEASES_FIXTURE_HTML)
        path, rows, appendix_path, appendix, source_file = pc.build("2026-07-28", source_kind=pc.SOURCE_KIND_TOP_RELEASES)
        by_id = {row["steam_app_id"]: row for row in rows}
        assert_true(path.exists(), "top releases pc output created")
        assert_true(appendix_path.exists(), "top releases appendix created")
        assert_equal(source_file, "steamdb_top_releases_2026-07-14_to_2026-07-27_game_rpg.html", "top releases source used")
        assert_equal(by_id["910"]["source_kind"], "top_releases", "source kind preserved")
        assert_equal(
            by_id["910"]["source_filter_note"],
            "SteamDB releases 2026-07-14 to 2026-07-27, games only, RPG genre",
            "source filter note preserved",
        )
        assert_equal(by_id["910"]["pc_main_report_candidate"], "true", "peak promotes main in period")
        assert_equal(by_id["920"]["pc_main_report_candidate"], "true", "exact mobile title promotes main")
        assert_equal(by_id["930"]["pc_main_report_candidate"], "false", "outside period peak does not promote")
        assert_true(all(row["pc_title"] for row in rows), "no blank pc title")
        assert_true(all(row["steam_app_id"] for row in rows), "no blank steam app id")
        assert_true(all(row["release_date"] for row in rows), "release date parsed when provided")
        assert_true("940" not in by_id, "junk exclusions still apply")
        assert_true(appendix, "top releases appendix has rows")
    with_temp_roots(run)


def test_missing_url_and_missing_html_fails_clearly():
    def run(_tmp):
        assert_raises(
            "SteamDB source URL file missing",
            lambda: pc.build("2026-07-28", "2026W30"),
            "missing URL fails",
        )
    with_temp_roots(run)


def test_parses_steamdb_table():
    rows = pc.parse_steamdb_table(FIXTURE_HTML)
    by_id = {row["steam_app_id"]: row for row in rows}
    assert_equal(by_id["100"]["pc_title"], "Ragnarok: The New World", "title parsed")
    assert_equal(by_id["200"]["release_date"], "2026-07-20", "release date parsed")
    assert_equal(by_id["200"]["steamdb_peak"], "12345", "peak parsed")
    assert_equal(by_id["200"]["steamdb_reviews"], "700", "reviews parsed")
    assert_equal(by_id["200"]["steamdb_price"], "$19.99", "price parsed")


def test_parses_saved_steamdb_row_shape():
    rows = pc.parse_steamdb_table(STEAMDB_SAVED_ROW_HTML, "2026W30")
    assert_equal(len(rows), 1, "saved row parsed")
    assert_equal(rows[0]["steam_app_id"], "3561220", "row app id parsed")
    assert_equal(rows[0]["pc_title"], "Pass the Fear", "class b title link preferred")
    assert_equal(rows[0]["release_date"], "2026-07-23", "unix data-sort release date parsed")
    assert_equal(rows[0]["steamdb_peak"], "10500", "saved row peak parsed")


def test_output_headers_are_stable():
    with repo_temp_dir("pc_headers_") as tmp:
        path = Path(tmp) / "out.csv"
        pc.write_csv(path, [])
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
    assert_equal(headers, pc.PC_MEETING_FIELDS, "pc output headers")


def test_source_metadata_columns_exist():
    assert_true("source_kind" in pc.PC_MEETING_FIELDS, "source kind column exists")
    assert_true("source_filter_note" in pc.PC_MEETING_FIELDS, "source filter note column exists")


def test_peak_above_10000_promotes_main_candidate():
    row = {"pc_title": "Global Hit", "release_date": "2026-07-20", "steamdb_peak": "10000"}
    result = pc.classify_pc_row(row, pc.parse_date("2026-07-14"), pc.parse_date("2026-07-26"), {})
    assert_equal(result["pc_main_report_candidate"], "true", "peak threshold main")
    assert_equal(result["pc_report_reason"], "steamdb_peak_above_10000_in_report_period", "peak reason")


def test_release_date_outside_period_does_not_promote_by_peak():
    row = {"pc_title": "Old Peak", "release_date": "2026-05-15", "steamdb_peak": "50000"}
    result = pc.classify_pc_row(row, pc.parse_date("2026-07-14"), pc.parse_date("2026-07-26"), {})
    assert_equal(result["pc_main_report_candidate"], "false", "outside period not main")
    assert_equal(result["pc_appendix_candidate"], "true", "outside period goes appendix")


def test_exact_mobile_title_match_promotes_main_candidate():
    row = {"pc_title": "Ragnarok: The New World", "release_date": "2025-01-01", "steamdb_peak": "1"}
    index = {
        pc.normalize_title("Ragnarok: The New World"): {
            "matched_mobile_main_game": "Ragnarok: The New World",
            "matched_mobile_unified_id": "mobile-1",
            "match_method": "exact_normalized_english_report_name",
        }
    }
    result = pc.classify_pc_row(row, pc.parse_date("2026-07-14"), pc.parse_date("2026-07-26"), index)
    assert_equal(result["pc_main_report_candidate"], "true", "mobile title match main")
    assert_equal(result["pc_report_reason"], "matched_mobile_main_game", "mobile match reason")


def test_dlc_demo_soundtrack_software_exclusions_work():
    titles = [
        "Big Game DLC",
        "Big Game Demo",
        "Big Game Soundtrack",
        "Big Game Editor Tool",
    ]
    for title in titles:
        row = {"pc_title": title, "release_date": "2026-07-20", "steamdb_peak": "50000"}
        result = pc.classify_pc_row(row, pc.parse_date("2026-07-14"), pc.parse_date("2026-07-26"), {})
        assert_equal(result["pc_main_report_candidate"], "false", title + " excluded")
        assert_true(result["exclude_reason"], title + " has exclude reason")


def test_needs_internet_enrichment_column_exists():
    assert_true("needs_internet_enrichment" in pc.PC_MEETING_FIELDS, "enrichment column exists")


def test_pc_appendix_output_is_created():
    def run(_tmp):
        setup_url_file()
        pc.fetch_live_html = lambda url: FIXTURE_HTML
        _path, _rows, appendix_path, appendix, _source_file = pc.build("2026-07-28", "2026W30")
        assert_true(appendix_path.exists(), "appendix output exists")
        assert_true(appendix, "appendix has rows")
    with_temp_roots(run)


def main():
    test_live_url_input_path_works_using_mocked_fixture()
    test_fallback_saved_html_works()
    test_multiple_weeks_combine_and_dedupe_by_higher_peak()
    test_top_releases_saved_html_builds_with_source_metadata_and_rules()
    test_missing_url_and_missing_html_fails_clearly()
    test_parses_steamdb_table()
    test_parses_saved_steamdb_row_shape()
    test_output_headers_are_stable()
    test_source_metadata_columns_exist()
    test_peak_above_10000_promotes_main_candidate()
    test_release_date_outside_period_does_not_promote_by_peak()
    test_exact_mobile_title_match_promotes_main_candidate()
    test_dlc_demo_soundtrack_software_exclusions_work()
    test_needs_internet_enrichment_column_exists()
    test_pc_appendix_output_is_created()
    print("PC_STEAMDB_DISCOVERY_CANDIDATES_TEST_PASS")


if __name__ == "__main__":
    main()
