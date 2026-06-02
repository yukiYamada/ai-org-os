#!/usr/bin/env python3
"""Brief inbox peek for mind-loop.sh integration (Fix #144 case A).

Usage:
    python peek_inbox.py <mind_name>

Prints a single-line summary to stdout when the recipient inbox is non-empty:
    "N pending dispatch(es): from X 'topic1'; from Y 'topic2'..."

Exits 0 on success (with or without output). Exits 0 also on **any error**
(silent fallback) so mind-loop's `if [ -n "$PEEK_SUMMARY" ]` gracefully
falls back to the default prompt.

Rationale (Fix #144 case A): mind-loop は claude -p の起動コストが大きいため、
inbox 状態を prompt 冒頭にプレヒントすると claude が「空 cycle 判定で早期 exit」
する時間を削減できる。peek 自体の失敗は cycle 進行を止めない (F3 / ADR-0013 §1)。

Standalone CLI として分離した理由: bash の `python -c "..."` インライン経由だと
MSYS bash の path translation (`/c/...` → `C:\...`) が argv 経由でないと働かず、
Windows ネイティブ python.exe が import path を解釈できない。本ファイルを
独立 script にすれば、`__file__` ベースの sys.path 解決が確実に動く。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows console (cp932 等) で UTF-8 を確実に出すための reconfigure。
# topic / from_mind に non-ASCII (em dash や日本語) が含まれると
# print() が UnicodeEncodeError で死に、silent skip 化して mind-loop の
# prompt に INBOX 句が挿入されなくなる回帰を防ぐ。
# (#137 / PR #140 と同じパターン、stdout encoding が読めない場合は no-op)。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, AttributeError):
        pass

# storage.py は同じディレクトリ内。__file__ ベースで解決すれば
# MSYS/Windows path 変換に影響されない。
sys.path.insert(0, str(Path(__file__).resolve().parent))


# Codex P2 (PR #145): claude -p に渡る argv 長を抑える。Windows
# CreateProcess の上限は ~32K、cmd.exe 経由だと ~8K。send_dispatch は topic
# の長さを制限していないので、巨大 topic が来ると claude 起動が落ちる。
# 各 topic を MAX_TOPIC_CHARS_PER_ENTRY、合計を MAX_TOTAL_SUMMARY_CHARS で
# 切り詰める (超過は ... + 件数だけ伝える)。
MAX_TOPIC_CHARS_PER_ENTRY = 80
MAX_TOTAL_SUMMARY_CHARS = 600


def _truncate(text: str, limit: int) -> str:
    """限度超過なら ... を末尾に付けて切る。limit=0 / 負は空文字。"""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def _summarize(messages: list[dict]) -> str:
    """messages → 1 行サマリ。先頭 5 件まで、超過分は `(+N more)` で表記。
    Codex P2 (PR #145): topic / 合計長を切り詰めて argv length blowup を防ぐ。
    """
    summaries: list[str] = []
    for m in messages[:5]:
        content = m.get("content", "")
        from_ = topic = None
        for line in content.split("\n"):
            if line.startswith("from:") and from_ is None:
                from_ = line.split(":", 1)[1].strip()
            elif line.startswith("topic:") and topic is None:
                topic = line.split(":", 1)[1].strip()
            if from_ and topic:
                break
        topic_clip = _truncate(topic or "", MAX_TOPIC_CHARS_PER_ENTRY)
        summaries.append(f"from {from_} '{topic_clip}'")
    n = len(messages)
    extra = f" (+{n - 5} more)" if n > 5 else ""
    full = f"{n} pending dispatch(es): " + "; ".join(summaries) + extra
    # 全体サイズ守る (1 件目巨大、5 件大量 等の合わせ技に備える safety net)
    return _truncate(full, MAX_TOTAL_SUMMARY_CHARS)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0  # silent: 引数不足は何も出さずに終わる
    mind_name = argv[1]
    try:
        # 遅延 import: storage 取得に失敗してもプロセス自体は 0 で抜ける
        from storage import Nexus  # noqa: PLC0415
    except Exception:
        return 0
    try:
        nx = Nexus(identity=None)
        result = nx.read_inbox(mind_name)
        messages = result.get("messages", [])
        if not messages:
            return 0
        print(_summarize(messages))
    except Exception:
        # Nexus.read_inbox の validate (= mind_name の regex 違反等) も含めて
        # 全て silent skip。mind-loop は INBOX 句なしの既存 prompt にフォールバック。
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
