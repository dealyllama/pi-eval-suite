#!/usr/bin/env bash
# eval.sh — pre-flight checks then launch run_eval.py
#
# Usage mirrors run_eval.py exactly:
#   ./eval.sh --model <model>
#   ./eval.sh --model <model> --new-model
#   ./eval.sh --model <model> --new-model --benchmark --limit 50
#   ./eval.sh --model <model> --gpu-server http://192.168.1.10:8765/gpu
#
# Additional behaviour vs calling run_eval.py directly:
#   - Activates .venv/ if present
#   - Warns if OLLAMA_BASE_URL is not set
#   - Pings Ollama before starting (fast fail)
#   - Checks Python 3.10+

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Activate venv if present ──────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
  echo "[ok] venv activated"
fi

# ── Python version check ──────────────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
  echo "ERROR: python3 not found."
  exit 1
fi

PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  echo "ERROR: Python 3.10+ required (found $PY_VERSION)."
  exit 1
fi

# ── OLLAMA_BASE_URL check ─────────────────────────────────────────────────────
OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
if [ -z "$OLLAMA_BASE_URL" ]; then
  echo "[warn] OLLAMA_BASE_URL not set — using default: $OLLAMA_URL"
  echo "       Set it in your shell profile to avoid this warning:"
  echo "         export OLLAMA_BASE_URL=http://<host>:11434"
  echo ""
fi

# ── Ollama connectivity check ─────────────────────────────────────────────────
OLLAMA_PING_URL="${OLLAMA_URL%/v1}"   # strip /v1 suffix if present
echo "[..] Checking Ollama at $OLLAMA_PING_URL ..."

if $PYTHON -c "
import urllib.request, sys, os
url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/v1').rstrip('/')
try:
    urllib.request.urlopen(url + '/api/tags', timeout=5)
    print('[ok] Ollama reachable')
except Exception as e:
    print(f'[ERROR] Cannot reach Ollama at {url}: {e}')
    sys.exit(1)
" ; then
  : # success, message already printed
else
  echo ""
  echo "Fix: make sure Ollama is running and OLLAMA_BASE_URL points to the right host."
  exit 1
fi

# ── requests availability check ───────────────────────────────────────────────
if ! $PYTHON -c "import requests" 2>/dev/null; then
  echo ""
  echo "ERROR: 'requests' package not installed."
  echo "Run setup first: ./setup.sh"
  exit 1
fi

echo ""

# ── Hand off to run_eval.py ───────────────────────────────────────────────────
exec "$PYTHON" "$SCRIPT_DIR/run_eval.py" "$@"
