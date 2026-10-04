@echo off
title SMC Forex Bot
color 0A
cd /d "%~dp0"
echo ============================================
echo   SMC Forex Bot
echo ============================================
echo Folder: %CD%
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  set PY=py
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    set PY=python
  ) else (
    echo ERROR: Python not found. Install Python and tick Add to PATH.
    pause
    exit /b 1
  )
)

echo Using %PY%
%PY% --version
echo.
echo Installing pandas numpy if needed...
%PY% -m pip install pandas numpy
echo.
echo Running bot...
echo.
%PY% smc_bot.py %*
echo.
pause
