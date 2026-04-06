#!/usr/bin/env python3
"""
Telegram Bot for Gangoos-coder Agent
Frontend for interacting with the MCP server and Ollama directly.
Provides CodeAct loop, tool execution, and real-time streaming.
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import json
import aiohttp
import re

from telegram import Update, Chat, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from telegram.error import TelegramError
from telegram.constants import ChatAction

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GangoosConfig:
    """Configuration from environment variables"""
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    MCP_URL = os.getenv("MCP_URL", "http://localhost:8080/api/v1/tools")
    ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
    DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen:latest")
    RATE_LIMIT_REQUESTS = 10
    RATE_LIMIT_SECONDS = 60


class RateLimiter:
    """Simple rate limiter per user"""

    def __init__(self, requests: int, seconds: int):
        self.requests = requests
        self.seconds = seconds
        self.user_requests: Dict[int, list] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Check if user is within rate limit"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.seconds)

        # Clean old requests
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if req_time > cutoff
        ]

        if len(self.user_requests[user_id]) < self.requests:
            self.user_requests[user_id].append(now)
            return True
        return False

    def get_remaining(self, user_id: int) -> int:
        """Get remaining requests before next reset"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.seconds)
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if req_time > cutoff
        ]
        return self.requests - len(self.user_requests[user_id])


class OllamaClient:
    """Client for Ollama API"""

    def __init__(self, host: str, model: str):
        self.host = host
        self.model = model
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()

    async def chat(self, message: str, system_prompt: str = "") -> str:
        """Chat with Ollama model"""
        try:
            url = f"{self.host}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                "stream": False
            }

            async with self.session.post(url, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    return f"Error: HTTP {resp.status}"
                result = await resp.json()
                return result.get("message", {}).get("content", "No response")

        except asyncio.TimeoutError:
            return "Error: Ollama timeout (>60s)"
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return f"Error: {str(e)}"

    async def stream_chat(self, message: str, system_prompt: str = ""):
        """Stream chat responses"""
        try:
            url = f"{self.host}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                "stream": True
            }

            async with self.session.post(url, json=payload, timeout=120) as resp:
                if resp.status != 200:
                    yield f"Error: HTTP {resp.status}"
                    return

                async for line in resp.content:
                    if line:
                        try:
                            chunk = json.loads(line)
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            pass

        except asyncio.TimeoutError:
            yield "Error: Ollama timeout"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"Error: {str(e)}"


