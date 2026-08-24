from pathlib import Path

import export_static_dashboard as exporter
from test_temp_utils import repo_temp_dir


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    market_row = {
        "sea_market_1_country": "PH", "sea_market_1_revenue_gross": "52050",
        "sea_market_2_country": "SG", "sea_market_2_revenue_gross": "42034",
        "sea_market_3_country": "ID", "sea_market_3_revenue_gross": "38215",
        "sea_market_4_country": "MY", "sea_market_4_revenue_gross": "32345",
    }
    market_html = exporter.top_sea_revenue_markets_html(market_row)
    assert_true("market-rank-1" in market_html and "Philippines" in market_html, "rank one market should be visually distinct")
    assert_true(market_html.index("Philippines") < market_html.index("Singapore") < market_html.index("Indonesia") < market_html.index("Malaysia"), "markets should be revenue ordered")
    assert_true("<ol" in market_html and "metric-badge" not in market_html, "markets should use a compact ranked list")

    assert_true(exporter.steam_rating_percent({"steamdb_rating_percent": "96"}) == "96", "supported Steam rating should render")
    assert_true(exporter.steam_rating_percent({"steamdb_rating_percent": "N/A"}) == "", "unsupported Steam rating should stay blank")
    pc_html = exporter.regional_pc_signals([{
        "report_classification": "pc_only", "Game Title": "PC Test", "Release Date": "2026-08-01",
        "steamdb_peak": "100", "steamdb_reviews": "50", "steamdb_rating_percent": "96",
        "steam_url": "https://example.com/steam", "Inclusion Reason": "SteamDB evidence",
    }])
    assert_true("96%" in pc_html and "Country revenue" not in pc_html and "iOS" not in pc_html, "PC cards should show supported rating without mobile metrics")

    report_row = {
        "Game Title": "Country Test", "Release Date": "2026-08-01",
        "report_classification": "mobile_only", "Publisher": "Pub",
        "Developer": "Dev", "Genre": "RPG", "Platform": "iOS, Android",
        "Key Details": "A mobile game.",
    }
    country_row = {
        "game_title": "Country Test", "original_title": "Country Test",
        "publisher": "Pub", "genre": "RPG", "sg_revenue_gross": "4000",
        "sg_downloads": "10", "sg_ios_rank": "1", "sg_android_rank": "2",
    }
    general_release_html = exporter.sea_country_card(country_row, "SG", [report_row])
    assert_true("First recorded mobile release" in general_release_html, "shared release date should be labeled as first recorded mobile release")
    assert_true("Mobile release in Singapore" not in general_release_html, "shared release date must not be labeled country-specific")
    specific_release_html = exporter.sea_country_card({**country_row, "sg_mobile_release_date": "2026-08-03"}, "SG", [report_row])
    assert_true("Mobile release in Singapore" in specific_release_html, "country-specific release date should use the country label")
    assert_true("First recorded mobile release" not in specific_release_html, "country-specific date should not use the general label")

    archive_html = exporter.proof_archive_cards([
        {"folder": "2026-08-18", "meeting": "18 Aug 2026", "period": "04 Aug 2026 to 17 Aug 2026", "data_as_of": "17 Aug 2026", "sea_game_count": 1, "sea_revenue": 100, "sea_downloads": 20, "href": "proof-runs/2026-08-18/latest-brief.html"},
        {"folder": "2026-07-21", "meeting": "21 Jul 2026", "period": "07 Jul 2026 to 20 Jul 2026", "data_as_of": "20 Jul 2026", "sea_game_count": 1, "sea_revenue": 90, "sea_downloads": 10, "href": "proof-runs/2026-07-21/latest-brief.html"},
    ])
    assert_true('data-archive-year="2026"' in archive_html and 'data-archive-month="08"' in archive_html, "archive cards should expose filter metadata")

    tracker_html = exporter.tracker_table([{
        "Game Title": "Tracker Game", "Publisher": "Pub", "Developer": "Dev", "Platform": "Mobile",
        "Release Date": "2026-08-01", "SG Gross Revenue": "1200", "SG Downloads": "30",
        "Related Brief": "18 Aug 2026 mock report | 04 Aug 2026 to 17 Aug 2026",
        "_brief_href": "proof-runs/2026-08-18/latest-brief.html", "_brief_period": "04 Aug 2026 to 17 Aug 2026",
        "meeting_date": "2026-08-18",
    }])
    assert_true(tracker_html.index("Related Brief") < tracker_html.index("Game Title"), "tracker brief action should be first")
    assert_true("brief-icon-link" in tracker_html and "aria-label=\"Open brief for 04 Aug 2026 to 17 Aug 2026\"" in tracker_html, "tracker brief action should be an accessible icon")
    assert_true("data-sort-date" in tracker_html and "data-sort-revenue" in tracker_html, "tracker rows should expose sortable values")

    original_assets = exporter.ASSETS
    with repo_temp_dir("static_dashboard_ui_") as temp:
        exporter.ASSETS = Path(temp) / "assets"
        exporter.write_assets()
        js = (exporter.ASSETS / "static-dashboard.js").read_text(encoding="utf-8")
        css = (exporter.ASSETS / "static-dashboard.css").read_text(encoding="utf-8")
        assert_true("archiveYear" in js and "archiveMonth" in js and "filterArchive" in js, "archive filters should have browser behavior")
        assert_true("trackerSort" in js and "trackerSortDirection" in js and "sortTracker" in js, "tracker sorting should have browser behavior")
        assert_true("IntersectionObserver" in js and "is-current" in js, "section selector should track the current section")
        assert_true("@media(max-width:768px)" in css and "on-page-nav" in css, "mobile navigation styling should be present")
    exporter.ASSETS = original_assets
    print("STATIC_DASHBOARD_UI_PASS")


if __name__ == "__main__":
    main()
