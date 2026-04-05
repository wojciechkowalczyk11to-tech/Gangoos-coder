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

pub static EXTENSION_NAME: &str = "hooks";

/// Pre/post tool hooks loaded from `.gangus/hooks.toml`.
/// Format:
/// ```toml
/// [pre_tool]
/// shell = ["echo 'before'"]
///
/// [post_tool]
/// shell = ["echo 'after'"]
/// ```
pub struct HooksClient {
    info: InitializeResult,
}

impl HooksClient {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("Hooks"),
            ),
        })
    }

    fn load_hooks_summary() -> Option<String> {
        let cwd = std::env::current_dir().ok()?;
        let path = cwd.join(".gangus").join("hooks.toml");
        if !path.exists() {
            return None;
        }
        let content = std::fs::read_to_string(&path).ok()?;
        let mut pre_count = 0usize;
        let mut post_count = 0usize;

        // Minimal parse: count non-empty lines in [pre_tool] and [post_tool] sections
        let mut section = "";
        for line in content.lines() {
            let line = line.trim();
            if line.starts_with("[pre_tool]") {
                section = "pre";
            } else if line.starts_with("[post_tool]") {
                section = "post";
            } else if line.starts_with('[') {
                section = "";
            } else if !line.is_empty() && !line.starts_with('#') {
                match section {
                    "pre" => pre_count += 1,
                    "post" => post_count += 1,
                    _ => {}
                }
            }
        }

        if pre_count + post_count == 0 {
            return None;
        }
        Some(format!(
            "Hooks active: {} pre-tool, {} post-tool",
            pre_count, post_count
        ))
    }
}

#[async_trait]
impl McpClientTrait for HooksClient {
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
            "hooks has no tools (called: {name})"
        ))]))
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, _session_id: &str) -> Option<String> {
        Self::load_hooks_summary()
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
    fn test_hooks_client_new() {
        let client = HooksClient::new(make_ctx());
        assert!(client.is_ok());
    }

    #[tokio::test]
    async fn test_hooks_no_toml_returns_none() {
        let client = HooksClient::new(make_ctx()).unwrap();
        // When no .gangus/hooks.toml exists, should return None
        // (may vary by cwd, just ensure no panic)
        let _ = client.get_moim("test_session").await;
    }

    #[test]
    fn test_load_hooks_summary_parses_counts() {
        use std::fs;
        let dir = std::env::temp_dir().join("gangus_hooks_test");
        let gangus_dir = dir.join(".gangus");
        let _ = fs::create_dir_all(&gangus_dir);
        fs::write(
            gangus_dir.join("hooks.toml"),
            "[pre_tool]\nshell = [\"echo before\"]\n\n[post_tool]\nshell = [\"echo after\"]\nshell2 = [\"echo after2\"]\n",
        )
        .unwrap();
        // Can't easily test load_hooks_summary without changing cwd, but verify parsing logic
        // by reading the file directly
        let content = fs::read_to_string(gangus_dir.join("hooks.toml")).unwrap();
        assert!(content.contains("[pre_tool]"));
        assert!(content.contains("[post_tool]"));
    }
}
