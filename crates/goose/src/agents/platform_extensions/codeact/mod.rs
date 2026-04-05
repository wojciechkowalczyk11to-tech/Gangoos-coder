use crate::agents::extension::PlatformExtensionContext;
use crate::agents::mcp_client::{Error, McpClientTrait};
use crate::agents::tool_execution::ToolCallContext;
use anyhow::Result;
use async_trait::async_trait;
use rmcp::model::{
    CallToolResult, Content, Implementation, InitializeResult, JsonObject, ListToolsResult,
    ServerCapabilities, Tool,
};
use serde_json::json;
use tokio_util::sync::CancellationToken;

pub static EXTENSION_NAME: &str = "codeact";

fn nexus_url() -> String {
    std::env::var("NEXUS_URL").unwrap_or_else(|_| "http://localhost:8080".to_string())
}

fn nexus_token() -> String {
    std::env::var("NEXUS_AUTH_TOKEN").unwrap_or_default()
}

/// Max code size: 1MB to prevent resource exhaustion on sandbox
const MAX_CODE_SIZE: usize = 1_048_576;

pub struct CodeActExtension {
    info: InitializeResult,
    /// Shared HTTP client — reused across all calls to avoid per-call DNS/TLS overhead
    client: reqwest::Client,
    /// Cached NEXUS URL (read once at construction)
    nexus_url: String,
    /// Cached NEXUS auth token (read once at construction)
    nexus_token: String,
}

impl CodeActExtension {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .map_err(|e| anyhow::anyhow!("CodeAct: failed to build HTTP client: {}", e))?;

        let token = nexus_token();
        if token.is_empty() {
            tracing::warn!(
                "NEXUS_AUTH_TOKEN is not set — codeact run_mojo calls will be unauthenticated"
            );
        }

        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("CodeAct"),
            ),
            client,
            nexus_url: nexus_url(),
            nexus_token: token,
        })
    }

    // Mojo CodeAct — first Mojo-native agent framework
    pub async fn execute_mojo(&self, code: &str, timeout_secs: u64) -> Result<String> {
        let start = std::time::Instant::now();
        let body = json!({
            "name": "mojo_exec",
            "arguments": {
                "code": code,
                "timeout": timeout_secs
            }
        });

        let response = self
            .client
            .post(format!("{}/tools/call", self.nexus_url))
            .header("Authorization", format!("Bearer {}", self.nexus_token))
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await;

        let elapsed_ms = start.elapsed().as_millis() as u64;

        match response {
            Ok(resp) => {
                let status = resp.status().as_u16();
                let text = resp.text().await.unwrap_or_default();

                // Parse inner NEXUS response and re-wrap with metadata
                // Non-JSON responses (e.g. HTML error pages) get exit_code -1 to avoid false success
                let inner: serde_json::Value = serde_json::from_str(&text).unwrap_or_else(|_| {
                    json!({ "stdout": "", "stderr": text, "exit_code": -1 })
                });

                let exit_code = inner.get("exit_code").and_then(|v| v.as_i64()).unwrap_or(0);
                let stdout = inner.get("stdout").and_then(|v| v.as_str()).unwrap_or(&text);
                let stderr = inner.get("stderr").and_then(|v| v.as_str()).unwrap_or("");

                let success = status == 200 && exit_code == 0;
                let result = json!({
                    "status": if success { "ok" } else { "error" },
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "execution_ms": elapsed_ms,
                });

                tracing::debug!(
                    session = "codeact",
                    step = "run_mojo",
                    success = success,
                    exit_code = exit_code,
                    elapsed_ms = elapsed_ms,
                    stdout_len = stdout.len(),
                    "mojo_exec trace"
                );

                Ok(result.to_string())
            }
            Err(e) => {
                tracing::warn!("run_mojo: NEXUS request failed after {}ms: {}", elapsed_ms, e);
                Err(anyhow::anyhow!(
                    "NEXUS connection failed after {}ms: {}",
                    elapsed_ms,
                    e
                ))
            }
        }
    }
}

