#!/usr/bin/env bash
# Syncr — One-command setup for backend + frontend
set -e

echo "=== Syncr Setup ==="

# ── Backend ──
echo ""
echo "→ Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "  Creating Python virtual environment..."
    python3 -m venv venv
else
    echo "  venv already exists, skipping creation."
fi

echo "  Activating venv and installing dependencies..."
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check for .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  Created .env from .env.example — fill in your API keys!"
    else
        echo "  WARNING: No .env or .env.example found."
    fi
else
    echo "  .env already exists."
fi

# Check Modal auth
if command -v modal &> /dev/null; then
    echo "  Modal CLI found."
else
    echo "  WARNING: Modal CLI not found. Run 'modal setup' after install."
fi

# Check ffmpeg
if command -v ffmpeg &> /dev/null; then
    echo "  ffmpeg found."
else
    echo "  WARNING: ffmpeg not found. Install it: brew install ffmpeg"
fi

cd ..

# ── Frontend ──
echo ""
echo "→ Setting up frontend..."
cd frontend

if command -v npm &> /dev/null; then
    npm install --silent
    echo "  npm dependencies installed."
else
    echo "  WARNING: npm not found. Install Node.js first."
fi

cd ..

echo ""
echo "=== Setup complete ==="
echo ""
echo "To run:"
echo "  Backend:  cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000"
echo "  Frontend: cd frontend && npm run dev"
echo ""
echo "Don't forget to:"
echo "  1. Fill in backend/.env with your API keys"
echo "  2. Run 'modal setup' and 'modal token new' if not already done"
echo "  3. Create Modal secrets: modal secret create mimic-secrets HF_TOKEN=... OPENAI_API_KEY=... ELEVENLABS_API_KEY=..."
