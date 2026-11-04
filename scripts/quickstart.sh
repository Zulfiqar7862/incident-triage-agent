#!/usr/bin/env bash
# One-command local boot: Python deps + frontend build + server on :8000.
# Works offline (deterministic scripted provider) with no .env.
# If GEMINI_API_KEY is set, uses Gemini.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip -q install -r requirements-dev.txt

if command -v npm >/dev/null 2>&1; then
  if [[ ! -d frontend/node_modules ]]; then
    (cd frontend && npm ci)
  fi
  (cd frontend && npm run build)
else
  echo "warning: npm not found; expecting frontend/dist to already exist" >&2
  if [[ ! -f frontend/dist/index.html ]]; then
    echo "error: frontend/dist missing and npm unavailable" >&2
    exit 1
  fi
fi

echo "Starting http://127.0.0.1:8000  (Ctrl+C to stop)"
echo "No API key → offline deterministic provider. Set GEMINI_API_KEY in .env for a live model."
echo "Dev hot-reload UI: make frontend-dev (proxies /api to :8000) in another terminal."
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
