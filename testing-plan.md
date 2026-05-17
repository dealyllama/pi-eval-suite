# Progressive Agentic Testing Plan

---
<!-- RUN PARAMETERS — substituted by run_eval.py when this file is created -->
| Parameter | Value |
|---|---|
| **run_id** | {{RUN_ID}} |
| **model**  | {{MODEL}}  |
| **created**| {{CREATED}}|
| **log**    | {{LOG_PATH}}|

---

## ⚡ START HERE — Read This Before Anything Else

This document is a step-by-step execution plan. You are the executor.

**How to use this document:**

1. Complete the **Session Setup** section below in full before proceeding to any tier.
   Do not skip setup steps. Each one has a verification action — run it.
2. Execute one test at a time. Do not read ahead and batch actions.
3. After every test, write a result row to `test-results.jsonl` before moving on.
   This is not optional — it is how progress survives a session failure.
4. At every **TIER GATE**, read the gate condition and stop if it is not met.
   Do not proceed to the next tier if any test in the current tier has status `FAIL`.
5. If you are unsure whether a result is a PASS or FAIL, record it as `WARN` with a
   detailed `notes` field and continue. Do not make silent judgment calls.
6. Do not use the `memory` tool for test state. It pollutes durable cross-session memory.
   Use `bash` or `write` to append to `test-results.jsonl` only.

**The result row format used throughout this plan:**
```json
{
  "run_id": "<value printed by run_eval.py — see Session Setup>",
  "phase": "agentic",
  "id": "T1.1",
  "model": "<model name — see Session Setup>",
  "status": "PASS",
  "timestamp": "<ISO 8601 UTC, e.g. 2026-05-17T10:30:00Z>",
  "duration_s": 4,
  "tools_used": ["mcp"],
  "tool_call_count": 2,
  "notes": ""
}
```

**Correct Pi API names (use these exactly):**
- Launch a background agent → `Agent` tool with `run_in_background: true`
- Steer a running agent → `steer_subagent(agent_id, message)`
- Retrieve agent results → `get_subagent_result(agent_id)`

---

## Session Setup (Complete Before Any Tier)

Work through each step in order. Do not proceed past setup until every verification passes.

### Step S1 — Read your session parameters

Your `run_id`, `model`, and log path are in the parameter table at the top of this file.
Read them now. You will use them in every result row you write.

- `RUN_ID` = the value in the **run_id** row of the table above
- `MODEL`  = the value in the **model** row of the table above
- `LOG`    = the value in the **log** row of the table above

**Do not proceed until you have read all three values from the table.**

**If any value still shows `{{RUN_ID}}` or `{{MODEL}}`:** This file was not created by
`run_eval.py` — it is the unsubstituted master template. Stop. Ask the user to run
`python3 run_eval.py --model <model>` to create a proper run directory, then open
the `testing-plan.md` inside that run directory instead.

---

### Step S2 — Verify scaffolding exists

`run_eval.py` creates scaffolding automatically, but verify it is present.

**Action:**
```bash
ls -la test-output/ && echo "test-output OK" || echo "MISSING: test-output/"
test -f test-results.jsonl && echo "test-results.jsonl OK" || echo "MISSING: test-results.jsonl"
```

**You should see:** Both lines ending in `OK`.

**If either is missing:** Run these to create them, then re-run the verification above:
```bash
mkdir -p test-output
touch test-results.jsonl
```

---

### Step S3 — Verify tool servers are connected

**Action:** `mcp()` with no arguments.

**You should see:** A list of connected servers. At minimum, `context-mode` must appear.

**If `context-mode` is not listed:** Run `mcp({ connect: "context-mode" })` and verify it
connects before proceeding. If it fails, record a FAIL for T1.1 and skip to T1.2.

---

### Step S4 — Record baseline state

You need a pre-test snapshot to isolate side effects.

**Action 1 — context-mode index row count:**
```
mcp({ tool: "context_mode_ctx_stats" })
```
Note the row count. If the index is empty, note that as the baseline (not an error).

