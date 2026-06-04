"""
Conduit small helpers (Phase 5f Step 3)。

stdlib only。`storage.py` / `event_log.py` の補助関数群と同じ作法で、
他モジュールから import される pure helper を置く場所。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import NamedTuple


def utc_iso_compact(now: datetime | None = None) -> str:
    """UTC 時刻を 'YYYYMMDDTHHMMSSZ' 形式で返す。

    issue id / dispatch msg id で既に使われているコンパクト ISO 形式。
    `now` を注入することで、test で時刻を固定できる (ADR-0018 の env 注入と
    同じ「外部依存をパラメタ化する」作法)。
    """
    moment = now if now is not None else datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%SZ")


class ParsedMsgId(NamedTuple):
    timestamp: str
    sender: str
    suffix: str


_TIMESTAMP_RE = re.compile(r"^\d{8}T\d{6}Z$")
_SUFFIX_RE = re.compile(r"^[0-9a-f]+$")


def parse_msg_id(msg_id: str) -> ParsedMsgId:
    """msg_id を `(timestamp, sender, suffix)` に分解する。

    形式: `<YYYYMMDDTHHMMSSZ>-<mind_name>-<hex suffix>`。
    `mind_name` 自体がハイフンを含み得る (例: `gm-default`) ため、
    先頭を timestamp / 末尾を suffix として固定し、間の全てを sender とする。

    形式不一致 (要素不足 / timestamp 不正 / suffix が hex でない) のとき
    `ValueError` を投げる。
    """
    parts = msg_id.split("-")
    if len(parts) < 3:
        raise ValueError(f"msg_id has too few '-' segments: {msg_id!r}")
    timestamp, *middle, suffix = parts
    if not middle:
        raise ValueError(f"missing mind_name segment in {msg_id!r}")
    if not _TIMESTAMP_RE.match(timestamp):
        raise ValueError(f"invalid timestamp segment {timestamp!r} in {msg_id!r}")
    if not _SUFFIX_RE.match(suffix):
        raise ValueError(f"invalid suffix segment {suffix!r} in {msg_id!r}")
    return ParsedMsgId(timestamp, "-".join(middle), suffix)
