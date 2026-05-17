#!/usr/bin/env bash
# setup.sh — create a virtual environment and install dependencies
#
# Usage:
#   ./setup.sh              # core only (run_eval, smoke_test, gpu_sidecar)
#   ./setup.sh --benchmarks # + datasets (benchmark.py ARC + HumanEval)
#   ./setup.sh --harness    # + lm-eval  (run_benchmarks.py — heavy ~500MB)
#   ./setup.sh --all        # everything
#
# The venv is created at .venv/ in this directory.
# Activate it manually with: source .venv/bin/activate

set -e

VENV=".venv"
TIER="core"

for arg in "$@"; do
  case $arg in
    --benchmarks) TIER="benchmarks" ;;
    --harness)    TIER="harness" ;;
    --all)        TIER="all" ;;
  esac
done

# ── Python version check ──────────────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
  echo "ERROR: python3 not found. Install Python 3.10+ and retry."
  exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "ERROR: Python 3.10+ required (found $PY_VERSION)."
  exit 1
fi
echo "[ok] Python $PY_VERSION"

# ── Create venv ───────────────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "[..] Creating virtual environment at $VENV/"
  $PYTHON -m venv "$VENV"
  echo "[ok] venv created"
else
  echo "[ok] venv already exists at $VENV/"
fi

PIP="$VENV/bin/pip"

# ── Install dependencies ──────────────────────────────────────────────────────
echo "[..] Installing: $TIER"
"$PIP" install --upgrade pip --quiet

case $TIER in
  core)
    "$PIP" install -r requirements.txt
    ;;
  benchmarks)
    "$PIP" install -r requirements-benchmarks.txt
    ;;
  harness)
    "$PIP" install -r requirements-harness.txt
    ;;
  all)
    "$PIP" install -r requirements-benchmarks.txt
    "$PIP" install -r requirements-harness.txt
    ;;
esac

echo ""
echo "Setup complete. Activate the environment with:"
echo "  source $VENV/bin/activate"
echo ""
echo "Then run an evaluation:"
echo "  ./eval.sh --model <model>"
