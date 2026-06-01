"""
observe.py --trace の実装層 (ADR-0026 §7)。

$AI_ORG_OS_HOME/logs/ 配下の全 JSONL を読み、時系列 (ts 昇順) に merge sort
して人間可読 1 行に整形する。

責務:
- iter_event_files: logs/ 配下の *.jsonl を recurse で列挙
- parse_since:      --since の指定 (1h / 30m / 5d / ISO 文字列) を ISO 文字列に正規化
- iter_events:      JSONL を 1 行ずつ parse、壊れた行は skip + stderr WARN (F3)、
                    since filter を適用、(ts, event_dict) を yield
- format_event:     event 種別ごとに人間可読 1 行を返す。未知 event は generic 形式

ADR-0014 物理境界: 本モジュールは host 側 (B 穴あき) から container の
$AI_ORG_OS_HOME/logs/ を読む読み手専用。書き込みはしない。

stdlib only (json / re / sys / datetime / pathlib)。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


def _default_logs_dir() -> Path:
    """$AI_ORG_OS_HOME/logs/ (ADR-0018 / ADR-0026 §1)。observe.py から
    import せず関数化、event_log.py 側の同名関数と意味的に揃える。"""
    import os

    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "logs"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "logs"


_RELATIVE_SINCE_RE = re.compile(r"^(\d+)([smhd])$")


def parse_since(spec: str | None, *, now: datetime | None = None) -> str | None:
    """--since の値を「ts と string 比較できる ISO-8601 文字列」に変換する。

    受理する形式:
    - 相対: "1h" / "30m" / "10s" / "5d" (時 / 分 / 秒 / 日)
    - 絶対: "2026-06-01T00:00:00Z" / "2026-06-01T00:00" (Z 推奨だが許容)
    - None / 空文字: そのまま None (= filter 無し)

    戻り値: ISO-8601 UTC ms precision string (string 比較で時系列順)、
    または None。malformed なら ValueError。

    `now` 引数は test 用注入点。本番は datetime.now(UTC)。
    """
    if spec is None or spec == "":
        return None
    spec = spec.strip()
    base_now = now if now is not None else datetime.now(timezone.utc)

    # 相対指定: 1h / 30m / 10s / 5d
    m = _RELATIVE_SINCE_RE.match(spec)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit == "s":
            delta = timedelta(seconds=amount)
        elif unit == "m":
            delta = timedelta(minutes=amount)
        elif unit == "h":
            delta = timedelta(hours=amount)
        else:  # "d"
            delta = timedelta(days=amount)
        target = base_now - delta
        return target.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    # 絶対 ISO 形式: Z / +00:00 / 末尾 timezone 無し のいずれも受ける
    s = spec
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(
            f"--since '{spec}' is not a relative duration (e.g. '1h', '30m') "
            f"nor an ISO-8601 timestamp"
        ) from exc
    if dt.tzinfo is None:
        # naive を UTC とみなす (ユーザー意図の最も安全な解釈)
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iter_event_files(logs_dir: Path) -> list[Path]:
    """logs_dir 配下の *.jsonl を recurse で集める (mind-loop は minds/<m>/ 配下)。
    順序は不定だが、後段で ts 昇順 merge sort するので呼び出し側は意識しない。"""
    if not logs_dir.is_dir():
        return []
    return sorted(logs_dir.rglob("*.jsonl"))


def iter_events(
    logs_dir: Path,
    *,
    since_ts: str | None = None,
    stderr: object | None = None,
) -> Iterator[dict]:
    """全 JSONL を読み、ts 昇順に event dict を yield する。

    - 壊れた行は skip し stderr に WARN (= F3 / ADR-0026 §7 / §5)。`ts` 欠落も skip。
    - since_ts が与えられたら、event["ts"] >= since_ts のものだけ通す
      (string 比較で OK = ISO-8601 ms precision の lexical sort は時系列順)。
    - メモリ: 全 event を 1 リストに集めて sort する単純実装。Phase 5f Step 1 では
      logs/ 容量 << RAM の想定。rotation 後 (PR-F) でも 1 file 10MB × 数件想定で
      問題なし。容量爆発時は別途 streaming-merge sort に差し替え。

    `stderr` は test 用注入点 (StringIO 等)。None なら sys.stderr。
    """
    if stderr is None:
        stderr = sys.stderr
    events: list[dict] = []
    for path in iter_event_files(logs_dir):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[trace] WARN: cannot read {path}: {exc}", file=stderr)
            continue
        for lineno, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"[trace] WARN: skip malformed line {path}:{lineno}: {exc}",
                    file=stderr,
                )
                continue
            if not isinstance(obj, dict):
                print(
                    f"[trace] WARN: skip non-object line {path}:{lineno}",
                    file=stderr,
                )
                continue
            ts = obj.get("ts")
            if not isinstance(ts, str):
                print(
                    f"[trace] WARN: skip line without 'ts' string {path}:{lineno}",
                    file=stderr,
                )
                continue
            if since_ts is not None and ts < since_ts:
                continue
            events.append(obj)
    events.sort(key=lambda e: e.get("ts", ""))
    yield from events


def format_event(e: dict) -> str:
    """1 event を `[ts] <human-readable summary>` に整形する。

    未知 event は generic fallback (`[ts] <event> actor=<actor> field=value ...`)。
    """
    ts = e.get("ts", "?")
    event = e.get("event", "?")
    actor = e.get("actor", "?")

    if event == "dispatch.sent":
        return (
            f"[{ts}] {e.get('from', '?')}→{e.get('to', '?')} "
            f"dispatch '{e.get('topic', '')}' (msg={e.get('msg_id', '?')})"
        )
    if event == "dispatch.acked":
        return (
            f"[{ts}] {e.get('by', '?')} acked dispatch "
            f"(msg={e.get('msg_id', '?')})"
        )
    if event == "cycle.start":
        return f"[{ts}] conductor cycle {e.get('cycle', '?')} start"
    if event == "cycle.end":
        return (
            f"[{ts}] conductor cycle {e.get('cycle', '?')} end "
            f"(duration={e.get('duration_ms', '?')}ms, "
            f"status={e.get('judgment_status', '?')})"
        )
    if event == "judgment.invoked":
        return (
            f"[{ts}] judgment invoked cycle {e.get('cycle', '?')} "
            f"(minds={e.get('input_minds', '?')})"
        )
    if event == "judgment.result":
        return (
            f"[{ts}] judgment cycle {e.get('cycle', '?')}: "
            f"status={e.get('status', '?')} "
            f"judgments={e.get('judgments_count', '?')} "
            f"planned={e.get('dispatches_planned', '?')} "
            f"warden_replies={e.get('warden_replies_read', '?')}"
        )
    if event == "warden_inbox.read":
        return (
            f"[{ts}] warden_inbox read cycle {e.get('cycle', '?')}: "
            f"{e.get('count', '?')} reply(s)"
        )
    if event == "warden_inbox.ack":
        return (
            f"[{ts}] warden_inbox acked cycle {e.get('cycle', '?')} "
            f"(msg={e.get('msg_id', '?')})"
        )
    if event == "actuator.prompt":
        return (
            f"[{ts}] actuator→{e.get('target', '?')} prompt "
            f"'{e.get('topic', '')}' (msg={e.get('msg_id', '?')}, "
            f"result={e.get('result', '?')})"
        )
    if event == "actuator.skipped":
        base = (
            f"[{ts}] actuator skipped {e.get('target', '?')} "
            f"(reason={e.get('reason', '?')})"
        )
        if "error" in e:
            base += f" [{e['error']}]"
        return base
    if event == "mind_loop.start":
        return (
            f"[{ts}] {actor} mind-loop cycle {e.get('cycle', '?')} start "
            f"(pid={e.get('pid', '?')})"
        )
    if event == "mind_loop.end":
        return (
            f"[{ts}] {actor} mind-loop cycle {e.get('cycle', '?')} end "
            f"(exit={e.get('exit_code', '?')}, "
            f"duration={e.get('duration_s', '?')}s)"
        )

    # generic fallback
    extras = " ".join(
        f"{k}={v}"
        for k, v in sorted(e.items())
        if k not in {"ts", "event", "actor"}
    )
    return f"[{ts}] {event} actor={actor}" + (f" {extras}" if extras else "")


def cmd_trace(
    *,
    since: str | None = None,
    logs_dir: Path | None = None,
    out: object | None = None,
    stderr: object | None = None,
) -> int:
    """`observe.py --trace [--since ...]` のエントリ。

    戻り値: 終了コード (0=正常、2=arg error)。

    Windows console は default で cp932 (#137)。JSONL は UTF-8 で保存
    されているのに stdout が cp932 だと、日本語 topic/body が化けて
    観察精度が落ちる。`sys.stdout` (Python 3.7+ TextIOWrapper) であれば
    `reconfigure` を呼んで UTF-8 に切り替える。`errors="replace"` で
    unmappable 文字は U+FFFD に degrade させ、クラッシュさせない。
    StringIO 等 (test 注入 / pipe) は `reconfigure` を持たないので
    自然に no-op となり、既存 test injection path を破壊しない。

    ADR-0014 物理境界: 本処理は host 側 (B 穴あき) の出力 encoding 是正で、
    container 内部の log 書き込み実装 (UTF-8 JSONL) には触れない。
    """
    if out is None:
        out = sys.stdout
    if stderr is None:
        stderr = sys.stderr
    # #137 fix: Windows console (cp932) で日本語 topic/body が化けるのを防ぐ。
    # hasattr で TextIOWrapper のみを対象にし、StringIO / mock を素通しする。
    if hasattr(out, "reconfigure"):
        try:
            out.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (ValueError, AttributeError):
            # 既に UTF-8 だったり、reconfigure が無効な stream の場合は黙って続行
            pass
    try:
        since_ts = parse_since(since)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=stderr)
        return 2
    target = logs_dir if logs_dir is not None else _default_logs_dir()
    count = 0
    for e in iter_events(target, since_ts=since_ts, stderr=stderr):
        print(format_event(e), file=out)
        count += 1
    if count == 0:
        # noise を減らすため stdout には何も出さない。stderr に hint 1 行。
        print(
            f"[trace] no events (logs_dir={target}, since={since or 'none'})",
            file=stderr,
        )
    return 0
