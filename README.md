# IBD Local Scan

Local proof of concept for Singapore mobile launch discovery and meeting-cycle market briefs.

The project stores workflow data locally and exports a static GitHub Pages dashboard. Sensor Tower API calls are only made by the live extraction scripts. Offline tests and static dashboard rendering do not call Sensor Tower.

## Setup

1. Copy `.env.example` to `.env` for local secrets.
2. Set `SENSORTOWER_AUTH_TOKEN` in your shell or deployment environment.
3. Set `APP_VIEWER_PASSWORD` and the country admin password variables in your shell or deployment environment.
4. Copy `config/settings.example.json` to `config/settings.json`.
5. Update report dates, ranking date, countries, or chart config in `config/settings.json` as needed.

Do not commit `.env` or `config/settings.json`.

## Dashboard

## Static GitHub Pages Dashboard

The deployed MVP is a view-only static website generated into:

```text
docs/
```

GitHub Pages can serve the site from `docs/` without running a Python server.

Build the static dashboard from existing local outputs:

```powershell
python scripts/export_static_dashboard.py
```

Open locally by double-clicking:

```text
docs/index.html
```

Static pages:

- `docs/index.html`
- `docs/latest-brief.html`
- `docs/latest-brief.html?view=table`
- `docs/historical-briefs.html`
- `docs/game-tracker.html`

The static site is view-only. It does not include login, Admin Console, country-admin access, browser-based audit log, or browser-based setting changes.

Meeting date changes for the static site are made by editing and committing:

```text
config/static_report_schedule.json
```

After changing the schedule config or refreshing report outputs, rerun the static export and commit the updated `docs/` files.

## Local Development Dashboard

Run the local dashboard:

```powershell
python scripts/local_dashboard_app.py
```

Open:

```text
http://127.0.0.1:8787
```

The old local Python dashboard remains useful for development. Its login/admin features are not used by the static GitHub Pages deployment. Local dashboard access is controlled by environment variables. Login requires a PlayPark email address and a password.

```powershell
$env:APP_VIEWER_PASSWORD='your_viewer_password'
$env:APP_ADMIN_PASSWORD_SG='your_sg_admin_password'
$env:APP_ADMIN_PASSWORD_TH='your_th_admin_password'
$env:APP_ADMIN_PASSWORD_MY='your_my_admin_password'
$env:APP_ADMIN_PASSWORD_ID='your_id_admin_password'
$env:APP_ADMIN_PASSWORD_PH='your_ph_admin_password'
$env:APP_ADMIN_PASSWORD_VN='your_vn_admin_password'
$env:APP_ALLOWED_EMAIL_DOMAINS='playpark.com'
```

Viewer login can open Latest Brief, table view, Brief Archive, and Game Tracker. A country admin password opens Admin Console and records the admin country in the session. Password values are never displayed or logged by the dashboard.

Successful admin date/settings changes append an audit row to:

```text
data/local_app/admin_audit_log.csv
```

Admins can view the most recent 100 rows at `/admin/audit-log`.

Optional port override:

```powershell
$env:IBD_DASHBOARD_PORT='8878'
python scripts/local_dashboard_app.py
```

## Weekly Candidate Capture

Live weekly capture:

```powershell
python scripts/weekly_candidate_capture.py
```

Offline/no-API test using existing local outputs:

```powershell
python scripts/weekly_candidate_capture.py --from-existing-outputs
```

The permanent candidate store is:

```text
data/candidates/weekly_candidate_store.csv
```

Weekly snapshots are written to:

```text
data/candidates/snapshots/
```

## Meeting-Date Final Report

Run on meeting day only when a real Sensor Tower refresh is intended:

```powershell
python scripts/meeting_date_final_report.py
```

This command refreshes SG ranks and SEA6 sales metrics through Sensor Tower, then rebuilds:

```text
data/output/final_sg_market_scan_current_workflow.csv
```

After successful completion, it updates:

```text
data/local_app/extraction_metadata.json
```

That metadata drives the dashboard `Data as of` label.

## No-API Validation

Candidate-store simulation:

```powershell
python scripts/test_candidate_store_simulation.py
```

Title mapping:

```powershell
python scripts/layer3_5_title_normalise.py
```

Current report build from existing local files:

```powershell
python scripts/current_report_watchlist_workflow.py
```

## Live API Scripts

These scripts require `SENSORTOWER_AUTH_TOKEN`:

- `scripts/layer1_sg_rankings_only_candidates.py`
- `scripts/layer2_enrich_unified_apps.py`
- `scripts/layer3_fetch_app_metadata.py`
- `scripts/layer4_fetch_sea6_sales_metrics.py`
- `scripts/refresh_report_period_ranks.py`
- `scripts/meeting_date_final_report.py`
- `scripts/weekly_candidate_capture.py` unless run with `--from-existing-outputs`

## Title Mapping

The local title mapping file is:

```text
data/reference/master_title_mapping.csv
```

Expected columns:

```text
original_title,unified_id,detected_language_code,english_display_title
```

Unknown non-Latin titles are preserved unchanged and flagged for review. The dashboard does not rough-translate unmapped titles.

## Deployment Notes

For GitHub Pages:

1. Push the repository to GitHub.
2. In repository settings, enable Pages from the `docs/` folder on the main branch.
3. Configure `SENSORTOWER_AUTH_TOKEN` as a GitHub Secret if GitHub Actions will run live extraction.
4. Use `.github/workflows/build-static-dashboard.yml` to rebuild the static site manually or on schedule. Manual modes are `static-export-only`, `weekly-capture`, and `meeting-day-final-report`.

Scheduled runs happen daily and use `config/static_report_schedule.json` to decide the correct action:

- On the configured weekly capture weekday, the workflow runs `scripts/weekly_candidate_capture.py`, then exports the static site.
- On the configured upcoming meeting date, the workflow runs `scripts/meeting_date_final_report.py`, then exports the static site.
- On other days, it runs static export only.

If a scheduled live automation is due but `SENSORTOWER_AUTH_TOKEN` is missing from GitHub Secrets, the workflow fails clearly and does not publish a fresh-looking stale site.

Before any broader deployment:

- keep secrets in environment variables,
- do not commit raw Sensor Tower responses,
- do not commit local logs, backups, caches, or runtime state,
- remember GitHub Pages is view-only static hosting,
- configure scheduled jobs deliberately because live Sensor Tower refreshes consume API calls.
