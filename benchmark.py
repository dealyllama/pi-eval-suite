#!/usr/bin/env python3
"""
Lightweight benchmark harness — calls Ollama API directly, no tokenizer needed.

Supported tasks:
  arc      — ARC-Challenge test set (1172 questions, 0-shot chat)
  ifeval   — IFEval (541 prompts, strict instruction following)
  humaneval — HumanEval pass@1 (164 problems, code generation)

Usage:
  python3 benchmark.py <model> arc [--limit N] [--concurrency N]
  python3 benchmark.py <model> ifeval [--limit N]
  python3 benchmark.py <model> humaneval [--limit N]

Examples:
  python3 benchmark.py gemma4-31b-research arc --limit 100
  python3 benchmark.py qwen36-35b-research arc
  python3 benchmark.py devstral-coding humaneval --limit 50
"""

import argparse
import json
import re
import subprocess
import threading
import time
import concurrent.futures
from datetime import datetime
from pathlib import Path

import requests

import os
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/v1").rstrip("/")
RESULTS_DIR = Path(__file__).parent / "benchmark_results"


# ── GPU utilization sampler ───────────────────────────────────────────────────

class GPUSampler:
    """Polls GPU metrics every 2s in a background thread.

    Two modes:
      - Local:  calls nvidia-smi directly (original behaviour, requires local GPU)
      - Remote: polls gpu_sidecar.py HTTP endpoint (portable, works from any host)

    Remote usage:
        GPUSampler(remote_url="http://192.168.1.x:8765/gpu").start()

    If remote_url is set but unreachable, falls back to logging empty samples
    (stats will return None values) rather than crashing.
    """

    def __init__(self, interval=2.0, remote_url=None):
        self.interval = interval
        self.remote_url = remote_url  # e.g. "http://ollama-host:8765/gpu"
        self.samples = []
        self.available = False  # set to True only after a successful probe
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        """Probe availability once before starting the sample loop.
        Warns and disables sampling if the source is unreachable — never raises.
        """
        if self.remote_url:
            ok = self._sample_remote()
            if ok:
                self.available = True
                print(f"  [gpu] remote sidecar OK: {self.remote_url}")
            else:
                print(f"  [gpu] warning: remote sidecar unreachable ({self.remote_url}) — "
                      "GPU metrics will be skipped")
                self.samples.clear()  # discard the failed probe attempt
        else:
            ok = self._sample_local()
            if ok:
                self.available = True
                self.samples.clear()  # discard probe sample; real run starts fresh
            else:
                print("  [gpu] warning: nvidia-smi not available — "
                      "GPU metrics will be skipped")
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join()
        return self

    def _sample_remote(self):
        """Poll gpu_sidecar.py endpoint. Returns True on success."""
        try:
            r = requests.get(self.remote_url, timeout=5)
            data = r.json()
            if "error" in data or not data.get("gpus"):
                return False
            # Aggregate across all GPUs (handles multi-GPU hosts)
            gpu_util = round(sum(g["gpu_util_pct"] for g in data["gpus"]) / len(data["gpus"]), 1)
            mem_util = round(sum(g["mem_util_pct"] for g in data["gpus"]) / len(data["gpus"]), 1)
            mem_used = sum(g["mem_used_mb"] for g in data["gpus"])
            self.samples.append({"gpu": gpu_util, "mem": mem_util, "mem_used_mb": mem_used})
            return True
        except Exception:
            return False

    def _sample_local(self):
        """Call nvidia-smi directly. Returns True on success."""
        try:
            out = subprocess.check_output([
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.memory,memory.used",
                "--format=csv,noheader,nounits"
            ], timeout=5).decode().strip()
            # Sum across multiple GPUs if present
            gpu_util_vals, mem_util_vals, mem_used_vals = [], [], []
            for line in out.splitlines():
                gpu_util, mem_util, mem_used = [int(x.strip()) for x in line.split(",")]
                gpu_util_vals.append(gpu_util)
                mem_util_vals.append(mem_util)
                mem_used_vals.append(mem_used)
            self.samples.append({
                "gpu": round(sum(gpu_util_vals) / len(gpu_util_vals), 1),
                "mem": round(sum(mem_util_vals) / len(mem_util_vals), 1),
                "mem_used_mb": sum(mem_used_vals),
            })
            return True
        except Exception:
            return False

    def _run(self):
        if not self.available:
            return  # probe failed at start() — nothing to do
        while not self._stop.wait(self.interval):
            if self.remote_url:
                self._sample_remote()
            else:
                self._sample_local()

    @property
    def stats(self):
        if not self.samples:
            return {"gpu_util_avg": None, "gpu_util_peak": None,
                    "mem_util_avg": None, "mem_used_peak_mb": None,
                    "samples": 0, "source": "remote" if self.remote_url else "local",
                    "available": self.available}
        gpus = [s["gpu"] for s in self.samples]
        mems = [s["mem"] for s in self.samples]
        mem_used = [s["mem_used_mb"] for s in self.samples]
        return {
            "gpu_util_avg": round(sum(gpus) / len(gpus), 1),
            "gpu_util_peak": max(gpus),
            "mem_util_avg": round(sum(mems) / len(mems), 1),
            "mem_used_peak_mb": max(mem_used),
            "samples": len(self.samples),
            "source": "remote" if self.remote_url else "local",
            "available": self.available,
        }

