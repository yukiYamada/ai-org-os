#!/usr/bin/env python3
r"""Brief inbox peek for mind-loop.sh integration (Fix #144 case A).

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

I/O bound (Codex P2 PR #145 fixup-2): per-cycle 呼び出しなので、`Nexus.read_inbox`
で **全 inbox file を full body 読み込む** のはサイズ blowup でコスト爆発する
(send_dispatch は body size を制限していない)。本 script は dir glob で
先頭 5 件だけ frontmatter のみを読む fast path を実装する。
"""

from __future__ import annotations

import os
import re
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


# Codex P2 (PR #145): claude -p に渡る argv 長を抑える。Windows
# CreateProcess の上限は ~32K、cmd.exe 経由だと ~8K。send_dispatch は topic
# の長さを制限していないので、巨大 topic が来ると claude 起動が落ちる。
# 各 topic を MAX_TOPIC_CHARS_PER_ENTRY、合計を MAX_TOTAL_SUMMARY_CHARS で
# 切り詰める (超過は ... + 件数だけ伝える)。
MAX_TOPIC_CHARS_PER_ENTRY = 80
MAX_TOTAL_SUMMARY_CHARS = 600
SUMMARY_LIMIT = 5

# storage.py の MIND_NAME_RE と同形 (二重防御として inline 化、
# storage import を fast path 経由で回避するため依存しない)。
_MIND_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _truncate(text: str, limit: int) -> str:
    """限度超過なら ... を末尾に付けて切る。limit=0 / 負は空文字。"""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def _inbox_dir(mind_name: str) -> Path:
    """$AI_ORG_OS_HOME/conduit-storage/inbox/<mind_name>/ を返す (ADR-0018)。"""
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        base = Path(env) / "conduit-storage"
    else:
        h = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
        base = Path(h) / ".ai-org-os" / "conduit-storage"
    return base / "inbox" / mind_name


def _parse_frontmatter_line(path: Path) -> tuple[str | None, str | None]:
    """先頭から frontmatter のみを line-by-line 読み、from / topic を抽出する。
    body は **読み込まない** (Codex P2 PR #145 fixup-2: body サイズ blowup
    対策)。
    """
    from_ = topic = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fp:
            in_fm = False
            for line in fp:
                line = line.rstrip("\r\n")
                if line == "---":
                    if not in_fm:
                        in_fm = True
                        continue
                    # 2 度目の `---` で frontmatter 終了 → body には触れず break
                    break
                if not in_fm:
                    # frontmatter 開始前に空行 / 他のテキストは無視
                    continue
                if line.startswith("from:") and from_ is None:
                    from_ = line.split(":", 1)[1].strip()
                elif line.startswith("topic:") and topic is None:
                    topic = line.split(":", 1)[1].strip()
                if from_ and topic:
                    break  # 2 fields 確定したら frontmatter の残りも読まない
    except OSError:
        pass
    return from_, topic


def _list_summaries(mind_name: str) -> tuple[list[tuple[str | None, str | None]], int]:
    """inbox dir を glob して先頭 SUMMARY_LIMIT 件の frontmatter のみ取得する。

    返り値: (entries, total_count)。entries は [(from, topic), ...] で先頭 5 件まで。

    Codex P2 PR #145 fixup-2: 旧実装は Nexus.read_inbox 経由で全 file の body
    を読み込んでいた。msg_id (= ファイル名) は時刻 prefix を含むので
    `sorted(glob('*.md'))` が概ね送信順で並ぶ。先頭 5 件だけ frontmatter
    line-by-line で読めば I/O は O(min(5, N) × frontmatter_size) に bounded。
    """
    inbox = _inbox_dir(mind_name)
    if not inbox.is_dir():
        return [], 0
    try:
        files = sorted(inbox.glob("*.md"))
    except OSError:
        return [], 0
    total = len(files)
    entries: list[tuple[str | None, str | None]] = []
    for path in files[:SUMMARY_LIMIT]:
        from_, topic = _parse_frontmatter_line(path)
        entries.append((from_, topic))
    return entries, total


def _summarize(entries: list[tuple[str | None, str | None]], total: int) -> str:
    """frontmatter entries → 1 行サマリ。total は全 inbox 件数、entries は先頭
    SUMMARY_LIMIT 件のみ。Codex P2 PR #145: topic / 合計長を切り詰める。
    """
    summaries: list[str] = []
    for from_, topic in entries:
        topic_clip = _truncate(topic or "", MAX_TOPIC_CHARS_PER_ENTRY)
        summaries.append(f"from {from_} '{topic_clip}'")
    extra = f" (+{total - SUMMARY_LIMIT} more)" if total > SUMMARY_LIMIT else ""
    full = f"{total} pending dispatch(es): " + "; ".join(summaries) + extra
    return _truncate(full, MAX_TOTAL_SUMMARY_CHARS)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0  # silent: 引数不足は何も出さずに終わる
    mind_name = argv[1]
    # path traversal / 巨大 name の防御。storage の validate と同じ regex。
    if not isinstance(mind_name, str) or not _MIND_NAME_RE.match(mind_name):
        return 0
    try:
        entries, total = _list_summaries(mind_name)
        if total == 0:
            return 0
        print(_summarize(entries, total))
    except Exception:
        # 全例外 silent skip。mind-loop は INBOX 句なしの既存 prompt にフォールバック。
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
