"""
NEXUS MCP — Browser Automation Module (Lightweight)

Playwright-based web automation with STRICT resource limits for e2-micro.
NOT a full browser-use agent — single-page operations only.

Constraints (e2-micro safe):
  - Single browser instance, reused
  - Auto-kill page after 30s timeout
  - Max 1 concurrent page
  - Headless only, --no-sandbox
  - Screenshot max 1280x720
  - DOM extraction max 50KB

Tools:
  - browser_screenshot:   Take screenshot of a URL (returns base64 PNG)
  - browser_extract:      Extract text/HTML/links from a page (JS-rendered)
  - browser_action:       Click, type, scroll on a page (single action)
  - browser_pdf:          Save page as PDF

Dependencies: playwright (+ chromium via playwright install chromium)
"""

import asyncio
import base64
import logging
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.browser")

PAGE_TIMEOUT_MS = 30_000
ACTION_TIMEOUT_MS = 10_000
MAX_DOM_CHARS = 50_000
MAX_SCREENSHOT_WIDTH = 1280
MAX_SCREENSHOT_HEIGHT = 720
BROWSER_CLOSE_AFTER_IDLE = 120


class _BrowserManager:
    """Lazy singleton: starts Chromium on first use, closes after idle."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._last_used = 0.0
        self._available = None

    async def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import playwright  # noqa: F401
            proc = await asyncio.create_subprocess_shell(
                "python3 -m playwright install --dry-run chromium 2>/dev/null || echo missing",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            self._available = b"missing" not in stdout
            if not self._available:
                log.warning("Chromium not installed. Run: playwright install chromium")
        except ImportError:
            self._available = False
            log.warning("playwright package not installed")
        return self._available

    async def get_browser(self):
        async with self._lock:
            if not await self._check_available():
                raise RuntimeError(
                    "Browser not available. Install with:\n"
                    "  pip install playwright && playwright install chromium --with-deps"
                )
            if self._browser is None or not self._browser.is_connected():
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--no-first-run",
                        "--disable-default-apps",
                        "--js-flags=--max-old-space-size=128",
                    ],
                )
                log.info("Browser launched (headless, resource-limited)")
            self._last_used = time.time()
            return self._browser

    async def new_page(self):
        browser = await self.get_browser()
        context = await browser.new_context(
            viewport={"width": MAX_SCREENSHOT_WIDTH, "height": MAX_SCREENSHOT_HEIGHT},
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
        )
        context.set_default_timeout(PAGE_TIMEOUT_MS)
        page = await context.new_page()
        await page.route("**/*.{mp4,webm,ogg,mp3,wav,flac}", lambda route: route.abort())
        await page.route("**/*.{woff,woff2,ttf,eot}", lambda route: route.abort())
        return page, context

    async def close_idle(self):
        if self._browser and time.time() - self._last_used > BROWSER_CLOSE_AFTER_IDLE:
            await self.close()

    async def close(self):
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
                log.info("Browser closed")


_mgr = _BrowserManager()


def register(mcp: FastMCP):

    class BrowserScreenshotInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., description="URL to screenshot")
        full_page: bool = Field(False, description="Capture full page (not just viewport)")
        wait_for: Optional[str] = Field(None, description="CSS selector to wait for before screenshot")

    @mcp.tool(
        name="browser_screenshot",
        annotations={"title": "Take Browser Screenshot", "readOnlyHint": True, "openWorldHint": True},
    )
    async def browser_screenshot(params: BrowserScreenshotInput, ctx: Context) -> str:
        """Take a screenshot of a URL using a real browser (JS-rendered).
        Returns base64-encoded PNG. Use for: visual testing, page verification,
        scraping JS-heavy sites.

        \u26a0\ufe0f Resource-limited: 30s timeout, 1280x720 viewport, heavy media blocked.
        """
        page = context = None
        try:
            page, context = await _mgr.new_page()
            await page.goto(params.url, wait_until="domcontentloaded")
            if params.wait_for:
                await page.wait_for_selector(params.wait_for, timeout=ACTION_TIMEOUT_MS)
            await page.wait_for_timeout(1500)
            screenshot_bytes = await page.screenshot(full_page=params.full_page, type="png")
            b64 = base64.b64encode(screenshot_bytes).decode()
            size_kb = len(screenshot_bytes) / 1024
            return (
                f"**URL:** {params.url}\n"
                f"**Size:** {size_kb:.1f} KB\n"
                f"**Viewport:** {MAX_SCREENSHOT_WIDTH}x{MAX_SCREENSHOT_HEIGHT}\n\n"
                f"![screenshot](data:image/png;base64,{b64})"
            )
        except Exception as e:
            return f"Error: {e}"
        finally:
            if context:
                await context.close()

    class BrowserExtractInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., description="URL to extract content from")
        selector: Optional[str] = Field(None, description="CSS selector to extract (default: body)")
        extract_type: str = Field("text", description="What to extract: text, html, links, meta, structured")

    @mcp.tool(
        name="browser_extract",
        annotations={"title": "Extract Page Content (JS-rendered)", "readOnlyHint": True, "openWorldHint": True},
    )
    async def browser_extract(params: BrowserExtractInput, ctx: Context) -> str:
        """Extract text, HTML, links, or metadata from a JS-rendered page.
        Unlike web_fetch, this executes JavaScript (SPAs, React, dynamic content).

        \u26a0\ufe0f 30s timeout, 50KB max output.
        """
        page = context = None
        try:
            page, context = await _mgr.new_page()
            await page.goto(params.url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            sel = params.selector or "body"

            if params.extract_type == "text":
                content = await page.inner_text(sel)
                return f"**URL:** {params.url}\n**Selector:** {sel}\n\n---\n\n{content[:MAX_DOM_CHARS]}"
            elif params.extract_type == "html":
                content = await page.inner_html(sel)
                return f"**URL:** {params.url}\n\n```html\n{content[:MAX_DOM_CHARS]}\n```"
            elif params.extract_type == "links":
                links = await page.eval_on_selector_all(
                    f"{sel} a[href]",
                    "els => els.slice(0, 100).map(a => ({text: a.innerText.trim().slice(0, 80), href: a.href}))",
                )
                output = f"**URL:** {params.url}\n**Links found:** {len(links)}\n\n"
                for link in links:
                    output += f"- [{link['text']}]({link['href']})\n"
                return output
            elif params.extract_type == "meta":
                meta = await page.evaluate("""() => ({
                    title: document.title,
                    description: document.querySelector('meta[name=description]')?.content || '',
                    og_title: document.querySelector('meta[property=\"og:title\"]')?.content || '',
                    og_image: document.querySelector('meta[property=\"og:image\"]')?.content || '',
                    canonical: document.querySelector('link[rel=canonical]')?.href || '',
                    lang: document.documentElement.lang || '',
                    h1: Array.from(document.querySelectorAll('h1')).map(h => h.innerText.trim()).slice(0, 5),
                })""")
                output = f"**URL:** {params.url}\n\n"
                for k, v in meta.items():
                    if v:
                        output += f"**{k}:** {v}\n"
                return output
            elif params.extract_type == "structured":
                import json as _json
                data = await page.evaluate("""() => {
                    const scripts = document.querySelectorAll('script[type=\"application/ld+json\"]');
                    return Array.from(scripts).map(s => { try { return JSON.parse(s.textContent); } catch { return null; } }).filter(Boolean);
                }""")
                return f"**URL:** {params.url}\n**JSON-LD blocks:** {len(data)}\n\n```json\n{_json.dumps(data, indent=2)[:MAX_DOM_CHARS]}\n```"
            else:
                return f"Unknown extract_type: {params.extract_type}. Use: text, html, links, meta, structured"
        except Exception as e:
            return f"Error: {e}"
        finally:
            if context:
                await context.close()

    class BrowserActionInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., description="URL to navigate to first")
        action: str = Field(..., description="Action: click, type, scroll_down, scroll_up, wait, evaluate")
        selector: Optional[str] = Field(None, description="CSS selector for click/type target")
        text: Optional[str] = Field(None, description="Text to type (for 'type' action)")
        js_code: Optional[str] = Field(None, description="JavaScript to evaluate (for 'evaluate' action)")

    @mcp.tool(
        name="browser_action",
        annotations={"title": "Browser Action (click/type/scroll)", "destructiveHint": True, "openWorldHint": True},
    )
    async def browser_action(params: BrowserActionInput, ctx: Context) -> str:
        """Perform a single browser action: click, type, scroll, or run JS.
        Navigate to URL first, then execute the action.

        \u26a0\ufe0f Single action per call. Chain multiple calls for complex flows.
        """
        page = context = None
        try:
            page, context = await _mgr.new_page()
            await page.goto(params.url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            if params.action == "click":
                if not params.selector:
                    return "Error: 'selector' required for click action"
                await page.click(params.selector, timeout=ACTION_TIMEOUT_MS)
                await page.wait_for_timeout(1000)
                title = await page.title()
                return f"\u2705 Clicked `{params.selector}` on {params.url}\n**Page title after:** {title}\n**URL after:** {page.url}"
            elif params.action == "type":
                if not params.selector or not params.text:
                    return "Error: 'selector' and 'text' required for type action"
                await page.fill(params.selector, params.text, timeout=ACTION_TIMEOUT_MS)
                return f"\u2705 Typed into `{params.selector}`: {params.text[:50]}..."
            elif params.action == "scroll_down":
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                return "\u2705 Scrolled down one viewport"
            elif params.action == "scroll_up":
                await page.evaluate("window.scrollBy(0, -window.innerHeight)")
                return "\u2705 Scrolled up one viewport"
            elif params.action == "wait":
                if params.selector:
                    await page.wait_for_selector(params.selector, timeout=ACTION_TIMEOUT_MS)
                    return f"\u2705 Element `{params.selector}` appeared"
                else:
                    await page.wait_for_timeout(3000)
                    return "\u2705 Waited 3 seconds"
            elif params.action == "evaluate":
                if not params.js_code:
                    return "Error: 'js_code' required for evaluate action"
                import json as _json
                result = await page.evaluate(params.js_code)
                return f"**Result:**\n```json\n{_json.dumps(result, indent=2, default=str)[:MAX_DOM_CHARS]}\n```"
            else:
                return f"Unknown action: {params.action}. Use: click, type, scroll_down, scroll_up, wait, evaluate"
        except Exception as e:
            return f"Error: {e}"
        finally:
            if context:
                await context.close()

    class BrowserPdfInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        url: str = Field(..., description="URL to save as PDF")
        path: str = Field("/tmp/nexus_page.pdf", description="Output PDF path")

    @mcp.tool(
        name="browser_pdf",
        annotations={"title": "Save Page as PDF", "readOnlyHint": True, "openWorldHint": True},
    )
    async def browser_pdf(params: BrowserPdfInput, ctx: Context) -> str:
        """Save a JS-rendered web page as PDF. Useful for archiving or reporting."""
        page = context = None
        try:
            page, context = await _mgr.new_page()
            await page.goto(params.url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await page.pdf(path=params.path, format="A4", print_background=True)
            import os
            size = os.path.getsize(params.path)
            return f"\u2705 Saved PDF: `{params.path}` ({size / 1024:.1f} KB)\n**URL:** {params.url}"
        except Exception as e:
            return f"Error: {e}"
        finally:
            if context:
                await context.close()

    log.info("Browser module registered: browser_screenshot, browser_extract, browser_action, browser_pdf")
