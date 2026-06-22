"""
Storage layer for Nexus.

Pure Python, standard library only. No MCP dependency, so this module can be
unit-tested without installing `mcp`.

`Nexus` is a thin class that owns a storage directory and exposes the three
core operations: send_dispatch / read_inbox / ack_dispatch.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from event_log import _default_logs_dir, write_event


def _default_storage_dir() -> Path:
    """$AI_ORG_OS_HOME/conduit-storage/ (Phase 5b-4 / ADR-0018)。

    関数化することで、env 切り替えだけでテスト隔離可能 (module load 時固定を回避)。
    """
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "conduit-storage"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "conduit-storage"


def _default_minds_dir() -> Path:
    """$AI_ORG_OS_HOME/minds/ (ADR-0018)。

    Fix #136: send_dispatch から recipient の .mind-loop.nudge を touch するのに
    必要。logs_dir / storage_dir と同じく関数化で env override をテスト容易に。
    """
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "minds"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "minds"


# 旧コードからの参照のため module-level エイリアスは残すが、関数で解決する。
DEFAULT_STORAGE_DIR = _default_storage_dir()

MIND_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MSG_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# Phase 5e / ADR-0024 §3: Mind が名乗れない予約語。Realm sender 専用。
# Mind が "warden" を名乗ると Warden 発信の dispatch と区別不能になり、
# identity の意味論が壊れる (Mind sender vs Realm sender の混同)。
# Conductor 経路 (`Nexus(identity=None).send_dispatch(from_mind="warden", ...)`)
# は許可するため、`_validate_mind_name` には予約語チェックを入れず、
# 別 helper `_reject_if_reserved_for_mind` で「Mind 名」として使う場面に
# 限定して reject する。Issue #112。
RESERVED_MIND_NAMES = frozenset({"warden"})


def _validate_mind_name(name: Any, field: str, *, is_mind_field: bool = False) -> None:
    """Validate Mind name format and optionally reject reserved names.

    Args:
        name: The name to validate
        field: Field name for error messages
        is_mind_field: If True, also reject RESERVED_MIND_NAMES (#197)
    """
    if not isinstance(name, str) or not MIND_NAME_RE.match(name):
        raise ValueError(f"invalid {field}: must match {MIND_NAME_RE.pattern}")
    if is_mind_field and name in RESERVED_MIND_NAMES:
        raise ValueError(
            f"invalid {field}: '{name}' is reserved for Realm senders "
            f"(ADR-0024 §3). Mind names cannot use: "
            f"{sorted(RESERVED_MIND_NAMES)}"
        )


def _reject_if_reserved_for_mind(name: str, field: str) -> None:
    """Mind 名として使われる場面で予約語を reject。

    呼ぶ場面:
    - `Nexus(identity=<name>)`: MCP server が Mind プロセス毎に立ち上がる
      identity binding。ここに "warden" を渡せると Mind が Warden の身体を
      乗っ取れる
    - 将来 register_mind 系 API ができたとき (現状 spawn-mind.sh が直接
      ファイル書き出ししているのでこの helper は呼ばれない、bash 側でも
      同じ予約語リストをハードコードして二重防御)
    """
    if name in RESERVED_MIND_NAMES:
        raise ValueError(
            f"invalid {field}: '{name}' is reserved for Realm senders "
            f"(ADR-0024 §3). Mind names cannot use: "
            f"{sorted(RESERVED_MIND_NAMES)}"
        )


def _validate_msg_id(msg_id: Any) -> None:
    if not isinstance(msg_id, str) or not MSG_ID_RE.match(msg_id):
        raise ValueError(f"invalid msg_id: must match {MSG_ID_RE.pattern}")


def _gen_msg_id(sender: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand = secrets.token_hex(4)
    return f"{ts}-{sender}-{rand}"


class AuthorizationError(Exception):
    """Identity binding violation (Issue #19, ADR-0008).

    Raised when a Nexus bound to one Mind identity is asked to act on behalf
    of another. Intentionally distinct from the built-in PermissionError so
    that OS-level filesystem permission failures (read-only mount, bad
    ownership) are NOT misreported as authorization denials.
    (Codex P2 PR #27 follow-up.)
    """
    pass


class Nexus:
    """Storage-level Nexus. The MCP wiring in nexus.py delegates to this class.

    Identity binding (Issue #19, ADR-0008):
      If ``identity`` is set (typically from the AI_ORG_OS_MIND_NAME environment
      variable when the Nexus is launched as a stdio subprocess of a single Mind),
      the Nexus will reject any operation that does not match this identity.
      This prevents one Mind from impersonating another Mind via crafted arguments.

      When ``identity`` is None (e.g. unit tests, HTTP transport for multi-tenant
      use cases), all operations are allowed regardless of from_mind / mind_name.
    """

    def __init__(
        self,
        storage_dir: Path | str | None = None,
        identity: str | None = None,
        logs_dir: Path | str | None = None,
        minds_dir: Path | str | None = None,
    ) -> None:
        base = Path(storage_dir) if storage_dir is not None else _default_storage_dir()
        self.storage_dir = base.resolve()
        self.inbox_dir = self.storage_dir / "inbox"
        self.archive_dir = self.storage_dir / "archive"
        # ADR-0026: 構造化ログ書き込み先。明示指定が無ければ
        # $AI_ORG_OS_HOME/logs/ にフォールバック。テストは tmp dir を渡す。
        logs_base = Path(logs_dir) if logs_dir is not None else _default_logs_dir()
        self.logs_dir = logs_base.resolve()
        # Fix #136: send_dispatch 経路で recipient Mindspace の nudge file を
        # touch するために minds_dir を保持。テストは tmp dir を渡す。
        minds_base = Path(minds_dir) if minds_dir is not None else _default_minds_dir()
        self.minds_dir = minds_base.resolve()
        # When identity is provided, validate its shape so it cannot be a path traversal etc.
        if identity is not None:
            _validate_mind_name(identity, "identity")
            # Issue #112 / ADR-0024 §3: Mind が "warden" として MCP server
            # を立ち上げられないように予約語を reject (identity=None で
            # 起動する Conductor/Warden 経路は影響なし)。
            _reject_if_reserved_for_mind(identity, "identity")
        self.identity = identity

    def _ensure_dirs(self) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _authorize(self, claimed: str, field: str) -> None:
        """Raise AuthorizationError if the caller is bound to an identity and it
        disagrees with the claimed mind_name / from_mind.

        Note: this raises AuthorizationError (ai-org-os domain exception), NOT
        the built-in PermissionError. OS-level fs permission failures from
        write_text / read_text / rename keep raising PermissionError and stay
        distinguishable for callers (Codex P2 PR #27 follow-up).
        """
        if self.identity is not None and claimed != self.identity:
            raise AuthorizationError(
                f"forbidden: this Nexus session is bound to mind '{self.identity}', "
                f"but {field}='{claimed}' was requested"
            )

    def assert_identity(self, claimed: str, field: str = "mind_name") -> None:
        """Public alias for _authorize.

        Phase 5b-2 (#75): Nexus 以外の Pillar (Inbox 等) の wrapper tool でも同じ
        identity binding を効かせるための公開 API。`_authorize` は internal helper
        として残す (既存呼び出し側の互換のため)。
        """
        self._authorize(claimed, field)

    # ---- operations ----------------------------------------------------------

    def send_dispatch(
        self,
        from_mind: str,
        to_mind: str,
        topic: str,
        body: str,
    ) -> dict[str, Any]:
        _validate_mind_name(from_mind, "from_mind", is_mind_field=True)
        _validate_mind_name(to_mind, "to_mind")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        # axiom: topic は YAML frontmatter の単一行に literal で埋め込むため、
        # 改行 (\n / \r) を含むと frontmatter が壊れて偽 `from:` 等の line を
        # 注入可能になる (= identity binding 突破)。Conduit Pillar 側で reject
        # することで Mind→Mind / Warden→Mind の両経路に同じ axiom が効く
        # (ADR-0021 A: 機械強制)。Codex P1 of Phase 5e Step B self-review。
        if "\n" in topic or "\r" in topic:
            raise ValueError("topic must not contain newlines (frontmatter integrity)")
        if not isinstance(body, str):
            raise ValueError("body must be a string")
        self._authorize(from_mind, "from_mind")
        self._ensure_dirs()

        msg_id = _gen_msg_id(from_mind)
        recipient_inbox = self.inbox_dir / to_mind
        recipient_inbox.mkdir(parents=True, exist_ok=True)
        msg_path = recipient_inbox / f"{msg_id}.md"
        dispatched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        content = (
            "---\n"
            f"from: {from_mind}\n"
            f"to: {to_mind}\n"
            f"topic: {topic}\n"
            f"dispatched_at: {dispatched_at}\n"
            f"msg_id: {msg_id}\n"
            "---\n\n"
            f"{body}\n"
        )
        msg_path.write_text(content, encoding="utf-8")
        # ADR-0026 §4.1: dispatch.sent event を JSONL に記録。
        # F3 準拠なので write_event 自体が失敗しても以下の return は影響を受けない。
        # `from` は Python 予約語のため **{"from": ...} で渡す。
        write_event(
            self.logs_dir / "dispatch.jsonl",
            event="dispatch.sent",
            actor="conduit",
            **{"from": from_mind},
            to=to_mind,
            topic=topic,
            msg_id=msg_id,
        )
        # Fix #136: recipient mind-loop.sh の sleep を即時抜けさせる nudge。
        # recipient の Mindspace が存在しない (= Mind 未 spawn / Warden / kill 後)
        # 場合は silent skip。失敗系は全て例外を吐かない (F3-like) — dispatch 本体
        # は既に永続化されており、nudge は best-effort な latency 改善でしかない。
        # 安全性: to_mind は _validate_mind_name 通過後の値で path traversal 不可。
        # 仮に recipient Mind が自 Mindspace を改竄しても影響は self-effect に限定。
        try:
            recipient_mindspace = self.minds_dir / to_mind
            if recipient_mindspace.is_dir():
                nudge_file = recipient_mindspace / ".mind-loop.nudge"
                nudge_file.touch()
        except OSError:
            # nudge file の I/O 失敗は dispatch 成功を覆さない。stderr ログも不要
            # (= operational noise を増やさない、polling fallback で 1 cycle 後に
            #  処理される)。
            pass
        return {
            "ok": True,
            "msg_id": msg_id,
            "dispatched_at": dispatched_at,
            "stored_at": str(msg_path),
        }

    def read_inbox(self, mind_name: str) -> dict[str, Any]:
        _validate_mind_name(mind_name, "mind_name")
        self._authorize(mind_name, "mind_name")
        self._ensure_dirs()
        inbox = self.inbox_dir / mind_name
        if not inbox.exists():
            return {"ok": True, "mind": mind_name, "count": 0, "messages": []}
        messages: list[dict[str, Any]] = []
        for msg_path in sorted(inbox.glob("*.md")):
            try:
                content = msg_path.read_text(encoding="utf-8")
            except OSError as exc:
                content = f"<read error: {exc}>"
            messages.append({"msg_id": msg_path.stem, "content": content})
        return {
            "ok": True,
            "mind": mind_name,
            "count": len(messages),
            "messages": messages,
        }

    def ack_dispatch(self, mind_name: str, msg_id: str) -> dict[str, Any]:
        """Acknowledge a dispatch.

        Idempotent: calling ack_dispatch on an already-archived message returns
        ok=True with `already_acked=True`. This lets MCP clients safely retry
        after transport timeouts without surfacing false errors.
        """
        _validate_mind_name(mind_name, "mind_name")
        _validate_msg_id(msg_id)
        self._authorize(mind_name, "mind_name")
        self._ensure_dirs()
        src = self.inbox_dir / mind_name / f"{msg_id}.md"
        dst_dir = self.archive_dir / mind_name
        dst = dst_dir / f"{msg_id}.md"

        # Idempotency: if the message has already been archived, treat as success.
        if dst.exists() and not src.exists():
            return {
                "ok": True,
                "archived_at": str(dst),
                "already_acked": True,
            }

        if not src.exists():
            # Never existed (neither in inbox nor archive).
            return {"ok": False, "error": f"message not found: {mind_name}/{msg_id}"}

        dst_dir.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        # ADR-0026 §4.1: dispatch.acked event を JSONL に記録。
        # 実際に archive へ移した時のみ書く (already_acked / not_found は書かない =
        # cycle に新しい情報がないため)。
        write_event(
            self.logs_dir / "dispatch.jsonl",
            event="dispatch.acked",
            actor="conduit",
            by=mind_name,
            msg_id=msg_id,
        )
        return {"ok": True, "archived_at": str(dst), "already_acked": False}