**Action 2 — Pi API directory:**
```bash
ls ~/.pi/agent/
```
Confirm `models.json` is present. If not, note it — T1.4 will investigate.

**Action 3 — Write the setup completion row:**
```bash
echo '{"run_id":"RUN_ID_HERE","phase":"agentic","id":"S0","model":"MODEL_HERE","status":"PASS","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","notes":"setup complete, index baseline noted"}' >> test-results.jsonl
```
Replace `RUN_ID_HERE` and `MODEL_HERE` with the values from Step S1.

**Verify it wrote:**
```bash
tail -1 test-results.jsonl
```
You should see the row you just wrote.

---

**Setup is complete. Proceed to Tier 1.**

---

## Test Isolation Policy

Any test that writes to shared state must follow this pattern before and after:

| Resource | Before test | After test |
|---|---|---|
| context-mode index | Note current row count from `ctx_stats` | `ctx_purge` only if this test added content to a previously clean index |
| `memory` entries | Note the exact `target` and `content` you will write | `memory remove` the exact entry added — verify removal with `memory_search` |
| Files written | Note the path | Move to `test-output/` or delete — never leave scratch files in the plan directory |

---

## Tier 1 — Foundational Tool Calls

**Purpose:** Verify core tools execute correctly and return structured results.
**Gate:** All four tests must be PASS before proceeding to Tier 2.

---

### T1.1 — context-mode health check

**What this tests:** The context-mode extension is installed, connected, and functional.

**Do this:**
1. `mcp({ connect: "context-mode" })`
2. `mcp({ tool: "context_mode_ctx_doctor" })`

**You should see:** A diagnostic report with a pass/fail result per component
(MCP connection, FTS5 index, fetch capability). An empty index is not an error here —
record it as the known baseline state.

**If the tool returns an error or hangs:** Record FAIL. The extension is not functional.
Do not proceed past T1.1 — Tier 2 and above depend on context-mode.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T1.1","model":"<MODEL>","status":"PASS|FAIL|WARN","timestamp":"<UTC>","notes":"<any non-pass details, or empty-index note if applicable>","tools_used":["mcp"],"tool_call_count":2}
```

---

### T1.2 — MCP tool enumeration

**What this tests:** Pi correctly enumerates all context-mode tools and their schemas.

**Do this:**
1. `mcp({ server: "context-mode" })`
2. Count the tools returned. Expected: **11 tools**.
3. Pick any 2–3 tools from the list and run `mcp({ describe: "<tool_name>" })` on each.
   Verify that parameter schemas are returned (not empty).

**You should see:** Exactly 11 tools listed; each described tool returns a schema with
at least a `parameters` field.

**If fewer than 11 tools are listed:** Record the actual count in `notes` and mark WARN.
**If `describe` returns empty schemas:** Record FAIL.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T1.2","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"tool_count=<N>; spot-checked: <tool1>, <tool2>","tools_used":["mcp"],"tool_call_count":4}
```

---

### T1.3 — Search execution and edge cases

**What this tests:** `ctx_search` handles normal queries, empty index, and bad input gracefully.

**Pre-condition:** Check your baseline note from S4. If the index was empty at setup,
that is expected here — an empty result is a pass, not an error.

**Do this:**
1. `mcp({ tool: "context_mode_ctx_search", args: '{"queries": ["testing"]}' })`
   - If index was empty: confirm the response is an empty result (not an error). ✓
   - If index had content: confirm results are returned with rankings/snippets. ✓
2. `mcp({ tool: "context_mode_ctx_search", args: '{"queries": [""]}' })`
   Confirm: does not crash, returns empty or an informative message.
3. `mcp({ tool: "context_mode_ctx_search", args: '{"queries": ["!@#$%^"]}' })`
   Confirm: does not crash.

**You should see:** Valid JSON responses for all three calls. No crashes.

