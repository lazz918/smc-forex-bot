@echo off
title SMC Scanner
cd /d "%~dp0"
where py >nul 2>&1 && set PY=py || set PY=python
%PY% -m pip install pandas numpy
%PY% smc_bot.py scanner
pause
