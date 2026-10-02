@echo off
title SMC Forex Bot
color 0A
cd /d "%~dp0"

echo ============================================
echo   SMC Forex Bot
echo ============================================
echo.
echo Folder: %CD%
echo.

where python >nul 2>&1
if %errorlevel%==0 (
    set PY=python
) else (
    where py >nul 2>&1
    if %errorlevel%==0 (
        set PY=py
    ) else (
        echo ERROR: Python is not on PATH.
        echo.
        echo Fix: open the Python installer on your desktop
        echo - click Modify
        echo - tick "Add python.exe to PATH"
        echo - click Install
        echo.
        echo Then close this window and double-click START.bat again.
        echo.
        pause
        exit /b 1
    )
)

echo Using: %PY%
%PY% --version
echo.

echo Installing libraries (first run may take 1-2 minutes)...
%PY% -m pip install pandas numpy yfinance requests streamlit plotly
echo.

if not exist "smc_forex_bot_v2.py" (
    echo ERROR: smc_forex_bot_v2.py is missing from this folder.
    echo Put START.bat in the same folder as the bot files.
    echo.
    pause
    exit /b 1
)

echo Starting bot...
echo.
%PY% smc_forex_bot_v2.py
echo.
echo Bot finished or stopped.
pause
