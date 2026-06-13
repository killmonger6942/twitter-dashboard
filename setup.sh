#!/usr/bin/env bash
set -euo pipefail

echo "=== Twitter Dashboard Backend Setup ==="
echo ""

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "  macOS: brew install python3"
    echo "  Ubuntu: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

echo "Found $(python3 --version)"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

echo "Installing Python dependencies..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

echo "Installing Playwright Chromium..."
.venv/bin/playwright install chromium

if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file..."

    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    read -p "Dashboard username [admin]: " DASH_USER
    DASH_USER=${DASH_USER:-admin}

    while true; do
        read -s -p "Dashboard password: " DASH_PASS
        echo
        if [ -z "$DASH_PASS" ]; then
            echo "Password cannot be empty."
        else
            break
        fi
    done

    DASH_HASH=$(.venv/bin/python3 -c "import bcrypt; print(bcrypt.hashpw(b'${DASH_PASS}', bcrypt.gensalt()).decode())")

    cat > .env << ENVEOF
# Auth
DASHBOARD_USERNAME=${DASH_USER}
DASHBOARD_PASSWORD=${DASH_HASH}
JWT_SECRET=${JWT_SECRET}

# Required: Get from https://aistudio.google.com/apikey
GEMINI_API_KEY=

# CORS: Add your Vercel URL here
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:4173
ENVEOF

    echo ""
    echo "IMPORTANT: Edit .env and add your GEMINI_API_KEY"
else
    echo ".env file already exists, skipping."
fi

mkdir -p data/browsers data/screenshots

echo "Initializing database..."
.venv/bin/python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')
from backend.models.database import init_db
asyncio.run(init_db())
"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your GEMINI_API_KEY"
echo "  2. Add your Vercel URL to ALLOWED_ORIGINS in .env"
echo "  3. Run ./start.sh to start the backend"