**If any call crashes or hangs:** Record FAIL for that specific sub-step in `notes`.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T1.3","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"empty-query: <ok|error>; special-char: <ok|error>","tools_used":["mcp"],"tool_call_count":3}
```

---

### T1.4 — File system access

**What this tests:** `read` and `bash` tools work for local file inspection.

**Do this:**
1. `bash("ls -la ~/.pi/agent/")`
   Confirm the directory exists and contains at minimum: `models.json`.
2. `read("~/.pi/agent/models.json")`
   Confirm the file is readable and contains valid JSON (not an error, not empty).
3. Cross-check: the directory listing from step 1 and the file content from step 2
   are consistent (same file appears in both).

**You should see:** A readable directory; `models.json` with parseable JSON content.

**If `models.json` is missing:** Record FAIL with note `"models.json not found at ~/.pi/agent/"`.
**If the file is unreadable or invalid JSON:** Record FAIL.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T1.4","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"models.json present: <yes|no>; valid JSON: <yes|no>","tools_used":["read","bash"],"tool_call_count":2}
```

---

### ✋ TIER 1 GATE

**Action:** Run this to check your results:
```bash
python3 -c "
import json
rows = [json.loads(l) for l in open('test-results.jsonl') if l.strip()]
t1 = [r for r in rows if r.get('id','').startswith('T1.')]
fails = [r['id'] for r in t1 if r['status'] == 'FAIL']
print('T1 results:', [(r['id'], r['status']) for r in t1])
print('FAILS:', fails if fails else 'none')
print('GATE:', 'STOP — fix failures before Tier 2' if fails else 'PASS — proceed to Tier 2')
"
```

**Stop here if the gate prints STOP.** Do not proceed to Tier 2 with a FAIL in Tier 1.

---

## Tier 2 — Multi-Tool Chains

**Purpose:** Scenarios requiring chaining multiple tools and making conditional decisions.
**Gate:** All four tests must be PASS or WARN before proceeding to Tier 3.
A WARN is acceptable; a FAIL is a hard stop.

---

### T2.1 — Parallel agent execution

**What this tests:** Background agents run independently and all complete even if one errors.

**Pre-condition:** Verify `test-output/` exists (Step S2 above).

**Do this:**
1. Launch three agents in parallel with `run_in_background: true`, `subagent_type: "Explore"`:
   - Agent A task: `"Explore ~/.pi/sessions/ and report: how many session files exist, what is the most recent modification date, and what file extensions are present."`
   - Agent B task: `"Explore ~/.pi/memory/ and report: how many memory files exist and what targets (user, project, memory) are represented."`
   - Agent C task: `"Explore ~/.pi/agent/agents/ and report: how many custom agent definitions exist and list their names."`
2. Save the agent IDs returned as `AGENT_A_ID`, `AGENT_B_ID`, `AGENT_C_ID`.
3. Retrieve results: `get_subagent_result(AGENT_A_ID)`, then B, then C.
4. Verify: all three returned results; results are coherent and cover different directories.

**Efficiency ceiling:** ≤ 6 tool calls per sub-agent (18 total across all three).

**You should see:** Three separate result sets with non-overlapping content.

**If one agent errors:** Check that the other two still completed independently.
Record the erroring agent's task in `notes` and mark WARN (not FAIL) if 2/3 completed.
Record FAIL only if all three failed.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T2.1","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"agents completed: <A|B|C>/<3>; any errors: <describe>","tools_used":["Agent","get_subagent_result"],"tool_call_count":6}
```

---

### T2.2 — Fetch, index, and search pipeline

**What this tests:** The full context-mode fetch-index-search lifecycle works end to end.

**Pre-condition:** Record current `ctx_stats` row count before this test.

**Do this:**
1. Choose a stable public URL with known text content. Use this one:
   `https://raw.githubusercontent.com/nicholasgasior/gsfmt/master/README.md`
   (A short, stable README. Substitute any other stable raw text URL if this is unavailable.)
2. `mcp({ tool: "context_mode_ctx_fetch_and_index", args: '{"url": "<URL>", "source": "T2.2-test"}' })`
3. `mcp({ tool: "context_mode_ctx_search", args: '{"queries": ["T2.2-test"]}' })`
   Confirm the newly indexed content appears in results.
