#!/usr/bin/env bash
# ============================================================
# VIBE SKILL: OpenAI SDK — Full API Coverage
# Target: Devstral-2 in terminal (Termux + Debian)
# Commands: oai_chat oai_json oai_stream oai_embed oai_fn
#           oai_img oai_vibe oai_models oai_file_upload
# Usage: source ~/vibe/openai/skill_openai.sh
# ============================================================

_OPENAI_BASE="https://api.openai.com/v1"
_OPENAI_KEY="${OPENAI_API_KEY:-$(grep OPENAI_API_KEY ~/.env 2>/dev/null | cut -d= -f2)}"

# ── CORE HELPER ──────────────────────────────────────────────────────
_oai() {
  local method="$1" endpoint="$2" data="$3"
  curl -s -X "$method" "${_OPENAI_BASE}${endpoint}" \
    -H "Authorization: Bearer ${_OPENAI_KEY}" \
    -H "Content-Type: application/json" \
    ${data:+-d "$data"}
}

# ── CHAT COMPLETION ───────────────────────────────────────────────────
# oai_chat <prompt> [model] [max_tokens] [temperature] [system]
oai_chat() {
  local prompt="$1"
  local model="${2:-gpt-4.1-mini}"
  local max_tokens="${3:-4096}"
  local temp="${4:-0.7}"
  local system="${5:-You are a helpful assistant.}"
  local body
  body=$(jq -n \
    --arg model "$model" \
    --arg sys "$system" \
    --arg usr "$prompt" \
    --argjson mt "$max_tokens" \
    --argjson t "$temp" \
    '{model:$model,max_tokens:$mt,temperature:$t,
      messages:[{role:"system",content:$sys},{role:"user",content:$usr}]}')
  _oai POST /chat/completions "$body" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
}

# ── STRUCTURED OUTPUT (JSON mode) ─────────────────────────────────────
# oai_json <prompt> [model]
oai_json() {
  local prompt="$1"
  local model="${2:-gpt-4.1-mini}"
  local body
  body=$(jq -n --arg model "$model" --arg usr "$prompt" \
    '{model:$model,max_tokens:2048,
      response_format:{type:"json_object"},
      messages:[{role:"user",content:$usr}]}')
  _oai POST /chat/completions "$body" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
}

# ── STREAMING ─────────────────────────────────────────────────────────
# oai_stream <prompt> [model]
oai_stream() {
  local prompt="$1"
  local model="${2:-gpt-4.1}"
  curl -sN -X POST "${_OPENAI_BASE}/chat/completions" \
    -H "Authorization: Bearer ${_OPENAI_KEY}" \
    -H "Content-Type: application/json" \
    -d $(jq -n --arg m "$model" --arg u "$prompt" \
      '{model:$m,stream:true,messages:[{role:"user",content:$u}]}') | \
  while IFS= read -r line; do
    [[ "$line" == data:* ]] || continue
    local data="${line#data: }"
    [[ "$data" == "[DONE]" ]] && break
    printf '%s' "$(echo "$data" | python3 -c \
      'import sys,json; d=json.load(sys.stdin); print(d["choices"][0]["delta"].get("content",""),end="")')"
  done
  echo
}

# ── EMBEDDINGS ────────────────────────────────────────────────────────
# oai_embed <text> [model] => shows first 5 dims
oai_embed() {
  local text="$1"
  local model="${2:-text-embedding-3-small}"
  _oai POST /embeddings \
    "$(jq -n --arg m "$model" --arg t "$text" '{model:$m,input:$t}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); e=d['data'][0]['embedding']; print(f'dims={len(e)} sample={e[:5]}')"
}

# ── FUNCTION / TOOL CALLING ───────────────────────────────────────────
# oai_fn <prompt> <tools_json_str> [model]
oai_fn() {
  local prompt="$1"
  local tools="$2"
  local model="${3:-gpt-4.1-mini}"
  _oai POST /chat/completions \
    "$(jq -n --arg m "$model" --arg u "$prompt" --argjson t "$tools" \
      '{model:$m,tools:$t,tool_choice:"auto",
        messages:[{role:"user",content:$u}]}')" | \
    python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),indent=2))"
}

