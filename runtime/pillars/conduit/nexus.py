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
# Phase 5d-3 (#68 / ADR-0017): Mind 向け観察 MCP tool。Observation Pillar の
# Mind-scope wrapping を経由して Mind が自分自身 / 自 dispatch / 自 Guild を
# 観察できるようにする。他 Mind / 他 Guild の情報は wrap 関数の戻り値で
# 物理的に除外される。
sys.path.insert(0, str(_RUNTIME_DIR / "pillars" / "observation"))
from mind_scope import (  # noqa: E402
    observe_self as _ms_observe_self,
    observe_dispatches_for as _ms_observe_dispatches_for,
    observe_guild_for as _ms_observe_guild_for,
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
                "kind / persona must be allowed by the Guild's manifest. "
                "Workspace defaults to the caller's own workspace (= team "
                "environment inheritance, Phase 5d-6 / dogfooding fix); "
                "explicit `workspace` arg overrides it (ADR-0022)."
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
                    "workspace": {
                        "type": "string",
                        "description": (
                            "Optional workspace template (ADR-0022). If omitted, "
                            "the new Mind inherits the caller's own workspace "
                            "(= team environment continuity). Explicit value "
                            "overrides this inheritance."
                        ),
                    },
                },
                "required": ["mind_name", "new_mind_name", "kind", "persona"],
            },
        ),
        # Phase 5c-3 (ADR-0021): spawn と対称な kill_mind tool。axiom:
        # guildmaster-only-kill (指示) を機械強制する。self-kill 不可 + 同 Guild
        # 境界の 2 段制約を入れる (詳細は templates/guilds/default/axiom.md)。
        # 内部では kill-mind.sh を subprocess 経由で呼び、registry-first 削除
        # 順序 (Codex P2 #91) を再利用する。
        Tool(
            name="kill_mind",
            description=(
                "Destroy a Mind in your Guild (the Mindspace is removed and the "
                "registry entry is invalidated). Guildmaster-only axiom (ADR-0021): "
                "only Minds whose persona is 'guildmaster' may call this, AND only "
                "for target Minds in the SAME guild, AND self-kill is forbidden. "
                "Otherwise code='forbidden'. Internally invokes kill-mind.sh. "
                "The last Guildmaster of a Guild cannot retire itself via this "
                "tool — a human operator must use kill-mind.sh from outside the "
                "Realm (ADR-0012)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {
                        "type": "string",
                        "description": "Your Mind name (the caller, must be guildmaster).",
                    },
                    "target_mind": {
                        "type": "string",
                        "description": (
                            "Mind name to destroy. Must be in the same Guild as "
                            "the caller, and must not equal mind_name (no self-kill)."
                        ),
                    },
                },
                "required": ["mind_name", "target_mind"],
            },
        ),
        # Phase 5d-3 (#68 / ADR-0017): Mind 向け Observation MCP tool。
        # Observation Pillar の Warden 内部 API を、Mind の自己観察スコープに
        # 絞って公開する。返り値は wrap 関数で物理的に他 Mind / 他 Guild の
        # 情報を含まないようフィルタされる。新規 axiom は不要 (identity
        # binding ADR-0008 + 既存 claim-only-own-guild の思想で十分)。
        Tool(
            name="observe_self",
            description=(
                "Return your own Mind's observation snapshot (status / category / "
                "unread / archive / mindspace size). No information about other "
                "Minds is exposed. identity binding (ADR-0008) ensures mind_name "
                "matches the caller in bound sessions."
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
            name="observe_my_dispatches",
            description=(
                "Return dispatches where you appear as either sender (from) or "
                "recipient (to). Dispatches between other Minds are filtered out. "
                "Optional window_seconds limits to dispatches within the last N "
                "seconds (default: all-time)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {"type": "string", "description": "Your Mind name."},
                    "window_seconds": {
                        "type": "integer",
                        "description": (
                            "Optional time window in seconds. Omit for all-time."
                        ),
                    },
                },
                "required": ["mind_name"],
            },
        ),
        Tool(
            name="observe_my_guild",
            description=(
                "Return a rollup of your Guild: members, guildmasters, and pending "
                "Issues belonging to your Guild. Other Guilds are not exposed. "
                "Returns code='forbidden' if you have no registry entry "
                "(same-guild boundary, mirroring claim-only-own-guild)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mind_name": {"type": "string", "description": "Your Mind name."},
                },
                "required": ["mind_name"],
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
            # Phase 5d-6 (#104 dogfooding fix): optional workspace 引数。
            # 省略時は caller の workspace を継承する (= team 環境継続)。
            # 明示時はそれが最優先 (spawn-mind.sh の解決順 #1 と整合)。
            workspace_arg = args.get("workspace")
            # 入力形式検証 (path traversal 等)
            _validate_mind_name(mind_name, "mind_name")
            _validate_mind_name(new_mind_name, "new_mind_name")
            _validate_mind_name(kind, "kind")
            _validate_mind_name(persona, "persona")
            if workspace_arg is not None:
                _validate_mind_name(workspace_arg, "workspace")
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
                # Phase 5d-6 (#104): caller の workspace を読む。Mind の
                # registry entry の workspace フィールドが authoritative
                # source (Phase 5d-2 で spawn-mind が registry に書き込む)。
                # MCP 引数 > 継承 > spawn-mind.sh 側 fallback (Guild manifest
                # → default) の優先順位を保つ。
                from guild import _read_mind_meta_field  # noqa: PLC0415

                requester_workspace = ""
                if workspace_arg:
                    requester_workspace = workspace_arg  # 明示優先
                else:
                    # caller の registry から workspace を継承
                    import os as _os  # noqa: PLC0415
                    home = _os.environ.get("AI_ORG_OS_HOME") or (
                        _os.environ.get("HOME") or _os.environ.get("USERPROFILE") or "."
                    )
                    reg_path = Path(home) / ("registry/minds/" + mind_name + ".md") \
                        if _os.environ.get("AI_ORG_OS_HOME") \
                        else Path(home) / ".ai-org-os" / "registry" / "minds" / (mind_name + ".md")
                    inherited = _read_mind_meta_field(reg_path, "workspace")
                    if inherited:
                        requester_workspace = inherited
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
                        # Windows JP locale (cp932) で subprocess output に
                        # 非 ASCII byte (日本語メッセージ等) が混じると
                        # capture_output + text=True のデフォルト codec
                        # (locale.getpreferredencoding = cp932) で
                        # UnicodeDecodeError → reader thread 死亡 → stdout
                        # が None になり、後段の `proc.stdout[-500:]` で
                        # 'NoneType' object is not subscriptable で result
                        # が「実 spawn 成功なのに ok=false」を返す不整合に
                        # なる (2026-05-26 dogfooding で実機検出)。
                        # encoding="utf-8" を明示し、念のため errors="replace"
                        # で decode 不能 byte は U+FFFD に置換して落とさない。
                        spawn_argv = [
                            "bash", str(spawn_sh),
                            "--guild", requester_guild,
                        ]
                        if requester_workspace:
                            # Phase 5d-6 (#104): caller の workspace を継承
                            # (or 明示引数で override) として spawn-mind に
                            # 渡す。spawn-mind 側の解決順 #1 (引数最優先)
                            # に乗る形。
                            spawn_argv.extend(["--workspace", requester_workspace])
                        spawn_argv.extend([kind, persona, new_mind_name])
                        proc = subprocess.run(
                            spawn_argv,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            # Windows + bash + multiple Python child processes
                            # (registry.py check / guild.py validate /
                            # workspace.py show) + git worktree add で実測 ~60s
                            # を超えるケースが発生 (Phase 5d-6 dogfooding 2026-05-28)。
                            # 60s は workspace モード spawn で margin 不足、
                            # 120s に拡大して Mindspace + worktree + registry
                            # の全 step が完了する余裕を確保する。
                            # Linux CI では 5s 程度なので影響無し。
                            timeout=120,
                        )
                    except subprocess.TimeoutExpired:
                        result = {
                            "ok": False,
                            "error": "spawn-mind.sh timed out (120s)",
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
                                # Phase 5d-6 (#104): 実際に使われた workspace を
                                # 戻り値に含める (継承だったのか明示だったのか
                                # caller 側で確認できるよう)。
                                "workspace": (
                                    requester_workspace
                                    if requester_workspace
                                    else "(spawn-mind fallback: Guild or default)"
                                ),
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
        elif name == "kill_mind":
            # Phase 5c-3 (ADR-0021): guildmaster-only-kill axiom 強制 + 既存
            # kill-mind.sh を subprocess で呼ぶ。spawn_mind と対称構造だが、
            # 3 段チェック (persona / self / same-guild) が入る。
            mind_name = args["mind_name"]
            target_mind = args["target_mind"]
            # 入力形式検証 (path traversal 等) — assert_identity / registry
            # lookup より前に行うこと。Codex P2 #88 と同じ思想。
            _validate_mind_name(mind_name, "mind_name")
            _validate_mind_name(target_mind, "target_mind")
            # identity binding (bound 時のみ効く)
            _nexus.assert_identity(mind_name)
            # axiom step 1: persona check (guildmaster-only-kill)
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
                        f"'{GUILDMASTER_PERSONA}' may kill other minds. "
                        f"mind '{mind_name}' has persona="
                        f"'{requester_persona}' (axiom: guildmaster-only-kill)"
                    ),
                    "requester_persona": requester_persona,
                }
            # axiom step 2: self-kill 不可。
            # persona check より後に置く理由: 「self-kill 不可」は guildmaster
            # 限定の制約 (designer が自分を kill しようとした場合は persona
            # 違反の方が本質的)。エラーメッセージの一貫性のためこの順に。
            elif mind_name == target_mind:
                result = {
                    "ok": False,
                    "code": "forbidden",
                    "error": (
                        f"forbidden: self-kill is not permitted "
                        f"(axiom: guildmaster-only-kill, no-self-kill clause). "
                        f"the last guildmaster of a guild, or a guildmaster "
                        f"that needs to retire, must be killed by a human "
                        f"operator via kill-mind.sh (ADR-0012)"
                    ),
                }
            else:
                # axiom step 3: same-guild boundary
                # read_inbox / spawn と同じ Guild 隔離思想。
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
                            f"guildmaster-only-kill)"
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
                            f"'{target_guild}'. cross-guild kill is not "
                            f"permitted (axiom: guildmaster-only-kill, "
                            f"same-guild boundary)"
                        ),
                        "requester_guild": requester_guild,
                        "target_guild": target_guild,
                    }
                else:
                    import subprocess  # noqa: PLC0415
                    kill_sh = (
                        _RUNTIME_DIR / "pillars" / "lifecycle" / "kill-mind.sh"
                    )
                    if not kill_sh.is_file():
                        result = {
                            "ok": False,
                            "error": f"kill-mind.sh not found at {kill_sh}",
                            "code": "internal_error",
                        }
                    else:
                        try:
                            # spawn_mind と同じく encoding="utf-8" を明示。
                            # 現在の kill-mind.sh は output が偶然全 ASCII
                            # なので問題は出ていないが、将来日本語メッセージ
                            # が混入したら spawn_mind と同じ症状になる
                            # (dogfooding 2026-05-26 で spawn_mind 側を実機検出、
                            # 予防的に kill_mind も同時に修正)。
                            # spawn と対称に 120s に拡大 (Phase 5d-6 dogfooding
                            # 2026-05-28 で spawn 側を実機検出、kill 側も予防的に)。
                            # kill は worktree remove + Mindspace rm + 旧 mind-loop
                            # の stop 等で複数 process を呼ぶため、Windows では
                            # 60s margin が将来不足する可能性がある。
                            proc = subprocess.run(
                                ["bash", str(kill_sh), target_mind],
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=120,
                            )
                        except subprocess.TimeoutExpired:
                            result = {
                                "ok": False,
                                "error": "kill-mind.sh timed out (120s)",
                                "code": "internal_error",
                            }
                        else:
                            if proc.returncode == 0:
                                result = {
                                    "ok": True,
                                    "killed_mind": target_mind,
                                    "guild": target_guild,
                                    "killed_by": mind_name,
                                    "stdout_tail": proc.stdout[-500:],
                                }
                            else:
                                # kill-mind.sh の exit code を伝える
                                # (2=mind not found, 5=registry remove failed)
                                result = {
                                    "ok": False,
                                    "error": (
                                        f"kill-mind.sh failed with exit "
                                        f"{proc.returncode}"
                                    ),
                                    "code": "kill_failed",
                                    "exit_code": proc.returncode,
                                    "stderr_tail": proc.stderr[-500:],
                                }
        elif name == "observe_self":
            # Phase 5d-3 (#68): Mind 向け Observation tool。identity binding
            # を assert した上で mind_scope.observe_self を呼ぶ。返り値は
            # 1 Mind 分のみで、他 Mind の情報は含まれない (wrap 側の物理保証)。
            mind_name = args["mind_name"]
            _validate_mind_name(mind_name, "mind_name")
            _nexus.assert_identity(mind_name)
            result = _ms_observe_self(mind_name)
        elif name == "observe_my_dispatches":
            mind_name = args["mind_name"]
            _validate_mind_name(mind_name, "mind_name")
            _nexus.assert_identity(mind_name)
            window = args.get("window_seconds")
            if window is not None and not isinstance(window, int):
                result = {
                    "ok": False,
                    "error": "window_seconds must be an integer",
                    "code": "invalid_input",
                }
            else:
                result = _ms_observe_dispatches_for(
                    mind_name, window_seconds=window,
                )
        elif name == "observe_my_guild":
            mind_name = args["mind_name"]
            _validate_mind_name(mind_name, "mind_name")
            _nexus.assert_identity(mind_name)
            result = _ms_observe_guild_for(mind_name)
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
