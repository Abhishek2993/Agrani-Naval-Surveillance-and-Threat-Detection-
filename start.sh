#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  start.sh — AGRANI Naval Surveillance & Threat Detection System
#  One-command launcher: trains ML model (if needed), starts Flask, opens browser
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║   AGRANI — Naval Surveillance & Threat Detection     ║"
echo "  ║   Indian Navy Coastal Zone Monitoring Network        ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Python check ────────────────────────────────────────────────────────────
PYTHON=python3
if ! command -v python3 &>/dev/null; then
  echo "❌  python3 not found. Please install Python 3.9+."
  exit 1
fi
echo "✓  Python: $($PYTHON --version)"

# ── 2. Virtual environment ────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "→  Creating virtual environment..."
  $PYTHON -m venv .venv
fi
source .venv/bin/activate
echo "✓  Virtual env: .venv activated"

# ── 3. Install dependencies ───────────────────────────────────────────────────
echo "→  Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt
echo "✓  Dependencies installed"

# ── 4. Train ML model (if not already present) ────────────────────────────────
if [ ! -f "ml/model.pkl" ]; then
  echo ""
  echo "→  ML model not found — generating training data and training..."
  cd ml
  $PYTHON generate_training_data.py
  $PYTHON train_model.py
  cd ..
  echo "✓  ML model trained and saved to ml/model.pkl"
else
  echo "✓  ML model already trained (ml/model.pkl)"
fi

# ── 5. Start the Flask backend in the background ──────────────────────────────
echo ""
echo "→  Starting Agrani backend in SIMULATION mode..."
FLASK_ENV=development $PYTHON -m backend.app --simulate --port 5001 &
BACKEND_PID=$!
echo "✓  Backend started (PID $BACKEND_PID)"

# Wait for Flask to be ready
echo "→  Waiting for server to be ready..."
for i in {1..20}; do
  if curl -s http://localhost:5001/api/nodes > /dev/null 2>&1; then
    echo "✓  Server is live at http://localhost:5001"
    break
  fi
  sleep 1
done

# ── 6. Open browser ───────────────────────────────────────────────────────────
echo "→  Opening dashboard in browser..."
if command -v open &>/dev/null; then         # macOS
  open "http://localhost:5001"
elif command -v xdg-open &>/dev/null; then   # Linux
  xdg-open "http://localhost:5001"
elif command -v start &>/dev/null; then      # Windows (WSL)
  start "http://localhost:5001"
fi

echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │  Dashboard → http://localhost:5001                  │"
echo "  │  API Nodes  → http://localhost:5001/api/nodes       │"
echo "  │  Press Ctrl+C to shut down                          │"
echo "  └─────────────────────────────────────────────────────┘"
echo ""

# ── 7. Keep running until Ctrl+C ──────────────────────────────────────────────
trap "echo ''; echo 'Shutting down...'; kill $BACKEND_PID 2>/dev/null; deactivate 2>/dev/null; exit 0" SIGINT SIGTERM
wait $BACKEND_PID
