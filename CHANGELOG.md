# Changelog

## v1.0.0-static-beta - Static GitHub Pages MVP

Summary:
Pivoted the project from a live Python dashboard app to a static GitHub Pages deployment model.

Included:
- Static dashboard export
- GitHub Pages-ready docs/ output
- View-only latest brief page
- View-only table page
- View-only historical briefs page
- View-only game tracker page
- Removal/deprioritisation of login/admin features for deployed static version
- Meeting date controlled by committed config file
- Automation preserved through Python scripts and GitHub Actions
- Scheduled GitHub Actions automation for weekly capture and meeting-day refresh
- Clear workflow failure when live automation is due but Sensor Tower secret is missing
- Static site can be viewed without running a Python server

Changed:
- Free deployment target changed from live Python app hosting to static GitHub Pages
- Users can view reports but cannot edit settings from the website
- Admin console is no longer part of the deployed free version
- Access control is removed for static deployment

Known limitations:
- Static site only updates after export/GitHub Actions run
- No live admin console
- No browser-based meeting-date edits
- No viewer/admin login in deployed static version
- GitHub Pages site is view-only
- Sensor Tower automation still depends on GitHub Secrets being configured
- Meeting cadence still depends on the committed static schedule config being kept current

Next planned work:
- Push to private/public GitHub repo as appropriate
- Enable GitHub Pages from docs/
- Configure GitHub Secrets
- Test manual GitHub Actions workflow
- Test scheduled automation after GitHub Secret setup

## v1.0.0-beta - Local MVP

Summary:
Initial local MVP of the IBD SG market scan dashboard with Sensor Tower workflow, authentication, audit logging, and documentation.

Included:
- Local dashboard for latest brief, historical briefs, game tracker, and admin console
- Meeting-date/report-period logic
- Weekly candidate capture workflow
- Meeting-day final report workflow
- Sensor Tower extraction workflow
- SEA6 revenue/download aggregation
- Title mapping and English display title handling
- Data-as-of metadata handling
- Controlled live test validation
- Viewer login
- Country-admin login
- Admin-only console
- Admin audit log
- Project architecture documentation
- Secret-safe Git setup

Known limitations:
- Deployment not yet completed
- Scheduled jobs not yet configured on a server
- Audit email is self-entered and not SSO-verified
- Country admin passwords may be shared
- Production environment variables still need to be configured on host
- Persistent storage still needs to be configured on host
- HTTPS/private hosting still required

Next planned work:
- Push to private GitHub
- Deploy to private host
- Configure production environment variables
- Configure persistent storage
- Configure scheduled jobs
- Run UAT with intended users
