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
use std::sync::{Arc, Mutex};
use tokio_util::sync::CancellationToken;

pub static EXTENSION_NAME: &str = "planner";

#[derive(Debug, Clone, Default)]
struct Plan {
    steps: Vec<String>,
    current: usize,
}

impl Plan {
    fn is_empty(&self) -> bool {
        self.steps.is_empty()
    }

    fn summary(&self) -> String {
        let total = self.steps.len();
        let done = self.current.min(total);
        let remaining: Vec<_> = self.steps[done..].iter().enumerate().collect();
        let mut lines = vec![format!("Plan: {done}/{total} done")];
        for (i, step) in remaining.iter().take(5) {
            lines.push(format!("  {}. {}", done + i + 1, step));
        }
        if remaining.len() > 5 {
            lines.push(format!("  ... and {} more steps", remaining.len() - 5));
        }
        lines.join("\n")
    }
}

pub struct PlannerClient {
    info: InitializeResult,
    plan: Arc<Mutex<Plan>>,
}

impl PlannerClient {
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> {
        Ok(Self {
            info: InitializeResult::new(ServerCapabilities::builder().build()).with_server_info(
                Implementation::new(EXTENSION_NAME.to_string(), "1.0.0".to_string())
                    .with_title("Planner"),
            ),
            plan: Arc::new(Mutex::new(Plan::default())),
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
struct SetPlanParams {
    /// Newline-separated list of plan steps
    steps: String,
}

#[derive(serde::Deserialize, JsonSchema)]
struct AdvancePlanParams {
    /// Number of steps to advance (default: 1)
    #[serde(default = "default_advance")]
    count: usize,
}

fn default_advance() -> usize {
    1
}

#[async_trait]
impl McpClientTrait for PlannerClient {
    async fn list_tools(
        &self,
        _session_id: &str,
        _next_cursor: Option<String>,
        _cancellation_token: CancellationToken,
    ) -> Result<ListToolsResult, Error> {
        Ok(ListToolsResult {
            tools: vec![
                Tool::new(
                    "set_plan".to_string(),
                    "Set a multi-step plan. Pass steps as newline-separated text.".to_string(),
                    Self::schema::<SetPlanParams>(),
                ),
                Tool::new(
                    "advance_plan".to_string(),
                    "Mark N steps as completed (default: 1).".to_string(),
                    Self::schema::<AdvancePlanParams>(),
                ),
                Tool::new(
                    "clear_plan".to_string(),
                    "Clear the current plan.".to_string(),
                    serde_json::json!({"type":"object","properties":{}})
                        .as_object()
                        .expect("clear_plan schema must be object")
                        .clone(),
                ),
            ],
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
            "set_plan" => {
                let params: SetPlanParams = serde_json::from_value(serde_json::Value::Object(
                    arguments.unwrap_or_default(),
                ))
                .map_err(|e| {
                    Error::McpError(rmcp::model::ErrorData::invalid_params(e.to_string(), None))
                })?;

                let steps: Vec<String> = params
                    .steps
                    .lines()
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect();

                let count = steps.len();
                if let Ok(mut plan) = self.plan.lock() {
                    *plan = Plan { steps, current: 0 };
                }
                Ok(CallToolResult::success(vec![Content::text(format!(
                    "Plan set with {count} steps."
                ))]))
            }
            "advance_plan" => {
                let params: AdvancePlanParams =
                    serde_json::from_value(serde_json::Value::Object(
                        arguments.unwrap_or_default(),
                    ))
                    .map_err(|e| {
                        Error::McpError(rmcp::model::ErrorData::invalid_params(
                            e.to_string(),
                            None,
                        ))
                    })?;

                let summary = if let Ok(mut plan) = self.plan.lock() {
                    plan.current = (plan.current + params.count).min(plan.steps.len());
                    plan.summary()
                } else {
                    "Plan lock error".to_string()
                };
                Ok(CallToolResult::success(vec![Content::text(summary)]))
            }
            "clear_plan" => {
                if let Ok(mut plan) = self.plan.lock() {
                    *plan = Plan::default();
                }
                Ok(CallToolResult::success(vec![Content::text(
                    "Plan cleared.".to_string(),
                )]))
            }
            _ => Ok(CallToolResult::error(vec![Content::text(format!(
                "planner: unknown tool: {name}"
            ))])),
        }
    }

    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }

    async fn get_moim(&self, _session_id: &str) -> Option<String> {
        let plan = self.plan.lock().ok()?;
        if plan.is_empty() {
            return None;
        }
        Some(plan.summary())
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
    async fn test_planner_empty_plan_returns_none() {
        let client = PlannerClient::new(make_ctx()).unwrap();
        let moim = client.get_moim("test_session").await;
        assert!(moim.is_none());
    }

    #[tokio::test]
    async fn test_planner_set_and_advance() {
        use tokio_util::sync::CancellationToken;
        let client = PlannerClient::new(make_ctx()).unwrap();
        let ctx = ToolCallContext {
            session_id: "test".to_string(),
            working_dir: None,
            tool_call_request_id: None,
        };
        let token = CancellationToken::new();

        // Set plan
        let args = serde_json::json!({"steps": "Step 1\nStep 2\nStep 3"});
        let result = client
            .call_tool(
                &ctx,
                "set_plan",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await
            .unwrap();
        assert!(!result.is_error.unwrap_or(false));

        // MOIM should now show plan
        let moim = client.get_moim("test").await;
        assert!(moim.is_some());
        assert!(moim.unwrap().contains("0/3"));

        // Advance
        let args = serde_json::json!({"count": 2});
        let _ = client
            .call_tool(
                &ctx,
                "advance_plan",
                Some(args.as_object().unwrap().clone()),
                token.clone(),
            )
            .await
            .unwrap();

        let moim = client.get_moim("test").await;
        assert!(moim.unwrap().contains("2/3"));
    }
}
