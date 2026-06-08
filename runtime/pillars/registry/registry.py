#!/usr/bin/env python3
"""
Registry Pillar v0.1: Mind Kind Registry。

Warden 起動時に Kind カタログを構築し、Kind 一覧 / 詳細 / 登録チェックを
提供する最小実装。

Phase 5c-1 (ADR-0020): Kind の lookup は 2 source overlay:
  1. `$AI_ORG_OS_HOME/kinds/*.md` (利用者の実体、優先)
  2. `templates/kinds/*.md` (ai-org-os 同梱テンプレ、fallback)

責務:
- list_kinds(kinds_dir=None) -> list[KindInfo]: 登録済み Kind の列挙
- get_kind(name, kinds_dir=None) -> KindInfo | None: 指定 Kind の詳細
- is_registered(name, kinds_dir=None) -> bool: Kind が登録されているか

設計の根拠:
- ADR-0002: Mind Kind Registry は Warden の責務、Realm の中
- ADR-0010: Warden は機能の集合体、観測は自由
- ADR-0011: Pillar は ai-org-os コア、編集不可領域、runtime/pillars/ 配下
- ADR-0015: 既存 Kind の選択は OK、新規 Kind の動的生成は NG
- ADR-0020: 世界の構成 (runtime/) と組織依存物 (templates/ + AI_ORG_OS_HOME)
  の物理分離。Kind は依存物カテゴリなので、本 Pillar は両 source を統合する。

依存:
- 標準ライブラリのみ（observation Pillar と同じ依存ゼロ方針）
- frontmatter (YAML サブセット) の手書きパーサ。kinds/*.md は単純な
  `key: value` だけを使うので、yaml ライブラリは不要。

Axiom 整合:
- Mindspace の中身に触れない（kinds source のみを読む）
- Kind は Pillar 領域のメタデータ、Mind の Body スペック定義

Usage:
  python3 runtime/pillars/registry/registry.py list           # 一覧（表）
  python3 runtime/pillars/registry/registry.py list --json    # 一覧（JSON）
  python3 runtime/pillars/registry/registry.py get generic    # 詳細
  python3 runtime/pillars/registry/registry.py check generic  # exit 0 if registered, exit 1 otherwise
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Locate runtime root and repo root from this file's path:
#   runtime/pillars/registry/registry.py
RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent
REPO_DIR = RUNTIME_DIR.parent
TEMPLATES_DIR = REPO_DIR / "templates"

# Phase 5g.A #170: framework_version constraint warner (same-dir import)。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from version import warn_if_mismatch as _warn_framework_mismatch  # noqa: E402


def _home_kinds_dir() -> Path | None:
    """利用者の Kind 実体 dir (`$AI_ORG_OS_HOME/kinds`)。未設定なら None。

    Phase 5c-1 / ADR-0020: 「同梱テンプレ vs 実体」の overlay の上層。
    """
    home = os.environ.get("AI_ORG_OS_HOME")
    if home:
        return Path(home) / "kinds"
    # HOME / USERPROFILE 経由のデフォルトは ADR-0018 と同じ流儀。
    # ただし「default fallback としての ~/.ai-org-os/kinds」も読みたいので付ける。
    h = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if h:
        return Path(h) / ".ai-org-os" / "kinds"
    return None


def _template_kinds_dir() -> Path:
    """同梱テンプレ Kind dir (`templates/kinds`)。ADR-0020 §3 の fallback 層。"""
    return TEMPLATES_DIR / "kinds"


def _search_dirs(kinds_dir: Path | None) -> list[Path]:
    """lookup する dir を「優先度が高い順」で返す。

    - kinds_dir が明示されていれば「テスト用 override」としてそれだけを返す
      (overlay を無視、既存テスト互換)。
    - そうでなければ home (実体) を先頭、templates (同梱) を末尾に。
    """
    if kinds_dir is not None:
        return [Path(kinds_dir)]
    dirs: list[Path] = []
    home = _home_kinds_dir()
    if home is not None and home.is_dir():
        dirs.append(home)
    dirs.append(_template_kinds_dir())
    return dirs


# Phase 5c-1 / ADR-0020: 後方互換シンボル。新規コードは _search_dirs を使う。
DEFAULT_KINDS_DIR = TEMPLATES_DIR / "kinds"

# spawn-mind.sh の _VALID_NAME_RE と整合させる。
# Kind name に許される文字: A-Za-z0-9._- のみ、1〜64 文字。
# これにより `get_kind("../etc")` のような path traversal を弾く。
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# frontmatter で読み取るキー。値は str として保持し、欠落時は "?" を返す。
_FRONTMATTER_KEYS = ("name", "version", "status")


class RegistryError(Exception):
    """Registry 層の汎用エラー（呼び出し側で扱いやすいよう型を切る）。"""


@dataclass(frozen=True)
class KindInfo:
    """Kind 1 件のメタデータ。"""

    name: str
    path: Path
    version: str
    status: str


def _is_valid_name(name: str) -> bool:
    """Kind 名のバリデーション。path traversal などを弾く。"""
    return bool(_VALID_NAME_RE.match(name))


def _parse_frontmatter(text: str) -> dict[str, str]:
    """先頭の `---` で挟まれた frontmatter を最小パースする。

    対応する書式:
      ---
      key: value
      key2: value2
      ---

    YAML の高機能（ネスト, list, quote, multi-line）は使わない。
    対象 (runtime/kinds/*.md) は単純な key: value のみを使う前提。

    frontmatter が無いファイルは空 dict を返す（呼び出し側で扱う）。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    result: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return result
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        result[key.strip()] = value.strip()
    # 閉じ `---` が無いケースは frontmatter として認めない（保守的に空を返す）
    return {}


def _read_kind_file(path: Path) -> KindInfo | None:
    """1 ファイルを KindInfo に変換する。

    frontmatter が無い / 読み取りエラー / kind key 欠落の場合は None を返す。
    None を返すケースでは標準エラーに warning を出す。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[WARN] failed to read {path}: {exc}", file=sys.stderr)
        return None

    fm = _parse_frontmatter(text)
    if not fm:
        print(f"[WARN] no frontmatter in {path}, skipping", file=sys.stderr)
        return None

    # `kind:` が公式キー（generic.md 参照）。`name:` も保険で受ける。
    kind_name = fm.get("kind") or fm.get("name")
    if not kind_name:
        print(
            f"[WARN] frontmatter missing 'kind' key in {path}, skipping",
            file=sys.stderr,
        )
        return None

    # ファイル名と frontmatter の name が一致することを保証する（不一致は warning）。
    # 例: generic.md の frontmatter には kind: generic と書く。
    file_stem = path.stem
    if kind_name != file_stem:
        print(
            f"[WARN] frontmatter kind '{kind_name}' does not match filename "
            f"'{file_stem}' in {path}; using filename",
            file=sys.stderr,
        )
        kind_name = file_stem

    # filename 由来の name は信頼するが、念のため再バリデーション。
    if not _is_valid_name(kind_name):
        print(
            f"[WARN] kind name '{kind_name}' from {path} is not a valid identifier, "
            f"skipping",
            file=sys.stderr,
        )
        return None

    # Phase 5g.A #170: optional framework_version constraint (warn on mismatch)。
    _warn_framework_mismatch(
        fm.get("framework_version", ""), source_label=f"kind:{kind_name}",
    )

    return KindInfo(
        name=kind_name,
        path=path,
        version=fm.get("version", "?"),
        status=fm.get("status", "?"),
    )


def list_kinds(kinds_dir: Path | None = None) -> list[KindInfo]:
    """Kind 一覧を返す (Phase 5c-1 / ADR-0020 で overlay 化)。

    - source: `$AI_ORG_OS_HOME/kinds/*.md` (実体) を最優先、無ければ
      `templates/kinds/*.md` (テンプレ) にフォールバック
    - 同名 Kind が両方にある場合、home 側を採用、templates 側は隠れる
    - Codex P2 (#88): higher-priority source に同名 .md が **存在する** 場合、
      たとえ malformed (frontmatter 不正等で parse 失敗) でも shadow とみなし、
      lower-priority source の同名 entry を採用しない。これにより `list` と
      `get_kind` / `is_registered` が一貫する (壊れた home file が静かに
      templates にフォールバックして見える不整合を防ぐ)。
    - .md 拡張子のみ対象
    - frontmatter から name / version / status を読む
    - frontmatter が無い / 不正なものは無視（warning ログのみ。lower への
      フォールバックは shadow ルールで抑制される）
    - 結果は name の辞書順でソート（呼び出し側で安定した順序を期待できる）

    `kinds_dir` を明示した場合は overlay を無視し、その dir 単体で動く
    (テスト用; 既存 API 互換)。

    冪等性: source の状態が変わらない限り同じ結果を返す。
    """
    results_by_name: dict[str, KindInfo] = {}
    # higher-priority source で「同名 .md が存在した stem」を記録。
    # malformed でファイルが parse 不能でも shadow として lower を抑止する。
    shadowed_stems: set[str] = set()
    for source in _search_dirs(kinds_dir):
        if not source.is_dir():
            continue
        try:
            entries = sorted(source.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            raise RegistryError(f"failed to list {source}: {exc}") from exc
        # この source で「.md が存在した stem」を一旦集める。
        # source 内のループが終わってから shadowed_stems に足す
        # (= 同 source 内の重複を排除しない設計だが、現状そもそも 1 stem
        # 1 file の前提なので副作用は無い)。
        local_stems: set[str] = set()
        for entry in entries:
            if not entry.is_file() or entry.suffix != ".md":
                continue
            stem = entry.stem
            local_stems.add(stem)
            if stem in shadowed_stems:
                # higher-priority source に同名があった (malformed 含む) → skip
                continue
            info = _read_kind_file(entry)
            if info is None:
                # 自分の source の parse 失敗。下位 source にもフォールバック
                # させない (Codex P2 #88: shadowing consistency)。
                continue
            # `info.name == stem` は _read_kind_file 内で正規化済 (不一致時は
            # filename を採用するため、shadow の判定も stem ベースで安全)。
            results_by_name.setdefault(info.name, info)
        shadowed_stems |= local_stems
    return sorted(results_by_name.values(), key=lambda k: k.name)


def get_kind(name: str, kinds_dir: Path | None = None) -> KindInfo | None:
    """指定 Kind の情報を返す。無ければ None。

    Phase 5c-1 / ADR-0020: home (実体) → templates (同梱) の順で探し、
    最初に **ファイルが存在した** source で read する。malformed (parse 失敗)
    の場合は None を返し、lower-priority source へはフォールバックしない
    (Codex P2 #88 / list_kinds と同じ shadowing consistency)。

    name のバリデーション (_VALID_NAME_RE) で path traversal 攻撃を防ぐ。
    """
    if not _is_valid_name(name):
        # 不正な名前は「無い」と等価に扱う（攻撃の足がかりにしない）
        return None

    for source in _search_dirs(kinds_dir):
        candidate = source / f"{name}.md"
        if candidate.is_file():
            # 最初に file が在った source で確定。malformed なら None。
            # 下位 source にはフォールバックしない (shadow 原則)。
            return _read_kind_file(candidate)
    return None


def is_registered(name: str, kinds_dir: Path | None = None) -> bool:
    """Kind が登録されているか (home overlay + templates の和集合で判定)。"""
    return get_kind(name, kinds_dir=kinds_dir) is not None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_table(kinds: list[KindInfo]) -> str:
    if not kinds:
        return "No kinds registered."
    lines = [
        "=== Mind Kind Registry ===",
        f"  total: {len(kinds)}",
        "",
        f"{'NAME':<20} {'VERSION':<10} {'STATUS':<14} PATH",
    ]
    for k in kinds:
        lines.append(f"{k.name:<20} {k.version:<10} {k.status:<14} {k.path}")
    return "\n".join(lines)


def _kind_to_dict(k: KindInfo) -> dict[str, str]:
    # asdict だと Path がそのまま入って json で落ちるので手動で str 化。
    d = asdict(k)
    d["path"] = str(k.path)
    return d


def _cmd_list(argv: list[str]) -> int:
    as_json = "--json" in argv
    kinds = list_kinds()
    if as_json:
        payload = {"kinds": [_kind_to_dict(k) for k in kinds]}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(_format_table(kinds))
    return 0


def _cmd_get(argv: list[str]) -> int:
    if not argv:
        print("[ERROR] 'get' requires a kind name", file=sys.stderr)
        return 2
    name = argv[0]
    as_json = "--json" in argv
    info = get_kind(name)
    if info is None:
        print(f"[ERROR] kind '{name}' is not registered", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(_kind_to_dict(info), indent=2, ensure_ascii=False))
    else:
        print(f"name:    {info.name}")
        print(f"version: {info.version}")
        print(f"status:  {info.status}")
        print(f"path:    {info.path}")
    return 0


def _cmd_check(argv: list[str]) -> int:
    if not argv:
        print("[ERROR] 'check' requires a kind name", file=sys.stderr)
        return 2
    name = argv[0]
    if is_registered(name):
        return 0
    return 1


def _print_help() -> None:
    print(
        "Usage:\n"
        "  registry.py list [--json]\n"
        "  registry.py get <name> [--json]\n"
        "  registry.py check <name>\n"
        "\n"
        "Exit codes:\n"
        "  list:  always 0\n"
        "  get:   0 = found, 1 = not found, 2 = usage error\n"
        "  check: 0 = registered, 1 = not registered, 2 = usage error"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return 0

    subcmd = args[0]
    rest = args[1:]
    if subcmd == "list":
        return _cmd_list(rest)
    if subcmd == "get":
        return _cmd_get(rest)
    if subcmd == "check":
        return _cmd_check(rest)
    print(f"[ERROR] unknown subcommand: {subcmd}", file=sys.stderr)
    _print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
