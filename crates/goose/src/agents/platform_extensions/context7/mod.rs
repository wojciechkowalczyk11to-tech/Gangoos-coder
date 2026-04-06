use crate::agents::extension::PlatformExtensionContext;
use crate::agents::mcp_client::{Error, McpClientTrait};
use crate::agents::tool_execution::ToolCallContext;
use anyhow::Result;
use async_trait::async_trait;
use once_cell::sync::Lazy;
use rmcp::model::{
    CallToolResult, Content, Implementation, InitializeResult, JsonObject, ListToolsResult,
    ServerCapabilities,
};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tokio_util::sync::CancellationToken;

pub static EXTENSION_NAME: &str = "context7";

/// Simple TTL cache for doc results — avoids per-turn HTTP fetches
struct DocCache {
    entries: HashMap<String, (String, Instant)>,
    ttl: Duration,
}

impl DocCache {
    fn new(ttl_secs: u64) -> Self {
        Self {
            entries: HashMap::new(),
            ttl: Duration::from_secs(ttl_secs),
        }
    }

    fn get(&self, key: &str) -> Option<&str> {
        self.entries.get(key).and_then(|(val, ts)| {
            if ts.elapsed() < self.ttl {
                Some(val.as_str())
            } else {
                None
            }
        })
    }

    fn insert(&mut self, key: String, val: String) {
        // Evict stale entries when cache grows large
        if self.entries.len() >= 200 {
            self.entries.retain(|_, (_, ts)| ts.elapsed() < self.ttl);
            // Hard cap: if still over limit after TTL eviction, drop oldest
            if self.entries.len() >= 200 {
                if let Some(oldest_key) = self
                    .entries
                    .iter()
                    .min_by_key(|(_, (_, ts))| *ts)
                    .map(|(k, _)| k.clone())
                {
                    self.entries.remove(&oldest_key);
                }
            }
        }
        self.entries.insert(key, (val, Instant::now()));
    }
}

static DOC_CACHE: Lazy<Mutex<DocCache>> = Lazy::new(|| Mutex::new(DocCache::new(300))); // 5 min TTL

/// Context7 extension — injects library documentation context into MOIM.
/// When the agent's conversation references a known library/framework, this extension
/// fetches relevant doc snippets and injects them so the LLM has up-to-date API knowledge.
pub struct Context7Client {
    info: InitializeResult,
    /// Optional Context7 API base URL. Falls back to built-in stubs if not set.
    api_url: Option<String>,
    /// Shared HTTP client
    client: reqwest::Client,
}

impl Context7Client {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        let api_url = std::env::var("CONTEXT7_API_URL").ok();
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(3))
            .build()
            .map_err(|e| anyhow::anyhow!("Context7: failed to build HTTP client: {}", e))?;
        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("Context7 Docs"),
            ),
            api_url,
            client,
        })
    }

    /// Detect which library/framework is referenced in the query.
    fn detect_library(input: &str) -> Option<(&'static str, &'static str)> {
        let lower = input.to_lowercase();
        // Order: most specific first to avoid false matches (e.g., "next.js" before "react")
        let pairs: &[(&str, &str)] = &[
            ("next.js", "Next.js"),
            ("nextjs", "Next.js"),
            ("fastapi", "FastAPI"),
            ("pytorch", "PyTorch"),
            ("tailwind", "Tailwind CSS"),
            ("numpy", "NumPy"),
            ("pandas", "Pandas"),
            ("axum", "Axum"),
            ("tokio", "Tokio"),
            ("mojo", "Mojo"),
            ("react", "React"),
        ];
        for (keyword, display) in pairs {
            if lower.contains(keyword) {
                return Some((keyword, display));
            }
        }
        None
    }

    /// Returns true for queries that look like they need documentation context.
    /// Uses word-boundary matching to avoid false positives on partial words.
    fn is_code_query(input: &str) -> bool {
        let triggers = [
            "how",
            "what",
            "why",
            "error",
            "fix",
            "bug",
            "implement",
            "write",
            "create",
            "use",
            "import",
            "hook",
            "function",
            "api",
            "docs",
            "example",
            "async",
            "await",
        ];
        let lower = input.to_lowercase();
        triggers.iter().any(|t| {
            lower
                .split(|c: char| !c.is_alphanumeric())
                .any(|word| word == *t)
        })
    }

    /// Fetch docs from Context7 API or return built-in stub. Results are cached for 5 minutes.
    async fn fetch_docs(&self, lib_key: &str, lib_name: &str, _query: &str) -> Option<String> {
        let cache_key = lib_key.to_string();

        // Check cache first (lock held briefly — no await)
        if let Ok(cache) = DOC_CACHE.lock() {
            if let Some(cached) = cache.get(&cache_key) {
                return Some(cached.to_string());
            }
        }

        // If a real Context7 API URL is configured, call it
        if let Some(ref base_url) = self.api_url {
            let url = format!("{}/resolve?lib={}", base_url, lib_key);
            if let Ok(resp) = self.client.get(&url).send().await {
                if let Ok(text) = resp.text().await {
                    if !text.is_empty() {
                        // Truncate at char boundary to avoid UTF-8 panic
                        let truncated: String = text.chars().take(800).collect();
                        let result = format!("**{} docs:**\n{}", lib_name, truncated);
                        if let Ok(mut cache) = DOC_CACHE.lock() {
                            cache.insert(cache_key, result.clone());
                        }
                        return Some(result);
                    }
                }
            }
            tracing::debug!(
                "Context7: API fetch failed for '{}', falling back to stubs",
                lib_key
            );
        }

        // Built-in stubs for offline / no-API use
        let stub = match lib_key {
            "mojo" => Some(
                "Mojo v26 key rules:\n\
                 • Use `def` (not `fn`) for regular functions\n\
                 • Argument conventions: `read` (immutable), `mut` (mutable), `var` (owned), `out` (output)\n\
                 • Use `comptime` for compile-time constants (not `alias`)\n\
                 • SIMD: `SIMD[DType.float32, 4]`; Tensor: `Tensor[DType.float32]`\n\
                 • stdlib: `from sys import info; from memory import UnsafePointer`"
            ),
            "tokio" => Some(
                "Tokio async runtime:\n\
                 • `#[tokio::main]` for async main\n\
                 • `tokio::spawn` for background tasks\n\
                 • `tokio::select!` for racing futures\n\
                 • `tokio::sync::{Mutex, RwLock, mpsc, broadcast}`"
            ),
            "axum" => Some(
                "Axum web framework:\n\
                 • `Router::new().route(\"/path\", get(handler))`\n\
                 • Extractors: `Path<T>`, `Query<T>`, `Json<T>`, `State<T>`\n\
                 • `axum::serve(listener, app).await`"
            ),
            "react" => Some(
                "React hooks:\n\
                 • `useState<T>(initial)` — local state\n\
                 • `useEffect(fn, [deps])` — side effects, cleanup via returned fn\n\
                 • `useCallback(fn, [deps])` — memoize callbacks\n\
                 • `useMemo(fn, [deps])` — memoize values"
            ),
            _ => None,
        };
        let result = stub.map(|s| format!("**{} (built-in docs):**\n{}", lib_name, s));
        // Cache stub too so we don't hit this path every turn
        if let (Some(ref r), Ok(mut cache)) = (result.as_ref(), DOC_CACHE.lock()) {
            cache.insert(cache_key, r.to_string());
        }
        result
    }
}

