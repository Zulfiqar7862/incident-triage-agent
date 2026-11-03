#!/usr/bin/env bash
# One-command local demo: venv + deps + server on :8000.
# Works offline (scripted policy) with no .env. If GEMINI_API_KEY is set, uses Gemini.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip -q install -r requirements-dev.txt
echo "Starting http://127.0.0.1:8000  (Ctrl+C to stop)"
echo "No API key → offline scripted policy. Set GEMINI_API_KEY in .env for a live model."
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
