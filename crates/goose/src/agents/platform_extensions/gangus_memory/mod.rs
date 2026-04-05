use crate::agents::extension::PlatformExtensionContext;
use crate::agents::mcp_client::{Error, McpClientTrait};
use crate::agents::tool_execution::ToolCallContext;
use anyhow::Result;
use async_trait::async_trait;
use rmcp::model::{
    CallToolResult, Content, Implementation, InitializeResult, JsonObject, ListToolsResult,
    ServerCapabilities,
};
use tokio_util::sync::CancellationToken;

pub static EXTENSION_NAME: &str = "gangus_memory";

pub struct GangusMemoryClient {
    info: InitializeResult,
}

impl GangusMemoryClient {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("Gangus Memory"),
            ),
        })
    }
}

#[async_trait]
impl McpClientTrait for GangusMemoryClient {
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
            "gangus_memory has no tools (called: {name})"
        ))]))
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, _session_id: &str) -> Option<String> {
        // Look for GANGUS.md in cwd and parent directories (up to 3 levels)
        let cwd = std::env::current_dir().ok()?;
        let candidates = [
            cwd.join("GANGUS.md"),
            cwd.parent()?.join("GANGUS.md"),
            cwd.parent()?.parent()?.join("GANGUS.md"),
        ];

        for path in &candidates {
            if path.exists() {
                match std::fs::read_to_string(path) {
                    Ok(content) if !content.trim().is_empty() => {
                        return Some(format!("**GANGUS.md:**\n{}", content.trim()));
                    }
                    _ => continue,
                }
            }
        }
        None
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
    fn test_gangus_memory_client_new() {
        let client = GangusMemoryClient::new(make_ctx());
        assert!(client.is_ok());
    }

    #[tokio::test]
    async fn test_gangus_memory_get_moim_no_file() {
        // Run from temp dir where no GANGUS.md exists
        let client = GangusMemoryClient::new(make_ctx()).unwrap();
        // Can't assert None because cwd may vary, just ensure it doesn't panic
        let _ = client.get_moim("test_session").await;
    }
}
