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
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use tokio_util::sync::CancellationToken;

pub static EXTENSION_NAME: &str = "gangus_memory";

/// In-memory storage entry with metadata
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct MemoryEntry {
    /// The stored value
    pub value: String,
    /// Optional category/tag for organization
    pub category: Option<String>,
    /// Optional description or notes
    pub notes: Option<String>,
    /// Timestamp when created (ISO 8601)
    pub created_at: String,
    /// Timestamp of last update
    pub updated_at: String,
}

/// In-memory database structure
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct MemoryDatabase {
    entries: HashMap<String, MemoryEntry>,
}

impl MemoryDatabase {
    /// Load from .gangoos/memory.json or return empty database
    fn load_or_default() -> Self {
        let path = Self::memory_file();
        if path.exists() {
            match fs::read_to_string(&path) {
                Ok(contents) => match serde_json::from_str::<Self>(&contents) {
                    Ok(db) => {
                        tracing::debug!("Loaded memory database from {:?}", path);
                        return db;
                    }
                    Err(e) => {
                        tracing::warn!("Failed to parse memory.json: {}", e);
                    }
                },
                Err(e) => {
                    tracing::warn!("Failed to read memory.json: {}", e);
                }
            }
        }
        Self::default()
    }

    /// Save database to .gangoos/memory.json
    fn save(&self) -> Result<()> {
        let path = Self::memory_file();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let json = serde_json::to_string_pretty(self)?;
        fs::write(&path, json)?;
        tracing::debug!("Saved memory database to {:?}", path);
        Ok(())
    }

    fn memory_file() -> PathBuf {
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        cwd.join(".gangoos").join("memory.json")
    }

    fn store(
        &mut self,
        key: String,
        value: String,
        category: Option<String>,
        notes: Option<String>,
    ) {
        let now = chrono::Utc::now().to_rfc3339();
        let existing_created_at = self
            .entries
            .get(&key)
            .map(|e| e.created_at.clone())
            .unwrap_or_else(|| now.clone());

        self.entries.insert(
            key,
            MemoryEntry {
                value,
                category,
                notes,
                created_at: existing_created_at,
                updated_at: now,
            },
        );
    }

    fn retrieve(&self, key: &str) -> Option<MemoryEntry> {
        self.entries.get(key).cloned()
    }

    fn search(&self, query: &str) -> Vec<(String, MemoryEntry)> {
        let query_lower = query.to_lowercase();
        self.entries
            .iter()
            .filter(|(k, v)| {
                k.to_lowercase().contains(&query_lower)
                    || v.value.to_lowercase().contains(&query_lower)
                    || v.notes
                        .as_ref()
                        .is_some_and(|n| n.to_lowercase().contains(&query_lower))
                    || v.category
                        .as_ref()
                        .is_some_and(|c| c.to_lowercase().contains(&query_lower))
            })
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect()
    }

    fn list_all(&self) -> Vec<(String, MemoryEntry)> {
        self.entries
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect()
    }

    fn forget(&mut self, key: &str) -> bool {
        self.entries.remove(key).is_some()
    }

    fn summary(&self) -> String {
        let total = self.entries.len();
        let categories: std::collections::HashSet<_> = self
            .entries
            .values()
            .filter_map(|e| e.category.as_ref())
            .collect();

        format!("Memory: {} entries, {} categories", total, categories.len())
    }
}

pub struct GangusMemoryClient {
    info: InitializeResult,
    db: std::sync::Mutex<MemoryDatabase>,
}

impl GangusMemoryClient {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        let db = MemoryDatabase::load_or_default();
        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("Gangus Memory"),
            ),
            db: std::sync::Mutex::new(db),
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
struct MemoryStoreParams {
    /// The key to store the memory under
    key: String,
    /// The value to store
    value: String,
    /// Optional category for organization (e.g., "bug", "design", "note")
    #[serde(default)]
    category: Option<String>,
    /// Optional notes/description
    #[serde(default)]
    notes: Option<String>,
}

