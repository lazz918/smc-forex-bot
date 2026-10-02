@echo off
REM Stop all background SMC bot processes
echo Stopping SMC bot processes...
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *" >nul 2>&1
wmic process where "CommandLine like '%%smc_forex_bot%%' or CommandLine like '%%smc_scanner_loop%%' or CommandLine like '%%smc_dashboard%%'" call terminate >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
echo Done. Check Task Manager if anything is still running.
pause
