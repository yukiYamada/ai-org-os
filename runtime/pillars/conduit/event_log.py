"""
Event log writer for Conduit (and other Pillars).

ADR-0026 で確定した構造化ログ (JSONL) の書き手側の共通 util。

責務 (ADR-0026 §3 / §5 / §8 A):
- envelope `{ts, event, actor, ...}` を 1 行 JSONL で append
- 書き込み失敗は **stderr WARN + return** で済ませて cycle を止めない (F3 / ADR-0013 §1)
- ts は UTC ISO-8601 milliseconds precision

呼び出し側 (PR-A 時点):
- Conduit `Nexus.send_dispatch` / `Nexus.ack_dispatch`

PR-B 以降:
- Conductor (cycle.* / judgment.* / warden_inbox.*)
- Actuator (actuator.kill / prompt / skipped)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _default_logs_dir() -> Path:
    """$AI_ORG_OS_HOME/logs/ (ADR-0018 / ADR-0026 §1)。

    関数化することで、env を切り替えるだけでテスト隔離が効く
    (module-level 定数だと import 時固定で test 不便)。
    """
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "logs"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "logs"


def _iso_ms_z() -> str:
    """UTC ISO-8601 with millisecond precision, suffixed 'Z'.

    例: '2026-06-01T01:42:13.123Z'
    """
    now = datetime.now(timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_event(
    log_path: Path,
    event: str,
    actor: str,
    **fields: Any,
) -> None:
    """1 event を JSONL 1 行として `log_path` に append する。

    Args:
        log_path: 書き込み先 (例: `$AI_ORG_OS_HOME/logs/dispatch.jsonl`)。
            親 dir が無ければ作る。
        event: ADR-0026 §4 の event 名 (例: `'dispatch.sent'`)。
        actor: 書き手 (例: `'conduit'`, `'conductor'`, Mind 名)。
        **fields: event 別の追加フィールド (例: `from_=..., to=..., msg_id=...`)。

    F3 準拠 (ADR-0013 §1 / ADR-0026 §5):
        OSError / JSON encode 失敗 / その他例外いずれも上位に raise しない。
        stderr に WARN を出して return する (= 観察補助情報という設計上の位置付け、
        失敗で cycle を止めない)。

    `from` は Python 予約語なので、呼び出し側は `**{"from": ...}` で渡すこと。
    """
    try:
        envelope: dict[str, Any] = {
            "ts": _iso_ms_z(),
            "event": event,
            "actor": actor,
        }
        envelope.update(fields)
        line = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n"
    except (TypeError, ValueError) as exc:
        # JSON encode 失敗 (= 非 JSON-serializable な field が混入)。
        # 本来は呼び出し側のバグなので WARN で見えるようにするが、raise しない。
        print(
            f"[event_log] WARN: failed to encode event '{event}': {exc}",
            file=sys.stderr,
        )
        return

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # text mode + utf-8 explicit。append-only。
        with open(log_path, "a", encoding="utf-8") as fp:
            fp.write(line)
    except OSError as exc:
        print(
            f"[event_log] WARN: failed to write to {log_path}: {exc}",
            file=sys.stderr,
        )
        return
