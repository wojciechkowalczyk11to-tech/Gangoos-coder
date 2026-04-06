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

pub static EXTENSION_NAME: &str = "planner";

/// Represents a single step in a plan
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct PlanStep {
    /// The step description
    pub description: String,
    /// Current status: pending, in_progress, completed, blocked
    pub status: String,
    /// Optional notes on the step
    #[serde(default)]
    pub notes: Option<String>,
    /// Dependencies: list of step indices that must complete first
    #[serde(default)]
    pub depends_on: Vec<usize>,
    /// When this step was created
    pub created_at: String,
    /// When this step was completed (if at all)
    #[serde(default)]
    pub completed_at: Option<String>,
}

/// A complete plan with metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    /// Unique plan ID (filename base)
    pub id: String,
    /// Human-readable plan title
    pub title: String,
    /// Plan description/context
    pub description: Option<String>,
    /// List of steps
    pub steps: Vec<PlanStep>,
    /// Overall plan status
    pub status: String, // active, paused, completed
    /// Creation timestamp
    pub created_at: String,
    /// Last update timestamp
    pub updated_at: String,
}

impl Plan {
    fn new(id: String, title: String, description: Option<String>) -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        Self {
            id,
            title,
            description,
            steps: Vec::new(),
            status: "active".to_string(),
            created_at: now.clone(),
            updated_at: now,
        }
    }

    fn add_step(&mut self, desc: String, depends_on: Vec<usize>) {
        let now = chrono::Utc::now().to_rfc3339();
        self.steps.push(PlanStep {
            description: desc,
            status: "pending".to_string(),
            notes: None,
            depends_on,
            created_at: now,
            completed_at: None,
        });
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    fn update_step(&mut self, index: usize, status: String, notes: Option<String>) -> bool {
        if index >= self.steps.len() {
            return false;
        }
        self.steps[index].status = status.clone();
        self.steps[index].notes = notes;
        if status == "completed" {
            self.steps[index].completed_at = Some(chrono::Utc::now().to_rfc3339());
        }
        self.updated_at = chrono::Utc::now().to_rfc3339();
        true
    }

    fn progress(&self) -> (usize, usize) {
        let completed = self
            .steps
            .iter()
            .filter(|s| s.status == "completed")
            .count();
        (completed, self.steps.len())
    }

    fn summary(&self) -> String {
        let (done, total) = self.progress();
        let mut lines = vec![
            format!("**Plan: {}**", self.title),
            format!("Progress: {}/{} steps completed", done, total),
            String::new(),
        ];

        // Show next 5 pending/in-progress steps
        let mut shown = 0;
        for (i, step) in self.steps.iter().enumerate() {
            if shown >= 5 {
                break;
            }
            if step.status != "completed" {
                let status_icon = match step.status.as_str() {
                    "in_progress" => "▶",
                    "blocked" => "⚠",
                    _ => "○",
                };
                lines.push(format!(
                    "  {} [{}] {}. {}",
                    status_icon,
                    step.status,
                    i + 1,
                    step.description
                ));
                shown += 1;
            }
        }

        if self.steps.len() > shown {
            lines.push(format!("  ... and {} more steps", self.steps.len() - shown));
        }

        lines.join("\n")
    }

    fn save(&self) -> Result<()> {
        let plans_dir = Self::plans_dir();
        fs::create_dir_all(&plans_dir)?;
        let path = plans_dir.join(format!("{}.json", self.id));
        let json = serde_json::to_string_pretty(self)?;
        fs::write(&path, json)?;
        tracing::debug!("Saved plan {} to {:?}", self.id, path);
        Ok(())
    }

    fn load(id: &str) -> Result<Self> {
        let plans_dir = Self::plans_dir();
        let path = plans_dir.join(format!("{}.json", id));
        if !path.exists() {
            return Err(anyhow::anyhow!("Plan not found: {}", id));
        }
        let contents = fs::read_to_string(&path)?;
        Ok(serde_json::from_str(&contents)?)
    }

    fn list_all() -> Result<Vec<Plan>> {
        let plans_dir = Self::plans_dir();
        let mut plans = Vec::new();
        if !plans_dir.exists() {
            return Ok(plans);
        }
        for entry in fs::read_dir(&plans_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                if let Ok(contents) = fs::read_to_string(&path) {
                    if let Ok(plan) = serde_json::from_str::<Plan>(&contents) {
                        plans.push(plan);
                    }
                }
            }
        }
        Ok(plans)
    }

    fn delete(id: &str) -> Result<()> {
        let plans_dir = Self::plans_dir();
        let path = plans_dir.join(format!("{}.json", id));
        if path.exists() {
            fs::remove_file(&path)?;
        }
        Ok(())
    }

    fn plans_dir() -> PathBuf {
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        cwd.join(".gangoos").join("plans")
    }
}