# ── Reference scores ──────────────────────────────────────────────────────────
REFERENCE_SCORES = """
Reference scores (for comparison):
  ARC-Challenge (0-shot chat):
    Gemma4-26B-A4B  IQ3_XXS : ~91%  (gguf-bench.com, 25-shot logprob)
    Qwen3.5-35B-A3B Q4_K_M  : ~90%  (gguf-bench.com)
  IFEval strict prompt-level:
    Gemma4-26B-A4B  IQ3_XXS : ~92%  (gguf-bench.com)
  SWE-Bench Verified:
    Qwen3.6-35B-A3B         : 73.4% (model card)
    Gemma4-31B              : 52.0% (model card comparison)
    Devstral-24B            : 46.8% (Ollama model card)
"""


def chat(model, messages, max_tokens=16, temperature=0.0, timeout=300):
    """Single chat call to Ollama. Returns (content, tok_stats) tuple.
    tok_stats = {"eval_tokens": int, "eval_tok_per_s": float} or {} on error.
    Uses 1024 min tokens to allow thinking models to complete before content appears.
    """
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                # Ensure thinking models have enough budget before content appears.
                # Thinking alone can consume 600-1500 tokens before content starts.
                "num_predict": max(max_tokens, 1024),
            }
        }, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        msg = data.get("message", {})
        content = msg.get("content", "").strip()

        # Capture token throughput from Ollama's timing fields
        eval_count = data.get("eval_count", 0)
        eval_ns = data.get("eval_duration", 0)
        tok_stats = {
            "eval_tokens": eval_count,
            "eval_tok_per_s": round(eval_count / (eval_ns / 1e9), 1) if eval_ns > 0 else 0.0,
        }
        return content, tok_stats
    except Exception as e:
        return f"ERROR: {e}", {}


# ── ARC-Challenge ─────────────────────────────────────────────────────────────

ARC_SYSTEM = (
    "You are a helpful assistant answering multiple-choice science questions. "
    "Respond with ONLY the single letter of the correct answer (A, B, C, or D). "
    "Do not explain. Do not repeat the question. Just one letter."
)

def format_arc_question(item):
    choices = item["choices"]
    labels = choices["label"]
    texts = choices["text"]
    options = "\n".join(f"{l}. {t}" for l, t in zip(labels, texts))
    return f"{item['question']}\n{options}"


