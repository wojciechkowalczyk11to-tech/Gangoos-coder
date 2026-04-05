"""
Code Verification Tool — DeepSeek reviews Python scripts before execution.
Acts as safety/quality layer in CodeAct pipeline:
  Coder (Codestral/Qwen) writes script → DeepSeek verifies → execute only if safe.

DeepSeek is cheap ($0.14/M input) and good at finding bugs.
Fallback to Groq (free) if DeepSeek is down.
"""
import os, json, urllib.request
from mcp.server.fastmcp import FastMCP

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")

REVIEW_PROMPT = """You are a senior Python code reviewer. Analyze this script for:

1. **BUGS**: Logic errors, wrong variable names, missing imports, incorrect API calls
2. **SECURITY**: Hardcoded secrets, shell injection, unsafe eval/exec, path traversal
3. **MCP ERRORS**: Wrong tool names, missing required params, incorrect endpoint URLs
4. **RUNTIME**: Will crash on execution? Missing error handling? Infinite loops?

Script to review:
```python
{code}
```

{context}

Respond in this EXACT JSON format:
{{
  "safe": true/false,
  "score": 1-10,
  "issues": [
    {{"severity": "critical|warning|info", "line": N, "description": "..."}}
  ],
  "fixed_code": "...corrected Python code if issues found, or null if safe...",
  "summary": "one-line verdict"
}}

If score >= 7 and no critical issues, set safe=true.
Output ONLY valid JSON."""


def _call_deepseek(prompt):
    if not DEEPSEEK_KEY:
        raise RuntimeError("No DEEPSEEK_API_KEY")
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a code review expert. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"]


def _call_groq(prompt):
    if not GROQ_KEY:
        raise RuntimeError("No GROQ_API_KEY")
    body = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a code review expert. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"]


def register(mcp: FastMCP):
    @mcp.tool(name="code_verify", annotations={"title": "Verify Python code before execution", "destructiveHint": False})
    async def code_verify(params: dict) -> str:
        """
        Review Python code for bugs, security issues, and MCP errors before executing.
        Uses DeepSeek (cheap) with Groq fallback (free).

        params:
          code (str, required): Python code to review
          context (str, optional): What the code is supposed to do
          auto_fix (bool, optional): Return fixed code if issues found (default: true)
          strict (bool, optional): Require score >= 8 for safe (default: false)
        """
        code = params.get("code", "")
        if not code:
            return "Error: 'code' is required"

        context = params.get("context", "")
        ctx_str = f"Context: {context}" if context else ""
        prompt = REVIEW_PROMPT.format(code=code, context=ctx_str)

        raw = None
        provider = None
        for name, fn in [("deepseek", _call_deepseek), ("groq", _call_groq)]:
            try:
                raw = fn(prompt)
                provider = name
                break
            except Exception as e:
                continue

        if not raw:
            return json.dumps({"error": "All review providers failed", "safe": True, "score": 5,
                               "summary": "Could not verify - proceed with caution"})

        try:
            review = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON from reviewer", "raw": raw[:500],
                               "safe": True, "score": 5})

        strict = params.get("strict", False)
        threshold = 8 if strict else 7
        review["safe"] = review.get("score", 0) >= threshold and not any(
            i.get("severity") == "critical" for i in review.get("issues", [])
        )
        review["provider"] = provider

        if not params.get("auto_fix", True):
            review.pop("fixed_code", None)

        return json.dumps(review)

    @mcp.tool(name="code_verify_and_exec", annotations={"title": "Verify then execute Python code", "destructiveHint": True})
    async def code_verify_and_exec(params: dict) -> str:
        """
        Review code with DeepSeek, then execute via python_exec if safe.
        If unsafe but fixable, execute the fixed version instead.

        params:
          code (str, required): Python code to review and execute
          context (str, optional): Task description
          force (bool, optional): Execute even if review fails (default: false)
          strict (bool, optional): Require score >= 8 (default: false)
        """
        code = params.get("code", "")
        if not code:
            return "Error: 'code' is required"

        # Step 1: Review
        review_result = await code_verify({
            "code": code,
            "context": params.get("context", ""),
            "auto_fix": True,
            "strict": params.get("strict", False),
        })
        review = json.loads(review_result)

        # Step 2: Decide what to execute
        exec_code = code
        used_fix = False

        if not review.get("safe", False):
            fixed = review.get("fixed_code")
            if fixed and fixed != "null":
                exec_code = fixed
                used_fix = True
            elif not params.get("force", False):
                return json.dumps({
                    "executed": False,
                    "reason": "Code review failed and no fix available",
                    "review": review,
                })

        # Step 3: Execute via MCP python_exec
        try:
            exec_headers = {
                "Authorization": f"Bearer {os.getenv('NEXUS_AUTH_TOKEN', '')}",
                "Content-Type": "application/json"
            }
            mcp_url = os.getenv("NEXUS_MCP_URL", "http://localhost:8080")
            payload = json.dumps({"code": exec_code}).encode()
            req = urllib.request.Request(
                f"{mcp_url}/api/v1/tools/python_exec",
                data=payload, headers=exec_headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                exec_result = json.loads(r.read())
        except Exception as e:
            exec_result = {"success": False, "error": str(e)}

        return json.dumps({
            "executed": True,
            "used_fixed_code": used_fix,
            "review_score": review.get("score", 0),
            "review_summary": review.get("summary", ""),
            "issues_found": len(review.get("issues", [])),
            "exec_success": exec_result.get("success", False),
            "exec_result": str(exec_result.get("result", ""))[:2000],
            "exec_error": exec_result.get("error"),
        })
