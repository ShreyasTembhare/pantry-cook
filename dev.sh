#!/usr/bin/env bash
# Start Pantry Cook: API on :8787, app on :3939. Postgres must already be running.
#
#   Git Bash (Windows):  ./dev.sh
#   PowerShell:          .\dev.ps1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_PID=""
FRONTEND_PID=""

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'dev.sh: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing '$1'. Install it and try again."
}

cleanup() {
  if [[ -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$FRONTEND_PID" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

ensure_env() {
  if [[ -f "$ROOT/.env" ]]; then
    return 0
  fi
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    log "Created .env from .env.example — set OPENAI_API_KEY for the hosted chef."
    return 0
  fi
  die "No .env file. Copy .env.example to .env first."
}

db_ready() {
  (cd "$ROOT/backend" && uv run python -c "
from sqlalchemy import create_engine, text
from app.config import settings
engine = create_engine(settings.database_url)
with engine.connect() as conn:
    conn.execute(text('select 1'))
") >/dev/null 2>&1
}

wait_for_postgres() {
  if db_ready; then
    log "Database is reachable."
    return 0
  fi
  log "Waiting for Postgres (PANTRY_DATABASE_URL in .env)…"
  local attempt
  for attempt in $(seq 1 60); do
    if db_ready; then
      log "Postgres is ready."
      return 0
    fi
    sleep 1
  done
  die "Could not connect to Postgres. Start PostgreSQL and check PANTRY_DATABASE_URL in .env (see README)."
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempt
  for attempt in $(seq 1 90); do
    if (cd "$ROOT/backend" && uv run python -c "
import urllib.request
try:
    urllib.request.urlopen('${url}', timeout=2)
except Exception:
    raise SystemExit(1)
" >/dev/null 2>&1); then
      log "$label is up."
      return 0
    fi
    sleep 1
  done
  die "Timed out waiting for $label ($url)."
}

need_cmd uv
need_cmd pnpm
ensure_env

if [[ ! -d "$ROOT/backend/.venv" ]]; then
  log "Installing backend dependencies…"
  (cd "$ROOT/backend" && uv sync --all-extras)
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  log "Installing frontend dependencies…"
  (cd "$ROOT/frontend" && pnpm install)
fi

wait_for_postgres

log "Applying migrations…"
(cd "$ROOT/backend" && uv run alembic upgrade head)

log "Starting API on http://127.0.0.1:8787 …"
(cd "$ROOT/backend" && uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload) &
BACKEND_PID=$!

log "Starting app on http://localhost:3939 …"
(cd "$ROOT/frontend" && pnpm dev) &
FRONTEND_PID=$!

wait_for_url "http://127.0.0.1:8787/api/health" "API"
wait_for_url "http://127.0.0.1:3939/" "App"

log ""
log "Pantry Cook is running."
log "  App:  http://localhost:3939"
log "  API:  http://localhost:8787"
log "  Docs: http://localhost:8787/docs"
log ""
log "Press Ctrl+C to stop the API and the frontend."

wait "$BACKEND_PID" "$FRONTEND_PID"
