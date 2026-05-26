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
  runtime/pillars/conduit/storage/
    inbox/<recipient>/<msg-id>.md     ← 未読
    archive/<recipient>/<msg-id>.md   ← 既読（ack 済み）

最小依存: mcp（公式 Python SDK）のみ。storage ロジックは storage.py に分離（テスト容易性のため）。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from storage import AuthorizationError, Nexus, _validate_mind_name

# Phase 5b-2 (#75): Inbox Pillar への cross-pillar import。
# ADR-0017 §5「Mind 側に Inbox 取り込み経路を提供」のために、Conduit Pillar が
# Mind 向け MCP tool として inbox.py の関数を wrap する。
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_RUNTIME_DIR / "pillars" / "inbox"))
sys.path.insert(0, str(_RUNTIME_DIR / "pillars" / "registry"))
from inbox import (  # noqa: E402
    IssueNotFoundError,
    IssueValidationError,
    claim_issue as _inbox_claim_issue,
    list_pending_issues as _inbox_list_pending,
    peek_pending_issue as _inbox_peek,
)
# Phase 5c-1 (#87 / ADR-0019): Guild mismatch 検出のため guild.py を import。
# Phase 5c-2 (ADR-0021): Guildmaster axiom の機械強制で is_guildmaster を使う。
from guild import (  # noqa: E402
    DEFAULT_GUILD,
    GUILDMASTER_PERSONA,
    get_mind_guild as _get_mind_guild,
    is_guildmaster as _is_guildmaster,
)

