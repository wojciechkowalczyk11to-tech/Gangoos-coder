#!/usr/bin/env python3
"""
CodeAct Agent — NEXUS Orchestration Engine
Claude = Brain (orchestrator)
This script = execution layer (cheap models do actual work)

Usage:
  python3 codeact_agent.py --task "napisz funkcję sortowania" --model deepseek
  python3 codeact_agent.py --task "znajdź bug w tym kodzie" --model codestral
  python3 codeact_agent.py --task "..." --json --model auto
  python3 codeact_agent.py --list-models
  echo '{"task":"...", "model":"deepseek"}' | python3 codeact_agent.py
"""

import sys
import json
import subprocess
import urllib.request
import urllib.error
import argparse
import os
import re
from datetime import datetime

# ─── API CONFIG ───────────────────────────────────────────────────────────────
# Wstaw swoje klucze tutaj lub ustaw jako zmienne środowiskowe
API_KEYS = {
    "deepseek": os.getenv("DEEPSEEK_API_KEY", ""),
    "mistral":  os.getenv("MISTRAL_API_KEY", ""),
    "openai":   os.getenv("OPENAI_API_KEY", ""),
    "xai":      os.getenv("XAI_API_KEY", ""),
    "codestral": os.getenv("MISTRAL_API_KEY", ""),  # Codestral uses Mistral API key
    "gemini": os.getenv("GOOGLE_API_KEY", ""),
    "groq": os.getenv("GROQ_API_KEY", ""),
}

# ─── MODEL ENDPOINTS (wszystkie OpenAI-compatible) ────────────────────────────
MODELS = {
    "deepseek": {
        "url":   "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "key":   API_KEYS["deepseek"],
        "cost":  "$0.14/1M",
        "best_for": ["code", "refactor", "debug", "boilerplate"],
    },
    "mistral": {
        "url":   "https://api.mistral.ai/v1/chat/completions",
        "model": "devstral-small-2505",
        "key":   API_KEYS["mistral"],
        "cost":  "FREE (promo)",
        "best_for": ["github", "pr", "review", "bug"],
    },
    "codestral": {
        "url":   "https://api.mistral.ai/v1/chat/completions",
        "model": "codestral-latest",
        "key":   API_KEYS["codestral"],
        "cost":  "$0.20/1M",
        "best_for": ["code", "completion", "refactor"],
    },
    "grok": {
        "url":   "https://api.x.ai/v1/chat/completions",
        "model": "grok-3-fast",
        "key":   API_KEYS["xai"],
        "cost":  "$0.30/1M",
        "best_for": ["research", "web", "long_context"],
    },
    "gemini": {
        "url":   "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.5-flash-preview-04-17",
        "key":   API_KEYS["gemini"],
        "cost":  "$0.075/1M",
        "best_for": ["reasoning", "multimodal", "long_context"],
    },
    "groq": {
        "url":   "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "key":   API_KEYS["groq"],
        "cost":  "$0.59/1M (ultra-fast)",
        "best_for": ["general", "inference", "fast"],
    },
    "openai": {
        "url":   "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "key":   API_KEYS["openai"],
        "cost":  "$0.15/1M",
        "best_for": ["json", "structured"],
    },
    "ollama": {
        "url":   os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/v1/chat/completions",
        "model": "deepseek-r1:8b",
        "key":   "local",
        "cost":  "FREE (local)",
        "best_for": ["free", "local", "reasoning"],
    },
}

# ─── SYSTEM PROMPT dla CodeAct ────────────────────────────────────────────────
CODEACT_SYSTEM = """Jesteś CodeAct agentem. Rozwiązujesz zadania przez iteracyjne generowanie i wykonywanie kodu.

FORMAT ODPOWIEDZI:
1. Krótka analiza (1-2 zdania)
2. Kod w bloku ```python ... ``` jeśli potrzebny
3. Po wykonaniu kodu — interpretacja wyniku i kolejny krok lub DONE

ZASADY:
- Generuj wykonalny Python
- Jeden krok na raz
- Jeśli kod wyrzuci błąd — popraw i spróbuj ponownie
- Oznacz koniec: TASK_COMPLETE: [wynik]
"""

