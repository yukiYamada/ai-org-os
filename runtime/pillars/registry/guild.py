#!/usr/bin/env python3
"""
Guild Catalog (Phase 5c-1 / ADR-0019 / ADR-0020 / 5c-2 P1 fix)。

Guild = 組織枠の物理表現 (ADR-0019)。本モジュールは:

- Guild manifest のロード (`<source>/<name>/manifest.md`)
- Guild membership 検証 (kind ∈ manifest.kinds, persona ∈ manifest.personas)
- Mind の所属 Guild 解決 (Mind registry の `guild:` フィールド)
- Mind の persona 解決 (Mind registry の `persona:` フィールド)
- Issue の所属 Guild 解決 (Issue frontmatter の `guild:` フィールド)
- Guild member 集約 (registry を走査して算出)

を提供する。

Phase 5c-1 (ADR-0020) で Guild manifest の source は 2 layer overlay に:
  1. `$AI_ORG_OS_HOME/guilds/<name>/` (利用者の組織実体、優先)
  2. `templates/guilds/<name>/` (ai-org-os 同梱テンプレ、fallback)

Phase 5c-2 P1 fix (#91 Codex): Mind の persona / guild は **Mind registry**
(`$AI_ORG_OS_HOME/registry/minds/<name>.md`) を authoritative source とする。
Mindspace 内の `.mind-meta.md` は Mind 自身が書き換え可能なため authz には
使わない (caller-writable な認可根拠を排除)。registry は Pillar 管理領域
(ADR-0011) に置かれ、spawn-mind.sh / kill-mind.sh のみが atomic に書き換える。

設計の根拠:
- ADR-0019 — Guild 物理表現と「組織パッケージ」基礎 (§1 の authoritative source
  は本 fix で `.mind-meta.md` → registry に更新)
- ADR-0020 — 世界の構成 (runtime/) vs 組織依存物 (templates/ + AI_ORG_OS_HOME)
  の物理分離。Guild manifest はこの「依存物」カテゴリ。
- ADR-0011 — Pillar 編集不可。本ファイルは Registry Pillar 配下。registry/ も
  Pillar 管理領域として Mind は触らない
- ADR-0008 — identity binding。本モジュールの persona / guild lookup と組み合わせて
  「Mind が自分以外を名乗らない」+「Mind が自分の persona/guild を偽れない」を成立
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
    # Phase 5d-4 (ADR-0022): Guild が組織既定の workspace を持てる。optional。
    # 未指定なら spawn-mind の解決順で "default" に fallback (ADR-0022 §4)。
    workspace: str
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


def _default_registry_dir() -> Path:
    """Mind registry dir (`$AI_ORG_OS_HOME/registry/minds/`)。

    Phase 5c-2 P1 fix (#91 Codex): Mind の persona / guild の authoritative
    source は registry。Mindspace 配下 (`$AI_ORG_OS_HOME/minds/<name>/`) では
    `.mind-meta.md` を Mind 自身が書き換え可能なため authz の根拠にできない
    (caller-controlled flag 問題)。registry は Pillar 管理領域。

    各 Mind の registry エントリは `<name>.md` (ファイル) として置く。中身は
    `.mind-meta.md` と同じ frontmatter (kind / persona / guild / spawned_at)。
    """
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "registry" / "minds"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "registry" / "minds"


# 旧 API 互換用エイリアス (テスト fixture が minds_dir を渡してくる呼び出しを
# 残しておくため)。新規コードは _default_registry_dir を使う。
def _default_minds_dir() -> Path:
    """[Deprecated, P1 fix #91] 旧 `.mind-meta.md` 走査用 Mindspace dir 解決。

    現在は authoritative source ではないので、本関数を直接使う新規ロジックは
    避けること。テスト fixture / informational lookup のみで使われる。
    """
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
        # Phase 5d-4 (ADR-0022): workspace は optional。未指定は空文字 → spawn-mind の
        # 解決順 (引数 > Guild > default) で fallback される。
        workspace=fm.get("workspace", ""),
        path=manifest_path,
        raw_frontmatter=fm,
    )


def list_guilds(guilds_dir: Path | None = None) -> list[str]:
    """登録済み Guild 名を返す (Phase 5c-1 / ADR-0020 で overlay 化)。

    home (`$AI_ORG_OS_HOME/guilds/`) と templates (`templates/guilds/`) の
    両方をスキャンして manifest.md を持つ dir 名を集める。同名は home が
    templates をマスクする (実体 overlay 原則)。

    Codex P2 (#88): manifest が **parse 可能** な dir のみ listing する。
    higher-priority source の manifest が malformed (schema_version 違反 /
    必須フィールド欠落 / guild フィールド不一致 等) の場合:
      1. その Guild を listing から **除外** する
      2. lower-priority source の同名にも **フォールバックさせない** (shadow)
      3. stderr に WARN を出して configuration error を可視化
    こうしないと `list` には現れるが `load_manifest` / `validate_membership`
    で fail する不整合 (= spawn / claim が「Guild は在るのに動かない」と
    なる) が起きる。registry.list_kinds と同じ shadowing 原則。

    手書きで作ったが manifest.md が無いディレクトリは無視する。
    """
    seen: set[str] = set()
    shadowed: set[str] = set()
    for source in _search_dirs(guilds_dir):
        if not source.is_dir():
            continue
        local_dirs: set[str] = set()
        for entry in sorted(source.iterdir()):
            if not entry.is_dir():
                continue
            if not GUILD_NAME_RE.match(entry.name):
                continue
            if not (entry / "manifest.md").is_file():
                continue
            local_dirs.add(entry.name)
            if entry.name in shadowed or entry.name in seen:
                # higher-priority source に同名 dir が在った (malformed 含む)
                # → 下位 source の同名は shadow される
                continue
            # parse まで含めて検証。malformed なら listing から除外 + shadow。
            try:
                load_manifest(entry.name, guilds_dir=source)
            except (GuildNotFoundError, GuildValidationError) as exc:
                print(
                    f"[WARN] guild '{entry.name}' manifest at {entry} is "
                    f"malformed, hiding from listing: {exc}",
                    file=sys.stderr,
                )
                continue
            seen.add(entry.name)
        shadowed |= local_dirs
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


def _registry_path_for(mind_name: str, registry_dir: Path | None) -> Path:
    """Mind registry エントリの絶対パス (`<registry>/<name>.md`)。

    Phase 5c-2 P1 fix: registry は Mindspace の外 (Pillar 管理領域)。
    `minds_dir` 引数 (旧 API) は本関数では使わない (registry は別 dir)。
    テスト fixture は registry_dir を明示する。
    """
    base = (
        Path(registry_dir)
        if registry_dir is not None
        else _default_registry_dir()
    )
    return base / f"{mind_name}.md"


def get_mind_guild(
    mind_name: str,
    minds_dir: Path | None = None,  # 旧 API 互換引数 (未使用)
    *,
    registry_dir: Path | None = None,
) -> str | None:
    """Mind の所属 Guild を **Mind registry** から読む。

    Phase 5c-2 P1 fix (#91 Codex 2 回目): registry エントリが存在しない /
    `guild:` フィールドが無い場合は **None** を返す。

    以前は `DEFAULT_GUILD` を fallback していたが、これは「過渡期 Mind /
    pre-migration Mind を default に勝手に分類する」挙動で、攻撃面になっていた:
      - default の Guildmaster が registry 無 target の inbox を読める
        (target も default と判定されて cross-guild check が通る)
      - 非 default の Mind が「registry 無」だと自 Guild の Issue を claim
        できなくなる、または他 Guild の Issue を誤って claim できる
    None を返すことで、caller (axiom 強制ロジック) が「unknown mind =
    forbidden」と明示判定できる。

    旧 API の `minds_dir` 引数は互換のため残すが本関数では参照しない。
    `.mind-meta.md` (Mindspace 内) は Mind が書き換え可能なため authoritative
    source としては使わない (Codex P1 #91 1 回目)。

    例外: 形式違反の mind_name は呼び出し側で拒否済の想定 (Nexus の identity
    binding 等)。本関数はファイル read 失敗を例外化しない。
    """
    reg_path = _registry_path_for(mind_name, registry_dir)
    value = _read_mind_meta_field(reg_path, "guild")
    return value if value else None


def get_mind_persona(
    mind_name: str,
    minds_dir: Path | None = None,  # 旧 API 互換引数 (未使用)
    *,
    registry_dir: Path | None = None,
) -> str | None:
    """Mind の persona を **Mind registry** から読む (Phase 5c-2 P1 fix #91)。

    Guildmaster axiom の機械強制で「発令 Mind の persona が guildmaster か?」を
    判定する根拠データ。authoritative source は registry (Pillar 管理) で
    あって Mindspace の `.mind-meta.md` ではない (caller-writable 排除)。

    registry エントリ無 / `persona:` 欠落のときは None。

    例外: 形式違反の mind_name は呼び出し側で拒否済の想定 (Nexus の identity
    binding 経由)。本関数は read 失敗を例外化せず None を返す (caller 側で
    None == 「guildmaster でない」と判断、forbidden で reject する)。
    """
    reg_path = _registry_path_for(mind_name, registry_dir)
    return _read_mind_meta_field(reg_path, "persona")


# Phase 5c-2 / ADR-0021: Guildmaster axiom の機械強制で使う persona 名。
# B (Persona = templates/personas/guildmaster.md) と A (axiom) の接続点。
GUILDMASTER_PERSONA = "guildmaster"


def is_guildmaster(
    mind_name: str,
    minds_dir: Path | None = None,  # 旧 API 互換引数 (未使用)
    *,
    registry_dir: Path | None = None,
) -> bool:
    """Mind の persona が guildmaster かどうか (Phase 5c-2 / ADR-0021)。

    Guildmaster 専用 axiom (`guildmaster-only-spawn` / `read-others-inbox-only-
    by-guildmaster`) の機械強制チェックで使う thin helper。authoritative
    source は Mind registry (Mindspace 外、P1 fix #91)。Persona が読めない /
    異なる場合は False を返す。
    """
    persona = get_mind_persona(mind_name, registry_dir=registry_dir)
    return persona == GUILDMASTER_PERSONA


def enumerate_guildmasters(
    guild_name: str,
    minds_dir: Path | None = None,  # 旧 API 互換引数 (未使用)
    *,
    registry_dir: Path | None = None,
) -> list[str]:
    """指定 Guild に所属する persona=guildmaster の Mind 一覧 (Phase 5c-2)。

    Phase 5c-2 P1 fix: authoritative source は Mind registry。
    observe.py --realm で Guild ごとの運営層の存在を可視化するために使う。
    """
    base = (
        Path(registry_dir)
        if registry_dir is not None
        else _default_registry_dir()
    )
    members = enumerate_members(guild_name, registry_dir=base)
    result: list[str] = []
    for m in members:
        entry = base / f"{m}.md"
        if _read_mind_meta_field(entry, "persona") == GUILDMASTER_PERSONA:
            result.append(m)
    return result


def enumerate_members(
    guild_name: str,
    minds_dir: Path | None = None,  # 旧 API 互換引数 (未使用)
    *,
    registry_dir: Path | None = None,
) -> list[str]:
    """指定 Guild に所属する Mind 名一覧 (Phase 5c-2 P1 fix #91)。

    所属の authoritative source は **Mind registry** (`$AI_ORG_OS_HOME/registry/
    minds/<name>.md` の `guild:` フィールド)。Mindspace 内の `.mind-meta.md`
    は Mind 自身が書き換え可能なため caller-controlled とみなし、authoritative
    source としては使わない。本関数は派生計算であり、`guilds/<name>/` 配下の
    manifest file は読まない。
    """
    base = (
        Path(registry_dir)
        if registry_dir is not None
        else _default_registry_dir()
    )
    if not base.is_dir():
        return []
    members: list[str] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_file() or entry.suffix != ".md":
            continue
        if not GUILD_NAME_RE.match(entry.stem):
            continue
        # Phase 5c-2 P1 fix (#91): guild フィールドが無い registry entry は
        # 「unknown mind」として skip。default に fallback して member 集計しない
        # (default Guildmaster の越境観察を防ぐため)。
        g = _read_mind_meta_field(entry, "guild")
        if g is not None and g == guild_name:
            members.append(entry.stem)
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
    print(f"workspace:      {m.workspace or '(none, falls back to default)'}")
    print(f"manifest:       {m.path}")
    return 0


def _cmd_members(args: argparse.Namespace) -> int:
    members = enumerate_members(args.guild)
    for name in members:
        print(name)
    return 0


def _cmd_get_workspace(args: argparse.Namespace) -> int:
    """Guild manifest の `workspace:` フィールドだけを emit する (spawn-mind 用)。

    Phase 5d-4 (ADR-0022): spawn-mind の解決順 (引数 > Guild > default) の
    middle layer を実現する thin helper。未設定なら空行を emit して exit 0。
    Guild 自体が存在しない / malformed のときは stderr に ERROR + exit 3/4。
    """
    try:
        m = load_manifest(args.guild)
    except GuildNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    except GuildValidationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 4
    print(m.workspace)
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

    p_get_ws = sub.add_parser(
        "get-workspace",
        help="Guild の workspace フィールドだけを emit (spawn-mind 用)",
    )
    p_get_ws.add_argument("guild")
    p_get_ws.set_defaults(func=_cmd_get_workspace)

    ns = parser.parse_args(list(argv) if argv is not None else None)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
