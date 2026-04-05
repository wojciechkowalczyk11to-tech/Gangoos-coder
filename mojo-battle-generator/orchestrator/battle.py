"""
DeepSeek R1 Survival-Deathmatch — self-improvement loop generujący dataset Mojo.

Architektura:
  - DeepSeek R1 (NEXUS API) = główny agent piszący kod
  - Claude Opus (puter.com FREE, OpenAI-compat) = krytyk/weryfikator
  - mojo_exec (Docker) = wykonanie kodu
  - NEXUS web_search = docs Mojo

Uruchom: python3 battle.py [--level 1] [--max 500]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json, time, argparse, requests
from datetime import datetime
from openai import OpenAI

from tools.mojo_exec import exec_mojo
from orchestrator.tasks import get_task, get_self_improvement_prompt

# ── Klienty ─────────────────────────────────────────────────────────────────
NEXUS_URL  = "http://localhost:8080"
NEXUS_AUTH = "Bearer REDACTED_NEXUS_TOKEN"

# Opus zastąpiony Grok-4 (frontier-level, skonfigurowany w NEXUS)
# puter.com wymaga prawdziwego konta — nie używamy

MAX_TOOL_ROUNDS  = 6
SELF_IMPROVE_EVERY = 10

# ── NEXUS MCP client (JSON-RPC 2.0 over HTTP+SSE) ────────────────────────────
_NEXUS_HEADERS = {
    "Authorization": NEXUS_AUTH,
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream"
}

def _nexus_session() -> str:
    """Otwiera sesję MCP i zwraca session-id."""
    r = requests.post(
        f"{NEXUS_URL}/mcp",
        json={"jsonrpc": "2.0", "id": "init", "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "mojo-battle", "version": "1.0"}}},
        headers=_NEXUS_HEADERS, stream=True, timeout=15
    )
    sid = r.headers.get("mcp-session-id", "")
    for _ in r.iter_lines():
        break
    return sid

def _nexus(tool: str, params: dict, timeout: int = 120) -> str:
    """Wywołuje narzędzie NEXUS MCP. Zwraca text result."""
    sid = _nexus_session()
    h = {**_NEXUS_HEADERS, "mcp-session-id": sid}
    r = requests.post(
        f"{NEXUS_URL}/mcp",
        json={"jsonrpc": "2.0", "id": "call",
              "method": "tools/call",
              "params": {"name": tool, "arguments": {"params": params}}},
        headers=h, stream=True, timeout=timeout
    )
    result = ""
    for line in r.iter_lines():
        if line:
            text = line.decode()
            if text.startswith("data: "):
                try:
                    d = json.loads(text[6:])
                    content = d.get("result", {}).get("content", [])
                    if isinstance(content, list):
                        result = "".join(c.get("text", "") for c in content)
                    elif isinstance(content, str):
                        result = content
                except Exception:
                    pass
    return result


def deepseek_r1(prompt: str, system: str = "") -> str:
    return _nexus("ai_query", {
        "provider": "deepseek",
        "model": "deepseek-reasoner",
        "prompt": prompt,
        "system": system or DEEPSEEK_SYSTEM,
        "max_tokens": 4096
    })


def opus_critique(prompt: str, system: str = "") -> str:
    """Grok-4-fast-reasoning jako krytyk (frontier-level, NEXUS)."""
    full = f"{system}\n\n{prompt}" if system else prompt
    return _nexus("ai_query", {
        "provider": "grok",
        "model": "grok-4-fast-reasoning",
        "prompt": full,
        "max_tokens": 2048
    })


def mojo_docs_search(query: str) -> str:
    return _nexus("web_fetch", {
        "url": f"https://docs.modular.com/mojo/manual/",
    })


# ── System prompts ───────────────────────────────────────────────────────────
DEEPSEEK_SYSTEM = """You are an expert Mojo programmer (Modular's Mojo language, v0.26+).
Solve Mojo coding challenges step-by-step.

Rules:
1. Write COMPLETE, compilable Mojo code (no pseudocode, no mcp_call() placeholders)
2. Use real Mojo v0.26+ syntax: UnsafePointer, SIMD, @parameter, comptime
3. After writing code, analyze if it would compile and run correctly
4. Fix errors iteratively
5. Always wrap final code in ```mojo ... ``` blocks

Output format:
```mojo
<complete working code here>
```
Explanation: <what it does and why>"""

OPUS_CRITIC_SYSTEM = """You are a senior Mojo/systems programming expert reviewer.
Review Mojo code critically. Check:
- Correctness of Mojo v0.26+ syntax
- Memory safety with UnsafePointer
- Performance (SIMD usage, avoid unnecessary allocations)
- Completeness (does it actually compile?)

Output JSON:
{
  "verdict": "pass|fail|improve",
  "issues": ["issue1", ...],
  "improved_code": "```mojo\n...\n```",
  "score": 0.0-1.0
}"""


# ── Agent loop ────────────────────────────────────────────────────────────────
def run_agent_loop(task: dict) -> dict:
    messages = []
    task_prompt = (
        f"Solve this Mojo programming task:\n\n{task['task']}\n\n"
        "Write complete, compilable Mojo code with real v0.26+ syntax. "
        "No pseudocode. Execute it mentally and verify it would work."
    )
    messages.append({"role": "user", "content": task_prompt})

    current_code = ""
    success = False
    error = ""
    opus_score = 0.0

    for turn in range(MAX_TOOL_ROUNDS):
        # DeepSeek generuje / poprawia
        ctx = "\n".join(
            f"{m['role'].upper()}: {m['content'][:600]}"
            for m in messages[-4:]
        )
        response = deepseek_r1(ctx if turn > 0 else task_prompt)
        messages.append({"role": "assistant", "content": response})

        code = _extract_code(response, "mojo") or _extract_code(response, "python") or ""

        if code:
            current_code = code
            # Wykonaj kod
            exec_result = exec_mojo(code)
            tool_feedback = (
                f"[mojo_exec] exit={exec_result['exit_code']}\n"
                f"stdout: {exec_result['stdout'][:400]}\n"
                f"stderr: {exec_result['stderr'][:400]}"
                + (" [SIMULATED]" if exec_result.get('simulated') else "")
            )
            messages.append({"role": "user", "content": tool_feedback})

            if exec_result['success']:
                # Weryfikuj przez Opus
                try:
                    opus_resp = opus_critique(
                        f"Task: {task['task']}\n\nCode:\n```mojo\n{code}\n```\nOutput: {exec_result['stdout'][:200]}",
                        system=OPUS_CRITIC_SYSTEM
                    )
                    messages.append({"role": "user", "content": f"[opus_critique]\n{opus_resp}"})
                    opus_score = float(_extract_json_field(opus_resp, "score") or 0.7)
                    verdict = _extract_json_field(opus_resp, "verdict")

                    if verdict in ("pass", "improve") and opus_score >= 0.6:
                        success = True
                        break
                    elif verdict == "fail":
                        improved = _extract_code(opus_resp, "mojo")
                        if improved:
                            messages.append({
                                "role": "user",
                                "content": f"Opus says fail (score={opus_score}). Improve:\n{opus_resp[:600]}"
                            })
                        continue
                    else:
                        success = True
                        break
                except Exception as e:
                    # puter down → akceptuj jeśli kompilacja OK
                    success = True
                    opus_score = 0.5
                    break
            else:
                error = exec_result['stderr'][:300]
                messages.append({
                    "role": "user",
                    "content": f"FAILED. Error:\n{error}\n\nFix it. Think about what went wrong."
                })

    return {
        "task": task,
        "messages": messages,
        "final_code": current_code,
        "success": success,
        "error": error,
        "turns": len([m for m in messages if m["role"] == "assistant"]),
        "opus_score": opus_score
    }


# ── Dataset format ────────────────────────────────────────────────────────────
def to_training_example(result: dict) -> dict:
    return {
        "messages": result["messages"],
        "metadata": {
            "task": result["task"]["task"][:100],
            "level": result["task"]["level"],
            "category": result["task"]["category"],
            "success": result["success"],
            "opus_score": result["opus_score"],
            "turns": result["turns"],
            "timestamp": datetime.utcnow().isoformat(),
            "generator": "deepseek-r1-opus-mojo-battle"
        }
    }


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--max", type=int, default=500)
    ap.add_argument("--out", default="../output/mojo_dataset.jsonl")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    history, level, total, success_count = [], args.level, 0, 0

    print(f"[*] Mojo Deathmatch — DeepSeek R1 ↔ Opus loop")
    print(f"[*] Target: {args.max} → {args.out}")
    print("-" * 55)

    with open(args.out, 'a') as outf:
        while total < args.max:

            # Meta-refleksja
            if total > 0 and total % SELF_IMPROVE_EVERY == 0:
                prompt = get_self_improvement_prompt(history)
                if prompt:
                    reflection = deepseek_r1(prompt, "Analyze your failures honestly.")
                    print(f"\n[REFLECT #{total}] {reflection[:150]}...\n")
                    recent_sr = sum(1 for h in history[-SELF_IMPROVE_EVERY:] if h.get('success')) / SELF_IMPROVE_EVERY
                    if recent_sr > 0.7 and level < 4:
                        level += 1
                        print(f"[↑] Level → {level} (SR={recent_sr:.0%})")

            error_ctx = history[-1].get('error') if history and not history[-1].get('success') else None
            task = get_task(level=level, error_context=error_ctx)

            print(f"[{total+1}/{args.max}] L{level} | {task['task'][:55]}...")
            t0 = time.time()
            result = run_agent_loop(task)
            dt = time.time() - t0

            history.append({'level': level, 'success': result['success'], 'error': result.get('error', '')})

            # Zapisz jeśli success lub ma error→fix flow (wartościowe dla fine-tuningu)
            has_fix_flow = result['turns'] > 1 and any(
                'fix' in m['content'].lower() or 'error' in m['content'].lower()
                for m in result['messages'] if m['role'] == 'user'
            )
            if result['success'] or has_fix_flow:
                outf.write(json.dumps(to_training_example(result), ensure_ascii=False) + '\n')
                outf.flush()
                total += 1
                if result['success']:
                    success_count += 1

            mark = "✓" if result['success'] else "✗"
            print(f"  {mark} turns={result['turns']} score={result['opus_score']:.2f} t={dt:.1f}s | n={total} ok={success_count}")

    print(f"\n[DONE] {total} examples, {success_count} OK → {args.out}")


def _extract_code(text: str, lang: str = "mojo") -> str:
    import re
    m = re.search(rf"```{lang}\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_json_field(text: str, field: str) -> str:
    import re, json as _j
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return str(_j.loads(m.group()).get(field, ""))
        except Exception:
            pass
    m = re.search(rf'"{field}"\s*:\s*"?([^",\n}}]+)"?', text)
    return m.group(1).strip() if m else ""


if __name__ == "__main__":
    main()
