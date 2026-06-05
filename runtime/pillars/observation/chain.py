"""
observe.py --chain の実装層 (Phase 5g.B #175)。

`logs/dispatch.jsonl` の `dispatch.sent` / `dispatch.acked` event から、
dispatch chain を時系列 view (text or mermaid) で表示する。

責務:
- iter_dispatch_events: dispatch.jsonl を読み event を yield、since / from
  filter を適用
- format_text:   時系列 ascii view (from → to: topic、ack 状態)
- format_mermaid: mermaid sequenceDiagram (= markdown / web 連携)
- summarize:     hop 数 / acked 率の集計
- cmd_chain:     observe.py から呼ばれる subcommand entry

ADR-0014 物理境界: host 側 (B 穴あき) から container の logs/ を読む観察専用。
stdlib only。trace.py の parse_since を再利用する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable


def _default_logs_dir() -> Path:
    """`$AI_ORG_OS_HOME/logs/` 解決。"""
    import os

    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "logs"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "logs"


def iter_dispatch_events(
    logs_dir: Path,
    *,
    from_mind: str | None = None,
    since_ts: str | None = None,
) -> Iterable[dict]:
    """`logs/dispatch.jsonl` から dispatch.sent / dispatch.acked を yield。

    filter:
    - since_ts: ISO 文字列。event.ts < since_ts は skip
    - from_mind: dispatch.sent の from field が一致するもののみ。acked event
      は msg_id 経由で sent と対応付けるため、まずは全 ack を保持しておき、
      呼び出し側で msg_id 一致のみを使う
    """
    path = logs_dir / "dispatch.jsonl"
    if not path.is_file():
        return
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        ev = obj.get("event")
        if ev not in ("dispatch.sent", "dispatch.acked"):
            continue
        ts = obj.get("ts")
        if not isinstance(ts, str):
            continue
        if since_ts is not None and ts < since_ts:
            continue
        if from_mind is not None and ev == "dispatch.sent":
            if obj.get("from") != from_mind:
                continue
        yield obj


def build_chain_view(events: Iterable[dict]) -> dict:
    """events から chain view を組み立てる。

    返す dict:
      timeline: [{ts, kind: "sent"|"acked", from, to, by, topic, msg_id,
                  acked: bool, ack_ts: str|None}], chronological
      summary: {sent_count, acked_count, unacked_count, ack_rate,
                participants: [Mind names], first_ts, last_ts}
    """
    sent_events: list[dict] = []
    ack_by_msgid: dict[str, dict] = {}
    for ev in events:
        if ev.get("event") == "dispatch.sent":
            sent_events.append(ev)
        elif ev.get("event") == "dispatch.acked":
            mid = ev.get("msg_id")
            if isinstance(mid, str):
                ack_by_msgid[mid] = ev

    # sent 単位で ack 紐付け
    timeline = []
    participants: set[str] = set()
    first_ts: str | None = None
    last_ts: str | None = None
    sent_count = len(sent_events)
    acked_count = 0
    for sent in sent_events:
        mid = sent.get("msg_id")
        ack = ack_by_msgid.get(mid) if isinstance(mid, str) else None
        entry = {
            "ts": sent.get("ts"),
            "kind": "sent",
            "from": sent.get("from") or "?",
            "to": sent.get("to") or "?",
            "by": None,
            "topic": sent.get("topic") or "",
            "msg_id": mid,
            "acked": ack is not None,
            "ack_ts": ack.get("ts") if ack else None,
        }
        timeline.append(entry)
        participants.add(entry["from"])
        participants.add(entry["to"])
        if ack is not None:
            acked_count += 1
        ts = entry["ts"]
        if isinstance(ts, str):
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

    # timeline は ts 昇順
    timeline.sort(key=lambda e: e.get("ts") or "")

    unacked_count = sent_count - acked_count
    ack_rate = (acked_count / sent_count) if sent_count > 0 else 0.0
    return {
        "timeline": timeline,
        "summary": {
            "sent_count": sent_count,
            "acked_count": acked_count,
            "unacked_count": unacked_count,
            "ack_rate": ack_rate,
            "participants": sorted(participants),
            "first_ts": first_ts,
            "last_ts": last_ts,
        },
    }


def _truncate_topic(topic: str, limit: int = 60) -> str:
    if len(topic) <= limit:
        return topic
    return topic[: limit - 3] + "..."


def format_text(view: dict) -> str:
    """ascii 1 行ごとに sent + ack 状態を出力。"""
    s = view["summary"]
    out: list[str] = []
    out.append("[Dispatch Chain]")
    if s["sent_count"] == 0:
        out.append("  (no dispatches in window)")
        return "\n".join(out) + "\n"
    out.append(
        f"  Period: {s['first_ts']} .. {s['last_ts']}"
    )
    out.append(
        f"  Sent: {s['sent_count']}   Acked: {s['acked_count']} "
        f"({s['ack_rate'] * 100:.1f}%)   Unacked: {s['unacked_count']}"
    )
    out.append(
        f"  Participants: {', '.join(s['participants'])}"
    )
    out.append("")
    out.append("[Timeline]")
    for entry in view["timeline"]:
        marker = "✓" if entry["acked"] else "·"
        # 古い Python / Windows console で文字化けすることがあるので fallback
        # 文字を使う (実 view は CI/Linux で出るので絵文字 OK だが安全側へ)
        marker = "[ack]" if entry["acked"] else "[..]"
        topic = _truncate_topic(entry["topic"])
        out.append(
            f"  {entry['ts']} {marker} {entry['from']:>14} -> {entry['to']:<14}: {topic}"
        )
    return "\n".join(out) + "\n"


def format_mermaid(view: dict) -> str:
    """mermaid sequenceDiagram (markdown 内に貼れる) を返す。

    参加者を declare してから dispatch.sent ごとに矢印を引く。ack は note 風に追加。
    """
    s = view["summary"]
    out: list[str] = []
    out.append("```mermaid")
    out.append("sequenceDiagram")
    for p in s["participants"]:
        # mermaid id は alphanumeric + _ のみ安全
        safe = p.replace("-", "_")
        out.append(f"  participant {safe} as {p}")
    for entry in view["timeline"]:
        f_safe = entry["from"].replace("-", "_")
        t_safe = entry["to"].replace("-", "_")
        topic = _truncate_topic(entry["topic"], 50)
        # mermaid は `:` の前後で label を取るので、topic 内の `:` は escape
        topic = topic.replace(":", "：")
        arrow = "->>" if entry["acked"] else "-->>"
        out.append(f"  {f_safe} {arrow} {t_safe}: {topic}")
    out.append("```")
    return "\n".join(out) + "\n"


def cmd_chain(
    *,
    from_mind: str | None = None,
    since: str | None = None,
    as_mermaid: bool = False,
    logs_dir: Path | None = None,
) -> int:
    """observe.py から呼ばれる entry。logs_dir は test 注入用。"""
    sys.path.insert(0, str(Path(__file__).parent))
    from trace import parse_since  # noqa: PLC0415

    try:
        since_ts = parse_since(since)
    except ValueError as exc:
        print(f"[chain] ERROR: {exc}", file=sys.stderr)
        return 2

    logs = logs_dir if logs_dir is not None else _default_logs_dir()
    events = list(iter_dispatch_events(logs, from_mind=from_mind, since_ts=since_ts))
    view = build_chain_view(events)
    # Windows / 古い locale で UnicodeEncodeError を避けるため stdout を utf-8
    # 明示 (= dispatch topic に em-dash / 全角文字が含まれていても落ちない)。
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    if as_mermaid:
        print(format_mermaid(view))
    else:
        print(format_text(view), end="")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dispatch chain visualizer")
    parser.add_argument("--from", dest="from_mind", help="filter by sender Mind")
    parser.add_argument("--since", help="time filter (1h / 30m / 5d / ISO ts)")
    parser.add_argument("--mermaid", action="store_true", help="output mermaid markdown")
    args = parser.parse_args()
    sys.exit(
        cmd_chain(
            from_mind=args.from_mind,
            since=args.since,
            as_mermaid=args.mermaid,
        )
    )