4. `mcp({ tool: "context_mode_ctx_stats" })`
   Confirm row count increased by at least 1 compared to your pre-test baseline.

**Teardown (run this after recording the result):**
If the index was clean before this test, run `mcp({ tool: "context_mode_ctx_purge", args: '{"confirm": true, "scope": "project"}' })` to restore the baseline.
If the index had content before this test, leave it — do not purge content you did not add.

**Fallback:** If `ctx_fetch_and_index` fails, test the manual path:
`fetch_content(url)` → extract text → `mcp({ tool: "context_mode_ctx_index", args: '{"content": "<text>", "source": "T2.2-manual"}' })`.
Record which path succeeded in `notes`.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T2.2","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"rows_before=<N>; rows_after=<N>; path=fetch_and_index|manual_fallback; purged=<yes|no>","tools_used":["mcp"],"tool_call_count":4}
```

---

### T2.3 — Multi-source research chain

**What this tests:** `web_search`, `code_search`, and `fetch_content` chain correctly,
and contradictions are acknowledged rather than silently dropped.

**Do this:**
1. `web_search({ queries: ["Rust edition 2024 migration breaking changes"] })`
2. `code_search({ query: "Rust 2024 edition migration" })`
3. `fetch_content({ url: "<most authoritative URL from step 1>" })`
4. Synthesize: write a 3–5 sentence answer that cites at least one source per claim.
   Explicitly call out any contradiction between the search results and the fetched content.
   If no contradiction exists, state that explicitly — do not omit the check.

**Efficiency ceiling:** ≤ 8 total tool calls.

**You should see:** Non-empty results from all three tools; a synthesis that names its sources.

**If any tool returns empty results:** Note which one and mark WARN. Do not re-try more
than once — if a retry also returns empty, accept it and move on.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T2.3","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"contradictions found: <yes/no/what>; empty tools: <none or list>","tools_used":["web_search","code_search","fetch_content"],"tool_call_count":<N>}
```

---

### T2.4 — Memory CRUD lifecycle

**What this tests:** The full add → search → update → remove memory lifecycle is consistent.

**Do this — in this exact order, verifying each step before the next:**

1. Add:
   `memory({ action: "add", target: "memory", content: "TEST_ENTRY_T2.4: canary value" })`
2. Verify add:
   `memory_search({ query: "TEST_ENTRY_T2.4" })` — confirm the entry appears.
   **If it does not appear:** Record FAIL immediately. Do not continue.
3. Update:
   `memory({ action: "replace", target: "memory", old_text: "TEST_ENTRY_T2.4: canary value", content: "TEST_ENTRY_T2.4: updated canary value" })`
4. Verify update:
   `memory_search({ query: "TEST_ENTRY_T2.4" })` — confirm the updated value is returned.
5. Remove:
   `memory({ action: "remove", target: "memory", old_text: "TEST_ENTRY_T2.4: updated canary value" })`
6. Verify removal:
   `memory_search({ query: "TEST_ENTRY_T2.4" })` — confirm no results are returned.
   **If the entry still appears:** Try the remove step again. If it persists after a second attempt, record FAIL and manually remove before proceeding.

