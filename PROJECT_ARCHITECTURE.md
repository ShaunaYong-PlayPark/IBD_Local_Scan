# IBD SG Market Scan POC Architecture

## 1. Project Purpose

The IBD Singapore market scan proof of concept helps PlayPark review newly visible mobile game launches in Singapore and prepare a meeting-ready market brief.

It is used by:

- Project owners who need a readable market brief.
- Viewers who need access to the latest report, historical briefs, and game tracker.
- Country admins who manage meeting dates and review admin activity.
- Future developers maintaining the local workflow and dashboard.

The project solves a simple problem: instead of manually checking Sensor Tower outputs, release signals, SEA6 performance, and report spreadsheets, it turns the local workflow data into a dashboard and final CSV that can be reviewed before each IBD meeting.

## 2. High-Level Architecture

The project is a local Python proof of concept with these parts:

- Local dashboard: served by `scripts/local_dashboard_app.py`.
- Viewer and country-admin authentication: simple cookie/session auth using environment variables.
- Admin audit logging: successful admin setting changes are appended to a local CSV.
- Weekly candidate capture: stores candidate games detected from weekly workflow outputs.
- Meeting-day final report generation: refreshes selected candidates and rebuilds the final report.
- Sensor Tower extraction: live extraction scripts call Sensor Tower only when explicitly run.
- Local data storage: CSV and JSON files under `data/`.

The dashboard reads local output files. It does not call Sensor Tower by itself.

## 3. Access Model

Login asks for:

- PlayPark email
- Password

Access is controlled by environment variables:

- `APP_VIEWER_PASSWORD` gives viewer access.
- `APP_ADMIN_PASSWORD_SG` gives Singapore admin access.
- `APP_ADMIN_PASSWORD_TH` gives Thailand admin access.
- `APP_ADMIN_PASSWORD_MY` gives Malaysia admin access.
- `APP_ADMIN_PASSWORD_ID` gives Indonesia admin access.
- `APP_ADMIN_PASSWORD_PH` gives Philippines admin access.
- `APP_ADMIN_PASSWORD_VN` gives Vietnam admin access.
- `APP_ALLOWED_EMAIL_DOMAINS` controls accepted email domains. The default is `playpark.com`.

Session data stores:

- `playpark_email`
- `role`
- `admin_country`

Viewer sessions have no `admin_country`.

Rules:

- Viewer users can access Latest Brief, table view, Brief Archive, and Game Tracker.
- Viewer users cannot access Admin Console or the admin audit log.
- Admin users can access all viewer pages, Admin Console, and the admin audit log.
- Admin navigation appears only for admin users.
- Logout clears the session.

## 4. Audit Logging

Admin audit log file:

```text
data/local_app/admin_audit_log.csv
```

Behavior:

- Append-only.
- Created with headers if missing.
- Logs successful admin changes only.
- Does not log failed attempts.
- Does not log passwords.
- Does not log the Sensor Tower token.
- Does not log secret environment variables.

Logged fields:

```text
timestamp, playpark_email, role, admin_country, action, field, old_value, new_value, path, ip_address
```

Admin audit route:

```text
/admin/audit-log
```

This route is admin-only and shows the most recent 100 audit rows, newest first.

The audit log file is ignored by Git because it may contain PlayPark email addresses and local admin activity.

Current limitation: the email identity is self-entered at login, and country admin passwords may be shared. For production, use named accounts or an identity provider.

## 5. Folder Structure

```text
scripts/
```

Python and PowerShell workflow scripts. This includes the dashboard app, candidate capture, Sensor Tower extraction layers, final report generation, and controlled live-test helper.

```text
templates/
```

HTML templates used by the dashboard.

```text
static/
```

Dashboard CSS and JavaScript assets.

```text
config/
```

Configuration examples and local settings. `config/settings.json` is local-only and ignored by Git.

```text
data/local_app/
```

Local dashboard state, extraction metadata, admin audit log, watchlist, and other runtime files.

```text
data/output/
```

Generated workflow outputs, including the final dashboard/report CSV.

```text
data/cache/
```

Local cache files. Ignored by Git.

```text
data/raw/
```

Raw Sensor Tower responses. Ignored by Git.

```text
backups/
```

Local backups made before risky edits or controlled live tests. Ignored by Git.

## 6. Main Workflow

Weekly candidate capture:

1. Weekly workflow outputs identify candidate games.
2. `scripts/weekly_candidate_capture.py` stores candidates in the weekly candidate store.
3. The no-API mode `--from-existing-outputs` can update the store from existing local outputs.

Meeting-date processing:

1. Meeting-cycle state defines the current report period.
2. Stored candidates are selected for that period.
3. Ranks are refreshed for selected report-period candidates.
4. SEA6 sales extraction runs for selected unified app IDs.
5. Title mapping normalizes display titles using the local master mapping.
6. Final report CSV is rebuilt.
7. Dashboard reads the final CSV and displays the brief.

