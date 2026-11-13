@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :launch

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.11 or newer is required: https://www.python.org/downloads/
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

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo Failed to install requirements
  pause
  exit /b 1
)

:launch
".venv\Scripts\python.exe" server.py %*
if errorlevel 1 pause