**Teardown note:** Steps 5–6 ARE the teardown. If this test fails before step 5,
manually remove the canary entry before running any subsequent test.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T2.4","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"failed at step: <N or none>; canary removed: <yes|no>","tools_used":["memory","memory_search"],"tool_call_count":6}
```

---

### ✋ TIER 2 GATE

```bash
python3 -c "
import json
rows = [json.loads(l) for l in open('test-results.jsonl') if l.strip()]
t2 = [r for r in rows if r.get('id','').startswith('T2.')]
fails = [r['id'] for r in t2 if r['status'] == 'FAIL']
warns = [r['id'] for r in t2 if r['status'] == 'WARN']
print('T2 results:', [(r['id'], r['status']) for r in t2])
print('WARNs:', warns if warns else 'none')
print('FAILs:', fails if fails else 'none')
print('GATE:', 'STOP — fix failures before Tier 3' if fails else 'PASS — proceed to Tier 3')
"
```

---

## Tier 3 — Complex Multi-Step Chains

**Purpose:** End-to-end reasoning, tool orchestration, and research with synthesis.
**Gate:** No FAIL results. WARNs are acceptable.

---

### T3.1 — End-to-end research pipeline

**What this tests:** Discovery → parallel gathering → synthesis → claim validation.

**Do this:**
1. **Discovery:** `web_search({ queries: ["<pick a current technical topic with verifiable facts, e.g. a library breaking change or migration guide>"] })`
   Choose a topic where you can verify at least 2 factual claims against independent sources.
2. **Parallel gathering:** Launch 2 background agents (`run_in_background: true`):
   - Agent A (`subagent_type: "Explore"`): `"Find official documentation and release notes for [your chosen topic]."`
   - Agent B (`subagent_type: "web-search-researcher"`): `"Find community opinions, known issues, and workarounds for [your chosen topic]."`
3. **Deep dive:** `fetch_content({ url: "<most authoritative URL from step 1>" })`
4. **Synthesis:** Combine Agent A, Agent B, and fetch_content results into a structured report:
   - Problem statement
   - Sources (with URLs)
   - Contradictions between official docs and community reports — state explicitly if none
   - Recommended action
5. **Validation:** Verify at least 2 factual claims against independent sources.
   State each claim and its corroborating source.

**Efficiency ceiling:** ≤ 15 total tool calls.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T3.1","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"topic: <topic>; sources_cited: <N>; contradictions: <yes/no>; claims_validated: <N>","tools_used":["web_search","Agent","fetch_content"],"tool_call_count":<N>}
```

---

### T3.2 — Codebase analysis and recommendation

**What this tests:** Navigation of a real codebase, integration mapping, and grounded recommendations.

**Target:** Use a real project under `~/dev/` — not `~/.pi/` config files and not this
test directory. Config JSON files do not yield meaningful codebase analysis.

**Do this:**
1. `Agent({ subagent_type: "codebase-locator", prompt: "Find the most complex component or module in [chosen project]." })`
2. `Agent({ subagent_type: "codebase-analyzer", prompt: "Analyze [component found in step 1] in detail." })`
3. `Agent({ subagent_type: "integration-scanner", prompt: "Find all inbound references to [component]." })`
4. `code_search({ query: "best practice pattern for [the functionality of that component]" })`
5. Produce a ranked output:
   - Strengths of current implementation
   - Weaknesses or anti-patterns
   - Recommended improvements with concrete examples

**Efficiency ceiling:** ≤ 12 total tool calls.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T3.2","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"project: <name>; component: <name>; recommendations: <N>","tools_used":["Agent","code_search"],"tool_call_count":<N>}
```

---

### T3.3 — Steer and resume a running agent

**What this tests:** Mid-execution steering changes a running agent's direction; results reflect it.

**Do this:**
1. Launch Agent A (`run_in_background: true`, `subagent_type: "web-search-researcher"`):
   `"Research AI agent evaluation methodologies — what approaches exist for measuring agent quality?"`
2. Launch Agent B (`run_in_background: true`, `subagent_type: "web-search-researcher"`):
   `"You will receive a research summary shortly. Identify the gaps and missing areas in it."`
3. **After 2–3 turns** (poll Agent A with `get_subagent_result` to see if it is still running),
   steer Agent A:
   `steer_subagent(AGENT_A_ID, "Focus specifically on open-source evaluation frameworks that have public GitHub repositories.")`
4. Wait for both agents to complete. Retrieve final results from both.
5. Verify: Agent A's final output addresses open-source frameworks with GitHub links.
   If it does not, note this as a race condition (A finished before the steer arrived) in `notes`.
6. Synthesize Agent A + Agent B into a comparison of evaluation approaches and their gaps.

**Edge case:** If Agent A finishes before you can steer it, record the race condition in
`notes` and mark WARN. Re-run with a broader initial task if you want to confirm steering works.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T3.3","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"steer delivered: <yes|no|race-condition>; A reflected steer: <yes|no>","tools_used":["Agent","steer_subagent","get_subagent_result"],"tool_call_count":<N>}
```

