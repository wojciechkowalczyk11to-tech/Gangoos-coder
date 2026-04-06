use crate::agents::extension::PlatformExtensionContext;
use crate::agents::mcp_client::{Error, McpClientTrait};
use crate::agents::tool_execution::ToolCallContext;
use anyhow::Result;
use async_trait::async_trait;
use rmcp::model::{
    CallToolResult, Content, Implementation, InitializeResult, JsonObject, ListToolsResult,
    ServerCapabilities, Tool,
};
use schemars::{schema_for, JsonSchema};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tokio_util::sync::CancellationToken;

pub static EXTENSION_NAME: &str = "hooks";

/// A single hook configuration
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct Hook {
    /// Unique hook name
    pub name: String,
    /// Hook event: pre_commit, post_commit, pre_test, post_test, pre_lint, post_lint, etc.
    pub event: String,
    /// Shell commands to execute (array for multiple commands)
    pub commands: Vec<String>,
    /// Whether this hook is enabled
    pub enabled: bool,
    /// Optional description
    #[serde(default)]
    pub description: Option<String>,
    /// Timeout in seconds for hook execution
    #[serde(default)]
    pub timeout_secs: Option<u64>,
}

impl Hook {
    fn status_str(&self) -> &'static str {
        if self.enabled {
            "enabled"
        } else {
            "disabled"
        }
    }
}

/// Hooks configuration database
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct HooksConfig {
    hooks: HashMap<String, Hook>,
}

impl HooksConfig {
    /// Load from .gangoos/hooks.toml or return default with built-in hooks
    fn load_or_default() -> Self {
        let path = Self::config_file();
        if path.exists() {
            if let Ok(contents) = fs::read_to_string(&path) {
                // Try YAML first (for .toml we'd need a toml parser)
                if let Ok(config) = serde_yaml::from_str::<Self>(&contents) {
                    tracing::debug!("Loaded hooks config from {:?}", path);
                    return config;
                }
                // Fallback: try JSON
                if let Ok(config) = serde_json::from_str::<Self>(&contents) {
                    tracing::debug!("Loaded hooks config from {:?} (JSON)", path);
                    return config;
                }
            }
        }

        // Load built-in hooks
        Self::with_builtin_hooks()
    }

    /// Create config with default built-in hooks
    fn with_builtin_hooks() -> Self {
        let mut config = Self::default();

        config.add_hook(Hook {
            name: "pre_commit_check".to_string(),
            event: "pre_commit".to_string(),
            commands: vec!["cargo fmt --check".to_string(), "cargo clippy".to_string()],
            enabled: true,
            description: Some("Format and lint checks before commit".to_string()),
            timeout_secs: Some(30),
        });

        config.add_hook(Hook {
            name: "test_runner".to_string(),
            event: "pre_commit".to_string(),
            commands: vec!["cargo test".to_string()],
            enabled: false,
            description: Some("Run test suite (optional, slower)".to_string()),
            timeout_secs: Some(120),
        });

        config.add_hook(Hook {
            name: "lint_check".to_string(),
            event: "pre_commit".to_string(),
            commands: vec!["cargo clippy -- -D warnings".to_string()],
            enabled: true,
            description: Some("Strict lint checking".to_string()),
            timeout_secs: Some(30),
        });

        config
    }

    fn add_hook(&mut self, hook: Hook) {
        self.hooks.insert(hook.name.clone(), hook);
    }

    fn save(&self) -> Result<()> {
        let path = Self::config_file();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        // Save as YAML for readability
        let yaml = serde_yaml::to_string(self)?;
        fs::write(&path, yaml)?;
        tracing::debug!("Saved hooks config to {:?}", path);
        Ok(())
    }

    fn get_hook(&self, name: &str) -> Option<&Hook> {
        self.hooks.get(name)
    }

    fn get_hook_mut(&mut self, name: &str) -> Option<&mut Hook> {
        self.hooks.get_mut(name)
    }

    fn list_all(&self) -> Vec<Hook> {
        self.hooks.values().cloned().collect()
    }

    fn list_by_event(&self, event: &str) -> Vec<Hook> {
        self.hooks
            .values()
            .filter(|h| h.event == event)
            .cloned()
            .collect()
    }