# ─── JSON CONVERSION PROMPT ───────────────────────────────────────────────────
JSON_CONVERT_SYSTEM = """Jesteś konwerterem tekstu na JSON dla systemu orkiestracyjnego.
Zadanie: Wczytaj surowy tekst/raport i skonwertuj na strukturalny JSON.

FORMAT WYJŚCIA:
{
  "status": "success|error",
  "summary": "krótkie podsumowanie",
  "key_results": [...],
  "metrics": {...},
  "timestamp": "ISO timestamp"
}

ZASADY:
- Wyciąg metryki i wyniki
- Strukturyzuj hierarchicznie
- Pomiń szum, zachowaj treść
- Zawsze valid JSON"""

# ─── HTTP CALL ────────────────────────────────────────────────────────────────
def call_model(model_cfg: dict, messages: list, max_tokens: int = 1500) -> str:
    payload = json.dumps({
        "model":      model_cfg["model"],
        "messages":   messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }).encode()

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {model_cfg['key']}" if model_cfg['key'] != "local" else {},
    }

    # Remove Authorization header for local models
    if model_cfg['key'] == "local":
        del headers["Authorization"]

    req = urllib.request.Request(
        model_cfg["url"], data=payload, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        raise RuntimeError(f"API {e.code}: {body}")

# ─── EXTRACT & EXECUTE CODE ───────────────────────────────────────────────────
def extract_code(text: str) -> str | None:
    """Wyciąga kod Python z odpowiedzi modelu."""
    match = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: szukaj exec bloków
    match = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    if match:
        code = match.group(1).strip()
        if any(kw in code for kw in ["import", "def ", "for ", "print("]):
            return code
    return None

def run_code(code: str, timeout: int = 30) -> tuple[str, bool]:
    """Wykonuje kod Python, zwraca (output, success)."""
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        return output[:2000] if output else "(brak outputu)", success
    except subprocess.TimeoutExpired:
        return f"TIMEOUT po {timeout}s", False
    except Exception as e:
        return f"EXEC ERROR: {e}", False

# ─── JSON CONVERSION ──────────────────────────────────────────────────────────
def json_convert(raw_text: str, use_model: str = "groq") -> dict:
    """Konwertuje surowy tekst na strukturalny JSON dla orkiestratora."""
    if use_model not in MODELS:
        use_model = "groq"

    model_cfg = MODELS[use_model]
    if not model_cfg["key"]:
        model_cfg = MODELS["openai"]  # Fallback

    messages = [
        {"role": "system", "content": JSON_CONVERT_SYSTEM},
        {"role": "user", "content": f"Tekst do konwersji:\n\n{raw_text}"},
    ]

    try:
        response = call_model(model_cfg, messages, max_tokens=2000)
        # Wyciągnij JSON z odpowiedzi
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return {"error": "Nie udało się wyciągnąć JSON", "raw": response}
    except Exception as e:
        return {"error": str(e)}

# ─── MAIN CODEACT LOOP ────────────────────────────────────────────────────────
def codeact_loop(task: str, model_name: str, max_iterations: int = 8, as_json: bool = False) -> dict:
    if model_name not in MODELS:
        return {"error": f"Nieznany model: {model_name}. Dostępne: {list(MODELS)}"}

    model_cfg = MODELS[model_name]
    if not model_cfg["key"] and model_name != "ollama":
        return {"error": f"Brak klucza API dla {model_name}. Ustaw {model_name.upper()}_API_KEY"}

    print(f"\n🎯 TASK: {task}")
    print(f"🤖 MODEL: {model_name} ({model_cfg['model']}) — {model_cfg['cost']}")
    if as_json:
        print(f"📊 OUTPUT: JSON mode")
    print("─" * 60)

    messages = [
        {"role": "system",  "content": CODEACT_SYSTEM},
        {"role": "user",    "content": f"ZADANIE: {task}"},
    ]

    history = []
    for i in range(max_iterations):
        print(f"\n[Iteracja {i+1}/{max_iterations}]")

        # 1. Wywołaj model
        try:
            response = call_model(model_cfg, messages)
        except RuntimeError as e:
            print(f"❌ API Error: {e}")
            return {"error": str(e), "history": history}

        print(f"🤖 {model_name}: {response[:300]}...")

        # 2. Sprawdź czy zadanie zakończone
        if "TASK_COMPLETE:" in response:
            result = response.split("TASK_COMPLETE:")[-1].strip()
            print(f"\n✅ DONE: {result}")
            output = {
                "result": result,
                "iterations": i+1,
                "history": history,
                "model": model_name,
                "timestamp": datetime.now().isoformat(),
            }

            # Convert to JSON if requested
            if as_json:
                output = json_convert(json.dumps(output, ensure_ascii=False), use_model=model_name)

            return output

        # 3. Wyciągnij i wykonaj kod
        code = extract_code(response)
        messages.append({"role": "assistant", "content": response})

        if code:
            print(f"\n⚙️  Executing code ({len(code)} chars)...")
            output, success = run_code(code)
            status = "✅" if success else "❌"
            print(f"{status} Output: {output[:200]}")

            feedback = f"Wynik wykonania kodu ({'sukces' if success else 'błąd'}):\n{output}"
            messages.append({"role": "user", "content": feedback})
            history.append({"iteration": i+1, "code": code, "output": output, "success": success})
        else:
            # Brak kodu — model odpowiada tekstowo, kontynuujemy
            messages.append({"role": "user", "content": "Kontynuuj. Jeśli skończone, napisz TASK_COMPLETE: [wynik]"})

    return {"error": "Max iteracji osiągnięty", "history": history}

# ─── ROUTING (auto-wybór modelu) ──────────────────────────────────────────────
def auto_route(task: str) -> str:
    """Automatyczny wybór najtańszego modelu dla zadania (uwzględniając WSZYSTKIE)."""
    task_lower = task.lower()

    # Gemini: długi kontekst, rozumowanie
    if any(kw in task_lower for kw in ["reasoning", "długi", "context", "analyze", "deep"]):
        return "gemini"

    # Groq: ultra-szybkie, ogólne
    if any(kw in task_lower for kw in ["szybko", "fast", "quick", "general"]):
        return "groq"

    # Codestral: kod, refaktoring
    if any(kw in task_lower for kw in ["código", "code", "refactor", "function", "generate"]):
        return "codestral"

    # Mistral: GitHub, PR, review
    if any(kw in task_lower for kw in ["github", "pr", "pull request", "bug", "issue", "review"]):
        return "mistral"

    # Grok: research, web
    if any(kw in task_lower for kw in ["research", "znajdź", "wyszukaj", "web", "explore"]):
        return "grok"

    # OpenAI: JSON, structured
    if any(kw in task_lower for kw in ["json", "structured", "schema", "parse"]):
        return "openai"

    # Local Ollama: free, local
    if any(kw in task_lower for kw in ["offline", "local", "free", "ollama"]):
        return "ollama"

    # Default: DeepSeek (najtańszy coder)
    return "deepseek"

# ─── LIST MODELS ──────────────────────────────────────────────────────────────
def list_models() -> None:
    """Wyświetl dostępne modele z kosztami."""
    print("\n" + "═" * 80)
    print("📋 DOSTĘPNE MODELE (CodeAct Agent)")
    print("═" * 80)

    for name, cfg in MODELS.items():
        api_status = "✅ Key found" if cfg["key"] else "⚠️  No key"
        print(f"\n{name.upper():12} | {cfg['model']:35} | {cfg['cost']:20} | {api_status}")
        print(f"  URL: {cfg['url']}")
        print(f"  Best for: {', '.join(cfg['best_for'])}")

    print("\n" + "═" * 80)
    print("AUTO-ROUTING examples:")
    print("  'code' → codestral | 'github' → mistral | 'json' → openai")
    print("  'reasoning' → gemini | 'fast' → groq | 'offline' → ollama")
    print("═" * 80 + "\n")

# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CodeAct Agent — NEXUS Orchestration")
    parser.add_argument("--task",  "-t", help="Zadanie do wykonania")
    parser.add_argument("--model", "-m", default="auto",
                        choices=["auto", "deepseek", "mistral", "codestral", "grok",
                                 "gemini", "groq", "openai", "ollama"],
                        help="Model (auto = smart routing)")
    parser.add_argument("--max-iter", type=int, default=8, help="Max iteracji (default: 8)")
    parser.add_argument("--json", action="store_true", help="Output as JSON (orchestrator mode)")
    parser.add_argument("--list-models", action="store_true", help="Pokaż dostępne modele i wyjdź")
    args = parser.parse_args()

    # List models i wyjdź
    if args.list_models:
        list_models()
        sys.exit(0)

    # Obsługa stdin JSON
    if not args.task:
        if not sys.stdin.isatty():
            data = json.loads(sys.stdin.read())
            args.task  = data.get("task", "")
            args.model = data.get("model", "auto")
            args.json  = data.get("json", False)
        else:
            parser.print_help()
            sys.exit(1)

    model = auto_route(args.task) if args.model == "auto" else args.model
    result = codeact_loop(args.task, model, args.max_iter, as_json=args.json)

    print("\n" + "═" * 60)
    print("📊 WYNIK KOŃCOWY:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
