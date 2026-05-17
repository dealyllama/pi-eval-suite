#!/usr/bin/env python3
"""
Smoke test suite for Ollama models.
Tests: (1) tool call, (2) thinking tags, (3) multi-turn coherence.
Usage: python3 smoke_test.py <model_name>
       python3 smoke_test.py --all
"""

import sys
import json
import os
import requests
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent

import os
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/v1").rstrip("/")

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the internet for current information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results", "default": 5}
            },
            "required": ["query"]
        }
    }
}

MODELS_TO_TEST = [
    "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL",
    "hf.co/unsloth/gemma-4-31B-it-GGUF:UD-Q3_K_XL",
    "devstral-small-2:24b",
    "qwen2.5:14b",
    "mistral-small3.2:latest",
    "gemma4:26b",
    "gemma4:31b",
    "gemma4-turbo-26b-fixed:latest",
    "gemma4-26b-abliterated:latest",
    "gemma4-e4b-abliterated:latest",
    "llama3.1:8b",
]

def chat(model, messages, tools=None, options=None):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options or {"temperature": 0.1, "num_predict": 1024}
    }
    if tools:
        payload["tools"] = tools
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def test_tool_call(model):
    """Test 1: Does the model emit a valid tool call?"""
    messages = [
        {"role": "user", "content": "Search for the latest news about RTX 5080 performance benchmarks."}
    ]
    result = chat(model, messages, tools=[TOOL_DEF])
    if "error" in result:
        return False, f"Request failed: {result['error']}"
    
    msg = result.get("message", {})
    tool_calls = msg.get("tool_calls", [])
    
    if tool_calls:
        tc = tool_calls[0]
        fn = tc.get("function", {})
        if fn.get("name") == "web_search":
            args = fn.get("arguments", {})
            if "query" in args:
                return True, f"✅ Valid tool call: web_search(query={args['query']!r})"
            return False, f"⚠️  Tool called but missing 'query' arg: {fn}"
        return False, f"⚠️  Wrong tool called: {fn.get('name')}"
    
    # Check if raw content contains tool call syntax (some models don't use Ollama's native format)
    content = msg.get("content", "")
    if "web_search" in content or "tool_call" in content.lower() or "<function" in content:
        return None, f"⚠️  Tool call in raw text (not structured): {content[:200]}"
    
    return False, f"❌ No tool call emitted. Response: {content[:200]}"

def test_thinking(model):
    """Test 2: Does the model use/strip thinking tags?"""
    messages = [
        {"role": "user", "content": "What is 17 * 23? Show your reasoning step by step."}
    ]
    result = chat(model, messages, options={"temperature": 0.6, "num_predict": 2048})
    if "error" in result:
        return None, f"Request failed: {result['error']}"
    
    msg = result.get("message", {})
    content = msg.get("content", "")
    thinking = msg.get("thinking", "")
    
    has_think_in_content = "<think>" in content or "</think>" in content
    has_thinking_field = bool(thinking)
    answer_has_391 = "391" in content  # 17*23=391
    
    if has_think_in_content:
        return False, f"❌ Thinking tags leaking into response content"
    elif has_thinking_field:
        return True, f"✅ Thinking separated correctly (thinking field present). Answer correct: {answer_has_391}"
    elif answer_has_391:
        return True, f"✅ No thinking (model may not support it). Answer correct: 391"
    else:
        return None, f"⚠️  No thinking + wrong/unclear answer. Content: {content[:200]}"

def test_multiturn(model):
    """Test 3: Multi-turn context coherence."""
    messages = [
        {"role": "user", "content": "My name is Alex and I'm testing you for agentic workflows."},
        {"role": "assistant", "content": "Hi Alex! I'm ready to help with agentic workflows. What would you like to test?"},
        {"role": "user", "content": "What is my name and what are we testing?"}
    ]
    result = chat(model, messages)
    if "error" in result:
        return False, f"Request failed: {result['error']}"
    
    content = result.get("message", {}).get("content", "")
    has_name = "alex" in content.lower()
    has_context = "agentic" in content.lower() or "workflow" in content.lower() or "test" in content.lower()
    
    if has_name and has_context:
        return True, f"✅ Context retained: name + topic. Response: {content[:150]}"
    elif has_name:
        return None, f"⚠️  Name retained but lost workflow context. Response: {content[:150]}"
    else:
        return False, f"❌ Context lost. Response: {content[:150]}"

def run_tests(model):
    print(f"\n{'='*60}")
    print(f"Testing: {model}")
    print(f"{'='*60}")
    
    results = {}
    
    print("\n[1/3] Tool call test...")
    ok, msg = test_tool_call(model)
    results["tool_call"] = {"pass": ok, "note": msg}
    print(f"  {msg}")
    
    print("\n[2/3] Thinking test...")
    ok, msg = test_thinking(model)
    results["thinking"] = {"pass": ok, "note": msg}
    print(f"  {msg}")
    
    print("\n[3/3] Multi-turn test...")
    ok, msg = test_multiturn(model)
    results["multiturn"] = {"pass": ok, "note": msg}
    print(f"  {msg}")
    
    passed = sum(1 for r in results.values() if r["pass"] is True)
    warned = sum(1 for r in results.values() if r["pass"] is None)
    failed = sum(1 for r in results.values() if r["pass"] is False)
    
    print(f"\nSummary: {passed}/3 pass, {warned} warn, {failed} fail")
    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 smoke_test.py <model_name>")
        print("       python3 smoke_test.py --all")
        sys.exit(1)
    
    if sys.argv[1] == "--all":
        models = MODELS_TO_TEST
    else:
        models = [sys.argv[1]]
    
    all_results = {}
    for model in models:
        all_results[model] = run_tests(model)
    
    # Print summary table
    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Model':<45} {'Tool':<8} {'Think':<8} {'Multi':<8}")
    print("-"*70)
    for model, results in all_results.items():
        def symbol(r):
            v = r.get("pass")
            return "✅" if v is True else ("⚠️ " if v is None else "❌")
        short_name = model.split("/")[-1][:42]
        print(f"{short_name:<45} {symbol(results.get('tool_call', {})):<8} {symbol(results.get('thinking', {})):<8} {symbol(results.get('multiturn', {})):<8}")
    
    # Save results
    output_file = HERE / f"smoke_test_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(output_file, "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "results": all_results}, f, indent=2)
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
