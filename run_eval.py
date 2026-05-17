#!/usr/bin/env python3
"""
Unified evaluation entry point.

Decision gate:
  --new-model    Run model smoke tests first (Phase 0). Hard stop if the model fails
                 basic capability checks — no point running agentic tests on a broken model.
                 Omit this flag when re-testing toolchain/config changes against a
                 known-good model: Phase 0 is skipped and you go straight to agentic tiers.

  --benchmark    Also run academic benchmarks after the smoke test (ARC-Challenge by default).
                 Time-consuming — use --limit for a quick sanity check.

Usage:
  python3 run_eval.py --model <model> [options]

Options:
  --model        Ollama model name (required)
  --new-model    Gate: run smoke + optional benchmark before agentic tests
  --benchmark    Run ARC-Challenge benchmark (implies --new-model gate)
  --limit N      Cap benchmark questions, e.g. 50 for a quick check (default: full run)
  --gpu-server   URL of gpu_sidecar.py, e.g. http://192.168.1.10:8765/gpu
  --run-id       Optional label for this run (default: timestamp).

Run directory layout:
  runs/<model-slug>_<run_id>/
    testing-plan.md       copy of master template with run_id + model substituted
    test-results.jsonl    append-only result log for this run
    test-output/          scratch directory for test artifacts

The master template (testing-plan.md at repo root) is never modified.
"""

import argparse
import json
import os
import re
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE      = Path(__file__).parent
RUNS_DIR  = HERE / "runs"
TEMPLATE  = HERE / "testing-plan.md"


# ── Run directory ─────────────────────────────────────────────────────────────

def make_run_dir(model: str, run_id: str) -> tuple[Path, Path, Path]:
    """Create runs/<model-slug>_<run_id>/ and return (run_dir, results_file, test_output)."""
    slug = re.sub(r'[:/\\\s]+', '_', model)   # filesystem-safe name
    run_dir = RUNS_DIR / f"{slug}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results_file = run_dir / "test-results.jsonl"
    test_output  = run_dir / "test-output"
    test_output.mkdir(exist_ok=True)
    if not results_file.exists():
        results_file.touch()

    # Copy and substitute the master template
    if TEMPLATE.exists():
        created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        text = TEMPLATE.read_text()
        text = text.replace("{{RUN_ID}}",   run_id)
        text = text.replace("{{MODEL}}",    model)
        text = text.replace("{{CREATED}}",  created)
        text = text.replace("{{LOG_PATH}}", str(results_file))
        dest = run_dir / "testing-plan.md"
        dest.write_text(text)
        print(f"[setup] plan  → {dest}")
    else:
        print(f"[setup] warning: master template not found at {TEMPLATE} — skipping copy")

    return run_dir, results_file, test_output


# ── Scaffolding ───────────────────────────────────────────────────────────────

def setup_scaffolding(run_id: str, model: str) -> tuple[Path, Path]:
    """Create the run directory and return (results_file, test_output)."""
    run_dir, results_file, test_output = make_run_dir(model, run_id)
    print(f"[setup] run dir → {run_dir}")
    print(f"[setup] log     → {results_file}")
    print(f"[setup] run_id  : {run_id}")
    print()
    return results_file, test_output


# ── Result writer ─────────────────────────────────────────────────────────────

def write_result(results_file: Path, run_id: str, phase: str, test_id: str,
                 status: str, model: str, notes: str = "", extra: dict | None = None):
    row = {
        "run_id":    run_id,
        "phase":     phase,       # "model" or "agentic"
        "id":        test_id,     # "P0.1", "P0.2", "T1.1", …
        "model":     model,
        "status":    status,      # "PASS" | "WARN" | "FAIL" | "SKIP"
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "notes":     notes,
    }
    if extra:
        row.update(extra)
    with open(results_file, "a") as f:
        f.write(json.dumps(row) + "\n")


# ── Phase 0: smoke test ───────────────────────────────────────────────────────

