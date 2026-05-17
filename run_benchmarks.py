#!/usr/bin/env python3
"""
Benchmark runner for local Ollama models.
Uses lm-evaluation-harness via the local OpenAI-compatible API.

Tasks:
  arc_challenge      - ARC Challenge (reasoning/knowledge, ~1172 q)
  ifeval             - IFEval strict instruction following (541 prompts)
  humaneval          - HumanEval code generation (164 problems)

Usage:
  python3 run_benchmarks.py <model> <task> [--limit N]

Examples:
  python3 run_benchmarks.py gemma4-31b-research arc_challenge --limit 50
  python3 run_benchmarks.py qwen36-35b-research ifeval
  python3 run_benchmarks.py devstral-coding humaneval --limit 50

Results are saved to: benchmark_results/<model>/<task>_<timestamp>.json
Reference scores from gguf-bench.com and model cards are at bottom of this file.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OLLAMA_BASE = "http://localhost:11434/v1"
RESULTS_DIR = Path(__file__).parent / "benchmark_results"

# ── Reference scores (from gguf-bench.com + model cards) ─────────────────────
REFERENCE = {
    "gemma4-26b-a4b-iq3xxs": {
        "arc_challenge": 91.6,
        "ifeval_strict": 92.5,
        "source": "gguf-bench.com",
    },
    "gemma4-31b-q4km": {
        "arc_challenge": None,   # not in gguf-bench yet
        "ifeval_strict": None,
        "source": "gguf-bench.com",
    },
    "qwen3.6-35b-a3b-bf16": {
        "swebench_verified": 73.4,
        "source": "Qwen3.6 model card",
    },
    "devstral-24b": {
        "swebench_verified": 46.8,
        "source": "Ollama/Mistral model card",
    },
}

TASK_CONFIGS = {
    "arc_challenge": {
        "task": "arc_challenge",
        "metric": "acc_norm",
        "num_fewshot": 25,
        "description": "ARC Challenge — knowledge/reasoning (25-shot)",
    },
    "ifeval": {
        "task": "ifeval",
        "metric": "prompt_level_strict_acc",
        "num_fewshot": 0,
        "description": "IFEval — strict instruction following (0-shot)",
        "extra_args": ["--apply_chat_template"],
    },
    "humaneval": {
        "task": "humaneval",
        "metric": "pass@1",
        "num_fewshot": 0,
        "description": "HumanEval — code generation pass@1",
        "extra_args": ["--confirm_run_unsafe_code"],
    },
}


def run_benchmark(model: str, task_name: str, limit: int | None = None):
    if task_name not in TASK_CONFIGS:
        print(f"Unknown task: {task_name}. Choose from: {list(TASK_CONFIGS)}")
        sys.exit(1)

    cfg = TASK_CONFIGS[task_name]
    out_dir = RESULTS_DIR / model.replace(":", "_").replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = out_dir / f"{task_name}_{timestamp}"

    print(f"\n{'='*60}")
    print(f"Model:  {model}")
    print(f"Task:   {cfg['description']}")
    print(f"Limit:  {limit if limit else 'full'}")
    print(f"Output: {out_file}.json")
    print(f"{'='*60}\n")

    cmd = [
        "python3", "-m", "lm_eval",
        "--model", "local-completions",
        "--model_args", f"model={model},base_url={OLLAMA_BASE}/completions,num_concurrent=1,max_retries=3,tokenized_requests=False",
        "--tasks", cfg["task"],
        "--num_fewshot", str(cfg["num_fewshot"]),
        "--output_path", str(out_file),
        "--log_samples",
    ]

    if limit:
        cmd += ["--limit", str(limit)]

    extra = cfg.get("extra_args", [])
    cmd += extra

    print("Command:", " ".join(cmd))
    print()

    result = subprocess.run(cmd, capture_output=False)

    # Parse and display result
    result_files = list(out_dir.glob(f"{task_name}_{timestamp}*.json"))
    if result_files:
        with open(result_files[0]) as f:
            data = json.load(f)
        results = data.get("results", {})
        print(f"\n{'='*60}")
        print(f"RESULTS: {model} / {task_name}")
        print(f"{'='*60}")
        for task_key, metrics in results.items():
            target = cfg["metric"]
            score = metrics.get(target) or metrics.get(target + ",none")
            if score is not None:
                print(f"  {target}: {score*100:.1f}%")
        print()
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run benchmarks on local Ollama models")
    parser.add_argument("model", help="Ollama model name, e.g. gemma4-31b-research")
    parser.add_argument("task", choices=list(TASK_CONFIGS), help="Benchmark task")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of examples (for quick checks)")
    args = parser.parse_args()

    sys.exit(run_benchmark(args.model, args.task, args.limit))


if __name__ == "__main__":
    main()

# ── Reference Scores Summary ──────────────────────────────────────────────────
#
# ARC Challenge (25-shot, acc_norm):
#   Gemma4-26B-A4B IQ3_XXS : 91.6%  (gguf-bench.com)
#   Gemma4-31B Q4_K_M       : ~92%   (estimated from dense scaling)
#   Qwen3.5-35B-A3B Q4_K_M  : ~90%   (gguf-bench.com, Qwen3.5)
#
# IFEval (0-shot, prompt_level_strict_acc):
#   Gemma4-26B-A4B IQ3_XXS : 92.5%  (gguf-bench.com)
#
# SWE-Bench Verified:
#   Qwen3.6-35B-A3B         : 73.4%  (model card)
#   Devstral-24B            : 46.8%  (Ollama/Mistral model card)
#   Gemma4-31B              : 52.0%  (Qwen3.6 model card comparison)
