#!/usr/bin/env python3
"""
Resource Usage Observer (Observation Pillar v0.2 / #66)。

`$AI_ORG_OS_HOME/minds/<mind>/` および `$AI_ORG_OS_HOME/conduit-storage/` の
バイト数 / ファイル数を計測する。**ファイル名 / 中身は読まない、`stat` の
`st_size` だけ集計** — Mindspace 不可侵 (ADR-0014) の精神を保つ。

設計の境界 (#66 Axiom 整合チェック):
- `os.scandir` 再帰、symlink フォロー禁止 (path traversal / 二重カウント防御)
- OSError は WARN を出して skip (集計全体を止めない)
- 単純な「総バイト数」と「ファイル数」のみ。dirent 名は出力に含めない
- 出力に登場するのは「Mind 名 (= Mindspace dir 名)」と「カテゴリ名 (mindspace
  / conduit-storage)」のみ。ファイル単位の名前 / mtime / 内容は **載せない**

依存: 標準ライブラリのみ (ADR-0005 / ADR-0009)。
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# Mind 名 (= mindspace dir 名) の検証。observe.py / storage.py と同じ規則。
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _default_home() -> Path:
    """`$AI_ORG_OS_HOME` (Phase 5b-4 / ADR-0018)。

    observe.py `_runtime_home` と同じ流儀。
    """
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os"


@dataclass(frozen=True)
class UsageBucket:
    """1 つの集計単位 (= 1 Mind か、conduit-storage 全体など)。

    `name` は category-relative なラベル (例: "alice" / "conduit-storage")。
    `category` は "mindspace" / "conduit-storage" のいずれか。`file_count` は
    再帰的に数えた regular file 数、`byte_count` は `stat().st_size` の総和。
    """

    name: str
    category: str
    file_count: int
    byte_count: int


def _scan_dir_size(root: Path) -> tuple[int, int]:
    """root 配下を再帰的に走査して (file_count, byte_count) を返す。

    - symlink (ファイル / ディレクトリとも) は **辿らず無視** する
      (`is_symlink()` で判定)。symlink 経由で外部 path や同一ファイルの
      二重カウントが起きる窓を塞ぐ
    - 個別の OSError は WARN を出して skip し、走査全体は継続
      (大量 Mind 環境で 1 file の lock が全集計を壊さないように)
    - `os.scandir` は dirent の `stat()` を file system に問い合わせるが、
      `entry.stat(follow_symlinks=False)` で symlink target を解決しない
    """
    if not root.is_dir():
        return (0, 0)
    file_count = 0
    byte_count = 0
    # iterative DFS。深さによる recursion depth limit を避ける。
    stack: list[Path] = [root]
    while stack:
        cur = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError as exc:
            print(
                f"[WARN] resource_usage: scandir failed at {cur}: {exc}",
                file=sys.stderr,
            )
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        # symlink は集計に含めない (#66 セキュリティ要件)
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                        continue
                    if entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        file_count += 1
                        byte_count += int(st.st_size)
                        continue
                    # block device / fifo / socket 等は無視 (運用上現れない
                    # はずだが、防御的に skip して総量にも入れない)
                except OSError as exc:
                    print(
                        f"[WARN] resource_usage: stat failed at "
                        f"{entry.path}: {exc}",
                        file=sys.stderr,
                    )
                    continue
    return (file_count, byte_count)


def per_mind_usage(home_dir: Path | None = None) -> list[UsageBucket]:
    """`<home>/minds/<mind>/` 配下を 1 Mind ずつ集計する。

    走査対象が無い (= まだ spawn-mind されてない環境) 場合は空リスト。
    Mind 名が `_VALID_NAME_RE` に合致しない dir は WARN で skip する
    (誤投入 / 攻撃的 path から守る)。symlink な mindspace dir も skip。
    """
    home = Path(home_dir) if home_dir is not None else _default_home()
    minds_root = home / "minds"
    if not minds_root.is_dir():
        return []
    buckets: list[UsageBucket] = []
    try:
        entries = list(os.scandir(minds_root))
    except OSError as exc:
        print(
            f"[WARN] resource_usage: scandir failed at {minds_root}: {exc}",
            file=sys.stderr,
        )
        return []
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if not _VALID_NAME_RE.match(entry.name):
            print(
                f"[WARN] resource_usage: skipping malformed mind dir name "
                f"'{entry.name}' under {minds_root}",
                file=sys.stderr,
            )
            continue
        files, total = _scan_dir_size(Path(entry.path))
        buckets.append(
            UsageBucket(
                name=entry.name,
                category="mindspace",
                file_count=files,
                byte_count=total,
            )
        )
    buckets.sort(key=lambda b: b.name)
    return buckets


def conduit_storage_usage(home_dir: Path | None = None) -> UsageBucket:
    """`<home>/conduit-storage/` 全体を 1 バケットに集計する。

    inbox / archive を区別せず合算。issue #66 §「Nexus storage の総バイト数」
    の要件に合わせる (粒度は将来 v1.0 で per-recipient まで分けてもよい)。
    """
    home = Path(home_dir) if home_dir is not None else _default_home()
    root = home / "conduit-storage"
    files, total = _scan_dir_size(root)
    return UsageBucket(
        name="conduit-storage",
        category="conduit-storage",
        file_count=files,
        byte_count=total,
    )


def all_usage(home_dir: Path | None = None) -> list[UsageBucket]:
    """per-mind + conduit-storage をまとめて返す (mindspace 群 → storage の順)。

    observe.py 側はこのリストをそのまま format 関数に渡せる。
    """
    out: list[UsageBucket] = list(per_mind_usage(home_dir))
    out.append(conduit_storage_usage(home_dir))
    return out


def _human_bytes(n: int) -> str:
    """ASCII テーブル用の短い人間可読バイト表記。

    KiB / MiB / GiB の 2 進接頭辞。 1024 未満は素のバイトを返す。
    境界精度は重要ではないため小数点 1 桁。
    """
    if n < 1024:
        return f"{n}B"
    units = ("KiB", "MiB", "GiB", "TiB")
    size = float(n) / 1024.0
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{n}B"  # 到達不能だが防御


def format_usage_table(buckets: list[UsageBucket]) -> str:
    """human-readable ASCII テーブル。observe.py の他セクションと揃える。"""
    if not buckets:
        return "(no resources)"
    headers = ("category", "name", "files", "bytes", "size")
    rows = [
        (
            b.category,
            b.name,
            str(b.file_count),
            str(b.byte_count),
            _human_bytes(b.byte_count),
        )
        for b in buckets
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


def usage_to_json(buckets: list[UsageBucket]) -> list[dict]:
    return [asdict(b) for b in buckets]


# ---- CLI ----


def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="resource_usage.py",
        description="Resource usage observer (Observation v0.2 / #66)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON instead of an ASCII table",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="override AI_ORG_OS_HOME (default: $AI_ORG_OS_HOME or ~/.ai-org-os)",
    )
    ns = parser.parse_args(argv)
    buckets = all_usage(ns.home)
    if ns.json:
        print(json.dumps(usage_to_json(buckets), ensure_ascii=False, indent=2))
    else:
        print(format_usage_table(buckets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
