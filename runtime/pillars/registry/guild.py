#!/usr/bin/env python3
"""
Guild Catalog (Phase 5c-1 / ADR-0019 / ADR-0020)。

Guild = 組織枠の物理表現 (ADR-0019)。本モジュールは:

- Guild manifest のロード (`<source>/<name>/manifest.md`)
- Guild membership 検証 (kind ∈ manifest.kinds, persona ∈ manifest.personas)
- Mind の所属 Guild 解決 (`.mind-meta.md` の `guild:` フィールド)
- Issue の所属 Guild 解決 (Issue frontmatter の `guild:` フィールド)
- Guild member 集約 (`.mind-meta.md` を走査して算出、ADR-0019 §1)

を提供する。

Phase 5c-1 (ADR-0020) で Guild manifest の source は 2 layer overlay に:
  1. `$AI_ORG_OS_HOME/guilds/<name>/` (利用者の組織実体、優先)
  2. `templates/guilds/<name>/` (ai-org-os 同梱テンプレ、fallback)

設計の根拠:
- ADR-0019 — Guild 物理表現と「組織パッケージ」基礎
- ADR-0020 — 世界の構成 (runtime/) vs 組織依存物 (templates/ + AI_ORG_OS_HOME)
  の物理分離。Guild manifest はこの「依存物」カテゴリ。
- ADR-0011 — Pillar 編集不可。本ファイルは Registry Pillar 配下
- ADR-0017 — 層 A / 層 B 分離。本モジュールは層 B (組織) を機械検証で
  支える infrastructure 層

依存: 標準ライブラリのみ (ADR-0005 / ADR-0009)。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# 本ファイルは runtime/pillars/registry/ 配下。
# Phase 5c-1 / ADR-0020 で Guild source は 2 layer overlay:
# - home  = $AI_ORG_OS_HOME/guilds/ (利用者の実体, 優先)
# - templ = templates/guilds/       (同梱テンプレ, fallback)
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_DIR = _RUNTIME_DIR.parent
_TEMPLATES_DIR = _REPO_DIR / "templates"

# 名前検証。spawn-mind.sh / inbox.py と同じ文字集合に揃える。
GUILD_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

DEFAULT_GUILD = "default"


class GuildError(Exception):
    """Guild 関連の汎用エラー。具体的サブクラスを使う。"""


class GuildNotFoundError(GuildError):
    """指定 Guild の manifest が存在しない。"""


class GuildValidationError(GuildError):
    """Guild 名 / kind / persona 等が manifest の制約に違反。"""


@dataclass(frozen=True)
class GuildManifest:
    """Guild manifest (`runtime/guilds/<name>/manifest.md`) の中身。

    schema_version != "0.1" は v0.1 では受理しない (ADR-0019 §2)。
    """

    name: str
    schema_version: str
    purpose: str
    kinds: tuple[str, ...]
    personas: tuple[str, ...]
    path: Path
    raw_frontmatter: dict[str, str] = field(default_factory=dict)


def _home_guilds_dir() -> Path | None:
    """利用者の Guild 実体 dir (`$AI_ORG_OS_HOME/guilds`)。

    Phase 5c-1 / ADR-0020: overlay の上層。未設定なら None。
    """
    home = os.environ.get("AI_ORG_OS_HOME")
    if home:
        return Path(home) / "guilds"
    h = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if h:
        return Path(h) / ".ai-org-os" / "guilds"
    return None


def _template_guilds_dir() -> Path:
    """同梱テンプレ Guild dir (`templates/guilds`)。ADR-0020 §3 fallback 層。"""
    return _TEMPLATES_DIR / "guilds"


def _search_dirs(guilds_dir: Path | None) -> list[Path]:
    """lookup する dir を「優先度が高い順」で返す (Phase 5c-1 / ADR-0020)。

    - guilds_dir が明示されていれば「テスト用 override」としてそれだけを返す
    - そうでなければ home (実体) を先頭、templates (同梱) を末尾に
    """
    if guilds_dir is not None:
        return [Path(guilds_dir)]
    # 互換: AI_ORG_OS_GUILDS_DIR env が指定されていればそれを最優先 (テスト用)。
    env = os.environ.get("AI_ORG_OS_GUILDS_DIR")
    if env:
        return [Path(env)]
    dirs: list[Path] = []
    home = _home_guilds_dir()
    if home is not None and home.is_dir():
        dirs.append(home)
    dirs.append(_template_guilds_dir())
    return dirs


def _default_minds_dir() -> Path:
    """`$AI_ORG_OS_HOME/minds/`。observe.py の `_minds_dir` と同じ規約。"""
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "minds"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "minds"


def _validate_guild_name(name: str) -> None:
    if not isinstance(name, str) or not GUILD_NAME_RE.match(name):
        raise GuildValidationError(
            f"invalid guild name: must match {GUILD_NAME_RE.pattern}"
        )


def _parse_yaml_list(value: str) -> tuple[str, ...]:
    """`[a, b, c]` 形式の最小パーサ。yaml ライブラリは使わない (依存ゼロ方針)。

    `[a,b,c]` / `[ a , b ]` / `[]` を許容。空要素は無視。
    """
    s = value.strip()
    if not (s.startswith("[") and s.endswith("]")):
        # bare scalar (a) → 単一要素として扱う
        return (s,) if s else ()
    inner = s[1:-1]
    if not inner.strip():
        return ()
    items = [item.strip() for item in inner.split(",")]
    return tuple(item for item in items if item)


def _parse_manifest_frontmatter(text: str) -> dict[str, str] | None:
    """`---` で囲まれた frontmatter を `{key: value}` dict に。

    inbox.py の `_parse_issue_file` と同じ流儀。listy な値は raw string のまま
    返し、呼び出し側で `_parse_yaml_list` する。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None
    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def load_manifest(
    guild_name: str,
    guilds_dir: Path | None = None,
) -> GuildManifest:
    """`<source>/<name>/manifest.md` を読んで GuildManifest を返す。

    Phase 5c-1 / ADR-0020: source は 2 layer overlay (home → templates)。
    最初に見つかった manifest.md を採用する。

    例外:
        GuildValidationError: guild_name 形式違反 / schema_version 不一致 /
            frontmatter 必須フィールド欠落
        GuildNotFoundError:   どの source にも manifest.md が無い
    """
    _validate_guild_name(guild_name)
    sources = _search_dirs(guilds_dir)
    manifest_path: Path | None = None
    for src in sources:
        candidate = src / guild_name / "manifest.md"
        if candidate.is_file():
            manifest_path = candidate
            break
    if manifest_path is None:
        attempted = ", ".join(str(s / guild_name / "manifest.md") for s in sources)
        raise GuildNotFoundError(
            f"guild '{guild_name}' has no manifest (looked at: {attempted})"
        )
    text = manifest_path.read_text(encoding="utf-8")
    fm = _parse_manifest_frontmatter(text)
    if fm is None:
        raise GuildValidationError(
            f"guild '{guild_name}' manifest has no/invalid frontmatter"
        )
    # 必須フィールドチェック
    required = ("guild", "schema_version", "kinds", "personas")
    for key in required:
        if key not in fm:
            raise GuildValidationError(
                f"guild '{guild_name}' manifest missing '{key}'"
            )
    # guild フィールドはディレクトリ名と一致しなければならない
    if fm["guild"] != guild_name:
        raise GuildValidationError(
            f"guild '{guild_name}' manifest declares guild='{fm['guild']}' (mismatch)"
        )
    if fm["schema_version"] != "0.1":
        raise GuildValidationError(
            f"guild '{guild_name}' schema_version='{fm['schema_version']}' "
            f"unsupported (v0.1 expects '0.1')"
        )
    return GuildManifest(
        name=guild_name,
        schema_version=fm["schema_version"],
        purpose=fm.get("purpose", ""),
        kinds=_parse_yaml_list(fm["kinds"]),
        personas=_parse_yaml_list(fm["personas"]),
        path=manifest_path,
        raw_frontmatter=fm,
    )


