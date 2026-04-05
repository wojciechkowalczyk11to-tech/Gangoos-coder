#!/usr/bin/env bash
# ============================================================
# VIBE SKILL: xAI SDK — Full Grok API Coverage
# Commands: grok_chat grok_stream grok_web grok_search
#           grok_embed grok_upload grok_vs_list grok_vibe
# Covers: Chat, Streaming, Responses API, Vector Stores,
#         File Search, Web Search, X Search, Embeddings
# Usage: source ~/vibe/xai/skill_xai.sh
# ============================================================

_XAI_BASE="https://api.x.ai/v1"
_XAI_KEY="${XAI_API_KEY:-$(grep XAI_API_KEY ~/.env 2>/dev/null | cut -d= -f2)}"
_XAI_DEFAULT_MODEL="grok-4-1-fast-reasoning"
_XAI_DEFAULT_COLLECTION="collection_3a79cc0c-997c-4871-8373-ff2ce5c54ee2"

_xai() {
  local method="$1" endpoint="$2" data="$3"
  curl -s -X "$method" "${_XAI_BASE}${endpoint}" \
    -H "Authorization: Bearer ${_XAI_KEY}" \
    -H "Content-Type: application/json" \
    ${data:+-d "$data"}
}

# ── CHAT COMPLETION (OpenAI-compatible) ───────────────────────
# grok_chat <prompt> [model] [max_tokens] [temp]
grok_chat() {
  local prompt="$1"
  local model="${2:-$_XAI_DEFAULT_MODEL}"
  local mt="${3:-4096}"
  local temp="${4:-0.7}"
  _xai POST /chat/completions \
    "$(jq -n --arg m "$model" --arg p "$prompt" --argjson mt "$mt" --argjson t "$temp" \
      '{model:$m,max_tokens:$mt,temperature:$t,messages:[{role:"user",content:$p}]}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
}

# ── STREAMING ─────────────────────────────────────────────
grok_stream() {
  local prompt="$1" model="${2:-$_XAI_DEFAULT_MODEL}"
  curl -sN -X POST "${_XAI_BASE}/chat/completions" \
    -H "Authorization: Bearer ${_XAI_KEY}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg m "$model" --arg p "$prompt" \
      '{model:$m,stream:true,messages:[{role:"user",content:$p}]}')" | \
  while IFS= read -r line; do
    [[ "$line" == data:* ]] || continue
    local data="${line#data: }"
    [[ "$data" == "[DONE]" ]] && break
    printf '%s' "$(echo "$data" | python3 -c \
      'import sys,json; d=json.load(sys.stdin); print(d["choices"][0]["delta"].get("content",""),end="")')"
  done; echo
}

# ── RESPONSES API CORE ─────────────────────────────────────────
_xai_responses() {
  local payload="$1"
  _xai POST /responses "$payload" | \
    python3 -c "
import sys, json
d = json.load(sys.stdin)
for item in d.get('output', []):
  for c in item.get('content', []):
    if c.get('type') == 'output_text': print(c['text'])
"
}

# ── WEB + X SEARCH (Responses API) ───────────────────────────────
# grok_web <query> [include_x:true|false]
grok_web() {
  local query="$1" x="${2:-true}"
  local tools='[{"type":"web_search"}]'
  [[ "$x" == "true" ]] && tools='[{"type":"web_search"},{"type":"x_search"}]'
  _xai_responses "$(jq -n --arg q "$query" --arg m "$_XAI_DEFAULT_MODEL" --argjson t "$tools" \
    '{model:$m,input:[{role:"user",content:$q}],tools:$t}')"
}

# ── VECTOR STORE SEARCH (Responses API / file_search) ────────────
# grok_search <query> [collection_id] [model]
grok_search() {
  local query="$1"
  local cid="${2:-$_XAI_DEFAULT_COLLECTION}"
  local model="${3:-$_XAI_DEFAULT_MODEL}"
  _xai_responses "$(jq -n --arg q "$query" --arg cid "$cid" --arg m "$model" \
    '{model:$m,input:[{role:"user",content:$q}],
      tools:[{type:"file_search",vector_store_ids:[$cid],max_num_results:10}]}')"
}

# ── VECTOR STORES CRUD ────────────────────────────────────────
grok_vs_list() {
  _xai GET /vector-stores | python3 -c "
import sys,json; d=json.load(sys.stdin)
for s in d.get('data',[]): print(f\"{s['id']} | {s.get('name','?')} | files:{s.get('file_counts',{}).get('completed','?')}\")" 2>/dev/null
}

grok_vs_create() {
  local name="$1"
  _xai POST /vector-stores "$(jq -n --arg n "$name" '{name:$n}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('VS ID:',d.get('id','ERR:',str(d)))"
}

grok_vs_status() {
  local vs_id="$1"
  _xai GET "/vector-stores/${vs_id}" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({k:d.get(k) for k in ['id','name','status','file_counts']},indent=2))"
}