SEA6 sales extraction:

- Uses selected unified app IDs.
- Aggregates country-level sales and downloads for SG, MY, TH, ID, PH, and VN.

Title mapping:

- Uses `data/reference/master_title_mapping.csv`.
- Keeps known English display titles stable.
- Flags unmapped non-Latin titles for review instead of rough-translating them.

Final CSV rebuild:

- Produces `data/output/final_sg_market_scan_current_workflow.csv`.
- This is the main dashboard/report input.

Dashboard display:

- Latest Brief reads the final CSV.
- Game Tracker reads the same local report data.
- Admin Console manages meeting date settings only in the current simplified POC.

## 7. Environment Variables

No actual values should be committed.

```text
SENSORTOWER_AUTH_TOKEN
```

Used by live Sensor Tower extraction scripts.

```text
APP_VIEWER_PASSWORD
```

Shared viewer password for dashboard read access.

```text
APP_ADMIN_PASSWORD_SG
APP_ADMIN_PASSWORD_TH
APP_ADMIN_PASSWORD_MY
APP_ADMIN_PASSWORD_ID
APP_ADMIN_PASSWORD_PH
APP_ADMIN_PASSWORD_VN
```

Country admin passwords. A matching password creates an admin session and stores the matching country code.

```text
APP_ALLOWED_EMAIL_DOMAINS
```

Comma-separated allowed email domains for login. Defaults to `playpark.com`.

## 8. Important Files

```text
scripts/local_dashboard_app.py
```

Local dashboard server, authentication, admin access control, audit-log route, and dashboard routing.

```text
scripts/weekly_candidate_capture.py
```

Weekly candidate capture entry point. Supports live capture and no-API capture from existing outputs.

```text
scripts/meeting_date_final_report.py
```

Meeting-day final report workflow. Runs report-period candidate preparation, rank refresh, SEA6 sales extraction, final CSV rebuild, and updates extraction metadata after successful Sensor Tower refresh.

```text
scripts/run_controlled_live_test.ps1
```

PowerShell helper for a controlled live Sensor Tower test using a known previous report period. Includes validation-only mode for checking existing outputs without rerunning live extraction.

```text
config/settings.example.json
```

Safe example config without secrets.

```text
.env.example
```

Safe example environment variables with placeholders only.

```text
data/reference/master_title_mapping.csv
```

Local title mapping file.

```text
data/local_app/extraction_metadata.json
```

Stores the Sensor Tower data-as-of metadata used by the dashboard.

```text
data/local_app/admin_audit_log.csv
```

Append-only local admin audit log. Ignored by Git.

## 9. Data-Flow Diagram

```text
Sensor Tower
  -> raw/extraction data
  -> SEA6 aggregation
  -> final CSV
  -> dashboard
```

```text
Admin login
  -> settings change
  -> config/state update
  -> append audit-log row
```

## 10. Deployment Requirements

Before this becomes a shared private web app:

- Use private hosting.
- Serve over HTTPS.
- Store all secrets in secure environment variables.
- Provide persistent storage for audit logs and local app state.
- Configure scheduled jobs for weekly and meeting-day workflows.
- Add a production secret/session key or use a proper server-side session store.
- Back up local state, output data, and audit logs.
- Consider replacing shared passwords with named accounts or SSO.

## 11. Scheduled Jobs

Weekly candidate capture:

```text
python scripts/weekly_candidate_capture.py
```

Meeting-day final report generation:

```text
python scripts/meeting_date_final_report.py
```

The meeting-day command makes live Sensor Tower calls and should only run when a real refresh is intended.

## 12. Recovery and Troubleshooting

Backups:

- Local backups are stored under `backups/`.
- Use them to restore config, output data, raw data, metadata, or state after a failed test.

Config restore:

- Restore `config/settings.json` from backup if report dates or ranking dates were changed during a test.

Controlled validation:

- Use `scripts/run_controlled_live_test.ps1 -ValidateOnly` to validate existing controlled-test outputs without making API calls.

Final CSV:

```text
data/output/final_sg_market_scan_current_workflow.csv
```

Extraction metadata:

```text
data/local_app/extraction_metadata.json
```

Audit log:

```text
data/local_app/admin_audit_log.csv
```

If the dashboard shows stale or unexpected data, check:

- Current report period in `config/settings.json`.
- Meeting-cycle state in `data/local_app/state.json`.
- Final CSV contents.
- Extraction metadata date.
- Whether the intended live workflow actually completed.

## 13. Current MVP Status

Working:

- Dashboard
- Viewer login
- Country-admin login
- Admin-only console
- Admin audit log
- Title mapping
- Meeting-date logic
- Data-as-of logic
- Live Sensor Tower workflow
- SEA6 extraction
- Final report rebuild

Remaining:

- Commit architecture document
- Push to private GitHub
- Deploy
- Configure production environment variables
- Use HTTPS/private access
- Configure persistent storage
- Configure scheduled jobs