def list_guilds(guilds_dir: Path | None = None) -> list[str]:
    """登録済み Guild 名の和集合を返す (Phase 5c-1 / ADR-0020 で overlay 化)。

    home (`$AI_ORG_OS_HOME/guilds/`) と templates (`templates/guilds/`) の
    両方をスキャンして manifest.md を持つ dir 名を集める。同名は片方にあれば
    1 件として扱う (実体が templates を覆い隠す形)。

    手書きで作ったが manifest が無いディレクトリは無視する。
    """
    seen: set[str] = set()
    for source in _search_dirs(guilds_dir):
        if not source.is_dir():
            continue
        for entry in sorted(source.iterdir()):
            if not entry.is_dir():
                continue
            if not GUILD_NAME_RE.match(entry.name):
                continue
            if (entry / "manifest.md").is_file():
                seen.add(entry.name)
    return sorted(seen)


def validate_membership(
    guild_name: str,
    *,
    kind: str,
    persona: str,
    guilds_dir: Path | None = None,
) -> GuildManifest:
    """spawn 前のチェック: kind/persona が Guild manifest に含まれるか。

    成功時は GuildManifest を返す (呼び出し側でそのまま使える)。
    例外:
        GuildNotFoundError:   Guild が存在しない
        GuildValidationError: kind / persona が manifest に無い
    """
    manifest = load_manifest(guild_name, guilds_dir=guilds_dir)
    if kind not in manifest.kinds:
        raise GuildValidationError(
            f"kind '{kind}' is not allowed in guild '{guild_name}' "
            f"(allowed: {list(manifest.kinds)})"
        )
    if persona not in manifest.personas:
        raise GuildValidationError(
            f"persona '{persona}' is not allowed in guild '{guild_name}' "
            f"(allowed: {list(manifest.personas)})"
        )
    return manifest