class MCPClient:
    """Client for MCP server tools"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()

    async def get_tools(self) -> Dict[str, Any]:
        """Get available tools"""
        try:
            async with self.session.get(self.base_url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"MCP error: {e}")
            return {"error": str(e)}

    async def execute_tool(self, tool_name: str, args: Dict) -> str:
        """Execute MCP tool"""
        try:
            url = f"{self.base_url}/{tool_name}/execute"
            async with self.session.post(url, json=args, timeout=30) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return json.dumps(result, indent=2)
                return f"Error: HTTP {resp.status}"
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return f"Error: {str(e)}"


class GangoosTelegramBot:
    """Main Telegram bot for Gangoos-coder"""

    def __init__(self, config: GangoosConfig):
        self.config = config
        self.rate_limiter = RateLimiter(
            config.RATE_LIMIT_REQUESTS,
            config.RATE_LIMIT_SECONDS
        )
        self.ollama = OllamaClient(config.OLLAMA_HOST, config.DEFAULT_MODEL)
        self.mcp = MCPClient(config.MCP_URL)
        self.app: Optional[Application] = None

    async def initialize(self):
        """Initialize bot and clients"""
        self.app = Application.builder().token(self.config.TELEGRAM_BOT_TOKEN).build()
        await self.ollama.initialize()
        await self.mcp.initialize()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("chat", self.cmd_chat))
        self.app.add_handler(CommandHandler("tool", self.cmd_tool))
        self.app.add_handler(CommandHandler("tools", self.cmd_list_tools))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("model", self.cmd_model))
        self.app.add_handler(CommandHandler("codeact", self.cmd_codeact))
        self.app.add_handler(CommandHandler("restart", self.cmd_restart))
        self.app.add_handler(CommandHandler("logs", self.cmd_logs))

    async def run(self):
        """Start bot"""
        logger.info("Starting Gangoos-coder Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("Bot started and polling")

    async def stop(self):
        """Stop bot and cleanup"""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        await self.ollama.close()
        await self.mcp.close()

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.config.ADMIN_CHAT_ID

    def check_rate_limit(self, update: Update) -> bool:
        """Check and enforce rate limit"""
        user_id = update.effective_user.id
        return self.rate_limiter.is_allowed(user_id)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        await update.message.reply_text(
            f"🤖 Welcome to Gangoos-coder, {user.first_name}!\n\n"
            "I'm a senior coding agent specializing in:\n"
            "• Rust, Python, Mojo\n"
            "• MCP servers and DevOps\n"
            "• CodeAct loops and tool execution\n\n"
            "Use /help to see available commands."
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
**Gangoos-coder Commands:**

/chat <message> - Chat with the agent
/tool <name> <args> - Execute MCP tool
/tools - List available tools
/status - System health check
/model - Show current model info
/codeact <task> - Run full CodeAct loop
/help - Show this help

**Examples:**
/chat How do I optimize Python code?
/tool execute_query SELECT * FROM users
/codeact Build a Rust binary tree

Use /status to check if services are online.
        """
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def cmd_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /chat command"""
        if not self.check_rate_limit(update):
            remaining = self.rate_limiter.get_remaining(update.effective_user.id)
            await update.message.reply_text(
                f"⏱️ Rate limited. Try again in {self.config.RATE_LIMIT_SECONDS}s. "
                f"({remaining} slots available)"
            )
            return

        if not context.args:
            await update.message.reply_text("Usage: /chat <message>")
            return

        message = " ".join(context.args)
        await update.message.chat.send_action(ChatAction.TYPING)

        response = await self.ollama.chat(message)
        self._format_and_send(await update.message.reply_text(response))

    async def cmd_tool(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tool command"""
        if not self.check_rate_limit(update):
            await update.message.reply_text("⏱️ Rate limited")
            return

        if len(context.args) < 1:
            await update.message.reply_text("Usage: /tool <name> [args as JSON]")
            return

        tool_name = context.args[0]
        args = {}

        if len(context.args) > 1:
            try:
                args = json.loads(" ".join(context.args[1:]))
            except json.JSONDecodeError:
                await update.message.reply_text("Invalid JSON arguments")
                return

        await update.message.chat.send_action(ChatAction.TYPING)
        result = await self.mcp.execute_tool(tool_name, args)

        # Format result
        if len(result) > 4000:
            chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
            for chunk in chunks:
                await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"```\n{result}\n```", parse_mode="Markdown")

    async def cmd_list_tools(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tools command"""
        await update.message.chat.send_action(ChatAction.TYPING)
        tools = await self.mcp.get_tools()

        if "error" in tools:
            await update.message.reply_text(f"❌ Error: {tools['error']}")
            return

        # Group tools by domain
        grouped = defaultdict(list)
        for tool in tools.get("tools", []):
            domain = tool.get("domain", "Other")
            grouped[domain].append(tool.get("name", "Unknown"))

        message = "**Available Tools:**\n\n"
        for domain in sorted(grouped.keys()):
            message += f"**{domain}**\n"
            for tool in grouped[domain]:
                message += f"  • {tool}\n"
            message += "\n"

        await update.message.reply_text(message, parse_mode="Markdown")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        status = "**System Status:**\n\n"

        # Check Ollama
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.config.OLLAMA_HOST}/api/tags", timeout=5) as resp:
                    ollama_ok = resp.status == 200
        except:
            ollama_ok = False

        status += f"{'✅' if ollama_ok else '❌'} Ollama: {self.config.OLLAMA_HOST}\n"

        # Check MCP
        try:
            tools = await self.mcp.get_tools()
            mcp_ok = "error" not in tools
        except:
            mcp_ok = False

        status += f"{'✅' if mcp_ok else '❌'} MCP Server: {self.config.MCP_URL}\n"

        await update.message.reply_text(status, parse_mode="Markdown")

    async def cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /model command"""
        model_info = f"**Current Model:** {self.config.DEFAULT_MODEL}\n"
        model_info += f"**Ollama Host:** {self.config.OLLAMA_HOST}\n"
        await update.message.reply_text(model_info, parse_mode="Markdown")

    async def cmd_codeact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /codeact command - full CodeAct loop"""
        if not context.args:
            await update.message.reply_text("Usage: /codeact <task description>")
            return

        task = " ".join(context.args)
        await update.message.chat.send_action(ChatAction.TYPING)

        system_prompt = """You are Gangoos-coder executing CodeAct pattern:
1. Understand the task
2. Generate code
3. Show execution steps
4. Observe results
5. Iterate if needed

Always use code blocks and explain each step."""

        response = await self.ollama.chat(task, system_prompt)
        await update.message.reply_text(response, parse_mode="Markdown")

    async def cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /restart command (admin only)"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only")
            return

        await update.message.reply_text("🔄 Restarting bot...")
        logger.info("Bot restart requested by admin")
        await self.stop()
        await self.initialize()
        await self.run()

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /logs command (admin only)"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only")
            return

        await update.message.reply_text("📋 Logs: Check server logs for details")

    def _format_and_send(self, message):
        """Format message with code blocks"""
        return message


async def main():
    """Main entry point"""
    if not GangoosConfig.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

    config = GangoosConfig()
    bot = GangoosTelegramBot(config)

    await bot.initialize()
    try:
        await bot.run()
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
