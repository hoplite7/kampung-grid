@echo off
REM Kampung Grid: one command to set up (first time) and run everything.
REM Windows: double-click start.bat, or run it from a terminal.
REM The backend opens in its own window. Close both windows (or press Ctrl+C) to stop.

setlocal
cd /d "%~dp0"
set "ROOT=%cd%"

REM ---- Check the tools are installed -----------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo ERROR: Python 3.11 or newer is needed. Install it from python.org and tick "Add Python to PATH".
  pause & exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo ERROR: Python 3.11 or newer is needed. Your Python is too old.
  pause & exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js is needed. Install the LTS version from nodejs.org.
  pause & exit /b 1
)

REM ---- Backend setup (only does work the first time) ---------------------------
cd /d "%ROOT%\backend"
if not exist .venv (
  echo.
  echo ==^> First run: creating the Python environment ^(about a minute^)
  %PY% -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip -q
)
REM Install any packages that are new since last time (quick when nothing changed).
echo.
echo ==^> Checking Python packages
.venv\Scripts\pip install -r requirements.txt -q
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo ==^> Created backend\.env. Paste your ANTHROPIC_API_KEY into it to use Claude.
  echo     The app works without it, using backup rules.
)
if not exist kampung.db (
  echo.
  echo ==^> Loading the fictional Block 123 and Block 125
  .venv\Scripts\python -m seed.seed
)

REM ---- Frontend setup (only the first time) -----------------------------------
cd /d "%ROOT%\frontend"
if not exist node_modules (
  echo.
  echo ==^> First run: installing frontend packages ^(a minute or two^)
  call npm install --silent
)

REM ---- Stop any old copy that's still running -----------------------------------
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>nul
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":5173 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>nul

REM ---- Run both ----------------------------------------------------------------
echo.
echo ==^> Starting the backend in a new window ^(port 8000^)
start "Kampung Grid backend" cmd /k "cd /d "%ROOT%\backend" && .venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

REM Give the backend a few seconds to start.
timeout /t 4 /nobreak >nul

echo.
echo ==^> Starting the frontend. Your browser will open http://localhost:5173
echo     Dashboard:      http://localhost:5173/dashboard
echo     Control panel:  http://localhost:5173/control
echo     Phone app:      http://localhost:5173/phone   ^(on a phone: use the Network address below^)
echo     To stop: close this window and the backend window.
echo.
call npm run dev -- --open / --strictPort
