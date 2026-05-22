"""
Storage layer for Nexus.

Pure Python, standard library only. No MCP dependency, so this module can be
unit-tested without installing `mcp`.

`Nexus` is a thin class that owns a storage directory and exposes the three
core operations: send_dispatch / read_inbox / ack_dispatch.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STORAGE_DIR = Path(__file__).parent.resolve() / "storage"

MIND_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MSG_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _validate_mind_name(name: Any, field: str) -> None:
    if not isinstance(name, str) or not MIND_NAME_RE.match(name):
        raise ValueError(f"invalid {field}: must match {MIND_NAME_RE.pattern}")


def _validate_msg_id(msg_id: Any) -> None:
    if not isinstance(msg_id, str) or not MSG_ID_RE.match(msg_id):
        raise ValueError(f"invalid msg_id: must match {MSG_ID_RE.pattern}")


def _gen_msg_id(sender: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand = secrets.token_hex(4)
    return f"{ts}-{sender}-{rand}"


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
    ) -> None:
        base = Path(storage_dir) if storage_dir is not None else DEFAULT_STORAGE_DIR
        self.storage_dir = base.resolve()
        self.inbox_dir = self.storage_dir / "inbox"
        self.archive_dir = self.storage_dir / "archive"
        # When identity is provided, validate its shape so it cannot be a path traversal etc.
        if identity is not None:
            _validate_mind_name(identity, "identity")
        self.identity = identity

    def _ensure_dirs(self) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _authorize(self, claimed: str, field: str) -> None:
        """Raise PermissionError if the caller is bound to an identity and it
        disagrees with the claimed mind_name / from_mind.
        """
        if self.identity is not None and claimed != self.identity:
            raise PermissionError(
                f"forbidden: this Nexus session is bound to mind '{self.identity}', "
                f"but {field}='{claimed}' was requested"
            )

    # ---- operations ----------------------------------------------------------

    def send_dispatch(
        self,
        from_mind: str,
        to_mind: str,
        topic: str,
        body: str,
    ) -> dict[str, Any]:
        _validate_mind_name(from_mind, "from_mind")
        _validate_mind_name(to_mind, "to_mind")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic must be a non-empty string")
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
        return {"ok": True, "archived_at": str(dst), "already_acked": False}
