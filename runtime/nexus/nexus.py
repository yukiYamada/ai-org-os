#!/usr/bin/env python3
"""
Nexus — ai-org-os の MCP server。

Mind 同士の Dispatch を仲介する「世界の経路」。
Mind は MCP 経由でこのサーバーの tool を呼ぶことで他 Mind と通信する。
Mind は他 Mind の Mindspace を直接触らない（Axiom: Mindspace 不可侵）。

提供する tool:
  - send_dispatch(from_mind, to_mind, topic, body): 送信
  - read_inbox(mind_name): 自分宛 inbox を読む
  - ack_dispatch(mind_name, msg_id): 処理済みとして archive へ移す

裏側ストレージ:
  runtime/nexus/storage/
    inbox/<recipient>/<msg-id>.md     ← 未読
    archive/<recipient>/<msg-id>.md   ← 既読（ack 済み）

最小依存: mcp（公式 Python SDK）のみ。storage ロジックは storage.py に分離（テスト容易性のため）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from storage import Nexus

_nexus = Nexus()

server: Server = Server("nexus")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_dispatch",
            description=(
                "Send a dispatch message from one Mind to another. "
                "The message is stored in the recipient's inbox and remains there until ack_dispatch is called."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "from_mind": {"type": "string", "description": "Sender Mind name."},
                    "to_mind": {"type": "string", "description": "Recipient Mind name."},
                    "topic": {"type": "string", "description": "Short subject line."},
                    "body": {"type": "string", "description": "Markdown body."},
                },
                "required": ["from_mind", "to_mind", "topic", "body"],
            },
        ),
        Tool(
            name="read_inbox",
            description=(
                "Read all messages currently in a Mind's inbox. "
                "Messages stay in the inbox until ack_dispatch is called for each."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {"type": "string", "description": "Your Mind name."},
                },
                "required": ["mind_name"],
            },
        ),
        Tool(
            name="ack_dispatch",
            description=(
                "Acknowledge a single message. "
                "It is moved from inbox to archive and will no longer appear in read_inbox."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {"type": "string", "description": "Your Mind name."},
                    "msg_id": {"type": "string", "description": "Message id to acknowledge."},
                },
                "required": ["mind_name", "msg_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "send_dispatch":
            result = _nexus.send_dispatch(
                from_mind=args["from_mind"],
                to_mind=args["to_mind"],
                topic=args["topic"],
                body=args["body"],
            )
        elif name == "read_inbox":
            result = _nexus.read_inbox(mind_name=args["mind_name"])
        elif name == "ack_dispatch":
            result = _nexus.ack_dispatch(mind_name=args["mind_name"], msg_id=args["msg_id"])
        else:
            result = {"ok": False, "error": f"unknown tool: {name}"}
    except KeyError as exc:
        result = {"ok": False, "error": f"missing argument: {exc.args[0]}"}
    except ValueError as exc:
        result = {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)
