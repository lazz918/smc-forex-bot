@echo off
REM ============================================================
REM  SMC Forex Bot - run in the background (Windows)
REM  Double-click this file. A console window will flash once
REM  then the bot keeps running with no window.
REM ============================================================
cd /d "%~dp0"

REM -- Create logs folder
if not exist "logs" mkdir logs

set LOGFILE=logs\bot_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%.log
set LOGFILE=%LOGFILE: =0%

echo Starting SMC bot in background...
echo Logs: %CD%\%LOGFILE%

REM pythonw = Python with NO console window
start "" /MIN pythonw "%~dp0smc_forex_bot_v2.py"

echo.
echo Bot is running in the background.
echo Close it from Task Manager: look for pythonw.exe
echo.
timeout /t 4 >nul
exit