def run_arc(model, limit=None, concurrency=1, gpu_url=None):
    from datasets import load_dataset
    ds = load_dataset("allenai/ai2_arc", "ARC-Challenge", split="test")
    if limit:
        ds = ds.select(range(min(limit, len(ds))))

    total = len(ds)
    correct = 0
    errors = 0
    results = []

    print(f"\nRunning ARC-Challenge on {model} ({total} questions, concurrency={concurrency})")
    start = time.time()
    gpu = GPUSampler(remote_url=gpu_url).start()

    def eval_one(item):
        prompt = format_arc_question(item)
        answer, tok = chat(model, [
            {"role": "system", "content": ARC_SYSTEM},
            {"role": "user", "content": prompt},
        ], max_tokens=4, temperature=0.0)

        # Extract first letter from response
        match = re.search(r'\b([A-D])\b', answer.upper())
        pred = match.group(1) if match else answer.upper()[:1]
        # Normalize gold: some ARC items use numeric keys (1-4) mapped to A-D
        gold = item["answerKey"]
        numeric_map = {"1": "A", "2": "B", "3": "C", "4": "D"}
        gold = numeric_map.get(gold, gold)
        return {"pred": pred, "gold": gold, "correct": pred == gold,
                "error": answer.startswith("ERROR"), "tok": tok}

    tok_rates = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(eval_one, item): i for i, item in enumerate(ds)}
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            r = future.result()
            results.append(r)
            if r["error"]:
                errors += 1
            elif r["correct"]:
                correct += 1
            if r["tok"].get("eval_tok_per_s", 0) > 0:
                tok_rates.append(r["tok"]["eval_tok_per_s"])
            done = len(results)
            if done % 25 == 0 or done == total:
                acc = correct / (done - errors) if (done - errors) > 0 else 0
                elapsed = time.time() - start
                tps = f"  ~{sum(tok_rates)/len(tok_rates):.1f} tok/s" if tok_rates else ""
                print(f"  [{done}/{total}] acc={acc*100:.1f}%  errors={errors}  "
                      f"elapsed={elapsed:.0f}s  ~{elapsed/done:.1f}s/q{tps}")

    valid = total - errors
    acc = correct / valid if valid > 0 else 0
    elapsed = time.time() - start
    avg_tps = round(sum(tok_rates) / len(tok_rates), 1) if tok_rates else None
    gpu.stop()
    gs = gpu.stats
    gs["avg_tok_per_s"] = avg_tps
    gs["elapsed_s"] = round(elapsed, 1)
    gs["s_per_question"] = round(elapsed / total, 1)
    print(f"\nARC-Challenge result: {correct}/{valid} = {acc*100:.1f}%  ({errors} errors)  {elapsed:.0f}s total")
    print(f"Throughput:  {avg_tps} tok/s avg  ~{elapsed/total:.1f}s/q")
    print(f"GPU utilization:  avg={gs['gpu_util_avg']}%  peak={gs['gpu_util_peak']}%  "
          f"mem_peak={gs['mem_used_peak_mb']}MB  ({gs['samples']} samples)")
    return acc, results, gs


# ── IFEval ────────────────────────────────────────────────────────────────────

def run_ifeval(model, limit=None, gpu_url=None):
    from datasets import load_dataset
    ds = load_dataset("google/IFEval", split="train")
    if limit:
        ds = ds.select(range(min(limit, len(ds))))

    total = len(ds)
    passed = 0
    errors = 0
    results = []

    print(f"\nRunning IFEval on {model} ({total} prompts)")
    start = time.time()
    gpu = GPUSampler(remote_url=gpu_url).start()

    for i, item in enumerate(ds):
        prompt = item["prompt"]
        response, tok = chat(model, [{"role": "user", "content": prompt}],
                        max_tokens=1024, temperature=0.0, timeout=300)

        is_error = response.startswith("ERROR")
        if is_error:
            errors += 1

        # Check each instruction in the prompt
        instruction_ids = item.get("instruction_id_list", [])
        kwargs_list = item.get("kwargs", [])

        prompt_passed = True
        if not is_error:
            from ifeval_utils import check_instruction
            for inst_id, kwargs in zip(instruction_ids, kwargs_list):
                if not check_instruction(inst_id, response, kwargs):
                    prompt_passed = False
                    break

        if not is_error and prompt_passed:
            passed += 1

        results.append({"prompt": prompt[:80], "response": response[:200],
                         "passed": prompt_passed, "error": is_error, "tok": tok})

        if (i + 1) % 50 == 0 or (i + 1) == total:
            acc = passed / (i + 1 - errors) if (i + 1 - errors) > 0 else 0
            print(f"  [{i+1}/{total}] strict_acc={acc*100:.1f}%  errors={errors}  "
                  f"elapsed={time.time()-start:.0f}s")

    valid = total - errors
    acc = passed / valid if valid > 0 else 0
    elapsed = time.time() - start
    tok_rates = [r["tok"].get("eval_tok_per_s", 0) for r in results if r["tok"].get("eval_tok_per_s", 0) > 0]
    avg_tps = round(sum(tok_rates) / len(tok_rates), 1) if tok_rates else None
    gpu.stop()
    gs = gpu.stats
    gs["avg_tok_per_s"] = avg_tps
    gs["elapsed_s"] = round(elapsed, 1)
    print(f"\nIFEval strict result: {passed}/{valid} = {acc*100:.1f}%  ({errors} errors)")
    print(f"Throughput:  {avg_tps} tok/s avg")
    print(f"GPU utilization:  avg={gs['gpu_util_avg']}%  peak={gs['gpu_util_peak']}%  "
          f"mem_peak={gs['mem_used_peak_mb']}MB  ({gs['samples']} samples)")
    return acc, results, gs