#[async_trait]
impl McpClientTrait for CodeActExtension {
    async fn list_tools(
        &self,
        _session_id: &str,
        _next_cursor: Option<String>,
        _cancellation_token: CancellationToken,
    ) -> Result<ListToolsResult, Error> {
        let run_mojo = Tool::new(
            "run_mojo".to_string(),
            "Execute Mojo code via NEXUS MCP mojo_exec. \
             Use this to run Mojo language programs, test Mojo snippets, or perform \
             high-performance numerical/systems work. Returns stdout, stderr, exit_code."
                .to_string(),
            json!({
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Mojo source code to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Execution timeout in seconds (default 60)",
                        "default": 60
                    }
                },
                "required": ["code"]
            })
            .as_object()
            .expect("run_mojo schema must be a JSON object")
            .clone(),
        );
        Ok(ListToolsResult {
            tools: vec![run_mojo],
            next_cursor: None,
            meta: None,
        })
    }

    async fn call_tool(
        &self,
        _ctx: &ToolCallContext,
        name: &str,
        arguments: Option<JsonObject>,
        _cancellation_token: CancellationToken,
    ) -> Result<CallToolResult, Error> {
        match name {
            "run_mojo" => {
                let args = arguments.unwrap_or_default();
                let code = args
                    .get("code")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default();
                if code.is_empty() {
                    return Ok(CallToolResult::error(vec![Content::text(
                        "run_mojo: 'code' argument is required",
                    )]));
                }
                if code.len() > MAX_CODE_SIZE {
                    return Ok(CallToolResult::error(vec![Content::text(
                        format!("run_mojo: code exceeds max size ({}B > {}B)", code.len(), MAX_CODE_SIZE),
                    )]));
                }
                let timeout_secs = args
                    .get("timeout")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(60)
                    .min(300); // cap at 5 minutes
                match self.execute_mojo(code, timeout_secs).await {
                    Ok(output) => Ok(CallToolResult::success(vec![Content::text(output)])),
                    Err(e) => Ok(CallToolResult::error(vec![Content::text(format!(
                        "run_mojo error: {e}"
                    ))])),
                }
            }
            _ => Ok(CallToolResult::error(vec![Content::text(format!(
                "codeact: unknown tool '{name}'"
            ))])),
        }
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, session_id: &str) -> Option<String> {
        // Check if Context7 has a last query to give routing hints
        let last_query = crate::agents::platform_extensions::context7::last_message::get(session_id)
            .unwrap_or_default();

        // Tool routing guidance based on last user intent
        let routing_hint = classify_intent(&last_query);

        Some(format!(
            "**CodeAct status:** ready (run_mojo → NEXUS mojo_exec)\n\
             **Tool routing:** {}\n\
             **Self-healing:** on error from run_mojo, inspect stderr and retry with fix\n\
             **Retry budget:** up to 3 attempts per execution task",
            routing_hint
        ))
    }
}

/// Classify user intent to guide tool routing.
fn classify_intent(input: &str) -> &'static str {
    if input.is_empty() {
        return "use LLM reasoning; escalate to run_mojo for code, Context7 for docs, MCP for services";
    }
    let lower = input.to_lowercase();
    if lower.contains("run")
        || lower.contains("execute")
        || lower.contains("compute")
        || lower.contains("calculate")
    {
        "prefer run_mojo for code execution tasks"
    } else if lower.contains("how")
        || lower.contains("what is")
        || lower.contains("explain")
        || lower.contains("docs")
    {
        "prefer Context7 for documentation lookups"
    } else if lower.contains("api")
        || lower.contains("http")
        || lower.contains("fetch")
        || lower.contains("request")
    {
        "prefer MCP tools for external API/service calls"
    } else {
        "use LLM reasoning; escalate to run_mojo for code, Context7 for docs, MCP for services"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::SessionManager;
    use std::sync::Arc;

    fn make_ctx() -> PlatformExtensionContext {
        PlatformExtensionContext {
            extension_manager: None,
            session_manager: Arc::new(SessionManager::instance()),
            session: None,
        }
    }

    #[test]
    fn test_codeact_new() {
        let client = CodeActExtension::new(make_ctx());
        assert!(client.is_ok());
    }

    #[tokio::test]
    async fn test_codeact_get_moim() {
        let client = CodeActExtension::new(make_ctx()).unwrap();
        let moim = client.get_moim("test_session").await;
        assert!(moim.is_some());
        let text = moim.unwrap();
        assert!(text.contains("CodeAct status"), "MOIM should contain status line");
        assert!(text.contains("run_mojo"), "MOIM should reference run_mojo tool");
    }
}