    fn enable_hook(&mut self, name: &str) -> bool {
        if let Some(hook) = self.get_hook_mut(name) {
            hook.enabled = true;
            true
        } else {
            false
        }
    }

    fn disable_hook(&mut self, name: &str) -> bool {
        if let Some(hook) = self.get_hook_mut(name) {
            hook.enabled = false;
            true
        } else {
            false
        }
    }

    fn delete_hook(&mut self, name: &str) -> bool {
        self.hooks.remove(name).is_some()
    }

    fn config_file() -> PathBuf {
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        cwd.join(".gangoos").join("hooks.yaml")
    }

    fn summary(&self) -> String {
        let total = self.hooks.len();
        let enabled = self.hooks.values().filter(|h| h.enabled).count();
        format!("Hooks: {}/{} enabled", enabled, total)
    }
}

pub struct HooksClient {
    info: InitializeResult,
    config: Arc<Mutex<HooksConfig>>,
}

impl HooksClient {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        let config = HooksConfig::load_or_default();
        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("Hooks"),
            ),
            config: Arc::new(Mutex::new(config)),
        })
    }

    fn schema<T: JsonSchema>() -> JsonObject {
        serde_json::to_value(schema_for!(T))
            .expect("schema serialization ok")
            .as_object()
            .expect("schema is object")
            .clone()
    }
}

#[derive(serde::Deserialize, JsonSchema)]
struct HooksListParams {
    /// Optional event filter (e.g., "pre_commit")
    #[serde(default)]
    event: Option<String>,
}

#[derive(serde::Deserialize, JsonSchema)]
struct HooksEnableParams {
    /// Hook name to enable
    name: String,
}

#[derive(serde::Deserialize, JsonSchema)]
struct HooksDisableParams {
    /// Hook name to disable
    name: String,
}

#[derive(serde::Deserialize, JsonSchema)]
struct HooksAddParams {
    /// Hook name (unique identifier)
    name: String,
    /// Hook event type
    event: String,
    /// Array of shell commands
    commands: Vec<String>,
    /// Optional description
    #[serde(default)]
    description: Option<String>,
    /// Optional timeout in seconds
    #[serde(default)]
    timeout_secs: Option<u64>,
}

#[derive(serde::Deserialize, JsonSchema)]
struct HooksDeleteParams {
    /// Hook name to delete
    name: String,
}

#[async_trait]
impl McpClientTrait for HooksClient {
    async fn list_tools(
        &self,
        _session_id: &str,
        _next_cursor: Option<String>,
        _cancellation_token: CancellationToken,
    ) -> Result<ListToolsResult, Error> {
        let tools = vec![
            Tool::new(
                "hooks_list".to_string(),
                "List all hooks, optionally filtered by event type (e.g., 'pre_commit')."
                    .to_string(),
                Self::schema::<HooksListParams>(),
            ),
            Tool::new(
                "hooks_enable".to_string(),
                "Enable a hook by name.".to_string(),
                Self::schema::<HooksEnableParams>(),
            ),
            Tool::new(
                "hooks_disable".to_string(),
                "Disable a hook by name.".to_string(),
                Self::schema::<HooksDisableParams>(),
            ),
            Tool::new(
                "hooks_add".to_string(),
                "Add a new hook or update an existing one.".to_string(),
                Self::schema::<HooksAddParams>(),
            ),
            Tool::new(
                "hooks_delete".to_string(),
                "Delete a hook by name. Cannot be undone.".to_string(),
                Self::schema::<HooksDeleteParams>(),
            ),
        ];
        Ok(ListToolsResult {
            tools,
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
            "hooks_list" => {
                let params: HooksListParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.config.lock() {
                    Ok(config) => {
                        let hooks = if let Some(event) = params.event {
                            config.list_by_event(&event)
                        } else {
                            config.list_all()
                        };

                        if hooks.is_empty() {
                            Ok(CallToolResult::success(vec![Content::text(
                                "No hooks found.".to_string(),
                            )]))
                        } else {
                            let mut output = format!("**{} hooks**\n\n", hooks.len());
                            for hook in hooks {
                                output.push_str(&format!(
                                    "- **{}** ({}): {}\n",
                                    hook.name, hook.event, hook.status_str()
                                ));
                                if let Some(desc) = hook.description {
                                    output.push_str(&format!("  {}\n", desc));
                                }
                                for cmd in &hook.commands {
                                    output.push_str(&format!("  - {}\n", cmd));
                                }
                            }
                            Ok(CallToolResult::success(vec![Content::text(output)]))
                        }
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire config lock".to_string(),
                    )])),
                }
            }