grok_vs_delete() {
  local vs_id="$1"
  _xai DELETE "/vector-stores/${vs_id}" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('Deleted:',d.get('deleted','?'))"
}

# ── FILE UPLOAD → VECTOR STORE ───────────────────────────────
# grok_upload <file_path> [collection_id]
grok_upload() {
  local fpath="$1" cid="${2:-$_XAI_DEFAULT_COLLECTION}"
  local fname; fname=$(basename "$fpath")
  echo "[xAI] Uploading $fname..."
  local file_id
  file_id=$(curl -s -X POST "${_XAI_BASE}/files" \
    -H "Authorization: Bearer ${_XAI_KEY}" \
    -F "purpose=collection" \
    -F "file=@${fpath};filename=${fname}" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','ERR:'+str(d)))")
  [[ "$file_id" == ERR* ]] && echo "[xAI] Upload failed: $file_id" && return 1
  echo "[xAI] file_id=$file_id -> attaching to $cid"
  _xai POST "/vector-stores/${cid}/files" \
    "$(jq -n --arg fid "$file_id" '{file_id:$fid}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('[xAI] status:',d.get('status'))"
}

# grok_upload_dir <directory> [collection_id] [extensions]
# Upload all matching files from a directory
grok_upload_dir() {
  local dir="$1" cid="${2:-$_XAI_DEFAULT_COLLECTION}" exts="${3:-.md .txt .py .js .ts .json}"
  local count=0
  while IFS= read -r -d '' f; do
    grok_upload "$f" "$cid" && ((count++))
  done < <(find "$dir" -maxdepth 3 -type f \( -name '*.md' -o -name '*.txt' -o -name '*.py' -o -name '*.js' -o -name '*.ts' \) -print0 2>/dev/null)
  echo "[xAI] Uploaded $count files to $cid"
}

# ── FILES API ────────────────────────────────────────────────────
grok_files_list() {
  _xai GET /files | python3 -c "
import sys,json; d=json.load(sys.stdin)
for f in d.get('data',[]): print(f\"  {f['id']} | {f.get('filename','?')} | {f.get('status','?')}\")" 2>/dev/null
}

grok_file_delete() {
  local fid="$1"
  _xai DELETE "/files/${fid}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('deleted:',d.get('deleted'))"
}

# ── EMBEDDINGS ───────────────────────────────────────────────
grok_embed() {
  local text="$1" model="${2:-v1}"
  _xai POST /embeddings \
    "$(jq -n --arg m "$model" --arg t "$text" '{model:$m,input:$t}')" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); e=d['data'][0]['embedding']; print(f'dims={len(e)} sample={e[:3]}')"
}

# ── LIST MODELS ──────────────────────────────────────────────────
grok_models() {
  echo "Available Grok models:"
  echo "  grok-4-1-fast-reasoning   ← default, best cost/quality"
  echo "  grok-4-fast-reasoning     ← slightly older fast"
  echo "  grok-4-0709               ← standard reasoning"
  echo "  grok-3                    ← large, high quality"
  echo "  grok-3-mini               ← small fast"
  echo "  grok-code-fast-1          ← code specialist"
  echo "  grok-4.20-beta-0309-reasoning  ← latest beta"
}

# ── VIBE INTENT → AUTO-CLASSIFY → EXECUTE ─────────────────────────
# Devstral-2 sends raw intent → Grok classifies → routes to optimal tool
# grok_vibe <intent>
grok_vibe() {
  local intent="$1"
  echo "[VIBE] Classifying: $intent"
  local route
  route=$(grok_chat \
    "Classify this intent into EXACTLY ONE word: WEB (live data/news/current events), SEARCH (knowledge base/docs query), CODE (generate or fix code), REASON (complex multi-step problem), CHAT (general conversation). Intent: ${intent}" \
    "grok-4-1-fast-reasoning" 20 0.0)
  route=$(echo "$route" | tr '[:lower:]' '[:upper:]' | tr -d '[:space:]')
  echo "[VIBE] Route: $route"
  echo "---"
  case "$route" in
    *WEB*)    grok_web "$intent" ;;
    *SEARCH*) grok_search "$intent" ;;
    *CODE*)   grok_chat "$intent" "grok-code-fast-1" ;;
    *REASON*) grok_chat "$intent" "grok-4-1-fast-reasoning" 8192 0.5 ;;
    *)        grok_chat "$intent" "grok-4-fast-reasoning" ;;
  esac
}

[[ "${VIBE_QUIET:-0}" != "1" ]] && echo "✅ xAI skill loaded."
[[ "${VIBE_QUIET:-0}" != "1" ]] && echo "   grok_chat | grok_stream | grok_web | grok_search | grok_embed | grok_upload | grok_vs_list | grok_vibe"