# Identity binding (Issue #19, ADR-0008):
#   When spawn-mind.sh launches this Nexus as a stdio subprocess for a single
#   Mind, it sets AI_ORG_OS_MIND_NAME to bind the session to that Mind.
#   If present, the Nexus rejects any operation that does not match.
#   If absent (e.g. manual `python nexus.py` for tests), the Nexus accepts all.
_BOUND_MIND = os.environ.get("AI_ORG_OS_MIND_NAME")
_nexus = Nexus(identity=_BOUND_MIND)

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
                "Messages stay in the inbox until ack_dispatch is called for each. "
                "Phase 5c-2 (ADR-0021): pass target_mind to read another Mind's "
                "inbox; this is only permitted when the caller's persona is "
                "'guildmaster' (axiom: read-others-inbox-only-by-guildmaster), "
                "otherwise code='forbidden' is returned."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {"type": "string", "description": "Your Mind name."},
                    "target_mind": {
                        "type": "string",
                        "description": (
                            "Optional. Mind name whose inbox you want to read. "
                            "Defaults to your own (mind_name). Reading another "
                            "Mind's inbox requires guildmaster persona."
                        ),
                    },
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
        # Phase 5b-2 (#75 / ADR-0017): Mind が自分で人間からの Issue を取り込む経路。
        # send_dispatch / read_inbox は Mind 同士の Dispatch 用。これとは別に、
        # 人間が runtime/issues/inbox/ に置いた Issue を Mind が読み・claim する tool。
        Tool(
            name="read_pending_issues",
            description=(
                "List pending Issues that humans have submitted to the Realm Inbox "
                "(under runtime/issues/inbox/). These are different from Mind-to-Mind "
                "dispatches read by read_inbox. Each Mind decides for itself whether "
                "to claim an Issue based on its Persona (ADR-0017 layer B)."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="claim_issue",
            description=(
                "Claim a pending Issue from the Realm Inbox. The Issue is moved from "
                "the Inbox to the Archive with claimed_by=<your Mind name> and "
                "claimed_at recorded in its frontmatter. Atomic — a concurrent claim "
                "by another Mind will fail with not-found. "
                "Guild axiom (ADR-0019): your Mind's guild must match the Issue's "
                "guild, otherwise this returns code='forbidden'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {"type": "string", "description": "Your Mind name."},
                    "issue_id": {"type": "string", "description": "issue_id to claim."},
                },
                "required": ["mind_name", "issue_id"],
            },
        ),
        # Phase 5c-2 (ADR-0021): Guildmaster Persona の Mind だけが他 Mind を
        # spawn できる axiom (guildmaster-only-spawn) を機械強制する経路。
        # spawn-mind.sh (人間 CLI) は ADR-0012 で人間が Realm 外なので axiom
        # 適用外。本 tool は Mind 内部から spawn する Realm 内経路で、axiom が
        # かかる。
        Tool(
            name="spawn_mind",
            description=(
                "Spawn a new Mind under your Guild. "
                "Guildmaster-only axiom (ADR-0021): only Minds whose persona is "
                "'guildmaster' may call this. Otherwise code='forbidden'. "
                "Internally invokes spawn-mind.sh with --guild equal to the "
                "caller's own guild (cross-guild spawn is not permitted in v0.1). "
                "kind / persona must be allowed by the Guild's manifest."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {
                        "type": "string",
                        "description": "Your Mind name (the caller, must be guildmaster).",
                    },
                    "new_mind_name": {
                        "type": "string",
                        "description": "Name for the new Mind being spawned.",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Kind of the new Mind (must be allowed by Guild manifest).",
                    },
                    "persona": {
                        "type": "string",
                        "description": "Persona of the new Mind (must be allowed by Guild manifest).",
                    },
                },
                "required": ["mind_name", "new_mind_name", "kind", "persona"],
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
            # Phase 5c-2 (ADR-0021): target_mind 省略 / mind_name と同じなら
            # 自分の inbox (現状通り = storage の identity binding で OK)。
            # 異なる target_mind を指定する場合は axiom
            # read-others-inbox-only-by-guildmaster を機械強制する。
            mind_name = args["mind_name"]
            target_mind = args.get("target_mind") or mind_name
            _validate_mind_name(mind_name, "mind_name")
            _validate_mind_name(target_mind, "target_mind")
            if target_mind == mind_name:
                result = _nexus.read_inbox(mind_name=mind_name)
            else:
                _nexus.assert_identity(mind_name)
                if not _is_guildmaster(mind_name):
                    from guild import (  # noqa: PLC0415
                        get_mind_persona as _get_persona,
                    )
                    requester_persona = _get_persona(mind_name) or "<unknown>"
                    result = {
                        "ok": False,
                        "code": "forbidden",
                        "error": (
                            f"forbidden: only minds with persona="
                            f"'{GUILDMASTER_PERSONA}' may read another mind's "
                            f"inbox. mind '{mind_name}' has persona="
                            f"'{requester_persona}' (axiom: "
                            f"read-others-inbox-only-by-guildmaster)"
                        ),
                        "requester_persona": requester_persona,
                    }
                else:
                    # Codex P1 (#91): Guildmaster であっても **異 Guild** の Mind
                    # を監視するのは axiom 違反 (Guild 隔離と claim-only-own-guild の
                    # 思想で同じ責任分界)。same-guild check を入れる。
                    # Codex P1 (#91 2 回目): registry エントリ無の Mind は
                    # unknown として forbidden。default fallback は cross-guild
                    # bypass の窓だった (default guildmaster が registry 無 target
                    # を観察できてしまう)。
                    requester_guild = _get_mind_guild(mind_name)
                    target_guild = _get_mind_guild(target_mind)
                    if requester_guild is None or target_guild is None:
                        result = {
                            "ok": False,
                            "code": "forbidden",
                            "error": (
                                f"forbidden: requester or target mind has no "
                                f"registry entry. requester='{mind_name}' "
                                f"(guild={requester_guild!r}), target="
                                f"'{target_mind}' (guild={target_guild!r}). "
                                f"both must be registered (axiom: "
                                f"read-others-inbox-only-by-guildmaster)"
                            ),
                            "requester_guild": requester_guild,
                            "target_guild": target_guild,
                        }
                    elif requester_guild != target_guild:
                        result = {
                            "ok": False,
                            "code": "forbidden",
                            "error": (
                                f"forbidden: guildmaster '{mind_name}' belongs "
                                f"to guild '{requester_guild}' but target "
                                f"'{target_mind}' belongs to guild "
                                f"'{target_guild}'. cross-guild observation is "
                                f"not permitted (axiom: "
                                f"read-others-inbox-only-by-guildmaster, "
                                f"same-guild boundary)"
                            ),
                            "requester_guild": requester_guild,
                            "target_guild": target_guild,
                        }
                    else:
                        # Guildmaster かつ同 Guild なら target_mind の inbox を読む。
                        # storage.Nexus._authorize は self.identity と target_mind を
                        # 比較するので、bound 状態だと self-bound でない限り失敗する。
                        # 同 storage_dir で identity 無効化した一時インスタンスを使う。
                        from storage import Nexus as _NexusCls  # noqa: PLC0415
                        unbound = _NexusCls(
                            storage_dir=_nexus.storage_dir, identity=None,
                        )
                        result = unbound.read_inbox(mind_name=target_mind)
                        result["observed_by"] = mind_name  # audit 用
        elif name == "ack_dispatch":
            result = _nexus.ack_dispatch(mind_name=args["mind_name"], msg_id=args["msg_id"])
        elif name == "read_pending_issues":
            # Phase 5b-2: 人間 Inbox の Issue 一覧。identity binding は不要
            # (read-only、公開キュー、ADR-0017 §3「Mind が自分で取りに行く」)。
            # Phase 5c-1 (ADR-0019): guild も含めて返す。
            # Mind 側 (Persona) は自身の guild と一致するもののみ claim する想定。
            records = _inbox_list_pending()
            result = {
                "ok": True,
                "count": len(records),
                "issues": [
                    {
                        "issue_id": r.issue_id,
                        "title": r.title,
                        "submitter": r.submitter,
                        "priority": r.priority,
                        "submitted_at": r.submitted_at,
                        "guild": r.guild,
                        "body": r.body,
                    }
                    for r in records
                ],
            }
        elif name == "claim_issue":
            # Phase 5b-2: mind_name は identity binding でチェック済 (bound 時のみ)。
            # claimed_by として archive に書き込まれる (ADR-0017 §1 traceability)。
            # Phase 5c-1 (#87 / ADR-0019): Guild mismatch を機械 reject する。
            mind_name = args["mind_name"]
            issue_id = args["issue_id"]
            # Codex P2 (#88): _nexus.assert_identity は unbound 時 (テスト /
            # manual モード) は no-op なので、crafted mind_name ('../...' 等)
            # を guild lookup (`_get_mind_guild`) に渡すと minds/ 外の
            # .mind-meta.md を読む path traversal の窓が空く。assert_identity
            # の前に明示的な format 検証を入れる (storage.py と同じ regex)。
            _validate_mind_name(mind_name, "mind_name")
            _nexus.assert_identity(mind_name)  # ADR-0008 enforcement (no-op if unbound)

            # peek → guild compare → atomic claim、の順。peek と claim の間に
            # 他 Mind が claim する race は残るが、その場合 _inbox_claim_issue
            # が IssueNotFoundError を上げて自然に伝播する (forbidden より
            # 後段で潰れる ≈ FIFO で並んでいた他 Mind の claim が勝つ)。
            issue_rec = _inbox_peek(issue_id)
            issue_guild = issue_rec.guild or DEFAULT_GUILD
            mind_guild = _get_mind_guild(mind_name)
            # Codex P1 (#91 2 回目): registry エントリ無の Mind は unknown
            # として forbidden (旧: DEFAULT_GUILD に fallback → cross-guild
            # bypass の窓だった)。
            if mind_guild is None:
                result = {
                    "ok": False,
                    "code": "forbidden",
                    "error": (
                        f"forbidden: mind '{mind_name}' has no registry entry "
                        f"(unknown guild). spawn-mind must register the Mind "
                        f"before any axiom-controlled operation."
                    ),
                    "mind_guild": None,
                    "issue_guild": issue_guild,
                }
            elif mind_guild != issue_guild:
                # ADR-0019 §3 axiom: claim-only-own-guild。
                # storage.AuthorizationError と同じ "forbidden" コードに揃え、
                # Mind 側 (Persona) が同じ handler で扱えるようにする。
                result = {
                    "ok": False,
                    "code": "forbidden",
                    "error": (
                        f"forbidden: mind '{mind_name}' belongs to guild "
                        f"'{mind_guild}', but issue '{issue_id}' belongs to "
                        f"guild '{issue_guild}' (axiom: claim-only-own-guild)"
                    ),
                    "mind_guild": mind_guild,
                    "issue_guild": issue_guild,
                }
            else:
                rec = _inbox_claim_issue(issue_id, claimer=mind_name)
                result = {
                    "ok": True,
                    "issue_id": rec.issue_id,
                    "title": rec.title,
                    "submitter": rec.submitter,
                    "priority": rec.priority,
                    "submitted_at": rec.submitted_at,
                    "guild": rec.guild,
                    "claimed_by": mind_name,
                    "body": rec.body,
                    "archived_path": str(rec.path),
                }
        elif name == "spawn_mind":
            # Phase 5c-2 (ADR-0021): Guildmaster-only-spawn axiom 強制 + 既存
            # spawn-mind.sh を subprocess で呼ぶ。仕様 (Guild manifest 検証 /
            # Registry kind 検証 / .mind-meta.md 生成等) は shell に集約済。
            mind_name = args["mind_name"]
            new_mind_name = args["new_mind_name"]
            kind = args["kind"]
            persona = args["persona"]
            # 入力形式検証 (path traversal 等)
            _validate_mind_name(mind_name, "mind_name")
            _validate_mind_name(new_mind_name, "new_mind_name")
            _validate_mind_name(kind, "kind")
            _validate_mind_name(persona, "persona")
            # identity binding (bound 時のみ効く)
            _nexus.assert_identity(mind_name)
            # axiom: guildmaster-only-spawn
            if not _is_guildmaster(mind_name):
                from guild import (  # noqa: PLC0415
                    get_mind_persona as _get_persona,
                )
                requester_persona = _get_persona(mind_name) or "<unknown>"
                result = {
                    "ok": False,
                    "code": "forbidden",
                    "error": (
                        f"forbidden: only minds with persona="
                        f"'{GUILDMASTER_PERSONA}' may spawn other minds. "
                        f"mind '{mind_name}' has persona="
                        f"'{requester_persona}' (axiom: guildmaster-only-spawn)"
                    ),
                    "requester_persona": requester_persona,
                }
            else:
                # 発令者の guild を解決 → 同 guild に spawn する (cross-guild
                # spawn は v0.1 で許可しない、ADR-0019 §3 と整合)。
                # _is_guildmaster が True を返している = registry エントリは
                # 存在する。なので requester_guild も None ではないはず。
                # defense in depth: 万一 None なら internal_error。
                requester_guild = _get_mind_guild(mind_name)
                import subprocess  # noqa: PLC0415
                spawn_sh = (
                    _RUNTIME_DIR / "pillars" / "lifecycle" / "spawn-mind.sh"
                )
                if requester_guild is None:
                    result = {
                        "ok": False,
                        "code": "internal_error",
                        "error": (
                            f"requester '{mind_name}' has persona=guildmaster "
                            f"but no guild field; registry entry is malformed"
                        ),
                    }
                elif not spawn_sh.is_file():
                    result = {
                        "ok": False,
                        "error": f"spawn-mind.sh not found at {spawn_sh}",
                        "code": "internal_error",
                    }
                else:
                    try:
                        proc = subprocess.run(
                            [
                                "bash", str(spawn_sh),
                                "--guild", requester_guild,
                                kind, persona, new_mind_name,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                    except subprocess.TimeoutExpired:
                        result = {
                            "ok": False,
                            "error": "spawn-mind.sh timed out (30s)",
                            "code": "internal_error",
                        }
                    else:
                        if proc.returncode == 0:
                            result = {
                                "ok": True,
                                "new_mind_name": new_mind_name,
                                "kind": kind,
                                "persona": persona,
                                "guild": requester_guild,
                                "spawned_by": mind_name,
                                "stdout_tail": proc.stdout[-500:],
                            }
                        else:
                            # spawn-mind.sh の exit code をそのまま伝える
                            # (2=unknown kind, 3=unknown persona, 11=unknown
                            # guild, etc)
                            result = {
                                "ok": False,
                                "error": (
                                    f"spawn-mind.sh failed with exit "
                                    f"{proc.returncode}"
                                ),
                                "code": "spawn_failed",
                                "exit_code": proc.returncode,
                                "stderr_tail": proc.stderr[-500:],
                            }
        else:
            result = {"ok": False, "error": f"unknown tool: {name}"}
    except KeyError as exc:
        result = {"ok": False, "error": f"missing argument: {exc.args[0]}"}
    except AuthorizationError as exc:
        # Identity binding violation (Issue #19, ADR-0008).
        # Domain-specific exception so callers can distinguish from OS-level
        # PermissionError raised by underlying fs operations
        # (Codex P2 PR #27 follow-up).
        result = {"ok": False, "error": str(exc), "code": "forbidden"}
    except IssueValidationError as exc:
        result = {"ok": False, "error": str(exc), "code": "invalid_input"}
    except IssueNotFoundError as exc:
        result = {"ok": False, "error": str(exc), "code": "not_found"}
    except ValueError as exc:
        result = {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        # Includes built-in PermissionError (fs-level), OSError, etc.
        # These are infrastructure failures, NOT authorization denials.
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
