"""
NEXUS MCP - ML Ops helpers for competitions and fast iteration loops.
Includes RunPod pod lifecycle helpers, Hugging Face helpers, Firecrawl scraping,
and log analysis/formatting tools.
"""

import json
import re
from statistics import mean
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from clients import get_clients


def _cfg():
    return __import__("config").settings


async def _request_json(client, method: str, url: str, headers: dict, body=None, params=None) -> dict:
    resp = await client.request(method, url, headers=headers, json=body, params=params)
    resp.raise_for_status()
    if resp.status_code == 204:
        return {"status": "success"}
    return resp.json()


def register(mcp: FastMCP):
    class RunPodTemplateDeployInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(..., description="New pod name")
        template_id: Optional[str] = Field(None, description="RunPod template id. Uses RUNPOD_TEMPLATE_ID if omitted.")
        gpu_count: int = Field(1, ge=1, le=8)

    @mcp.tool(name="runpod_deploy_from_template", annotations={"destructiveHint": True})
    async def runpod_deploy_from_template(params: RunPodTemplateDeployInput, ctx: Context) -> str:
        """Deploy a new RunPod pod from template id via GraphQL."""
        cfg = _cfg()
        key = cfg.RUNPOD_API_KEY
        template_id = params.template_id or cfg.RUNPOD_TEMPLATE_ID
        if not key:
            return "Error: RUNPOD_API_KEY is not set."
        if not template_id:
            return "Error: template_id is required (or set RUNPOD_TEMPLATE_ID)."

        client = get_clients()["general"]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        query = """
mutation Deploy($input: PodFindAndDeployOnDemandInput!) {
  podFindAndDeployOnDemand(input: $input) {
    id
    name
    desiredStatus
    imageName
    costPerHr
  }
}
"""
        variables = {
            "input": {
                "name": params.name,
                "templateId": template_id,
                "gpuCount": params.gpu_count,
            }
        }
        try:
            data = await _request_json(
                client,
                "POST",
                "https://api.runpod.io/graphql",
                headers=headers,
                body={"query": query, "variables": variables},
            )
            pod = data.get("data", {}).get("podFindAndDeployOnDemand")
            if not pod:
                return f"Error: {json.dumps(data)[:1200]}"
            return (
                "RunPod pod deployed.\n"
                f"id: {pod.get('id')}\n"
                f"name: {pod.get('name')}\n"
                f"status: {pod.get('desiredStatus')}\n"
                f"costPerHr: {pod.get('costPerHr')}"
            )
        except Exception as e:
            return f"Error: {e}"

    class RunPodPodActionInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        pod_id: str = Field(..., description="RunPod pod id")
        action: str = Field(..., description="Action: stop, resume, terminate")

    @mcp.tool(name="runpod_pod_action", annotations={"destructiveHint": True})
    async def runpod_pod_action(params: RunPodPodActionInput, ctx: Context) -> str:
        """Stop/resume/terminate a RunPod pod."""
        cfg = _cfg()
        key = cfg.RUNPOD_API_KEY
        if not key:
            return "Error: RUNPOD_API_KEY is not set."
        if params.action not in {"stop", "resume", "terminate"}:
            return "Error: action must be one of stop/resume/terminate."

        mutation_map = {
            "stop": "mutation($id:String!){ podStop(input:{podId:$id}) }",
            "resume": "mutation($id:String!){ podResume(input:{podId:$id}) }",
            "terminate": "mutation($id:String!){ podTerminate(input:{podId:$id}) }",
        }
        client = get_clients()["general"]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            data = await _request_json(
                client,
                "POST",
                "https://api.runpod.io/graphql",
                headers=headers,
                body={"query": mutation_map[params.action], "variables": {"id": params.pod_id}},
            )
            return f"RunPod action `{params.action}` sent for pod `{params.pod_id}`.\n{json.dumps(data)[:800]}"
        except Exception as e:
            return f"Error: {e}"

    class HFModelSearchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., description="Search query, e.g. tiny language model")
        limit: int = Field(10, ge=1, le=50)

    @mcp.tool(name="hf_model_search", annotations={"readOnlyHint": True})
    async def hf_model_search(params: HFModelSearchInput, ctx: Context) -> str:
        """Search models on Hugging Face Hub."""
        cfg = _cfg()
        client = get_clients()["general"]
        headers = {"Content-Type": "application/json"}
        if cfg.HUGGINGFACE_TOKEN:
            headers["Authorization"] = f"Bearer {cfg.HUGGINGFACE_TOKEN}"
        try:
            data = await _request_json(
                client,
                "GET",
                "https://huggingface.co/api/models",
                headers=headers,
                params={"search": params.query, "limit": params.limit},
            )
            output = f"# HF Models ({len(data)})\n\n"
            for m in data:
                output += (
                    f"- **{m.get('id', 'unknown')}** | downloads: {m.get('downloads', 'n/a')} | "
                    f"likes: {m.get('likes', 'n/a')}\n"
                )
            return output
        except Exception as e:
            return f"Error: {e}"

    class HFModelCardInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        model_id: str = Field(..., description="Model id on Hugging Face, e.g. Qwen/Qwen2.5-0.5B")

    @mcp.tool(name="hf_model_info", annotations={"readOnlyHint": True})
    async def hf_model_info(params: HFModelCardInput, ctx: Context) -> str:
        """Get detailed metadata for a Hugging Face model."""
        cfg = _cfg()
        client = get_clients()["general"]
        headers = {"Content-Type": "application/json"}
        if cfg.HUGGINGFACE_TOKEN:
            headers["Authorization"] = f"Bearer {cfg.HUGGINGFACE_TOKEN}"
        try:
            url = f"https://huggingface.co/api/models/{params.model_id}"
            data = await _request_json(client, "GET", url, headers=headers)
            tags = ", ".join(data.get("tags", [])[:15])
            return (
                f"# HF Model: {params.model_id}\n\n"
                f"- private: {data.get('private', False)}\n"
                f"- downloads: {data.get('downloads', 'n/a')}\n"
                f"- likes: {data.get('likes', 'n/a')}\n"
                f"- tags: {tags}\n"
            )
        except Exception as e:
            return f"Error: {e}"

    class FirecrawlScrapeInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., description="Target URL to scrape")
        formats: list[str] = Field(["markdown"], description="Output formats, e.g. markdown, html")

    @mcp.tool(name="firecrawl_scrape", annotations={"readOnlyHint": True})
    async def firecrawl_scrape(params: FirecrawlScrapeInput, ctx: Context) -> str:
        """Scrape webpage via Firecrawl API."""
        cfg = _cfg()
        key = cfg.FIRECRAWL_API_KEY
        if not key:
            return "Error: FIRECRAWL_API_KEY is not set."
        client = get_clients()["general"]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"url": params.url, "formats": params.formats}
        try:
            data = await _request_json(
                client,
                "POST",
                "https://api.firecrawl.dev/v1/scrape",
                headers=headers,
                body=body,
            )
            payload = data.get("data", {})
            md = payload.get("markdown", "")
            if md:
                return f"# Firecrawl Scrape\n\n{md[:12000]}"
            return json.dumps(data)[:12000]
        except Exception as e:
            return f"Error: {e}"

    class TrainingLogAnalyzeInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        raw_log: str = Field(..., description="Raw training log text.")

    @mcp.tool(name="training_log_analyze", annotations={"readOnlyHint": True})
    async def training_log_analyze(params: TrainingLogAnalyzeInput, ctx: Context) -> str:
        """Extract useful metrics from raw training logs."""
        txt = params.raw_log
        losses = [float(x) for x in re.findall(r"(?:loss|train_loss)[=: ]+([0-9]*\\.?[0-9]+)", txt, flags=re.I)]
        lrs = [float(x) for x in re.findall(r"(?:lr|learning[_ ]?rate)[=: ]+([0-9.eE+-]+)", txt, flags=re.I)]
        steps = [int(x) for x in re.findall(r"(?:step)[=: ]+([0-9]+)", txt, flags=re.I)]
        nan_hits = len(re.findall(r"\\bnan\\b|overflow|diverg", txt, flags=re.I))
        oom_hits = len(re.findall(r"out of memory|cuda oom|oom", txt, flags=re.I))

        lines = ["# Training Log Analysis", ""]
        lines.append(f"- steps_detected: {len(steps)}")
        if steps:
            lines.append(f"- max_step: {max(steps)}")
        lines.append(f"- loss_points: {len(losses)}")
        if losses:
            lines.append(f"- first_loss: {losses[0]:.6f}")
            lines.append(f"- last_loss: {losses[-1]:.6f}")
            lines.append(f"- mean_loss: {mean(losses):.6f}")
            trend = "down" if losses[-1] < losses[0] else "up_or_flat"
            lines.append(f"- loss_trend: {trend}")
        lines.append(f"- lr_points: {len(lrs)}")
        if lrs:
            lines.append(f"- last_lr: {lrs[-1]}")
        lines.append(f"- nan_or_divergence_markers: {nan_hits}")
        lines.append(f"- oom_markers: {oom_hits}")

        actions = []
        if nan_hits > 0:
            actions.append("Reduce learning rate and enable gradient clipping.")
        if oom_hits > 0:
            actions.append("Lower batch size or use gradient accumulation/checkpointing.")
        if losses and losses[-1] >= losses[0]:
            actions.append("Tune LR schedule and warmup, verify data quality.")
        if not actions:
            actions.append("Run looks stable. Continue and validate on held-out set.")

        lines.append("")
        lines.append("## Suggested next actions")
        for a in actions:
            lines.append(f"- {a}")
        return "\n".join(lines)

    class ExperimentFormatInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        title: str = Field(..., description="Experiment/run title")
        objective: str = Field(..., description="Objective, e.g. maximize score under size/time limits")
        metrics_json: str = Field(..., description="JSON with final metrics")
        notes: str = Field("", description="Additional notes")

    @mcp.tool(name="experiment_report_format", annotations={"readOnlyHint": True})
    async def experiment_report_format(params: ExperimentFormatInput, ctx: Context) -> str:
        """Format a compact experiment report for leaderboard iteration."""
        try:
            metrics = json.loads(params.metrics_json)
        except Exception:
            return "Error: metrics_json must be valid JSON string."

        lines = [
            f"# {params.title}",
            "",
            f"## Objective\n{params.objective}",
            "",
            "## Metrics",
        ]
        for k, v in metrics.items():
            lines.append(f"- {k}: {v}")
        lines.extend(
            [
                "",
                "## Decision",
                "- Keep if score improved and constraints still pass.",
                "- Otherwise rollback and change one major variable only.",
                "",
                "## Notes",
                params.notes or "n/a",
            ]
        )
        return "\n".join(lines)