def _read_mind_meta_field(meta_path: Path, key: str) -> str | None:
    """`.mind-meta.md` の frontmatter から 1 フィールドを読む。

    observe.py の `_read_meta` と同じ流儀だが、未設定時は None を返す
    (default fallback の判別をしたい呼び出し側のため)。
    """
    if not meta_path.is_file():
        return None
    try:
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}:"):
                value = line.split(":", 1)[1].strip()
                return value if value else None
    except OSError:
        return None
    return None


def get_mind_guild(
    mind_name: str,
    minds_dir: Path | None = None,
) -> str:
    """Mind の所属 Guild を `.mind-meta.md` から読む。

    `.mind-meta.md` が存在しない / `guild:` フィールドが無い場合は
    `DEFAULT_GUILD` を返す (後方互換: Phase 5c-1 以前の Mind は default 扱い)。

    例外: 形式違反の mind_name は呼び出し側で拒否済の想定 (Nexus 側の
    identity binding 等)。本関数はファイル read 失敗を例外化しない。
    """
    base = Path(minds_dir) if minds_dir is not None else _default_minds_dir()
    meta_path = base / mind_name / ".mind-meta.md"
    value = _read_mind_meta_field(meta_path, "guild")
    return value if value else DEFAULT_GUILD


def enumerate_members(
    guild_name: str,
    minds_dir: Path | None = None,
) -> list[str]:
    """指定 Guild に所属する Mind 名一覧 (`.mind-meta.md` を走査)。

    所属の authoritative source は `.mind-meta.md` の `guild:` フィールド
    (ADR-0019 §1)。本関数は派生計算であり、`runtime/guilds/<name>/` の
    file は読まない。
    """
    base = Path(minds_dir) if minds_dir is not None else _default_minds_dir()
    if not base.is_dir():
        return []
    members: list[str] = []
    for mind_dir in sorted(base.iterdir()):
        if not mind_dir.is_dir():
            continue
        meta = mind_dir / ".mind-meta.md"
        if not meta.is_file():
            continue
        g = _read_mind_meta_field(meta, "guild") or DEFAULT_GUILD
        if g == guild_name:
            members.append(mind_dir.name)
    return members


# ---- CLI (主に spawn-mind.sh からの呼び出し用) ------------------------------


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        validate_membership(args.guild, kind=args.kind, persona=args.persona)
    except GuildNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    except GuildValidationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 4
    print(f"ok: kind={args.kind} persona={args.persona} guild={args.guild}")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    names = list_guilds()
    if not names:
        print("(no guilds)")
        return 0
    for name in names:
        print(name)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        m = load_manifest(args.guild)
    except GuildNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    except GuildValidationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 4
    print(f"guild:          {m.name}")
    print(f"schema_version: {m.schema_version}")
    print(f"purpose:        {m.purpose}")
    print(f"kinds:          {list(m.kinds)}")
    print(f"personas:       {list(m.personas)}")
    print(f"manifest:       {m.path}")
    return 0


def _cmd_members(args: argparse.Namespace) -> int:
    members = enumerate_members(args.guild)
    for name in members:
        print(name)
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="guild.py",
        description="Guild catalog (ADR-0019 / Phase 5c-1)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser(
        "validate",
        help="kind/persona が Guild manifest に含まれるか検証 (spawn-mind 用)",
    )
    p_validate.add_argument("--guild", required=True)
    p_validate.add_argument("--kind", required=True)
    p_validate.add_argument("--persona", required=True)
    p_validate.set_defaults(func=_cmd_validate)

    p_list = sub.add_parser("list", help="登録済み Guild の一覧")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Guild manifest を表示")
    p_show.add_argument("guild")
    p_show.set_defaults(func=_cmd_show)

    p_members = sub.add_parser(
        "members",
        help="指定 Guild の所属 Mind 一覧 (.mind-meta.md 走査の派生)",
    )
    p_members.add_argument("guild")
    p_members.set_defaults(func=_cmd_members)

    ns = parser.parse_args(list(argv) if argv is not None else None)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
