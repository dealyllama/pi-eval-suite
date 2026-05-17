# FOSS Agentic Toolchain Evaluation Suite

A testing framework for evaluating **models** and **agentic toolchains** running on a local
Ollama server. Built around [Pi](https://github.com/earendil-works/pi/tree/main/packages/coding-agent) as the agent runtime.

The key distinction this suite makes — and that most off-the-shelf eval frameworks miss —
is the difference between testing a *model* and testing a *system*. The same model can
perform dramatically differently depending on the tools, prompts, and orchestration wrapped
around it. This suite tests both layers independently and gives you a version-controlled
history so you can measure whether changes to your toolchain are actually helping.

---

## How it works

Two evaluation layers, run in sequence:

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1 — Model Evaluation  (Python scripts, ~5–30 min)        │
│                                                                 │
│  Gate: is this a new model?                                     │
│    Yes → smoke test → optional benchmark → proceed              │
│    No  → skip, go straight to Layer 2                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │ pass
┌───────────────────────────▼─────────────────────────────────────┐
│  Layer 2 — Agentic Evaluation  (Pi test plan, ~1–2 hrs)         │
│                                                                 │
│  Tier 1: Foundational tool calls                                │
│  Tier 2: Multi-tool chains                                      │
│  Tier 3: Complex research and orchestration                     │
│  Tier 4: Regression (requires a prior baseline run)            │
│  Tier 5: Adversarial and error recovery                         │
└─────────────────────────────────────────────────────────────────┘
```

Every run gets its own directory under `runs/`. Results are append-only JSONL. The whole
thing lives in git so you have a complete history of every evaluation you have ever run.

---

## Prerequisites

**On your tablet (or wherever you run Pi):**
- [Pi](https://github.com/earendil-works/pi/tree/main/packages/coding-agent) with the `context-mode` extension installed
- Python 3.10+ with `requests` installed (`pip install requests`)
- Git

**On your Ollama host (WSL2 Ubuntu in this setup):**
- [Ollama](https://ollama.com/) running and reachable on your local network
- Python 3.10+ (for `gpu_sidecar.py`)
- NVIDIA drivers with `nvidia-smi` available (optional — GPU metrics are nice-to-have)

**For academic benchmarks only** (`benchmark.py` / `run_benchmarks.py`):
- `pip install datasets requests` (for `benchmark.py`)
- `pip install lm-eval` (for `run_benchmarks.py`, uses lm-evaluation-harness)

---

## Repository layout

```
model_testing/
│
├── README.md                 this file
├── testing-plan.md           master template — never run directly, never edit during a run
│
├── run_eval.py               unified entry point — start every evaluation here
├── smoke_test.py             quick model capability check (tool calling, thinking, multi-turn)
├── benchmark.py              academic benchmarks via direct Ollama API (ARC, IFEval, HumanEval)
├── run_benchmarks.py         academic benchmarks via lm-evaluation-harness
├── gpu_sidecar.py            lightweight HTTP server — run this on your Ollama host
│
└── runs/                     one directory per evaluation run (git tracked)
    └── <model>_<run_id>/
        ├── testing-plan.md   copy of master with run_id and model pre-filled
        ├── test-results.jsonl results from both layers for this run
        └── test-output/      scratch files and artifacts produced during the run
```

> **The master `testing-plan.md` is a template.** Never open it in Pi and start running
> tests. Always use the copy inside a `runs/` directory created by `run_eval.py`.

---

## First-time setup

### 1. Clone the repo

```bash
git clone https://github.com/dealyllama/pi-eval-suite.git
cd pi-eval-suite
```

### 2. Install dependencies

```bash
# Core only — enough for run_eval.py, smoke_test.py, eval.sh
./setup.sh

# Core + benchmark.py (ARC-Challenge, HumanEval via direct Ollama API)
./setup.sh --benchmarks

# Core + lm-evaluation-harness for run_benchmarks.py (~500MB, optional)
./setup.sh --harness

# Everything
./setup.sh --all
```

This creates `.venv/` and installs into it. `eval.sh` activates it automatically.
If you prefer a manual install: `pip install -r requirements.txt` (and optionally
`requirements-benchmarks.txt` or `requirements-harness.txt`).

### 3. Point the scripts at your Ollama host

All scripts read `OLLAMA_BASE_URL` from the environment. Set it once in your shell profile:

```bash
# ~/.bashrc or ~/.profile on your tablet
export OLLAMA_BASE_URL=http://192.168.1.10:11434
```

Replace `192.168.1.10` with your WSL2 host's LAN IP. To find it:
```bash
# Run this on WSL2
hostname -I | awk '{print $1}'
```

> **Note:** WSL2 gets a new IP on every Windows restart. If connectivity breaks, re-run
> the command above and update your environment variable.

### 3. Set up the GPU sidecar (optional but recommended)

The GPU sidecar runs on your Ollama host and exposes `nvidia-smi` metrics over HTTP so
benchmark runs on your tablet can capture GPU utilization. It has no external dependencies.

**On your WSL2 machine:**

```bash
# Copy gpu_sidecar.py to your WSL2 home directory
scp gpu_sidecar.py user@windows-host:~/gpu_sidecar.py

# Start it (runs in background, logs to gpu_sidecar.log)
ssh user@windows-host "nohup python3 ~/gpu_sidecar.py &> ~/gpu_sidecar.log &"

# Verify it's working
curl http://192.168.1.10:8765/gpu
```

You should see a JSON response with GPU utilization, memory, and temperature.

**Make it start automatically on WSL2 login** — add to `~/.bashrc` on WSL2:
```bash
(pgrep -f gpu_sidecar.py || nohup python3 ~/gpu_sidecar.py &> ~/gpu_sidecar.log &)
```

**Windows Firewall** — run once in an admin PowerShell to allow inbound connections:
```powershell
netsh advfirewall firewall add rule name="GPU Sidecar" dir=in action=allow protocol=TCP localport=8765
```

### 4. Verify Pi is ready

Open Pi and confirm `context-mode` is connected:
```
mcp()
```
You should see `context-mode` in the server list with 11 tools. If not, install the
extension and restart Pi before running any agentic tests.

---

## Running an evaluation

### Step 1 — Decide which path you're on

| Situation | Command |
|---|---|
| **New model** — first time testing this model | `./eval.sh --model <model> --new-model` |
| **New model + benchmark scores** | `./eval.sh --model <model> --new-model --benchmark` |
| **Toolchain change** — same model, different Pi config | `./eval.sh --model <model>` |
| **Quick benchmark only** (no agentic tests) | `python3 smoke_test.py <model>` then `python3 benchmark.py <model> arc --limit 50` |

With GPU metrics from the sidecar, append `--gpu-server http://192.168.1.10:8765/gpu` to
any `run_eval.py` or `benchmark.py` command.

### Step 2 — Run `run_eval.py`

```bash
# Example: new model, quick benchmark sanity check, GPU metrics
./eval.sh \
  --model hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL \
  --new-model \
  --benchmark --limit 50 \
  --gpu-server http://192.168.1.10:8765/gpu
```

`eval.sh` activates the venv, checks Python version, verifies Ollama is reachable,
then passes all arguments through to `run_eval.py`. You can call `run_eval.py` directly
if you prefer to manage the environment yourself.

This will:
1. Create a run directory at `runs/<model-slug>_<timestamp>/`
2. Copy the master test plan into it with your `run_id` and model name already filled in
3. Run the smoke test — if the model fails, it stops here
4. Run the benchmark (if requested)
5. Print the exact path to open in Pi
1. Create a run directory at `runs/<model-slug>_<timestamp>/`
2. Copy the master test plan into it with your `run_id` and model name already filled in
3. Run the smoke test — if the model fails, it stops here
4. Run the benchmark (if requested)
5. Print the exact path to open in Pi

At the end you'll see something like:

```
============================================================
Ready for agentic tests (Phase 1–5)
============================================================

  Open this file in Pi and begin at Tier 1:
    /path/to/runs/Qwen3.6-35B_20260517_103725/testing-plan.md

  Results log : runs/Qwen3.6-35B_20260517_103725/test-results.jsonl
  run_id      : 20260517_103725
  model       : hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL
```

### Step 3 — Open the plan in Pi and run the agentic tests

Open the file path printed above in Pi. The first thing you'll see is a parameter table:

```markdown
| run_id  | 20260517_103725                                         |
| model   | hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL         |
| created | 2026-05-17T10:37:25Z                                    |
| log     | runs/Qwen3.6-35B_20260517_103725/test-results.jsonl    |
```

The model does not need to look anything up — its identity and result log path are right
there. Follow the **START HERE** section, complete setup steps S1–S4, then work through
the tiers in order.

Each test follows the same pattern:
- **Do this** — exact actions to take
- **You should see** — what success looks like
- **If you see something else** — recovery steps
- **Record** — exact JSON to append to `test-results.jsonl`

Tier gates are runnable bash commands that read the results file and print PASS or STOP.
The model does not make judgment calls about whether to proceed.

---

## Understanding results

### The result log

All phases write to the same `test-results.jsonl` inside the run directory.
Each line is one result:

```json
{"run_id":"20260517_103725","phase":"model","id":"P0.1/tool_call","model":"qwen36-35b","status":"PASS","timestamp":"2026-05-17T10:37:30Z","notes":""}
{"run_id":"20260517_103725","phase":"agentic","id":"T1.1","model":"qwen36-35b","status":"PASS","timestamp":"2026-05-17T10:42:11Z","duration_s":4,"tools_used":["mcp"],"tool_call_count":2,"notes":""}
```

| Field | Values | Meaning |
|---|---|---|
| `phase` | `model` / `agentic` | Which layer produced this result |
| `id` | `P0.1`, `T1.1`, … | Phase/tier/test identifier |
| `status` | `PASS` / `WARN` / `FAIL` / `SKIP` | Outcome |
| `tool_call_count` | integer | Efficiency metric — compare against per-test ceilings in the plan |

### Summarising a run

```bash
python3 -c "
import json
rows = [json.loads(l) for l in open('runs/<run-dir>/test-results.jsonl') if l.strip()]
for s in ['PASS','WARN','FAIL','SKIP']:
    ids = [r['id'] for r in rows if r.get('status') == s]
    if ids: print(f'{s:5}: {ids}')
"
```

### Comparing two runs

```bash
# Side-by-side status comparison
diff \
  <(python3 -c "import json; [print(r['id'], r['status']) for r in [json.loads(l) for l in open('runs/run1/test-results.jsonl')] if l.strip()]") \
  <(python3 -c "import json; [print(r['id'], r['status']) for r in [json.loads(l) for l in open('runs/run2/test-results.jsonl')] if l.strip()]")
```

Or just use `git diff runs/run1/test-results.jsonl runs/run2/test-results.jsonl`.

---

## Git workflow

The intent is that `runs/` is committed alongside the code so every evaluation is
permanently part of the repo history.

```bash
# After completing a run
git add runs/<model>_<run_id>/
git commit -m "eval: qwen36-35b toolchain v2 — T1-T3 all PASS"

# Start fresh from a clean state
git pull                        # get latest template + scripts
python3 run_eval.py --model <model>   # creates a new run directory
```

The master `testing-plan.md` gets better over time as you update it. Because each run
directory contains a *copy* of the template at the time it was created, old runs are
unaffected by template changes — you can always see exactly what instructions were used
for any historical run.

**Suggested `.gitignore`:**
```gitignore
__pycache__/
*.pyc
runs/*/test-output/          # ignore scratch artifacts
*.backup*.md                 # ignore backup files
```

If you'd rather not commit run directories at all (treat git as source-only):
```gitignore
runs/
```

---

## Individual tools reference

### `eval.sh` — recommended entry point

Thin wrapper around `run_eval.py` that handles environment setup and pre-flight checks.

```bash
./eval.sh --model <model> [same options as run_eval.py]
```

Checks performed before handing off:
- Python 3.10+ present
- `.venv/` activated if it exists
- `OLLAMA_BASE_URL` set (warns if not)
- Ollama API reachable (fast-fails with a clear message if not)
- `requests` package installed

---

### `setup.sh` — environment setup

```bash
./setup.sh              # core only
./setup.sh --benchmarks # + datasets (benchmark.py)
./setup.sh --harness    # + lm-eval  (run_benchmarks.py, ~500MB)
./setup.sh --all        # everything
```

Creates `.venv/` in the repo root. Run once after cloning. Re-run after pulling if
new dependencies are added.

---

### `run_eval.py` — unified entry point

```
python3 run_eval.py --model <model> [options]

  --model        Ollama model name (required)
  --new-model    Run smoke test gate before agentic tests
  --benchmark    Run ARC-Challenge benchmark (requires --new-model or implies it)
  --limit N      Cap benchmark questions (e.g. 50 for a quick sanity check)
  --gpu-server   URL of gpu_sidecar.py (e.g. http://192.168.1.10:8765/gpu)
  --run-id       Override the auto-generated timestamp run ID
```

Always start here. It creates the run directory, copies and substitutes the test plan,
runs model tests if requested, and tells you exactly what to open in Pi.

---

### `smoke_test.py` — quick model capability screen

Tests three things every model must be able to do before it's worth evaluating further:

| Test | What it checks |
|---|---|
| Tool call | Model emits a structurally valid tool call when a tool is available |
| Thinking | Thinking tokens are correctly separated (not leaking into response content) |
| Multi-turn | Model retains context across a short conversation |

```bash
# Test one model
python3 smoke_test.py hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL

# Test all models in the MODELS_TO_TEST list
python3 smoke_test.py --all
```

Results are printed as a summary table and saved to `smoke_test_results_<timestamp>.json`.

**When to run directly:** When you want a fast ✅/⚠️/❌ on a new model pull without
starting a full evaluation run. `run_eval.py --new-model` calls this automatically.

---

### `benchmark.py` — academic benchmarks (direct Ollama API)

Runs standardised benchmarks by calling the Ollama API directly. No lm-evaluation-harness
required. Captures token throughput and (if the GPU sidecar is available) GPU utilization.

| Task | Dataset | Metric | Questions |
|---|---|---|---|
| `arc` | ARC-Challenge | accuracy | 1,172 |
| `ifeval` | IFEval | strict prompt-level accuracy | 541 |
| `humaneval` | HumanEval | pass@1 | 164 |

```bash
# Full ARC run
python3 benchmark.py qwen36-35b arc

# Quick 50-question sanity check with GPU metrics
python3 benchmark.py qwen36-35b arc --limit 50 --gpu-server http://192.168.1.10:8765/gpu

# Parallel requests (faster for non-thinking models; use 1 for thinking models)
python3 benchmark.py qwen36-35b arc --concurrency 4

# IFEval
python3 benchmark.py qwen36-35b ifeval

# HumanEval (code generation)
python3 benchmark.py qwen36-35b humaneval --limit 50
```

Results are saved to `benchmark_results/<model>/<task>_<timestamp>.json`.

**Reference scores** (printed at the start of each run for comparison):
- ARC-Challenge: Gemma4-26B IQ3_XXS ~91%, Qwen3.5-35B Q4_K_M ~90%
- IFEval strict: Gemma4-26B IQ3_XXS ~92%
- SWE-Bench Verified: Qwen3.6-35B 73.4%, Devstral-24B 46.8%

---

### `run_benchmarks.py` — benchmarks via lm-evaluation-harness

Alternative benchmark runner using the [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)
framework. Uses the Ollama OpenAI-compatible endpoint. Produces results in the harness's
standard output format, which is more comparable to published leaderboard numbers.

```bash
# Requires: pip install lm-eval
python3 run_benchmarks.py qwen36-35b arc_challenge --limit 50
python3 run_benchmarks.py qwen36-35b ifeval
python3 run_benchmarks.py qwen36-35b humaneval --limit 50
```

Use this when you want scores that are directly comparable to published benchmarks.
Use `benchmark.py` when you want faster iteration and GPU utilization data.

---

### `gpu_sidecar.py` — GPU metrics server (runs on Ollama host)

A minimal HTTP server (no external dependencies) that exposes `nvidia-smi` data as JSON.
Run this on your WSL2 machine so benchmark runs on your tablet can capture GPU metrics.

```bash
# Start on WSL2
python3 gpu_sidecar.py                      # default: 0.0.0.0:8765
python3 gpu_sidecar.py --port 9000          # custom port

# Check it's working
curl http://localhost:8765/gpu
curl http://localhost:8765/health

# Example response
{
  "gpus": [{
    "index": 0,
    "name": "NVIDIA GeForce RTX 4090",
    "gpu_util_pct": 94,
    "mem_util_pct": 78,
    "mem_used_mb": 19240,
    "mem_total_mb": 24576,
    "temp_c": 72,
    "power_w": 320.5
  }],
  "timestamp": "2026-05-17T10:37:25Z"
}
```

GPU metrics are **optional**. If the sidecar is unreachable, benchmark runs warn once and
continue without GPU data. All other metrics (token throughput, accuracy) still work.

---

## The agentic test plan — what it actually tests

The `testing-plan.md` is not a test suite you run in a terminal. It is a structured
instruction document that Pi reads and executes, with Pi itself as the thing under test.

This is important: because Pi is the agent runtime, it cannot be meaningfully tested from
outside — an external harness that talks to Ollama directly bypasses all of Pi's value
(tool routing, context management, sub-agent orchestration, memory, extensions). The plan
tests the full stack.

**What each tier targets:**

| Tier | Focus | Why it matters |
|---|---|---|
| 1 — Foundational | Individual tool calls work correctly | Nothing else functions if tools are broken |
| 2 — Chaining | Multi-tool sequences, conditional logic | Most real tasks require chained tools |
| 3 — Orchestration | Parallel agents, research pipelines, feedback loops | High-value automation requires this |
| 4 — Regression | Tool paths are stable across runs | Detects silent degradation after model/config changes |
| 5 — Adversarial | Graceful handling of failures and empty results | Production reliability |

**The efficiency ceilings** in each test (e.g. "≤ 8 tool calls") are not arbitrary. They
encode the expected cost of each task. A model that takes 3× as many tool calls to do the
same work as a previous run is a signal that something regressed, even if the outcome was
technically correct.

---

## Troubleshooting

**`OLLAMA_BASE_URL` not set / connection refused**
The scripts default to `http://localhost:11434`. If Ollama is on another machine, set the
environment variable before running anything.

**WSL2 IP changed after Windows restart**
Run `hostname -I` on WSL2, update `OLLAMA_BASE_URL`, restart gpu_sidecar if running.

**GPU sidecar unreachable**
Check the Windows Firewall rule (`netsh advfirewall firewall show rule name="GPU Sidecar"`).
Check that WSL2 is running (`wsl --list --running` in PowerShell).
Benchmark runs continue without GPU data — this is not a blocker.

**Pi shows `{{RUN_ID}}` or `{{MODEL}}` in the plan**
You opened the master template directly. Always use the copy inside a `runs/` directory.
Run `python3 run_eval.py --model <model>` to create one.

**Smoke test fails with `Request failed: Connection refused`**
Ollama is not reachable. Verify `OLLAMA_BASE_URL` and that the model is pulled
(`ollama pull <model>`).

**context-mode not found in `mcp()`**
The extension is not installed or Pi needs a restart. Install context-mode and reopen Pi.

**Tier gate shows STOP**
A test in the current tier has status `FAIL`. Do not proceed. Read the `notes` field of the
failing result row to understand what went wrong, fix the underlying issue, and re-run that
tier. You can re-run a single tier by opening the plan in a new Pi session — the results
file is append-only so previous passes are preserved.
