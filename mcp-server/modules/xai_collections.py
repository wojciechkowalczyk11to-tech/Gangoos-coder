"""NEXUS MCP — xAI Collections & Knowledge Module
Tools for xAI Responses API: vector store search, web search, file upload.
"""
import json, logging, os
from typing import Optional
from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.xai")
DEFAULT_COLLECTION_ID = os.getenv("NEXUS_TOOLS_COLLECTION_ID", "collection_3a79cc0c-997c-4871-8373-ff2ce5c54ee2")
XAI_BASE_URL = "https://api.x.ai/v1"

def _xai_headers() -> dict:
    api_key = os.getenv("XAI_API_KEY", "")
    if not api_key:
        raise ValueError("XAI_API_KEY environment variable is not set")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

def _parse_responses_output(data: dict) -> str:
    try:
        texts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    texts.append(content["text"])
        if texts:
            return "\n\n".join(texts)
    except (KeyError, TypeError, AttributeError):
        pass
    if "output_text" in data:
        return data["output_text"]
    return f"[xAI response parse error]\n{json.dumps(data, indent=2)[:2000]}"

def register(mcp: FastMCP):
    class XAICollectionSearchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., description="Natural language search query for the vector store", min_length=1, max_length=10000)
        collection_id: str = Field(default=DEFAULT_COLLECTION_ID, description="xAI vector store / collection ID to search")
        model: str = Field(default="grok-4-1-fast-reasoning", description="Grok model to use for the Responses API call")

    @mcp.tool(name="xai_collection_search", annotations={"title": "Search xAI Vector Store Collection", "readOnlyHint": True, "openWorldHint": True})
    async def xai_collection_search(params: XAICollectionSearchInput, ctx: Context) -> str:
        """Search a xAI vector store (collection) using the Responses API with\n        collections_search tool. Returns Grok's synthesized answer based on\n        documents in the collection.\n\n        Uses POST https://api.x.ai/v1/responses with:\n          tools: [{\"type\": \"file_search\", \"vector_store_ids\": [...]}]\n        """
        client = get_clients()["general"]
        try:
            headers = _xai_headers()
        except ValueError as e:
            return f"Error: {e}"
        payload = {"model": params.model, "input": [{"role": "user", "content": params.query}], "tools": [{"type": "file_search", "vector_store_ids": [params.collection_id], "max_num_results": 10}]}
        try:
            resp = await client.post(f"{XAI_BASE_URL}/responses", headers=headers, json=payload, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()
            result = _parse_responses_output(data)
            log.info(f"xai_collection_search: query='{params.query[:50]}' collection={params.collection_id}")
            return f"**xAI Collection Search** — `{params.collection_id}`\n\n{result}"
        except Exception as e:
            return f"Error searching xAI collection: {e}"

    class XAICollectionListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        limit: int = Field(20, ge=1, le=100, description="Max number of collections to return")

    @mcp.tool(name="xai_collection_list", annotations={"title": "List xAI Collections", "readOnlyHint": True})
    async def xai_collection_list(params: XAICollectionListInput, ctx: Context) -> str:
        """List all xAI vector store collections (knowledge bases) available to this API key.\n        Returns collection IDs, names, and file counts.\n        Uses GET https://api.x.ai/v1/vector-stores\n        """
        client = get_clients()["general"]
        try:
            headers = _xai_headers()
        except ValueError as e:
            return f"Error: {e}"
        try:
            resp = await client.get(f"{XAI_BASE_URL}/vector-stores", headers=headers, params={"limit": params.limit}, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            stores = data.get("data", [])
            if not stores:
                return "No xAI vector store collections found."
            output = f"# xAI Collections ({len(stores)})\n\n"
            for s in stores:
                output += f"### {s.get('name','Unnamed')}\n- **ID**: `{s.get('id','?')}`\n- **Status**: {s.get('status','?')}\n\n"
            return output
        except Exception as e:
            return f"Error listing xAI collections: {e}"

    class XAICollectionUploadInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        collection_id: str = Field(default=DEFAULT_COLLECTION_ID, description="xAI vector store ID to upload the file to")
        file_path: str = Field(..., description="Local file path on the server to upload (e.g. /workspace/docs/notes.md)")
        filename: Optional[str] = Field(None, description="Override filename (defaults to basename of file_path)")

    @mcp.tool(name="xai_collection_upload", annotations={"title": "Upload File to xAI Collection", "destructiveHint": False})
    async def xai_collection_upload(params: XAICollectionUploadInput, ctx: Context) -> str:
        """Upload a local file to an xAI vector store collection.\n        Step 1: POST /v1/files with purpose=collection to upload the file.\n        Step 2: POST /v1/vector-stores/{collection_id}/files to attach it.\n        Supports: .txt, .md, .pdf, .json, .csv, .py, .js, .ts, .html\n        """
        import os, httpx
        client = get_clients()["general"]
        try:
            headers_auth = _xai_headers()
        except ValueError as e:
            return f"Error: {e}"
        if not os.path.exists(params.file_path):
            return f"Error: File not found: {params.file_path}"
        filename = params.filename or os.path.basename(params.file_path)
        try:
            with open(params.file_path, "rb") as f:
                file_content = f.read()
            upload_headers = {"Authorization": headers_auth["Authorization"]}
            async with httpx.AsyncClient(timeout=120.0) as uc:
                upload_resp = await uc.post(f"{XAI_BASE_URL}/files", headers=upload_headers, files={"file": (filename, file_content)}, data={"purpose": "collection"})
            upload_resp.raise_for_status()
            file_id = upload_resp.json().get("id")
            if not file_id:
                return f"Error: No file_id returned"
            attach_resp = await client.post(f"{XAI_BASE_URL}/vector-stores/{params.collection_id}/files", headers=headers_auth, json={"file_id": file_id}, timeout=60.0)
            attach_resp.raise_for_status()
            return f"Uploaded {filename} -> file_id={file_id} -> collection={params.collection_id}"
        except Exception as e:
            return f"Error uploading: {e}"

    class XAIWebSearchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., description="Search query", min_length=1, max_length=10000)
        model: str = Field(default="grok-4-1-fast-reasoning", description="Grok model to use")
        include_x_search: bool = Field(True, description="Also search X (Twitter) posts in addition to web")

    @mcp.tool(name="xai_web_search", annotations={"title": "Grok Web + X Search", "readOnlyHint": True, "openWorldHint": True})
    async def xai_web_search(params: XAIWebSearchInput, ctx: Context) -> str:
        """Search the web (and optionally X/Twitter) using Grok's Responses API.\n        Returns Grok's synthesized answer with citations.\n        Uses tools: web_search + x_search (optional).\n\n        Ideal for: real-time information, news, current events, technical research.\n        """
        client = get_clients()["general"]
        try:
            headers = _xai_headers()
        except ValueError as e:
            return f"Error: {e}"
        tools = [{"type": "web_search"}]
        if params.include_x_search:
            tools.append({"type": "x_search"})
        payload = {"model": params.model, "input": [{"role": "user", "content": params.query}], "tools": tools}
        try:
            resp = await client.post(f"{XAI_BASE_URL}/responses", headers=headers, json=payload, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()
            result = _parse_responses_output(data)
            return f"**Grok Web Search**\n\n{result}"
        except Exception as e:
            return f"Error in xAI web search: {e}"