#[async_trait]
impl McpClientTrait for Context7Client {
    async fn list_tools(
        &self,
        _session_id: &str,
        _next_cursor: Option<String>,
        _cancellation_token: CancellationToken,
    ) -> Result<ListToolsResult, Error> {
        Ok(ListToolsResult {
            tools: vec![],
            next_cursor: None,
            meta: None,
        })
    }

    async fn call_tool(
        &self,
        _ctx: &ToolCallContext,
        name: &str,
        _arguments: Option<JsonObject>,
        _cancellation_token: CancellationToken,
    ) -> Result<CallToolResult, Error> {
        Ok(CallToolResult::error(vec![Content::text(format!(
            "context7: unknown tool '{name}'"
        ))]))
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, session_id: &str) -> Option<String> {
        // Get last user message to detect library context
        let query = crate::agents::platform_extensions::context7::last_message::get(session_id);
        let query = query.as_deref().unwrap_or("");

        if !Self::is_code_query(query) {
            return None;
        }

        let (lib_key, lib_name) = Self::detect_library(query)?;
        let docs = self.fetch_docs(lib_key, lib_name, query).await?;

        tracing::debug!("Context7 injecting docs for: {}", lib_name);
        Some(format!("**[Context7: {}]**\n{}", lib_name, docs))
    }
}

/// Lightweight per-session last-message store.
/// Extensions call `last_message::set(session_id, text)` after each user turn.
pub mod last_message {
    use once_cell::sync::Lazy;
    use std::collections::HashMap;
    use std::sync::Mutex;

    static STORE: Lazy<Mutex<HashMap<String, String>>> = Lazy::new(|| Mutex::new(HashMap::new()));

    pub fn set(session_id: &str, message: &str) {
        if let Ok(mut guard) = STORE.lock() {
            // Cap at 1000 sessions to prevent unbounded growth
            if guard.len() >= 1000 && !guard.contains_key(session_id) {
                // Remove an arbitrary entry to make room
                if let Some(key) = guard.keys().next().cloned() {
                    guard.remove(&key);
                }
            }
            guard.insert(session_id.to_string(), message.to_string());
        }
    }

    pub fn get(session_id: &str) -> Option<String> {
        STORE.lock().ok()?.get(session_id).cloned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_library_mojo() {
        assert!(Context7Client::detect_library("how do I use mojo structs").is_some());
    }

    #[test]
    fn test_detect_library_none() {
        assert!(Context7Client::detect_library("what is the weather today").is_none());
    }

    #[test]
    fn test_is_code_query() {
        assert!(Context7Client::is_code_query("how does useEffect work"));
        assert!(!Context7Client::is_code_query("hello world"));
    }

    #[test]
    fn test_last_message_store() {
        last_message::set("sess-1", "how does mojo work");
        let msg = last_message::get("sess-1");
        assert_eq!(msg.as_deref(), Some("how does mojo work"));
    }
}
