@echo off
REM Streamlit dashboard - starts minimized, stays running
cd /d "%~dp0"
if not exist "logs" mkdir logs
start "SMC Dashboard" /MIN python -m streamlit run "%~dp0smc_dashboard.py" --server.headless true --server.port 8501
echo Dashboard starting at http://localhost:8501
echo Window is minimized. Close it from Task Manager (python.exe) or run stop_bot.bat
timeout /t 5 >nul
exit
