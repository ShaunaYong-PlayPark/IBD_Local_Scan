from pathlib import Path
import re

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
    assert_true('class="metric-badge neutral">PC</span>' in pc_html and "console-tag" not in pc_html, "PC-only cards should show PC without implying console availability")
    sourced_pc_html = exporter.platform_chips_for_row({"Game Title": "Sourced PC", "report_classification": "pc_only", "console_source_url": "https://example.com/console"}, "PC")
    assert_true('>PC</span>' in sourced_pc_html and 'title="Console availability source">Console</a>' in sourced_pc_html, "sourced PC cards should show a separate Console tag")

    cross_report_row = {
        "Game Title": "Cross-platform Test", "Release Date": "2026-08-01",
        "report_classification": "mobile_led_cross_platform", "Publisher": "Pub",
        "Developer": "Dev", "Genre": "RPG", "Platform": "iOS, Android, Steam",
        "Key Details": "A mobile-first cross-platform game.",
    }
    cross_html = exporter.sea_regional_mobile_card({
        "game_title": "Cross-platform Test", "original_title": "Cross-platform Test",
        "publisher": "Pub", "genre": "RPG", "platforms": "iOS, Android, Steam",
        "sea_st_gross_revenue": "4000", "sea_st_downloads": "10",
    }, [cross_report_row])
    assert_true(cross_html.count("Mobile + PC/Console") == 1, "cross-platform classification should render once beside the title")
    assert_true("console-tag" not in cross_html, "unsourced cross-platform cards should not render a Console tag")
    sourced_cross_html = exporter.sea_regional_mobile_card({
        "game_title": "Cross-platform Test", "original_title": "Cross-platform Test",
        "publisher": "Pub", "genre": "RPG", "platforms": "iOS, Android, Steam",
        "sea_st_gross_revenue": "4000", "sea_st_downloads": "10",
    }, [{**cross_report_row, "console_source_url": "https://example.com/console"}])
    assert_true(sourced_cross_html.count("Mobile + PC/Console") == 1 and sourced_cross_html.count('title="Console availability source">Console</a>') == 1, "sourced cross-platform cards should keep one classification and one Console tag")

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
        "Game Title": "Tracker Game", "Publisher": "Pub", "Developer": "Dev", "Platform": "Steam, PlayStation 5",
        "report_classification": "pc_only", "console_source_url": "https://example.com/console",
        "Release Date": "2026-08-01", "SG Gross Revenue": "1200", "SG Downloads": "30",
        "Related Brief": "18 Aug 2026 mock report | 04 Aug 2026 to 17 Aug 2026",
        "_brief_href": "proof-runs/2026-08-18/latest-brief.html", "_brief_period": "04 Aug 2026 to 17 Aug 2026",
        "meeting_date": "2026-08-18",
    }])
    assert_true(tracker_html.index("Related Brief") < tracker_html.index("Game Title"), "tracker brief action should be first")
    assert_true("brief-icon-link" in tracker_html and "folder-icon" in tracker_html and "aria-label=\"Open brief for 04 Aug 2026 to 17 Aug 2026\"" in tracker_html, "tracker brief action should be an accessible folder icon")
    assert_true("▣" not in tracker_html and "Developer" not in tracker_html, "tracker should not show the old symbol or developer")
    assert_true("data-sort-date" in tracker_html and "data-sort-revenue" in tracker_html and "data-sort-genre" in tracker_html, "tracker rows should expose sortable values")
    assert_true("PC, Console" in tracker_html, "tracker platforms should normalize to PC, Console")

    original_assets = exporter.ASSETS
    with repo_temp_dir("static_dashboard_ui_") as temp:
        exporter.ASSETS = Path(temp) / "assets"
        exporter.write_assets()
        js = (exporter.ASSETS / "static-dashboard.js").read_text(encoding="utf-8")
        css = (exporter.ASSETS / "static-dashboard.css").read_text(encoding="utf-8")
        assert_true("archiveYear" in js and "archiveMonth" in js and "filterArchive" in js, "archive filters should have browser behavior")
        assert_true("levels = ['Primary', 'Secondary', 'Tertiary']" in js and "tracker${level}Sort" in js, "tracker should expose multi-level sorting")
        assert_true("downloadTrackerCsv" in js and "escapeCsv" in js, "tracker should export filtered rows as CSV")
        assert_true("trackerSuggestions" in js and "ArrowDown" in js and "Escape" in js, "tracker search should provide keyboard-accessible suggestions")
        assert_true("IntersectionObserver" in js and "is-current" in js, "section selector should track the current section")
        assert_true("@media(max-width:768px)" in css and "on-page-nav" in css, "mobile navigation styling should be present")
        assert_true("site-header>.on-page-nav" in css and "on-page-nav[aria-expanded=\"true\"] .on-page-links" in css and "position:absolute!important" in css, "section selector should sit in the upper sticky header")
        assert_true(".on-page-nav{position:sticky" not in css and "on-page-nav{position:fixed" not in css and "on-page-nav{position:relative" not in css, "section selector should not float over the report body")
    exporter.ASSETS = original_assets
    controlled = exporter.apply_controlled_genres([{"Game Title": "Star Sailors", "Genre": "Role Playing", "source_urls": ""}])
    assert_true(controlled[0]["Genre"] == "RPG; Turn-Based Strategy", "normal export should apply Star Sailors controlled genre before validation")
    exporter.require_valid_game_genres(controlled)
    comparison = exporter.comparable_html({"comparable_game": "Reference Game", "comparison_reason": "Shared gameplay loop", "comparison_source_url": "https://example.com/reference"})
    assert_true("Comparable to" in comparison and "<a" not in comparison, "comparable-game name should be plain text")
    assert_true('href="https://play.google.com/store/apps/details?id=game"' in exporter.game_title_html("Reported Game", {"report_classification": "mobile_only", "source_urls": "https://play.google.com/store/apps/details?id=game"}), "reported game title should carry its own storefront link")
    assert_true(exporter.game_source_url({"report_classification": "mobile_only", "source_urls": "https://example.com/official | https://play.google.com/store/apps/details?id=game"}).startswith("https://play.google.com/"), "mobile title links should prefer a confirmed mobile storefront")
    assert_true(exporter.game_source_url({"report_classification": "pc_only", "source_urls": "https://example.com/official", "steam_url": "https://store.steampowered.com/app/1/"}).startswith("https://store.steampowered.com/"), "PC title links should prefer Steam")
    surviving_row = {"Game Title": "Surviving for 33 days", "report_classification": "mobile_only", "mobile_storefront_url": "https://play.google.com/store/apps/details?id=com.tg.sc33t.tw", "source_urls": "https://survive33days.37.com.cn/article"}
    assert_true(exporter.game_source_url(surviving_row) == "https://play.google.com/store/apps/details?id=com.tg.sc33t.tw", "Surviving for 33 Days should use its verified Google Play storefront")

    news_html = exporter.news_context_card({
        "title_en": "Regional announcement", "source": "Example", "published_at": "2026-08-12",
        "affected_countries": "SG, MY, PH, ID, TH, VN", "url": "https://example.com",
        "context_type": "industry_trend", "key_details": "A factual event.", "why_it_matters": "Relevant regional context.",
    }, "Industry trend")
    assert_true(all(f'class="country-code-tag">{code}<' in news_html for code in ("SG", "MY", "PH", "ID", "TH", "VN")), "affected markets should render SEA6 country-code tags")

    generated = [Path("docs/latest-brief.html")] + [Path(f"docs/proof-runs/{date}/latest-brief.html") for date in ("2026-07-07", "2026-07-21", "2026-08-04", "2026-08-18")]
    archive_html = Path("docs/historical-briefs.html").read_text(encoding="utf-8")
    assert_true("Proof run" not in archive_html and "Mock report" not in archive_html and "Latest report" not in archive_html, "archive cards should use neutral completion wording")
    for path in generated:
        html = path.read_text(encoding="utf-8")
        assert_true("Developer" not in html, f"developer should be absent from executive UI: {path}")
        assert_true("Mobile-only Games" in html or "Mobile + PC/Console Games" in html, f"release grouping should render: {path}")
        assert_true('class="comparison-block"><b>Comparable to</b><p><a ' not in html, f"comparables should remain plain text: {path}")
        pc_cards = re.findall(r'<article class="regional-pc-card">(.*?)</article>', html, flags=re.S)
        assert_true(all("Steam URL</a>" not in card for card in pc_cards), f"PC cards should not duplicate the title Steam link: {path}")
        assert_true("<span class=\"genre-tag\">Games<" not in html and "<span class=\"genre-tag\">Game<" not in html, f"generic genre tag should not render: {path}")
        mobile_cards = re.findall(r'<article class="sea-country-card">(.*?)</article>', html, flags=re.S)
        for card in mobile_cards:
            if "Mobile" in card and "sea-country-card-heading" in card:
                heading = re.search(r'<div class="sea-country-card-heading">(.*?)</div>', card, flags=re.S)
                assert_true(heading and re.search(r'<h3><a href="https://(?:apps\.apple\.com|play\.google\.com)/', heading.group(1)), f"mobile final-report card must link its title to a mobile storefront: {path}")
    print("STATIC_DASHBOARD_UI_PASS")


if __name__ == "__main__":
    main()