#[derive(serde::Deserialize, JsonSchema)]
struct MemoryRetrieveParams {
    /// The key to retrieve
    key: String,
}

#[derive(serde::Deserialize, JsonSchema)]
struct MemorySearchParams {
    /// Search query (matched against keys, values, and notes)
    query: String,
}

#[derive(serde::Deserialize, JsonSchema)]
struct MemoryForgetParams {
    /// The key to forget/delete
    key: String,
}

#[async_trait]
impl McpClientTrait for GangusMemoryClient {
    async fn list_tools(
        &self,
        _session_id: &str,
        _next_cursor: Option<String>,
        _cancellation_token: CancellationToken,
    ) -> Result<ListToolsResult, Error> {
        let tools = vec![
            Tool::new(
                "memory_store".to_string(),
                "Store a key-value memory entry with optional category and notes. \
                 Persists to .gangoos/memory.json for long-term project memory."
                    .to_string(),
                Self::schema::<MemoryStoreParams>(),
            ),
            Tool::new(
                "memory_retrieve".to_string(),
                "Retrieve a memory entry by key. Returns value, category, notes, and timestamps."
                    .to_string(),
                Self::schema::<MemoryRetrieveParams>(),
            ),
            Tool::new(
                "memory_search".to_string(),
                "Search memory entries by query. Searches across keys, values, categories, and notes."
                    .to_string(),
                Self::schema::<MemorySearchParams>(),
            ),
            Tool::new(
                "memory_list".to_string(),
                "List all memory entries in the database with their metadata.".to_string(),
                serde_json::json!({"type":"object","properties":{}})
                    .as_object()
                    .expect("memory_list schema must be object")
                    .clone(),
            ),
            Tool::new(
                "memory_forget".to_string(),
                "Delete a memory entry by key. Cannot be undone.".to_string(),
                Self::schema::<MemoryForgetParams>(),
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
            "memory_store" => {
                let params: MemoryStoreParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.db.lock() {
                    Ok(mut db) => {
                        db.store(
                            params.key.clone(),
                            params.value,
                            params.category,
                            params.notes,
                        );
                        let _ = db.save();
                        Ok(CallToolResult::success(vec![Content::text(format!(
                            "Memory stored: {}",
                            params.key
                        ))]))
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire database lock".to_string(),
                    )])),
                }
            }