            "hooks_enable" => {
                let params: HooksEnableParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.config.lock() {
                    Ok(mut config) => {
                        if config.enable_hook(&params.name) {
                            let _ = config.save();
                            Ok(CallToolResult::success(vec![Content::text(format!(
                                "Hook enabled: {}",
                                params.name
                            ))]))
                        } else {
                            Ok(CallToolResult::error(vec![Content::text(format!(
                                "Hook not found: {}",
                                params.name
                            ))]))
                        }
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire config lock".to_string(),
                    )])),
                }
            }

            "hooks_disable" => {
                let params: HooksDisableParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.config.lock() {
                    Ok(mut config) => {
                        if config.disable_hook(&params.name) {
                            let _ = config.save();
                            Ok(CallToolResult::success(vec![Content::text(format!(
                                "Hook disabled: {}",
                                params.name
                            ))]))
                        } else {
                            Ok(CallToolResult::error(vec![Content::text(format!(
                                "Hook not found: {}",
                                params.name
                            ))]))
                        }
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire config lock".to_string(),
                    )])),
                }
            }

            "hooks_add" => {
                let params: HooksAddParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.config.lock() {
                    Ok(mut config) => {
                        let hook = Hook {
                            name: params.name.clone(),
                            event: params.event,
                            commands: params.commands,
                            enabled: true,
                            description: params.description,
                            timeout_secs: params.timeout_secs,
                        };
                        config.add_hook(hook);
                        if let Err(e) = config.save() {
                            return Ok(CallToolResult::error(vec![Content::text(format!(
                                "Failed to save hooks: {}",
                                e
                            ))]));
                        }
                        Ok(CallToolResult::success(vec![Content::text(format!(
                            "Hook added: {}",
                            params.name
                        ))]))
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire config lock".to_string(),
                    )])),
                }
            }

            "hooks_delete" => {
                let params: HooksDeleteParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.config.lock() {
                    Ok(mut config) => {
                        if config.delete_hook(&params.name) {
                            let _ = config.save();
                            Ok(CallToolResult::success(vec![Content::text(format!(
                                "Hook deleted: {}",
                                params.name
                            ))]))
                        } else {
                            Ok(CallToolResult::error(vec![Content::text(format!(
                                "Hook not found: {}",
                                params.name
                            ))]))
                        }
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire config lock".to_string(),
                    )])),
                }
            }

            _ => Ok(CallToolResult::error(vec![Content::text(format!(
                "hooks: unknown tool '{name}'"
            ))])),
        }
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, _session_id: &str) -> Option<String> {
        match self.config.lock() {
            Ok(config) => {
                let summary = config.summary();
                if config.hooks.is_empty() {
                    return None;
                }
                Some(format!(
                    "**[Hooks Status]**\n{}\n\nUse `hooks_list`, `hooks_enable`, `hooks_disable` to manage.",
                    summary
                ))
            }
            Err(_) => None,
        }
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

    #[test]
    fn test_hooks_config_builtin() {
        let config = HooksConfig::with_builtin_hooks();
        assert!(!config.hooks.is_empty());
        assert!(config.get_hook("pre_commit_check").is_some());
    }

    #[tokio::test]
    async fn test_hooks_enable_disable() {
        use tokio_util::sync::CancellationToken;
        let client = HooksClient::new(make_ctx()).unwrap();
        let ctx = ToolCallContext {
            session_id: "test".to_string(),
            working_dir: None,
            tool_call_request_id: None,
        };
        let token = CancellationToken::new();

        // Disable a built-in hook
        let args = json!({"name": "test_runner"});
        let result = client
            .call_tool(
                &ctx,
                "hooks_disable",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await
            .unwrap();
        assert!(!result.is_error.unwrap_or(false));
    }
}