---

### T3.4 — Research, document, and validate with feedback loop

**What this tests:** Full research lifecycle with explicit documentation and self-validation.

**Pre-condition:** Verify `test-output/` exists.

**Do this:**
1. Define a research question. Use: `"What are the trade-offs between the major open-source LLM evaluation frameworks?"`
2. Run a structured research plan using `web_search`, `code_search`, `fetch_content`, and
   at least one background `Agent` for parallel source fetching.
3. Write findings to `test-output/T3.4-findings.md` using the `write` tool.
   The document must include: introduction, findings per framework, sources section.
4. `read("test-output/T3.4-findings.md")` — identify 2–3 gaps or unsupported claims.
   State what they are before proceeding.
5. Run a targeted `web_search` or `Agent` call to address each identified gap.
6. Append a `## Validation` section to the document confirming each major claim has a source.
   Use `edit` to append — do not rewrite the whole file.

**Teardown:** `test-output/T3.4-findings.md` is intentional output — do not delete.

**Efficiency ceiling:** ≤ 20 total tool calls.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T3.4","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"gaps_found: <N>; gaps_resolved: <N>; validation_section_added: <yes|no>","tools_used":["web_search","Agent","write","read","edit"],"tool_call_count":<N>}
```

---

### ✋ TIER 3 GATE

```bash
python3 -c "
import json
rows = [json.loads(l) for l in open('test-results.jsonl') if l.strip()]
t3 = [r for r in rows if r.get('id','').startswith('T3.')]
fails = [r['id'] for r in t3 if r['status'] == 'FAIL']
print('T3 results:', [(r['id'], r['status']) for r in t3])
print('FAILs:', fails if fails else 'none')
print('GATE:', 'STOP' if fails else 'PASS — proceed to Tier 4 (or Baseline Capture)')
"
```

---

## Baseline Capture (Required Before Tier 4)

**Purpose:** Tier 4 compares against a known-good run. You must capture a baseline first.

**Pre-condition:** Tiers 1–3 must all show PASS or WARN in `test-results.jsonl`.

**Do this:**
1. Read all T1.x result rows from `test-results.jsonl`.
2. For each T1 test, record the sequence of tools used and the argument structure
   (not the exact values — the structure and order).
3. Write this to `test-output/golden-baseline.json`:

```json
{
  "captured_run_id": "<RUN_ID>",
  "captured_at": "<UTC timestamp>",
  "model": "<MODEL>",
  "t1_tool_sequences": {
    "T1.1": ["mcp:connect", "mcp:tool:ctx_doctor"],
    "T1.2": ["mcp:server", "mcp:describe", "mcp:describe"],
    "T1.3": ["mcp:tool:ctx_search", "mcp:tool:ctx_search", "mcp:tool:ctx_search"],
    "T1.4": ["bash:ls", "read:models.json"]
  }
}
```

Adjust the sequences to reflect what you actually did. Use the `write` tool.

**Verify:**
```bash
python3 -c "import json; print(json.load(open('test-output/golden-baseline.json')))"
```
You should see the parsed dict without errors.

---

## Tier 4 — Regression Check

**Purpose:** Verify that tool paths are stable across runs.
**Pre-condition:** `test-output/golden-baseline.json` must exist (Baseline Capture above).

---

### T4.1 — Deterministic tool path check

**Do this:**
1. Re-run T1.1 through T1.4.
2. For each test, note the tool names and argument structure used.
3. Compare against `test-output/golden-baseline.json`.
4. Record any deviations: different tool, different order, extra calls.

**What counts as a deviation:**
- Different tool chosen for the same step → FAIL
- Different argument structure → FAIL
- Extra intermediate tool call → WARN
- Different argument *values* (e.g. slightly different search phrase) → acceptable, not a deviation

**Record one row per T1 test re-run, plus a summary:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T4.1","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"deviations: <none | list what changed>","tool_call_count":<N>}
```

---

## Tier 5 — Adversarial and Error Recovery

**Purpose:** Verify the agent handles invalid inputs and broken tool outputs without crashing
or continuing silently as if nothing went wrong.

