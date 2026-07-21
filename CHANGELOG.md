# Changelog

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