# ── IMAGE GENERATION (DALL-E 3) ───────────────────────────────────────
# oai_img <prompt> [1024x1024|1792x1024|1024x1792] [standard|hd]
oai_img() {
  local prompt="$1"
  local size="${2:-1024x1024}"
  local quality="${3:-standard}"
  _oai POST /images/generations \
    "$(jq -n --arg p "$prompt" --arg s "$size" --arg q "$quality" \
      '{model:"dall-e-3",prompt:$p,n:1,size:$s,quality:$q}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data'][0]['url'])"
}

# ── FILE UPLOAD ───────────────────────────────────────────────────────
# oai_file_upload <path> [assistants|fine-tune|batch]
oai_file_upload() {
  local path="$1" purpose="${2:-assistants}"
  curl -s -X POST "${_OPENAI_BASE}/files" \
    -H "Authorization: Bearer ${_OPENAI_KEY}" \
    -F "purpose=$purpose" \
    -F "file=@$path" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('File ID:',d.get('id'))"
}

# ── ASSISTANTS v2 ─────────────────────────────────────────────────────
oai_assistant_create() {
  local name="$1" instr="$2" model="${3:-gpt-4.1-mini}"
  _oai POST /assistants \
    "$(jq -n --arg n "$name" --arg i "$instr" --arg m "$model" \
      '{name:$n,instructions:$i,model:$m}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('Assistant ID:',d.get('id'))"
}

# ── BATCH API ─────────────────────────────────────────────────────────
oai_batch_create() {
  local file_id="$1"
  _oai POST /batches \
    "$(jq -n --arg fid "$file_id" \
      '{input_file_id:$fid,endpoint:"/v1/chat/completions",completion_window:"24h"}')"
}

# ── LIST MODELS ───────────────────────────────────────────────────────
oai_models() {
  _oai GET /models | \
    python3 -c "import sys,json; [print(m['id']) for m in sorted(json.load(sys.stdin)['data'],key=lambda x:x['id'])]"
}

# ── VIBE PROMPT TRANSFORMER ───────────────────────────────────────────
# Devstral-2 sends raw intent → gpt-4.1-mini refines → optimal prompt → execute
# oai_vibe <raw_intent> [target_model]
oai_vibe() {
  local intent="$1"
  local model="${2:-gpt-4.1-mini}"
  echo "[VIBE] Transforming intent..."
  local refined
  refined=$(oai_chat \
    "Transform this raw intent into a perfect prompt for ${model}. Be precise, include output format. Raw: ${intent}" \
    "gpt-4.1-mini" 1024 0.2 \
    "You are a prompt engineer. Output ONLY the refined prompt, no preamble, no quotes.")
  echo "[VIBE] Prompt: $refined"
  echo "[VIBE] Executing on $model..."
  echo "---"
  oai_chat "$refined" "$model"
}

# ── O3-MINI REASONING ────────────────────────────────────────────────
# oai_reason <problem> [effort: low|medium|high]
oai_reason() {
  local problem="$1" effort="${2:-medium}"
  _oai POST /chat/completions \
    "$(jq -n --arg p "$problem" --arg e "$effort" \
      '{model:"o3-mini",reasoning_effort:$e,
        messages:[{role:"user",content:$p}]}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
}

# ── GPT-4.1 VISION ───────────────────────────────────────────────────
# oai_vision <image_url> <question>
oai_vision() {
  local url="$1" question="$2"
  _oai POST /chat/completions \
    "$(jq -n --arg q "$question" --arg u "$url" \
      '{model:"gpt-4.1",max_tokens:1024,
        messages:[{role:"user",content:[
          {type:"image_url",image_url:{url:$u}},
          {type:"text",text:$q}
        ]}]}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
}

[[ "${VIBE_QUIET:-0}" != "1" ]] && echo "✅ OpenAI skill loaded."
[[ "${VIBE_QUIET:-0}" != "1" ]] && echo "   oai_chat | oai_json | oai_stream | oai_embed | oai_fn | oai_img | oai_vibe | oai_reason | oai_vision | oai_models"