def run_smoke(model: str, run_id: str, results_file: Path) -> bool:
    """Run smoke_test.py and parse results. Returns True if model passes gate."""
    print("=" * 60)
    print("Phase 0.1 — Smoke test")
    print("=" * 60)

    result = subprocess.run(
        [sys.executable, str(HERE / "smoke_test.py"), model],
        capture_output=False,
    )

    if result.returncode != 0:
        write_result(results_file, run_id, "model", "P0.1", "FAIL", model,
                     notes="smoke_test.py exited non-zero")
        return False

    import glob
    pattern = str(HERE / "smoke_test_results_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        write_result(results_file, run_id, "model", "P0.1", "WARN", model,
                     notes="smoke_test.py produced no result file — check path")
        return True  # Don't hard-block on a missing file

    latest = json.loads(Path(files[-1]).read_text())
    model_results = latest.get("results", {}).get(model, {})

    any_fail = False
    for test_name, r in model_results.items():
        status = "PASS" if r.get("pass") is True else (
                 "WARN" if r.get("pass") is None else "FAIL")
        if status == "FAIL":
            any_fail = True
        write_result(results_file, run_id, "model", f"P0.1/{test_name}", status, model,
                     notes=r.get("note", ""))

    if any_fail:
        print(f"\n[gate] FAIL — {model} failed one or more smoke tests.")
        print("[gate] Agentic tests require a functional model. Stopping.")
        return False

    print(f"\n[gate] PASS — {model} passed smoke tests. Proceeding.")
    return True


# ── Phase 0: benchmark (optional) ────────────────────────────────────────────

def run_benchmark(model: str, run_id: str, results_file: Path,
                  limit: int | None, gpu_server: str | None):
    """Run ARC-Challenge benchmark. Writes a single summary result row."""
    print()
    print("=" * 60)
    print("Phase 0.2 — ARC-Challenge benchmark")
    print("=" * 60)

    cmd = [sys.executable, str(HERE / "benchmark.py"), model, "arc"]
    if limit:
        cmd += ["--limit", str(limit)]
    if gpu_server:
        cmd += ["--gpu-server", gpu_server]

    result = subprocess.run(cmd, capture_output=False)

    status = "PASS" if result.returncode == 0 else "FAIL"
    write_result(results_file, run_id, "model", "P0.2/arc", status, model,
                 notes="see benchmark_results/ for full detail")


# ── Phase 1-5: agentic handoff ────────────────────────────────────────────────

def print_agentic_handoff(model: str, run_id: str, results_file: Path, plan_path: Path):
    """Print clear instructions for continuing into the Pi agentic test plan."""
    print()
    print("=" * 60)
    print("Ready for agentic tests (Phase 1–5)")
    print("=" * 60)
    print()
    print("  Open this file in Pi and begin at Tier 1:")
    print(f"    {plan_path}")
    print()
    print(f"  Results log : {results_file}")
    print(f"  run_id      : {run_id}")
    print(f"  model       : {model}")
    print()
    print("  The run_id and model are already substituted into the plan file.")
    print("  Tier gate: do not proceed to the next tier if any test has status FAIL.")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Unified eval entry point — model gate + agentic test handoff"
    )
    parser.add_argument("--model",      required=True, help="Ollama model name")
    parser.add_argument("--new-model",  action="store_true",
                        help="Run smoke test gate before agentic tests")
    parser.add_argument("--benchmark",  action="store_true",
                        help="Run ARC-Challenge benchmark (after smoke, before agentic)")
    parser.add_argument("--limit",      type=int, default=None,
                        help="Cap benchmark questions (e.g. 50 for a quick check)")
    parser.add_argument("--gpu-server", default=None, metavar="URL",
                        help="gpu_sidecar.py URL, e.g. http://192.168.1.10:8765/gpu")
    parser.add_argument("--run-id",     default=None,
                        help="Label for this run (default: auto timestamp)")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Create run directory, copy + substitute template, init scaffolding
    results_file, _ = setup_scaffolding(run_id, args.model)
    slug = re.sub(r'[:/\\\s]+', '_', args.model)
    plan_path = RUNS_DIR / f"{slug}_{run_id}" / "testing-plan.md"

    # 2. Phase 0 gate — only when testing a new model
    if args.new_model or args.benchmark:
        passed = run_smoke(args.model, run_id, results_file)
        if not passed:
            sys.exit(1)

        if args.benchmark:
            run_benchmark(args.model, run_id, results_file, args.limit, args.gpu_server)
    else:
        print("[gate] --new-model not set — skipping model tests.")
        print("[gate] Assuming model is known-good; proceeding to agentic tests.\n")
        write_result(results_file, run_id, "model", "P0.x", "SKIP", args.model,
                     notes="--new-model not set; model tests skipped by design")

    # 3. Agentic handoff — always
    print_agentic_handoff(args.model, run_id, results_file, plan_path)


if __name__ == "__main__":
    main()
