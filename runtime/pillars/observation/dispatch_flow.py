#!/usr/bin/env python3
"""
Dispatch Flow Observer (Observation Pillar v0.2 / #66)。

`$AI_ORG_OS_HOME/conduit-storage/{inbox,archive}/<to>/*.md` を全件走査し、
**frontmatter のみ** から `from → to` の集計 (count / first_at / last_at) を
返す。**本文は読まない** — Mindspace 不可侵 (ADR-0014) の精神を Conduit
storage 側にも拡張: Warden であっても通信内容の中身は見ない、流量と方向のみ
見る (`pillars/conduit/dispatch-format.md` 参照)。

設計の境界 (#66 Axiom 整合チェック):
- frontmatter = Conduit storage 公開領域、Mindspace 配下は読まない ✓
- 本文を読まない実装上の保証 = 「冒頭の `---` から 2 個目の `---` まで」のみ
  read。それ以降の line は parse しない (本文の `---` を frontmatter 終端と
  誤認する罠も避ける)
- ill-formed file は WARN を stderr に出して skip (analytics 全体を壊さない)
- OSError も skip (個別 file 単位、再帰中断しない)

依存: 標準ライブラリのみ (ADR-0005 / ADR-0009)。
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Iterator

# `from` / `to` の検証用 regex。storage._VALID_NAME_RE と同じ文字集合。
# 不正なフィールドが書かれた dispatch は集計から除外する (Warden 観測の
# 信頼性のため、汚染データを混ぜない)。
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# dispatched_at の検証 regex (ISO 8601 UTC, dispatch-format.md の契約)。
_DISPATCHED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _default_conduit_storage_dir() -> Path:
    """`$AI_ORG_OS_HOME/conduit-storage/` を返す (Phase 5b-4 / ADR-0018)。

    env が無ければ `~/.ai-org-os/conduit-storage/` を fallback。observe.py の
    `_conduit_storage_dir` と同じ流儀。
    """
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "conduit-storage"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "conduit-storage"


@dataclass(frozen=True)
class FlowEdge:
    """from → to の集計 1 件。

    inbox + archive を合算した「累積 dispatch 数」を表す。state を区別したい
    なら別途 inbox_count / archive_count を持つよう拡張するが、v0.2 では
    issue が指定する「from → to (count, last_at, first_at)」のみ。
    """

    from_mind: str
    to_mind: str
    count: int
    first_at: str  # ISO 8601 UTC、count==0 では空文字
    last_at: str   # ISO 8601 UTC


def parse_dispatch_frontmatter(path: Path) -> dict[str, str] | None:
    """1 つの dispatch file を開き、**frontmatter のみ** を dict で返す。

    本文に立ち入らないため、open() して 1 行ずつ読みつつ「冒頭の `---` →
    次の `---`」までで読み取りを打ち切る (file 全体を `read_text` しない)。
    `dispatch-format.md` で凍結された契約に従う:
      - 1 行目が `---` でない → None (ill-formed)
      - 2 個目の `---` が見つからない (EOF までに) → None
      - 必須フィールド (from / to / dispatched_at) のいずれかが欠落 → None
      - 必須フィールドの形式違反 → None

    None を返す場合は stderr に WARN を出す (運用者が後で原因調査できるよう)。
    """
    try:
        f = path.open("r", encoding="utf-8")
    except OSError as exc:
        print(
            f"[WARN] dispatch_flow: cannot open {path}: {exc}",
            file=sys.stderr,
        )
        return None

    meta: dict[str, str] = {}
    try:
        first = f.readline()
        if first.rstrip("\r\n") != "---":
            print(
                f"[WARN] dispatch_flow: no frontmatter at {path}",
                file=sys.stderr,
            )
            return None
        # 以降「---」が来るまで 1 行ずつ読む。本文には絶対に到達しない
        # ように、`for line in f` ではなく明示的に readline + break で
        # 打ち切る (本文側の `---` をうっかり拾わない)。
        while True:
            line = f.readline()
            if not line:
                # EOF: 終端 --- が見つからないまま file が終わった
                print(
                    f"[WARN] dispatch_flow: unterminated frontmatter at {path}",
                    file=sys.stderr,
                )
                return None
            stripped = line.rstrip("\r\n")
            if stripped == "---":
                break
            # `key: value` のみ受け付ける。コメント / 空行は無視。
            if not stripped or stripped.lstrip().startswith("#"):
                continue
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            meta[key.strip()] = value.strip()
    except OSError as exc:
        print(
            f"[WARN] dispatch_flow: read error at {path}: {exc}",
            file=sys.stderr,
        )
        return None
    except UnicodeDecodeError as exc:
        # Codex P1 (#93): 非 UTF-8 file が混入していた場合、readline() が
        # UnicodeDecodeError を上げる。OSError のみ catch していると 1 件の
        # 壊れた file が `observe.py --flow` 全体を落とす。本モジュールの
        # 契約 (「ill-formed file は skip して継続」) を守るため明示的に
        # catch して None を返す。frontmatter が UTF-8 でない時点で
        # dispatch-format.md の契約違反 (本文だけが non-UTF-8 でも、本文に
        # 到達する前に frontmatter 読み取り中の readline で発生しうる)。
        print(
            f"[WARN] dispatch_flow: decode error at {path}: {exc}",
            file=sys.stderr,
        )
        return None
    finally:
        f.close()

    # 必須フィールド + 形式検証。dispatch-format.md §「frontmatter フィール
    # ド契約」と整合する。topic / msg_id は本実装では使わない (集計に不要)
    # ので存在しなくても skip しない (将来の append-only 拡張に備える)。
    for required in ("from", "to", "dispatched_at"):
        if required not in meta:
            print(
                f"[WARN] dispatch_flow: missing '{required}' in {path}",
                file=sys.stderr,
            )
            return None

    if not _VALID_NAME_RE.match(meta["from"]):
        print(
            f"[WARN] dispatch_flow: invalid from='{meta['from']}' in {path}",
            file=sys.stderr,
        )
        return None
    if not _VALID_NAME_RE.match(meta["to"]):
        print(
            f"[WARN] dispatch_flow: invalid to='{meta['to']}' in {path}",
            file=sys.stderr,
        )
        return None
    if not _DISPATCHED_AT_RE.match(meta["dispatched_at"]):
        print(
            f"[WARN] dispatch_flow: invalid dispatched_at="
            f"'{meta['dispatched_at']}' in {path}",
            file=sys.stderr,
        )
        return None

    return meta


def iter_dispatches(
    storage_dir: Path | None = None,
) -> Iterator[dict[str, str]]:
    """inbox と archive を順に走査し、parse 成功した frontmatter dict を
    1 つずつ yield する。ill-formed / OSError は skip。

    走査対象: `<storage_dir>/{inbox,archive}/<recipient>/*.md`。
    `<recipient>` は dispatch-format.md の契約で `_VALID_NAME_RE` に合致。
    合致しないディレクトリ (= 攻撃的・誤投入) は **skip** して WARN。

    symlink フォロー禁止 (#66 セキュリティ要件): `os.scandir` で
    `is_symlink()` の項目は無視する。同じく recipient dir / msg file も
    symlink 経由の解決は禁止 (path traversal 防御)。
    """
    base = (
        Path(storage_dir)
        if storage_dir is not None
        else _default_conduit_storage_dir()
    )
    for state_dir_name in ("inbox", "archive"):
        state_dir = base / state_dir_name
        if not state_dir.is_dir():
            continue
        try:
            recipients = list(os.scandir(state_dir))
        except OSError as exc:
            print(
                f"[WARN] dispatch_flow: scandir failed at {state_dir}: {exc}",
                file=sys.stderr,
            )
            continue
        for rec_entry in recipients:
            try:
                if rec_entry.is_symlink():
                    # symlink 経由は path traversal の窓
                    continue
                if not rec_entry.is_dir():
                    continue
            except OSError:
                continue
            if not _VALID_NAME_RE.match(rec_entry.name):
                print(
                    f"[WARN] dispatch_flow: skipping malformed recipient "
                    f"dir name '{rec_entry.name}' under {state_dir}",
                    file=sys.stderr,
                )
                continue
            try:
                msg_entries = list(os.scandir(rec_entry.path))
            except OSError as exc:
                print(
                    f"[WARN] dispatch_flow: scandir failed at "
                    f"{rec_entry.path}: {exc}",
                    file=sys.stderr,
                )
                continue
            for msg_entry in msg_entries:
                try:
                    if msg_entry.is_symlink():
                        continue
                    if not msg_entry.is_file():
                        continue
                except OSError:
                    continue
                if not msg_entry.name.endswith(".md"):
                    continue
                meta = parse_dispatch_frontmatter(Path(msg_entry.path))
                if meta is None:
                    continue
                # to フィールドと recipient dir が食い違うのは契約違反
                # (storage.py が必ず一致させる)。報告して skip。
                if meta["to"] != rec_entry.name:
                    print(
                        f"[WARN] dispatch_flow: 'to'={meta['to']!r} mismatches "
                        f"recipient dir '{rec_entry.name}' at "
                        f"{msg_entry.path}",
                        file=sys.stderr,
                    )
                    continue
                yield meta


def aggregate_flow(
    storage_dir: Path | None = None,
    *,
    metas: Iterable[dict[str, str]] | None = None,
) -> list[FlowEdge]:
    """from → to で集計した FlowEdge のリストを返す。

    `metas` を渡せばそれを集計対象として使う (テストで pre-built リストを
    渡すための injection 点)。省略時は `iter_dispatches(storage_dir)` を
    そのまま消費する。

    結果は (from_mind, to_mind) の辞書順でソート。同 edge 内の first_at /
    last_at は ISO 8601 UTC の文字列比較で決定 (`Z` サフィックス付き
    秒精度なので lexicographic == 時系列、契約より)。
    """
    source: Iterable[dict[str, str]]
    if metas is not None:
        source = metas
    else:
        source = iter_dispatches(storage_dir)
    buckets: dict[tuple[str, str], dict[str, str | int]] = {}
    for m in source:
        key = (m["from"], m["to"])
        cur = buckets.get(key)
        if cur is None:
            buckets[key] = {
                "count": 1,
                "first_at": m["dispatched_at"],
                "last_at": m["dispatched_at"],
            }
        else:
            cur["count"] = int(cur["count"]) + 1
            # 文字列比較で min / max を更新 (lexicographic == 時系列)
            if m["dispatched_at"] < str(cur["first_at"]):
                cur["first_at"] = m["dispatched_at"]
            if m["dispatched_at"] > str(cur["last_at"]):
                cur["last_at"] = m["dispatched_at"]
    edges = [
        FlowEdge(
            from_mind=k[0],
            to_mind=k[1],
            count=int(v["count"]),
            first_at=str(v["first_at"]),
            last_at=str(v["last_at"]),
        )
        for k, v in buckets.items()
    ]
    edges.sort(key=lambda e: (e.from_mind, e.to_mind))
    return edges


def format_flow_table(edges: list[FlowEdge]) -> str:
    """human-readable な ASCII テーブルとして整形する。

    observe.py の他セクションと並べて出すため、左寄せ + パディング揃え。
    edges が空のときは `(no dispatches)` を返す。
    """
    if not edges:
        return "(no dispatches)"
    headers = ("from", "to", "count", "first_at", "last_at")
    rows = [
        (e.from_mind, e.to_mind, str(e.count), e.first_at, e.last_at)
        for e in edges
    ]
    widths = [
        max(len(headers[i]), max(len(r[i]) for r in rows))
        for i in range(len(headers))
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    for row in rows:
        lines.append(fmt.format(*row))
    return "\n".join(lines)


def flow_to_json(edges: list[FlowEdge]) -> list[dict]:
    """machine-readable な dict のリストに変換する。"""
    return [asdict(e) for e in edges]


# ---- CLI (主に動作確認 / observe.py からの委譲先) ---------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="dispatch_flow.py",
        description="Dispatch flow observer (Observation v0.2 / #66)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON instead of an ASCII table",
    )
    parser.add_argument(
        "--storage-dir",
        type=Path,
        default=None,
        help=(
            "override conduit-storage dir (default: "
            "$AI_ORG_OS_HOME/conduit-storage)"
        ),
    )
    ns = parser.parse_args(argv)
    edges = aggregate_flow(ns.storage_dir)
    if ns.json:
        print(json.dumps(flow_to_json(edges), ensure_ascii=False, indent=2))
    else:
        print(format_flow_table(edges))
    return 0


if __name__ == "__main__":
    sys.exit(main())