            "memory_retrieve" => {
                let params: MemoryRetrieveParams = serde_json::from_value(
                    serde_json::Value::Object(arguments.unwrap_or_default()),
                )
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.db.lock() {
                    Ok(db) => match db.retrieve(&params.key) {
                        Some(entry) => {
                            let result =
                                serde_json::to_string_pretty(&entry).unwrap_or_else(|_| {
                                    format!("Error serializing entry for key: {}", params.key)
                                });
                            Ok(CallToolResult::success(vec![Content::text(result)]))
                        }
                        None => Ok(CallToolResult::error(vec![Content::text(format!(
                            "Memory not found: {}",
                            params.key
                        ))])),
                    },
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire database lock".to_string(),
                    )])),
                }
            }

            "memory_search" => {
                let params: MemorySearchParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.db.lock() {
                    Ok(db) => {
                        let results = db.search(&params.query);
                        if results.is_empty() {
                            Ok(CallToolResult::success(vec![Content::text(format!(
                                "No results for query: {}",
                                params.query
                            ))]))
                        } else {
                            let mut output = format!("Found {} results:\n\n", results.len());
                            for (key, entry) in results {
                                output.push_str(&format!("**{}**\n", key));
                                output.push_str(&format!("  Value: {}\n", entry.value));
                                if let Some(cat) = entry.category {
                                    output.push_str(&format!("  Category: {}\n", cat));
                                }
                                if let Some(notes) = entry.notes {
                                    output.push_str(&format!("  Notes: {}\n", notes));
                                }
                                output.push_str(&format!("  Updated: {}\n\n", entry.updated_at));
                            }
                            Ok(CallToolResult::success(vec![Content::text(output)]))
                        }
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire database lock".to_string(),
                    )])),
                }
            }

            "memory_list" => match self.db.lock() {
                Ok(db) => {
                    let entries = db.list_all();
                    if entries.is_empty() {
                        Ok(CallToolResult::success(vec![Content::text(
                            "Memory database is empty.".to_string(),
                        )]))
                    } else {
                        let mut output = format!("Total {} memory entries:\n\n", entries.len());
                        for (key, entry) in entries {
                            output.push_str(&format!("**{}**\n", key));
                            output.push_str(&format!("  Value: {}\n", entry.value));
                            if let Some(cat) = entry.category {
                                output.push_str(&format!("  Category: {}\n", cat));
                            }
                            if let Some(notes) = entry.notes {
                                output.push_str(&format!("  Notes: {}\n", notes));
                            }
                            output.push_str(&format!("  Created: {}\n", entry.created_at));
                            output.push_str(&format!("  Updated: {}\n\n", entry.updated_at));
                        }
                        Ok(CallToolResult::success(vec![Content::text(output)]))
                    }
                }
                Err(_) => Ok(CallToolResult::error(vec![Content::text(
                    "Failed to acquire database lock".to_string(),
                )])),
            },

            "memory_forget" => {
                let params: MemoryForgetParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match self.db.lock() {
                    Ok(mut db) => {
                        if db.forget(&params.key) {
                            let _ = db.save();
                            Ok(CallToolResult::success(vec![Content::text(format!(
                                "Forgotten: {}",
                                params.key
                            ))]))
                        } else {
                            Ok(CallToolResult::error(vec![Content::text(format!(
                                "Memory not found: {}",
                                params.key
                            ))]))
                        }
                    }
                    Err(_) => Ok(CallToolResult::error(vec![Content::text(
                        "Failed to acquire database lock".to_string(),
                    )])),
                }
            }

            _ => Ok(CallToolResult::error(vec![Content::text(format!(
                "gangus_memory: unknown tool '{name}'"
            ))])),
        }
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, _session_id: &str) -> Option<String> {
        match self.db.lock() {
            Ok(db) => {
                let summary = db.summary();
                if db.entries.is_empty() {
                    return None;
                }
                Some(format!(
                    "**[Gangus Memory]**\n{}\n\nUse `memory_search`, `memory_store`, `memory_list` to manage project memories.",
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
    fn test_gangus_memory_client_new() {
        let client = GangusMemoryClient::new(make_ctx());
        assert!(client.is_ok());
    }

    #[tokio::test]
    async fn test_memory_store_and_retrieve() {
        use tokio_util::sync::CancellationToken;
        let client = GangusMemoryClient::new(make_ctx()).unwrap();
        let ctx = ToolCallContext {
            session_id: "test".to_string(),
            working_dir: None,
            tool_call_request_id: None,
        };
        let token = CancellationToken::new();

        // Store
        let args = json!({
            "key": "test_key",
            "value": "test_value",
            "category": "test"
        });
        let result = client
            .call_tool(
                &ctx,
                "memory_store",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await
            .unwrap();
        assert!(!result.is_error.unwrap_or(false));

        // Retrieve
        let args = json!({"key": "test_key"});
        let result = client
            .call_tool(
                &ctx,
                "memory_retrieve",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await
            .unwrap();
        assert!(!result.is_error.unwrap_or(false));
    }

    #[tokio::test]
    async fn test_memory_search() {
        use tokio_util::sync::CancellationToken;
        let client = GangusMemoryClient::new(make_ctx()).unwrap();
        let ctx = ToolCallContext {
            session_id: "test".to_string(),
            working_dir: None,
            tool_call_request_id: None,
        };
        let token = CancellationToken::new();

        // Store a memory
        let args = json!({
            "key": "bug_fix_123",
            "value": "Fixed authentication timeout",
            "category": "bug"
        });
        let _ = client
            .call_tool(
                &ctx,
                "memory_store",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await;

        // Search
        let args = json!({"query": "bug"});
        let result = client
            .call_tool(
                &ctx,
                "memory_search",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await
            .unwrap();
        assert!(!result.is_error.unwrap_or(false));
    }
}
