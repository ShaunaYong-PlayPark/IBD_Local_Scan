@echo off
echo Stopping IBD SG Local Dashboard...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*local_dashboard_app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Done. You can close this window.
pause
