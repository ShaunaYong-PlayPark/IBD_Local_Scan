# IBD Local Scan

Local proof of concept for Singapore mobile launch discovery and meeting-cycle market briefs.

The project stores workflow data locally and serves a private local dashboard. Sensor Tower API calls are only made by the live extraction scripts. Offline tests and dashboard rendering do not call Sensor Tower.

## Setup

1. Copy `.env.example` to `.env` for local secrets.
2. Set `SENSORTOWER_AUTH_TOKEN` in your shell or deployment environment.
3. Copy `config/settings.example.json` to `config/settings.json`.
4. Update report dates, ranking date, countries, or chart config in `config/settings.json` as needed.

Do not commit `.env` or `config/settings.json`.

## Dashboard

Run the local dashboard:

```powershell
python scripts/local_dashboard_app.py
```

Open:

```text
http://127.0.0.1:8787
```

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

Before publishing to GitHub or deploying:

- keep secrets in environment variables,
- do not commit raw Sensor Tower responses,
- do not commit local logs, backups, caches, or runtime state,
- add private access control before sharing with external viewers,
- use persistent storage for mutable CSV/JSON state or migrate to a database.
