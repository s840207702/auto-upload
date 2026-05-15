@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 (
  echo [ERROR] Failed to enter app folder.
  pause
  exit /b 1
)

set "APP_PORT=5409"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PY=.venv\Scripts\python.exe"

echo.
echo ========================================
echo   Social Auto Upload Oneclick
echo ========================================
echo.

if not exist "%PY%" (
  echo [INFO] Local venv not found. Creating it with uv...
  where uv >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] uv was not found and .venv is missing.
    echo Please install uv or create .venv manually.
    pause
    exit /b 1
  )
  uv venv --python 3.12
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv.
    pause
    exit /b 1
  )
)

echo [INFO] Checking Python runtime...
"%PY%" -c "import sys; print(sys.executable)"
if errorlevel 1 (
  echo [ERROR] Python runtime is not usable.
  pause
  exit /b 1
)

echo [INFO] Checking Python dependencies...
"%PY%" -c "import flask, flask_cors, playwright, xhs, biliup, loguru, qrcode, requests" >nul 2>nul
if errorlevel 1 (
  where uv >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Dependencies are missing and uv was not found.
    echo Please install uv, then run this file again.
    pause
    exit /b 1
  )
  echo [INFO] Installing dependencies...
  uv pip install -r requirements-oneclick.txt
  if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
  )
)

if not exist "videoFile" mkdir "videoFile"
if not exist "cookiesFile" mkdir "cookiesFile"
if not exist "db" mkdir "db"
if not exist "logs" mkdir "logs"

if not exist ".starter\playwright-installed.flag" (
  echo [INFO] Installing Chromium for Playwright...
  "%PY%" -m playwright install chromium
  if not errorlevel 1 (
    if not exist ".starter" mkdir ".starter"
    echo installed>".starter\playwright-installed.flag"
  )
)

echo [INFO] Stopping old process on port %APP_PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%APP_PORT%') do (
  taskkill /PID %%a /F >nul 2>nul
)

echo [INFO] Starting backend...
start "SAU Backend" /b "%PY%" main.py

echo [INFO] Waiting for service...
timeout /t 5 /nobreak >nul

echo [INFO] Opening browser...
start "" "http://127.0.0.1:%APP_PORT%/"

echo.
echo App URL: http://127.0.0.1:%APP_PORT%/
echo Keep this window open while using the app.
echo.
pause
endlocal
