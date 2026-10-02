@echo off
REM ============================================================
REM  Create a Windows Task that starts the scanner at logon
REM  and keeps it running in the background (no window).
REM  Right-click this file -> Run as administrator
REM ============================================================
cd /d "%~dp0"

schtasks /Create /TN "SMC_Forex_Scanner" /TR "\"%~dp0run_scanner_loop.bat\"" /SC ONLOGON /RL LIMITED /F /IT

if %errorlevel%==0 (
    echo.
    echo Task "SMC_Forex_Scanner" installed.
    echo It will start automatically when you log into Windows.
    echo.
    echo To start it NOW:
    echo   schtasks /Run /TN "SMC_Forex_Scanner"
    echo.
    echo To remove it later:
    echo   schtasks /Delete /TN "SMC_Forex_Scanner" /F
) else (
    echo Failed. Right-click this file and choose "Run as administrator".
)
echo.
pause