pub struct PlannerClient {
    info: InitializeResult,
    /// In-memory cache of active plan (for MOIM)
    active_plan: Arc<Mutex<Option<Plan>>>,
}

impl PlannerClient {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        // Try to load the most recently updated plan as active
        let active = if let Ok(plans) = Plan::list_all() {
            plans.into_iter().max_by_key(|p| p.updated_at.clone())
        } else {
            None
        };

        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("Planner"),
            ),
            active_plan: Arc::new(Mutex::new(active)),
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
struct PlanCreateParams {
    /// Human-readable plan title
    title: String,
    /// Optional plan description
    #[serde(default)]
    description: Option<String>,
    /// Newline-separated list of initial steps (optional)
    #[serde(default)]
    steps: Option<String>,
}

#[derive(serde::Deserialize, JsonSchema)]
struct PlanUpdateStepParams {
    /// Plan ID
    plan_id: String,
    /// Step index (0-based)
    step_index: usize,
    /// New status: pending, in_progress, completed, blocked
    status: String,
    /// Optional notes
    #[serde(default)]
    notes: Option<String>,
}

#[derive(serde::Deserialize, JsonSchema)]
struct PlanGetParams {
    /// Plan ID to retrieve
    plan_id: String,
}

#[derive(serde::Deserialize, JsonSchema)]
struct PlanDeleteParams {
    /// Plan ID to delete
    plan_id: String,
}

