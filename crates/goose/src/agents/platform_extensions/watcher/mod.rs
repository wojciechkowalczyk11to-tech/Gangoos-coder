pub mod daemon;
pub mod git_context;
pub mod index;

use crate::agents::extension::PlatformExtensionContext;
use crate::agents::mcp_client::{Error, McpClientTrait};
use crate::agents::tool_execution::ToolCallContext;
use anyhow::Result;
use async_trait::async_trait;
use rmcp::model::{
    CallToolResult, Content, Implementation, InitializeResult, JsonObject, ListToolsResult,
    ServerCapabilities,
};
use std::path::PathBuf;
use std::sync::Arc;
use tokio_util::sync::CancellationToken;

use self::daemon::WatcherDaemon;
use self::index::ChangeType;

pub static EXTENSION_NAME: &str = "watcher";

pub struct WatcherClient {
    info: InitializeResult,
    daemon: Arc<WatcherDaemon>,
}

impl WatcherClient {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        let working_dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build())
                .with_server_info(
                    Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                        .with_title("Workspace Watcher"),
                ),
            daemon: Arc::new(WatcherDaemon::new(working_dir)),
        })
    }
}

#[async_trait]
impl McpClientTrait for WatcherClient {
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
            "watcher has no tools (called: {name})"
        ))]))
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, _session_id: &str) -> Option<String> {
        let changes = self.daemon.get_changes_since_last_call().await;
        if changes.is_empty() {
            return None;
        }

        let mut lines = vec!["**Files changed since last turn:**".to_string()];
        for change in changes.iter().take(20) {
            let label = match change.change_type {
                ChangeType::New => "NEW",
                ChangeType::Modified => "MODIFIED",
            };
            lines.push(format!("  • {} {}", label, change.path.display()));
        }
        if changes.len() > 20 {
            lines.push(format!("  ... and {} more", changes.len() - 20));
        }

        if let Some(git_status) = git_context::get_git_status(self.daemon.working_dir()) {
            lines.push(String::new());
            lines.push("**Git status:**".to_string());
            lines.push(git_status);
        }

        Some(lines.join("\n"))
    }
}
