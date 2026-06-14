@echo off
setlocal
title CINEMATIC CONSOLE LD
cd /d "%~dp0"

rem ---------------------------------------------------------------
rem  Cinematic Console - one-command start
rem  1) create venv + install deps on first run
rem  2) build frontend if dist missing and npm is available
rem  3) launch backend on http://127.0.0.1:7860 and open browser
rem ---------------------------------------------------------------

set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [setup] creating Python venv ...
    where python >nul 2>nul && (python -m venv .venv) || (
        where py >nul 2>nul && (py -3 -m venv .venv) || (
            echo [error] Python 3.10+ not found in PATH. Install Python and retry.
            pause & exit /b 1
        )
    )
)

"%PY%" -c "import fastapi, uvicorn, httpx, PIL" >nul 2>nul || (
    echo [setup] installing Python dependencies ...
    "%PY%" -m pip install -r requirements.txt --disable-pip-version-check
    if errorlevel 1 ( echo [error] pip install failed. & pause & exit /b 1 )
)

if not exist "frontend\dist\index.html" (
    where npm >nul 2>nul && (
        echo [setup] building frontend ...
        pushd frontend
        if not exist node_modules call npm install --no-fund --no-audit
        call npm run build
        popd
    ) || (
        echo [warn] frontend\dist missing and npm not found - UI will be unavailable.
    )
)

echo [start] Cinematic Console on http://127.0.0.1:7860
"%PY%" run.py
pause
