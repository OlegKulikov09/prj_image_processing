#!/usr/bin/env bash
# Start the retrieval backend + GUI on http://127.0.0.1:8000
set -e
cd "$(dirname "$0")"
exec ./.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
