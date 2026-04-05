"""
NEXUS MCP — Google Drive + Vertex AI Search Module
Full Drive access: list, read, create, search.
Vertex AI Search for semantic search across entire Drive.
Uses Application Default Credentials (ADC).
"""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from clients import get_clients
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.gdrive")


async def _get_drive_headers():
    """Get OAuth2 headers for Drive API."""
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/drive.file",
        ]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {creds.token}"}


def register(mcp: FastMCP):

    class DriveListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: Optional[str] = Field(None, description="Drive search query (e.g. 'name contains \"nexus\"')")
        folder_id: Optional[str] = Field(None, description="List files in specific folder by ID")
        page_size: int = Field(20, ge=1, le=100)
        mime_type: Optional[str] = Field(None, description="Filter by MIME type")

    @mcp.tool(name="gdrive_list", annotations={"readOnlyHint": True})
    async def gdrive_list(params: DriveListInput, ctx: Context) -> str:
        """List files in Google Drive. Supports search queries and folder browsing."""
        client = get_clients()["general"]
        headers = await _get_drive_headers()

        q_parts = ["trashed = false"]
        if params.query:
            q_parts.append(params.query)
        if params.folder_id:
            q_parts.append(f"'{params.folder_id}' in parents")
        if params.mime_type:
            q_parts.append(f"mimeType = '{params.mime_type}'")

        try:
            resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params={
                    "q": " and ".join(q_parts),
                    "pageSize": params.page_size,
                    "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
                    "orderBy": "modifiedTime desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            files = data.get("files", [])

            if not files:
                return "No files found."

            output = "# Google Drive Files\n\n"
            for f in files:
                icon = "📁" if "folder" in f.get("mimeType", "") else "📄"
                size = f.get("size", "—")
                if size != "—":
                    size = f"{int(size) / 1024:.1f} KB"
                output += f"{icon} **{f['name']}**\n"
                output += f"   ID: `{f['id']}` | Modified: {f.get('modifiedTime', 'N/A')[:10]} | Size: {size}\n"
                output += f"   [Open]({f.get('webViewLink', '#')})\n\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class DriveReadInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        file_id: str = Field(..., description="Google Drive file ID")
        export_mime: Optional[str] = Field(None, description="Export format: text/plain, text/csv, application/pdf, etc. For Google Docs use text/plain.")

    @mcp.tool(name="gdrive_read", annotations={"readOnlyHint": True})
    async def gdrive_read(params: DriveReadInput, ctx: Context) -> str:
        """Read/export a file from Google Drive. For Google Docs, exports as plain text by default."""
        client = get_clients()["general"]
        headers = await _get_drive_headers()

        try:
            # First get file metadata
            meta_resp = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{params.file_id}",
                headers=headers,
                params={"fields": "name,mimeType,size"},
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json()

            is_google_doc = "google-apps" in meta.get("mimeType", "")

            if is_google_doc:
                export_mime = params.export_mime or "text/plain"
                resp = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{params.file_id}/export",
                    headers=headers,
                    params={"mimeType": export_mime},
                )
            else:
                resp = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{params.file_id}",
                    headers=headers,
                    params={"alt": "media"},
                )

            resp.raise_for_status()
            content = resp.text[:30000]  # Limit content size
            return f"# {meta['name']}\n\nType: {meta['mimeType']}\n\n---\n\n{content}"
        except Exception as e:
            return f"Error reading file: {e}"

    class DriveCreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(..., description="File name")
        content: str = Field(..., description="File content (text)")
        mime_type: str = Field("text/plain", description="MIME type of content")
        folder_id: Optional[str] = Field(None, description="Parent folder ID")

    @mcp.tool(name="gdrive_create", annotations={"destructiveHint": True})
    async def gdrive_create(params: DriveCreateInput, ctx: Context) -> str:
        """Create a new file in Google Drive."""
        client = get_clients()["general"]
        headers = await _get_drive_headers()

        metadata = {"name": params.name, "mimeType": params.mime_type}
        if params.folder_id:
            metadata["parents"] = [params.folder_id]

        try:
            # Multipart upload
            import io
            boundary = "nexus_mcp_boundary"
            body = (
                f"--{boundary}\r\n"
                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {params.mime_type}\r\n\r\n"
                f"{params.content}\r\n"
                f"--{boundary}--"
            )
            headers["Content-Type"] = f"multipart/related; boundary={boundary}"
            resp = await client.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                headers=headers,
                content=body.encode(),
            )
            resp.raise_for_status()
            data = resp.json()
            return f"✅ File created: **{data['name']}**\nID: `{data['id']}`"
        except Exception as e:
            return f"Error: {e}"

    class DriveSearchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., description="Full-text search query across all Drive files")
        page_size: int = Field(10, ge=1, le=50)

    @mcp.tool(name="gdrive_search", annotations={"readOnlyHint": True})
    async def gdrive_search(params: DriveSearchInput, ctx: Context) -> str:
        """Full-text search across Google Drive. Searches file names and content."""
        client = get_clients()["general"]
        headers = await _get_drive_headers()
        try:
            resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params={
                    "q": f"fullText contains '{params.query}' and trashed = false",
                    "pageSize": params.page_size,
                    "fields": "files(id,name,mimeType,modifiedTime,webViewLink,snippet)",
                    "orderBy": "modifiedTime desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            files = data.get("files", [])
            if not files:
                return f"No results for '{params.query}'"

            output = f"# Drive Search: '{params.query}'\n\n"
            for f in files:
                output += f"📄 **{f['name']}** — {f.get('mimeType', '')}\n"
                output += f"   ID: `{f['id']}` | Modified: {f.get('modifiedTime', 'N/A')[:10]}\n"
                output += f"   [Open]({f.get('webViewLink', '#')})\n\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    # ── Vertex AI Search (semantic search over Drive) ───

    class VertexSearchInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., description="Natural language search query")
        data_store_id: str = Field(..., description="Vertex AI Search data store ID (linked to Drive)")
        page_size: int = Field(5, ge=1, le=20)

    @mcp.tool(name="vertex_search_drive", annotations={"readOnlyHint": True})
    async def vertex_search_drive(params: VertexSearchInput, ctx: Context) -> str:
        """Semantic search across Google Drive using Vertex AI Search.
        Requires a pre-configured Vertex AI Search data store linked to Drive.
        Returns ranked, relevant results with snippets.
        """
        import google.auth
        import google.auth.transport.requests

        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())

        url = (
            f"https://discoveryengine.googleapis.com/v1/projects/{cfg.GCP_PROJECT_ID}"
            f"/locations/{cfg.VERTEX_LOCATION}/dataStores/{params.data_store_id}"
            f"/servingConfigs/default_search:search"
        )

        try:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
                json={
                    "query": params.query,
                    "pageSize": params.page_size,
                    "queryExpansionSpec": {"condition": "AUTO"},
                    "spellCorrectionSpec": {"mode": "AUTO"},
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                return f"No semantic results for '{params.query}'"

            output = f"# Vertex AI Search: '{params.query}'\n\n"
            for i, r in enumerate(results, 1):
                doc = r.get("document", {})
                derived = doc.get("derivedStructData", {})
                title = derived.get("title", doc.get("id", "Untitled"))
                link = derived.get("link", "#")
                snippets = derived.get("snippets", [])
                snippet_text = snippets[0].get("snippet", "") if snippets else ""

                output += f"### {i}. {title}\n"
                output += f"   [Open]({link})\n"
                if snippet_text:
                    output += f"   > {snippet_text[:500]}\n"
                output += "\n"
            return output
        except Exception as e:
            return f"Error: {e}"

    class VertexSearchMultiInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str = Field(..., description="Natural language search query")
        data_store_ids: list[str] = Field(..., description="List of Vertex AI Search data store IDs")
        page_size: int = Field(5, ge=1, le=20)

    @mcp.tool(name="vertex_search_multistore", annotations={"readOnlyHint": True})
    async def vertex_search_multistore(params: VertexSearchMultiInput, ctx: Context) -> str:
        """Semantic search across multiple Vertex AI Search data stores.
        Merges and ranks results across stores.
        """
        import google.auth
        import google.auth.transport.requests
        import asyncio

        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}

        async def search_store(store_id: str):
            url = (
                f"https://discoveryengine.googleapis.com/v1/projects/{cfg.GCP_PROJECT_ID}"
                f"/locations/{cfg.VERTEX_LOCATION}/dataStores/{store_id}"
                f"/servingConfigs/default_search:search"
            )
            try:
                resp = await client.post(
                    url,
                    headers=headers,
                    json={
                        "query": params.query,
                        "pageSize": params.page_size,
                        "queryExpansionSpec": {"condition": "AUTO"},
                        "spellCorrectionSpec": {"mode": "AUTO"},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                for r in results:
                    r["_store_id"] = store_id
                return results
            except Exception as e:
                log.warning(f"Error searching store {store_id}: {e}")
                return []

        try:
            all_results = await asyncio.gather(*[search_store(sid) for sid in params.data_store_ids])
            merged = []
            for res_list in all_results:
                merged.extend(res_list)

            if not merged:
                return f"No semantic results for '{params.query}' across {len(params.data_store_ids)} stores."

            # Sort by relevance score (assuming higher is better, if available)
            # Vertex AI Search doesn't always return a score, so we just interleave or use what we have
            # We'll just take the top N across all
            merged = merged[:params.page_size * len(params.data_store_ids)]

            output = f"# Vertex AI Multi-Store Search: '{params.query}'\n\n"
            for i, r in enumerate(merged, 1):
                doc = r.get("document", {})
                derived = doc.get("derivedStructData", {})
                title = derived.get("title", doc.get("id", "Untitled"))
                link = derived.get("link", "#")
                snippets = derived.get("snippets", [])
                snippet_text = snippets[0].get("snippet", "") if snippets else ""
                store_id = r.get("_store_id", "unknown")

                output += f"### {i}. {title} (Store: `{store_id}`)\n"
                output += f"   [Open]({link})\n"
                if snippet_text:
                    output += f"   > {snippet_text[:500]}\n"
                output += "\n"
            return output
        except Exception as e:
            return f"Error in multi-store search: {e}"

    class VertexIndexStatusInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        data_store_id: str = Field(..., description="Vertex AI Search data store ID")

    @mcp.tool(name="vertex_index_status", annotations={"readOnlyHint": True})
    async def vertex_index_status(params: VertexIndexStatusInput, ctx: Context) -> str:
        """Check indexing status of a Vertex AI Search data store."""
        import google.auth
        import google.auth.transport.requests

        state = {"clients": get_clients(), "settings": __import__("config").settings}
        client = state["clients"]["general"]
        cfg = state["settings"]

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())

        url = (
            f"https://discoveryengine.googleapis.com/v1/projects/{cfg.GCP_PROJECT_ID}"
            f"/locations/{cfg.VERTEX_LOCATION}/dataStores/{params.data_store_id}"
        )

        try:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            resp.raise_for_status()
            data = resp.json()

            name = data.get("displayName", params.data_store_id)
            doc_count = data.get("documentCount", "unknown")
            create_time = data.get("createTime", "unknown")

            output = f"# Vertex AI Data Store Status\n\n"
            output += f"- **ID**: `{params.data_store_id}`\n"
            output += f"- **Name**: {name}\n"
            output += f"- **Document Count**: {doc_count}\n"
            output += f"- **Created**: {create_time}\n"
            
            return output
        except Exception as e:
            return f"Error checking index status: {e}"
