"""
Conduit small helpers (Phase 5f Step 3)。

stdlib only。`storage.py` / `event_log.py` の補助関数群と同じ作法で、
他モジュールから import される pure helper を置く場所。
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_iso_compact(now: datetime | None = None) -> str:
    """UTC 時刻を 'YYYYMMDDTHHMMSSZ' 形式で返す。

    issue id / dispatch msg id で既に使われているコンパクト ISO 形式。
    `now` を注入することで、test で時刻を固定できる (ADR-0018 の env 注入と
    同じ「外部依存をパラメタ化する」作法)。
    """
    moment = now if now is not None else datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%SZ")
