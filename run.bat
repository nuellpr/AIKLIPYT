@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :check_deps

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.11 or newer is required: https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required. Installed Python is older than 3.11.
  pause
  exit /b 1
)

echo Creating virtual environment...
%PY% -m venv .venv
if errorlevel 1 (
  echo Failed to create .venv
  pause
  exit /b 1
)

:check_deps
if exist ".venv\.req-stamp" (
  fc /b requirements.txt ".venv\.req-stamp" >nul 2>nul && goto :launch
)

echo Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install --quiet --no-input -r requirements.txt
if errorlevel 1 (
  echo Failed to install requirements
  pause
  exit /b 1
)
copy /y requirements.txt ".venv\.req-stamp" >nul

:launch
if /I "%~1"=="--update" (
  echo Updating yt-dlp...
  ".venv\Scripts\python.exe" -m pip install --no-input --upgrade yt-dlp
  exit /b %errorlevel%
)
".venv\Scripts\python.exe" server.py %*
if errorlevel 1 pause
