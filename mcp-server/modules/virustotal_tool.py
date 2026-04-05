"""
VirusTotal Tool — scan files, URLs, domains, IPs for malware/threats.
Free API: 4 requests/minute, 500/day.
"""
import os, json, urllib.request, urllib.parse
from mcp.server.fastmcp import FastMCP

VT_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
VT_BASE = "https://www.virustotal.com/api/v3"


def _vt_request(method, path, body=None):
    if not VT_KEY:
        return {"error": "VIRUSTOTAL_API_KEY not set"}
    headers = {"x-apikey": VT_KEY, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(f"{VT_BASE}{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def _format_stats(attrs):
    stats = attrs.get("last_analysis_stats", {})
    return {
        "malicious": stats.get("malicious", 0),
        "suspicious": stats.get("suspicious", 0),
        "harmless": stats.get("harmless", 0),
        "undetected": stats.get("undetected", 0),
        "reputation": attrs.get("reputation", "N/A"),
    }


def register(mcp: FastMCP):
    @mcp.tool(name="vt_scan_url", annotations={"title": "Scan URL with VirusTotal", "destructiveHint": False})
    async def vt_scan_url(params: dict) -> str:
        """
        Submit a URL for scanning and get analysis results.
        params: url (str, required)
        """
        url = params.get("url", "")
        if not url:
            return "Error: 'url' is required"

        # Submit URL for scanning
        data = urllib.parse.urlencode({"url": url}).encode()
        headers = {"x-apikey": VT_KEY, "Content-Type": "application/x-www-form-urlencoded"}
        try:
            req = urllib.request.Request(f"{VT_BASE}/urls", data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                submit = json.loads(r.read())
        except Exception as e:
            return json.dumps({"error": f"Submit failed: {e}"})

        # Get URL report using URL ID (base64 of URL without padding)
        import base64
        url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        result = _vt_request("GET", f"/urls/{url_id}")
        if "error" in result:
            return json.dumps(result)

        attrs = result.get("data", {}).get("attributes", {})
        return json.dumps({
            "url": url,
            "analysis": _format_stats(attrs),
            "categories": attrs.get("categories", {}),
            "title": attrs.get("title", ""),
            "final_url": attrs.get("last_final_url", url),
        })

    @mcp.tool(name="vt_scan_domain", annotations={"title": "Check domain reputation on VirusTotal", "destructiveHint": False})
    async def vt_scan_domain(params: dict) -> str:
        """
        Get VirusTotal report for a domain.
        params: domain (str, required)
        """
        domain = params.get("domain", "")
        if not domain:
            return "Error: 'domain' is required"

        result = _vt_request("GET", f"/domains/{domain}")
        if "error" in result:
            return json.dumps(result)

        attrs = result.get("data", {}).get("attributes", {})
        return json.dumps({
            "domain": domain,
            "analysis": _format_stats(attrs),
            "registrar": attrs.get("registrar", ""),
            "creation_date": attrs.get("creation_date", ""),
            "whois": attrs.get("whois", "")[:300],
            "dns_records": attrs.get("last_dns_records", [])[:5],
        })

    @mcp.tool(name="vt_scan_ip", annotations={"title": "Check IP reputation on VirusTotal", "destructiveHint": False})
    async def vt_scan_ip(params: dict) -> str:
        """
        Get VirusTotal report for an IP address.
        params: ip (str, required)
        """
        ip = params.get("ip", "")
        if not ip:
            return "Error: 'ip' is required"

        result = _vt_request("GET", f"/ip_addresses/{ip}")
        if "error" in result:
            return json.dumps(result)

        attrs = result.get("data", {}).get("attributes", {})
        return json.dumps({
            "ip": ip,
            "analysis": _format_stats(attrs),
            "as_owner": attrs.get("as_owner", ""),
            "asn": attrs.get("asn", ""),
            "country": attrs.get("country", ""),
            "network": attrs.get("network", ""),
        })

    @mcp.tool(name="vt_scan_hash", annotations={"title": "Check file hash on VirusTotal", "destructiveHint": False})
    async def vt_scan_hash(params: dict) -> str:
        """
        Get VirusTotal report for a file by hash (MD5, SHA1, or SHA256).
        params: hash (str, required)
        """
        file_hash = params.get("hash", "")
        if not file_hash:
            return "Error: 'hash' is required (MD5, SHA1, or SHA256)"

        result = _vt_request("GET", f"/files/{file_hash}")
        if "error" in result:
            return json.dumps(result)

        attrs = result.get("data", {}).get("attributes", {})
        return json.dumps({
            "hash": file_hash,
            "analysis": _format_stats(attrs),
            "type": attrs.get("type_description", ""),
            "size": attrs.get("size", 0),
            "names": attrs.get("names", [])[:5],
            "tags": attrs.get("tags", [])[:10],
            "first_seen": attrs.get("first_submission_date", ""),
        })

    @mcp.tool(name="vt_search", annotations={"title": "Search VirusTotal intelligence", "destructiveHint": False})
    async def vt_search(params: dict) -> str:
        """
        Search VirusTotal for files, URLs, domains matching a query.
        params: query (str, required) - VT search query (e.g. "type:pdf positives:5+")
                limit (int, optional, default 10)
        """
        query = params.get("query", "")
        if not query:
            return "Error: 'query' is required"

        limit = min(int(params.get("limit", 10)), 20)
        encoded = urllib.parse.quote(query)
        result = _vt_request("GET", f"/search?query={encoded}&limit={limit}")
        if "error" in result:
            return json.dumps(result)

        items = result.get("data", [])
        summary = []
        for item in items:
            attrs = item.get("attributes", {})
            summary.append({
                "id": item.get("id", ""),
                "type": item.get("type", ""),
                "stats": _format_stats(attrs),
                "name": attrs.get("meaningful_name", attrs.get("names", [""])[0] if attrs.get("names") else ""),
            })
        return json.dumps({"count": len(items), "results": summary})
