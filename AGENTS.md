# AGENTS.md — Pi Eval Suite

This file tells AI agents how to work in this repository correctly.
Read it in full before taking any action.

---

## Two completely separate modes of operation

This repo supports two activities that must never be mixed in the same session:

| Mode | You are... | Working on... |
|---|---|---|
| **Development** | Improving the evaluation suite itself | Source files, templates, scripts |
| **Execution** | Running an evaluation against a model | A specific `runs/` directory |

**If you are not sure which mode you are in, stop and ask.**

---

## Mode 1 — Development

You are in development mode when the task involves:
- Editing or improving `benchmark.py`, `smoke_test.py`, `run_eval.py`, `run_benchmarks.py`, `gpu_sidecar.py`
- Editing or improving the master `testing-plan.md` template
- Editing `eval.sh`, `setup.sh`, `requirements*.txt`, `.gitignore`, `README.md`, or this file
- Adding new benchmark tasks, fixing bugs, improving test structure

### What to do in development mode

- Edit source files directly using `edit` or `write`
- Test Python changes with `python3 -m py_compile <file>` before considering them done
- When editing `testing-plan.md`, remember it is a **template** — preserve all `{{RUN_ID}}`,
  `{{MODEL}}`, `{{CREATED}}`, and `{{LOG_PATH}}` placeholders exactly as-is
- Keep the `runs/` directory structure and `.gitignore` consistent with any new output files
  you add to scripts

### What NOT to do in development mode

- **Do not run `./eval.sh` or `python3 run_eval.py`** — this creates a new run directory and
  copies the template. Only do this when you intend to start a real evaluation.
- **Do not run `python3 benchmark.py` or `python3 smoke_test.py` against a real model** unless
  explicitly asked to test a script change end-to-end.
- **Do not write to any `runs/` directory** — run directories are produced by `run_eval.py`,
  not by hand.
- **Do not edit `runs/*/testing-plan.md`** — those are completed or in-progress run records.
  Edit the master `testing-plan.md` at the repo root instead.
- **Do not edit `runs/*/test-results.jsonl`** — that is append-only run history.

---

## Mode 2 — Execution

You are in execution mode when the task involves:
- Running an evaluation against a specific model
- Working through the tiers in a `testing-plan.md` inside a `runs/` directory
- Appending results to a `runs/*/test-results.jsonl` file

### Before you start execution

`run_eval.py` (or `eval.sh`) must have already been run by the user. It creates the run
directory and substitutes the plan. You should be given a path like:

```
runs/qwen36-35b_20260517_103725/testing-plan.md
```

If you are not given this path, or if the file still contains `{{RUN_ID}}` or `{{MODEL}}`
as literal text, stop. The user needs to run `./eval.sh --model <model>` first.

### What to do in execution mode

- Open the `testing-plan.md` **inside the run directory** — not the master template at the
  repo root
- Follow the START HERE section and complete setup steps S1–S4 before any tier
- Execute one test at a time; record a result row before moving to the next test
- Append results to the `test-results.jsonl` **inside the same run directory**
- Run tier gate commands exactly as written in the plan before proceeding to the next tier

### What NOT to do in execution mode

- **Do not edit source files** (`benchmark.py`, `smoke_test.py`, `run_eval.py`, etc.)
- **Do not edit the master `testing-plan.md`** at the repo root
- **Do not create a new run directory** — one already exists for this session
- **Do not use the `memory` tool to track test state** — it pollutes durable cross-session
  memory. Use `bash` or `write` to append to `test-results.jsonl` only.
- **Do not skip tier gates** — if a gate prints STOP, stop.

---

## Repository map (quick reference)

```
pi-eval-suite/
│
├── AGENTS.md              this file
├── README.md              human-facing documentation
│
│  ── Source files (development mode only) ──
├── testing-plan.md        master template — contains {{PLACEHOLDERS}}, never run directly
├── run_eval.py            unified entry point; creates run directories
├── eval.sh                pre-flight wrapper around run_eval.py
├── setup.sh               venv creation and dependency install
├── smoke_test.py          quick model capability screen
├── benchmark.py           direct-API benchmarks (ARC, HumanEval)
├── run_benchmarks.py      lm-evaluation-harness benchmarks
├── gpu_sidecar.py         GPU metrics HTTP server (deploy to Ollama host)
├── requirements*.txt      dependency tiers
│
│  ── Run directories (execution mode only) ──
└── runs/
    └── <model>_<run_id>/
        ├── testing-plan.md      substituted copy — this is what Pi executes
        ├── test-results.jsonl   append-only result log for this run
        └── test-output/         scratch files produced during the run
```

---

## Key rules, summarised

1. Master `testing-plan.md` contains `{{PLACEHOLDERS}}` — never execute it directly.
2. Run directories under `runs/` are records — never edit them in development mode.
3. `test-results.jsonl` is append-only — never truncate or overwrite it.
4. `memory` tool is off-limits for test state — use `bash`/`write` to the results file.
5. One mode per session — do not switch between development and execution in the same session.
