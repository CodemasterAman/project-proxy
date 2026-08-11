#!/usr/bin/env bash
# ============================================================
#  susgrade backend launcher (macOS / Linux)
#  Run:  bash run.sh   (from the backend/ folder)
# ============================================================
cd "$(dirname "$0")" || exit 1

echo "Installing dependencies (first run only)..."
python3 -m pip install -r requirements.txt || {
  echo "Could not install dependencies. Is Python 3 installed?"
  exit 1
}

echo ""
echo "============================================================"
echo "  susgrade backend is starting on http://127.0.0.1:8000"
echo "  Keep this terminal OPEN while you use mutation testing."
echo "  Test it: open http://127.0.0.1:8000/health"
echo "  Stop it: press Ctrl+C"
echo "============================================================"
echo ""

python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