# ── HumanEval ─────────────────────────────────────────────────────────────────

HUMANEVAL_SYSTEM = (
    "You are an expert Python programmer. Complete the provided function. "
    "Return ONLY the complete function implementation including the def line. "
    "No explanations, no markdown fences, no extra text."
)

def run_humaneval(model, limit=None, gpu_url=None):
    from datasets import load_dataset
    ds = load_dataset("openai/openai_humaneval", split="test")
    if limit:
        ds = ds.select(range(min(limit, len(ds))))

    total = len(ds)
    passed = 0
    errors = 0
    results = []

    print(f"\nRunning HumanEval on {model} ({total} problems)")
    start = time.time()
    gpu = GPUSampler(remote_url=gpu_url).start()

    tok_rates = []
    for i, item in enumerate(ds):
        prompt = item["prompt"]
        response, tok = chat(model, [
            {"role": "system", "content": HUMANEVAL_SYSTEM},
            {"role": "user", "content": f"Complete this Python function:\n\n{prompt}"},
        ], max_tokens=512, temperature=0.0, timeout=180)

        is_error = response.startswith("ERROR")
        if is_error:
            errors += 1
            results.append({"task_id": item["task_id"], "passed": False, "error": True, "tok": tok})
            continue

        if tok.get("eval_tok_per_s", 0) > 0:
            tok_rates.append(tok["eval_tok_per_s"])

        # Run the test
        code = response
        # Strip markdown fences if present
        code = re.sub(r'^```python\n?|^```\n?|```$', '', code, flags=re.MULTILINE).strip()
        test_code = f"{code}\n\n{item['test']}\ncheck({item['entry_point']})"

        try:
            exec_globals = {}
            exec(compile(test_code, "<string>", "exec"), exec_globals)
            passed += 1
            results.append({"task_id": item["task_id"], "passed": True, "error": False, "tok": tok})
        except Exception as e:
            results.append({"task_id": item["task_id"], "passed": False,
                             "error": False, "exc": str(e)[:100], "tok": tok})

        if (i + 1) % 25 == 0 or (i + 1) == total:
            acc = passed / (i + 1 - errors) if (i + 1 - errors) > 0 else 0
            tps = f"  ~{sum(tok_rates)/len(tok_rates):.1f} tok/s" if tok_rates else ""
            print(f"  [{i+1}/{total}] pass@1={acc*100:.1f}%  errors={errors}  "
                  f"elapsed={time.time()-start:.0f}s{tps}")

    valid = total - errors
    acc = passed / valid if valid > 0 else 0
    elapsed = time.time() - start
    avg_tps = round(sum(tok_rates) / len(tok_rates), 1) if tok_rates else None
    gpu.stop()
    gs = gpu.stats
    gs["avg_tok_per_s"] = avg_tps
    gs["elapsed_s"] = round(elapsed, 1)
    print(f"\nHumanEval pass@1: {passed}/{valid} = {acc*100:.1f}%  ({errors} errors)")
    print(f"Throughput:  {avg_tps} tok/s avg  ~{elapsed/total:.1f}s/problem")
    print(f"GPU utilization:  avg={gs['gpu_util_avg']}%  peak={gs['gpu_util_peak']}%  "
          f"mem_peak={gs['mem_used_peak_mb']}MB  ({gs['samples']} samples)")
    return acc, results, gs


# ── Main ──────────────────────────────────────────────────────────────────────

TASKS = {"arc": run_arc, "ifeval": run_ifeval, "humaneval": run_humaneval}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("task", choices=list(TASKS))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Parallel requests (ARC only; use 1 for thinking models)")
    parser.add_argument("--gpu-server", default=None, metavar="URL",
                        help="gpu_sidecar.py URL for remote GPU metrics, e.g. http://192.168.1.10:8765/gpu")
    args = parser.parse_args()

    out_dir = RESULTS_DIR / args.model.replace(":", "_").replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    print(REFERENCE_SCORES)

    kwargs = {"limit": args.limit, "gpu_url": args.gpu_server}
    if args.task == "arc":
        kwargs["concurrency"] = args.concurrency

    score, detail, gpu_stats = TASKS[args.task](args.model, **kwargs)

    out = {
        "model": args.model,
        "task": args.task,
        "score": score,
        "limit": args.limit,
        "timestamp": ts,
        "gpu_stats": gpu_stats,
        "results": detail,
    }
    out_file = out_dir / f"{args.task}_{ts}.json"
    with open(out_file, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved: {out_file}")


if __name__ == "__main__":
    main()