#[async_trait]
impl McpClientTrait for PlannerClient {
    async fn list_tools(
        &self,
        _session_id: &str,
        _next_cursor: Option<String>,
        _cancellation_token: CancellationToken,
    ) -> Result<ListToolsResult, Error> {
        let tools = vec![
            Tool::new(
                "plan_create".to_string(),
                "Create a new plan with optional initial steps. Returns plan ID.".to_string(),
                Self::schema::<PlanCreateParams>(),
            ),
            Tool::new(
                "plan_update_step".to_string(),
                "Update a step's status (pending, in_progress, completed, blocked) and notes."
                    .to_string(),
                Self::schema::<PlanUpdateStepParams>(),
            ),
            Tool::new(
                "plan_get".to_string(),
                "Retrieve full details of a plan by ID.".to_string(),
                Self::schema::<PlanGetParams>(),
            ),
            Tool::new(
                "plan_list".to_string(),
                "List all plans with their current status and progress.".to_string(),
                serde_json::json!({"type":"object","properties":{}})
                    .as_object()
                    .expect("plan_list schema")
                    .clone(),
            ),
            Tool::new(
                "plan_delete".to_string(),
                "Delete a plan and all its steps. Cannot be undone.".to_string(),
                Self::schema::<PlanDeleteParams>(),
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
            "plan_create" => {
                let params: PlanCreateParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                let plan_id = format!("plan_{}", chrono::Utc::now().timestamp_millis() % 1_000_000);
                let mut plan = Plan::new(plan_id.clone(), params.title, params.description);

                if let Some(steps_text) = params.steps {
                    for step_desc in steps_text.lines() {
                        let trimmed = step_desc.trim();
                        if !trimmed.is_empty() {
                            plan.add_step(trimmed.to_string(), Vec::new());
                        }
                    }
                }

                if let Err(e) = plan.save() {
                    return Ok(CallToolResult::error(vec![Content::text(format!(
                        "Failed to save plan: {}",
                        e
                    ))]));
                }

                // Set as active
                if let Ok(mut active) = self.active_plan.lock() {
                    *active = Some(plan.clone());
                }

                Ok(CallToolResult::success(vec![Content::text(format!(
                    "Plan created: {} ({} steps)",
                    plan_id,
                    plan.steps.len()
                ))]))
            }

            "plan_update_step" => {
                let params: PlanUpdateStepParams = serde_json::from_value(
                    serde_json::Value::Object(arguments.unwrap_or_default()),
                )
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match Plan::load(&params.plan_id) {
                    Ok(mut plan) => {
                        if plan.update_step(params.step_index, params.status.clone(), params.notes)
                        {
                            if let Err(e) = plan.save() {
                                return Ok(CallToolResult::error(vec![Content::text(format!(
                                    "Failed to save plan: {}",
                                    e
                                ))]));
                            }
                            // Update active cache
                            if let Ok(mut active) = self.active_plan.lock() {
                                *active = Some(plan.clone());
                            }
                            let (done, total) = plan.progress();
                            Ok(CallToolResult::success(vec![Content::text(format!(
                                "Step {} updated to '{}'. Progress: {}/{}",
                                params.step_index, params.status, done, total
                            ))]))
                        } else {
                            Ok(CallToolResult::error(vec![Content::text(format!(
                                "Invalid step index: {}",
                                params.step_index
                            ))]))
                        }
                    }
                    Err(e) => Ok(CallToolResult::error(vec![Content::text(format!(
                        "Failed to load plan: {}",
                        e
                    ))])),
                }
            }

            "plan_get" => {
                let params: PlanGetParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match Plan::load(&params.plan_id) {
                    Ok(plan) => {
                        let mut output = format!("**{}**\n", plan.title);
                        if let Some(desc) = plan.description {
                            output.push_str(&format!("Description: {}\n\n", desc));
                        }
                        let (done, total) = plan.progress();
                        output.push_str(&format!("Progress: {}/{} steps\n\n", done, total));
                        for (i, step) in plan.steps.iter().enumerate() {
                            output.push_str(&format!(
                                "{}. [{}] {}\n",
                                i + 1,
                                step.status,
                                step.description
                            ));
                            if !step.depends_on.is_empty() {
                                output.push_str(&format!("   Depends on: {:?}\n", step.depends_on));
                            }
                            if let Some(notes) = &step.notes {
                                output.push_str(&format!("   Notes: {}\n", notes));
                            }
                        }
                        Ok(CallToolResult::success(vec![Content::text(output)]))
                    }
                    Err(e) => Ok(CallToolResult::error(vec![Content::text(format!(
                        "Plan not found: {}",
                        e
                    ))])),
                }
            }

            "plan_list" => match Plan::list_all() {
                Ok(plans) => {
                    if plans.is_empty() {
                        Ok(CallToolResult::success(vec![Content::text(
                            "No plans found.".to_string(),
                        )]))
                    } else {
                        let mut output = format!("**{} plans**\n\n", plans.len());
                        for plan in &plans {
                            let (done, total) = plan.progress();
                            output.push_str(&format!(
                                "- **{}** ({}): {}/{} done\n",
                                plan.id, plan.status, done, total
                            ));
                        }
                        Ok(CallToolResult::success(vec![Content::text(output)]))
                    }
                }
                Err(e) => Ok(CallToolResult::error(vec![Content::text(format!(
                    "Failed to list plans: {}",
                    e
                ))])),
            },

            "plan_delete" => {
                let params: PlanDeleteParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                match Plan::delete(&params.plan_id) {
                    Ok(_) => {
                        // Clear active if it was this plan
                        if let Ok(mut active) = self.active_plan.lock() {
                            if let Some(ref p) = *active {
                                if p.id == params.plan_id {
                                    *active = None;
                                }
                            }
                        }
                        Ok(CallToolResult::success(vec![Content::text(format!(
                            "Plan deleted: {}",
                            params.plan_id
                        ))]))
                    }
                    Err(e) => Ok(CallToolResult::error(vec![Content::text(format!(
                        "Failed to delete plan: {}",
                        e
                    ))])),
                }
            }

            _ => Ok(CallToolResult::error(vec![Content::text(format!(
                "planner: unknown tool '{name}'"
            ))])),
        }
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, _session_id: &str) -> Option<String> {
        match self.active_plan.lock() {
            Ok(guard) => guard
                .as_ref()
                .map(|plan| format!("**[Active Plan]**\n{}", plan.summary())),
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
    fn test_planner_client_new() {
        let client = PlannerClient::new(make_ctx());
        assert!(client.is_ok());
    }

    #[tokio::test]
    async fn test_plan_create_and_update() {
        use tokio_util::sync::CancellationToken;
        let client = PlannerClient::new(make_ctx()).unwrap();
        let ctx = ToolCallContext {
            session_id: "test".to_string(),
            working_dir: None,
            tool_call_request_id: None,
        };
        let token = CancellationToken::new();

        // Create plan
        let args = json!({
            "title": "Test Plan",
            "steps": "Step 1\nStep 2"
        });
        let result = client
            .call_tool(
                &ctx,
                "plan_create",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await
            .unwrap();
        assert!(!result.is_error.unwrap_or(false));
    }
}