---

### T5.1 — Invalid tool argument

**What this tests:** The agent correctly identifies an error and does not hang or silently proceed.

**Do this:**
1. `mcp({ server: "non-existent-server" })`
2. Observe the response.

**You should see:** An error response describing the failure. The correct outcome here IS
an error. Receiving a clear error message = PASS. No error = FAIL. Hang = FAIL.

**Do not:** Re-try this call. One attempt is sufficient.

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T5.1","model":"<MODEL>","status":"PASS|FAIL","timestamp":"<UTC>","notes":"error received: <yes|no>; hung: <yes|no>; error message: <first 100 chars>","tool_call_count":1}
```

---

### T5.2 — Empty result handling

**What this tests:** The agent recognises empty results and does not loop, hallucinate, or break.

**Do this:**
1. `web_search({ queries: ["xq7z9f2k-deliberately-nonexistent-term-8b3j1p"] })`
2. Observe: does the response acknowledge empty results? Does it attempt a pivot?

**You should see:** Acknowledgement of empty results within ≤ 2 attempts. No fabricated results.

**Failure conditions:**
- Agent invents results that do not exist → FAIL
- Agent retries more than 2 times → FAIL
- Agent crashes or hangs → FAIL
- Agent acknowledges empty and pivots or concludes cleanly → PASS

**Record:**
```json
{"run_id":"<RUN_ID>","phase":"agentic","id":"T5.2","model":"<MODEL>","status":"...","timestamp":"<UTC>","notes":"fabricated: <yes|no>; retries: <N>; graceful conclusion: <yes|no>","tool_call_count":<N>}
```

---

## Efficiency Audit

Run this after completing all tiers. It does not produce new result rows — it reviews
what is already in `test-results.jsonl`.

```bash
python3 -c "
import json
rows = [json.loads(l) for l in open('test-results.jsonl') if l.strip()]
agentic = [r for r in rows if r.get('phase') == 'agentic']
ceilings = {'T2.1': 18, 'T2.3': 8, 'T3.1': 15, 'T3.2': 12, 'T3.3': 20, 'T3.4': 20}
print('--- Tool call audit ---')
for r in agentic:
    tid = r.get('id','')
    count = r.get('tool_call_count', 0)
    ceiling = ceilings.get(tid)
    if ceiling:
        flag = 'OK' if count <= ceiling else 'OVER'
        print(f'  {tid}: {count}/{ceiling} {flag}')
print()
print('--- Status summary ---')
for status in ['PASS','WARN','FAIL','SKIP']:
    ids = [r[\"id\"] for r in agentic if r.get(\"status\") == status]
    if ids: print(f'  {status}: {ids}')
"
```

---

## Scoring Reference

| Criterion | PASS | WARN | FAIL |
|:---|:---|:---|:---|
| Tool execution | Zero errors, expected output | Minor format issues | Unexpected error / crash |
| Result accuracy | Matches ground truth | Minor discrepancies | Major inaccuracies |
| Reasoning quality | Logical, cites sources | Mostly logical | Gaps or hallucinations |
| Tool chaining | All tools correct | 1 minor misstep | Broken chain |
| End-to-end flow | Efficient, no backtracking | Minor detour | Loops or wasted calls |
| Efficiency | Within ceiling | ≤ 20% over ceiling | > 20% over ceiling |
| Adversarial recovery | Graceful pivot | Slow/clunky | Crash / hang / silent failure |
| Context retention | Recalls step-1 facts at step 5+ | Minor imprecision | Contradicts earlier facts |

---

## Tier 6 — Model Comparison (Placeholder)

To compare two models on the same agentic tasks:
1. Run this full plan once per model via `run_eval.py --model <model> --run-id <label>`.
2. Each run produces its own rows in `test-results.jsonl` tagged by `run_id` and `model`.
3. Compare PASS/WARN/FAIL counts and tool_call_counts across run_ids for the same test IDs.

For a focused comparison, re-run T3.1 and T3.4 under each model — they are the primary
reasoning stress tests.
