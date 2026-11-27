#!/usr/bin/env bash
# Kampung Grid: one command to set up (first time) and run everything.
# Mac / Linux:   ./start.sh
# Stop it with Ctrl+C (stops both the backend and the frontend).

set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31mERROR: %s\033[0m\n" "$1"; exit 1; }

# ---- Check the tools are installed -----------------------------------------
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || fail "Python 3.11 or newer is needed. Install it from python.org."
command -v npm >/dev/null 2>&1 || fail "Node.js is needed. Install the LTS version from nodejs.org."

# ---- Backend setup (only does work the first time) ---------------------------
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  say "First run: creating the Python environment (about a minute)"
  "$PY" -m venv .venv
  ./.venv/bin/pip install --upgrade pip -q
fi
# Install any packages that are new since last time (quick when nothing changed).
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  say "Installing Python packages"
  ./.venv/bin/pip install -r requirements.txt -q
  touch .venv/.installed
fi
if [ ! -f .env ]; then
  cp .env.example .env
  say "Created backend/.env. Paste your ANTHROPIC_API_KEY into it to use Claude (the app works without it, using backup rules)."
fi
if [ ! -f kampung.db ]; then
  say "Loading the fictional Block 123 and Block 125"
  ./.venv/bin/python -m seed.seed
fi

# ---- Frontend setup (only the first time) -----------------------------------
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  say "First run: installing frontend packages (a minute or two)"
  npm install --silent
fi

# ---- Stop any old copy that's still running -----------------------------------
# (e.g. from another terminal), so there's never two backends fighting over a port.
if command -v lsof >/dev/null 2>&1; then
  # lsof "fails" when nothing is found, which is the normal case, so "|| true".
  OLD_PIDS="$( { lsof -ti tcp:8000 -sTCP:LISTEN; lsof -ti tcp:5173 -sTCP:LISTEN; } 2>/dev/null || true)"
  if [ -n "$OLD_PIDS" ]; then
    say "Stopping an old copy of the app that was still running"
    echo "$OLD_PIDS" | xargs kill 2>/dev/null || true
    sleep 1
  fi
fi

# ---- Run both ----------------------------------------------------------------
cd "$ROOT/backend"
say "Starting the backend on port 8000"
./.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
trap 'echo; echo "Stopping..."; kill $BACKEND_PID 2>/dev/null; exit 0' INT TERM EXIT

# Wait until the backend answers (up to 20 seconds).
for _ in $(seq 1 40); do
  if curl -s http://localhost:8000/health >/dev/null 2>&1; then break; fi
  sleep 0.5
done

cd "$ROOT/frontend"
say "Starting the frontend. Your browser will open http://localhost:5173"
echo "    Dashboard:      http://localhost:5173/dashboard"
echo "    Control panel:  http://localhost:5173/control"
echo "    Phone app:      http://localhost:5173/phone   (on a phone: use the Network address below)"
echo "    Press Ctrl+C to stop everything."
npm run dev -- --open / --strictPort
