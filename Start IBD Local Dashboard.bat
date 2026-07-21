@echo off
cd /d "%~dp0"
echo Starting IBD SG Local Dashboard...
echo.
echo Open this in Chrome or Edge:
echo http://127.0.0.1:8787
echo.
echo Keep this window open while using the dashboard.
echo Press Ctrl+C to stop the dashboard.
echo.
py scripts\local_dashboard_app.py
pause
