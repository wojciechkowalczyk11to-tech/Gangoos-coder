"""
NEXUS MCP — Notifications Module
Telegram, Email (SMTP/SES), Slack, Discord
"""
import json
import logging
import os
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP, Context

log = logging.getLogger("nexus-mcp.notifications")


def register(mcp: FastMCP):

    # ── Telegram ─────────────────────────────────────────

    class TelegramSendInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        chat_id: str = Field(..., description="Telegram chat_id or @username")
        text: str = Field(..., description="Message text (supports Markdown)")
        bot_token: Optional[str] = Field(None, description="Bot token (uses TELEGRAM_BOT_TOKEN env if not set)")
        parse_mode: str = Field("Markdown", description="Parse mode: Markdown or HTML")
        disable_notification: bool = Field(False, description="Send silently")

    @mcp.tool(name="telegram_send", annotations={"title": "Telegram Send Message"})
    async def telegram_send(params: TelegramSendInput, ctx: Context) -> str:
        """Send a message via Telegram bot."""
        import httpx
        token = params.bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return "Error: No bot token provided and TELEGRAM_BOT_TOKEN not set"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": params.chat_id,
                        "text": params.text,
                        "parse_mode": params.parse_mode,
                        "disable_notification": params.disable_notification,
                    },
                    timeout=15,
                )
                data = r.json()
                if data.get("ok"):
                    return json.dumps({"status": "sent", "message_id": data["result"]["message_id"]})
                return json.dumps({"error": data.get("description", "unknown error")})
        except Exception as e:
            return f"Error: {e}"

    class TelegramFileInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        chat_id: str = Field(..., description="Telegram chat_id")
        file_path: str = Field(..., description="Local file path to send")
        caption: Optional[str] = Field(None, description="File caption")
        bot_token: Optional[str] = Field(None, description="Bot token")

    @mcp.tool(name="telegram_send_file", annotations={"title": "Telegram Send File"})
    async def telegram_send_file(params: TelegramFileInput, ctx: Context) -> str:
        """Send a file via Telegram bot."""
        import httpx
        token = params.bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return "Error: No bot token"
        try:
            with open(params.file_path, "rb") as f:
                file_data = f.read()
            filename = os.path.basename(params.file_path)
            async with httpx.AsyncClient() as client:
                data = {"chat_id": params.chat_id}
                if params.caption:
                    data["caption"] = params.caption
                r = await client.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data=data,
                    files={"document": (filename, file_data)},
                    timeout=60,
                )
                result = r.json()
                return json.dumps({"status": "sent" if result.get("ok") else "error", "response": result})
        except Exception as e:
            return f"Error: {e}"

    # ── Email ─────────────────────────────────────────────

    class EmailInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        to: str = Field(..., description="Recipient email address")
        subject: str = Field(..., description="Email subject")
        body: str = Field(..., description="Email body (plain text or HTML)")
        from_email: Optional[str] = Field(None, description="Sender email (uses SMTP_FROM env if not set)")
        smtp_host: Optional[str] = Field(None, description="SMTP host (uses SMTP_HOST env)")
        smtp_port: int = Field(587, description="SMTP port")
        smtp_user: Optional[str] = Field(None, description="SMTP username (uses SMTP_USER env)")
        smtp_password: Optional[str] = Field(None, description="SMTP password (uses SMTP_PASSWORD env)")
        html: bool = Field(False, description="Send as HTML email")

    @mcp.tool(name="email_send", annotations={"title": "Send Email via SMTP"})
    async def email_send(params: EmailInput, ctx: Context) -> str:
        """Send email via SMTP (Gmail, SendGrid, AWS SES, etc.)."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        host = params.smtp_host or os.environ.get("SMTP_HOST", "")
        user = params.smtp_user or os.environ.get("SMTP_USER", "")
        password = params.smtp_password or os.environ.get("SMTP_PASSWORD", "")
        from_email = params.from_email or os.environ.get("SMTP_FROM", user)

        if not host:
            return "Error: SMTP_HOST not configured"
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = params.subject
            msg["From"] = from_email
            msg["To"] = params.to
            mime_type = "html" if params.html else "plain"
            msg.attach(MIMEText(params.body, mime_type))

            with smtplib.SMTP(host, params.smtp_port) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.sendmail(from_email, params.to, msg.as_string())
            return json.dumps({"status": "sent", "to": params.to, "subject": params.subject})
        except Exception as e:
            return f"Error: {e}"

    # ── Slack ─────────────────────────────────────────────

    class SlackInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        webhook_url: Optional[str] = Field(None, description="Slack webhook URL (uses SLACK_WEBHOOK env)")
        channel: Optional[str] = Field(None, description="Channel name (for bot token mode)")
        text: str = Field(..., description="Message text")
        username: Optional[str] = Field(None, description="Bot display name")

    @mcp.tool(name="slack_send", annotations={"title": "Slack Send Message"})
    async def slack_send(params: SlackInput, ctx: Context) -> str:
        """Send message to Slack via webhook."""
        import httpx
        webhook = params.webhook_url or os.environ.get("SLACK_WEBHOOK", "")
        if not webhook:
            return "Error: No webhook URL provided and SLACK_WEBHOOK not set"
        payload = {"text": params.text}
        if params.username:
            payload["username"] = params.username
        if params.channel:
            payload["channel"] = params.channel
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(webhook, json=payload, timeout=10)
                return json.dumps({"status": "ok" if r.text == "ok" else "error", "response": r.text})
        except Exception as e:
            return f"Error: {e}"

    # ── Discord ───────────────────────────────────────────

    class DiscordInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        webhook_url: str = Field(..., description="Discord webhook URL")
        content: str = Field(..., description="Message content")
        username: Optional[str] = Field(None, description="Override bot name")

    @mcp.tool(name="discord_send", annotations={"title": "Discord Send Message"})
    async def discord_send(params: DiscordInput, ctx: Context) -> str:
        """Send message to Discord via webhook."""
        import httpx
        payload = {"content": params.content}
        if params.username:
            payload["username"] = params.username
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(params.webhook_url, json=payload, timeout=10)
                return json.dumps({"status_code": r.status_code, "ok": r.status_code in (200, 204)})
        except Exception as e:
            return f"Error: {e}"

    log.info("Notifications module registered (Telegram, Email, Slack, Discord)")
