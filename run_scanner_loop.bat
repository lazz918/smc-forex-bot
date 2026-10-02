@echo off
REM ============================================================
REM  SMC Forex Bot - scanner loop (keeps scanning forever)
REM  Runs hidden. Restarts automatically if it crashes.
REM ============================================================
cd /d "%~dp0"
if not exist "logs" mkdir logs

:loop
echo [%date% %time%] Scanner started >> logs\scanner.log
pythonw "%~dp0smc_scanner_loop.py"
echo [%date% %time%] Scanner exited, restarting in 60s >> logs\scanner.log
timeout /t 60 /nobreak >nul
goto loop
