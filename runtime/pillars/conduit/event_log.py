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

ローテーション (PR-F / ADR-0026 §6, Issue #135):
- size-based のみ。閾値 (default 10MB) を超えたら `<name>.jsonl` → `<name>.jsonl.1`
  → `.2` → ... → `.N` (default N=5、超えた最古は削除)。
- 閾値・retain は env var で C カテゴリ (manifest) 上書き可:
    - `AI_ORG_OS_LOG_MAX_BYTES` (default 10485760 = 10 MB)
    - `AI_ORG_OS_LOG_RETAIN`    (default 5)
- 「ローテーションする」という行為自体は A (axiom / 機械強制)。
- gz 圧縮 / TTL / `observe.py --prune-logs` は後続 PR (本 PR では未実装)。
- ローテーション失敗 (rename/unlink の OSError 等) は F3 準拠で
  stderr WARN を出して **新 event の append は試みる**。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_RETAIN = 5


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


def _read_int_env(name: str, default: int) -> int:
    """env var を int として読む。不正値は default に fallback。

    負値・0 は default に fallback (rotation を無効化したい場合は将来 ADR で別途 sentinel を)。
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    if v <= 0:
        return default
    return v


def _rotate_if_needed(log_path: Path) -> None:
    """`log_path` の現在サイズが閾値以上なら rotation を行う (ADR-0026 §6 / Issue #135)。

    閾値未満なら何もせず即 return (= rotation 非トリガ時のオーバーヘッドは `os.stat` 1 回のみ)。

    F3 準拠:
        rename/unlink で OSError が出た場合は stderr WARN を出して return。
        呼び出し側は **そのまま append を試みる** (= rotation 失敗を理由に
        新 event の書き込みは止めない、データ欠落許容は 1 event 単位)。

    並行性 (CLAUDE.md §3.3):
        rename / unlink は別 writer と race し得るが、ai-org-os は
        single-process Conductor + 1 Conduit per Realm なので実害は想定外。
        将来 multi-writer 化する場合は flock 等を別 ADR で。

    Args:
        log_path: 監視対象 path。存在しなければ何もしない。
    """
    try:
        size = log_path.stat().st_size
    except FileNotFoundError:
        return
    except OSError as exc:
        print(
            f"[event_log] WARN: failed to stat {log_path} for rotation: {exc}",
            file=sys.stderr,
        )
        return

    max_bytes = _read_int_env("AI_ORG_OS_LOG_MAX_BYTES", _DEFAULT_MAX_BYTES)
    if size < max_bytes:
        return

    retain = _read_int_env("AI_ORG_OS_LOG_RETAIN", _DEFAULT_RETAIN)

    # 旧い順に削除→shift。retain=5 のとき:
    #   .5 を unlink (もし存在すれば)
    #   .4 → .5
    #   .3 → .4
    #   .2 → .3
    #   .1 → .2
    #   <name> → .1
    def _suffixed(n: int) -> Path:
        # 単純な文字列連結で `<name>.N` を作る。
        # Path.with_suffix を使うと multi-dot file (例: `a.b.jsonl`) で
        # 「最後の suffix」しか触らないため意図と外れる可能性がある。
        return log_path.parent / f"{log_path.name}.{n}"

    try:
        oldest = _suffixed(retain)
        if oldest.exists():
            oldest.unlink()
        # shift from (retain-1) down to 1
        for i in range(retain - 1, 0, -1):
            src = _suffixed(i)
            if src.exists():
                dst = _suffixed(i + 1)
                src.replace(dst)
        # current → .1
        log_path.replace(_suffixed(1))
    except OSError as exc:
        print(
            f"[event_log] WARN: rotation failed for {log_path}: {exc}",
            file=sys.stderr,
        )
        # 失敗しても append は続行 (F3)。caller がそのまま open する。
        return


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

    ローテーション (ADR-0026 §6 / Issue #135):
        append 前に size を確認し、閾値超過時は `.1, .2, ..., .N` に shift。
        rotation 失敗は WARN のみで append は続行 (= 個別 event の at-most-once と整合)。

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

    # rotation は append 直前に判定。失敗しても append は続ける (F3)。
    _rotate_if_needed(log_path)

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
