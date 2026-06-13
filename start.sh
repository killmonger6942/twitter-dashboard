#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "ERROR: Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found. Run ./setup.sh first."
    exit 1
fi

if ! grep -q "GEMINI_API_KEY=." .env 2>/dev/null; then
    echo "WARNING: GEMINI_API_KEY appears to be empty in .env"
    echo "  AI features will not work until you add it."
    echo ""
fi

echo "Starting Twitter Dashboard backend on http://0.0.0.0:8000"
echo "Press Ctrl+C to stop"
echo ""

exec .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
