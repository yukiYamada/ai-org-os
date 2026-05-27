#!/usr/bin/env python3
"""
Workspace Catalog (Phase 5d-1 / ADR-0022)。

Workspace = Mind の作業環境 (vcs / repo / worktree モード等) を C 依存注入
として表現する 4 番目のテンプレートカテゴリ (kinds / personas / guilds に
並ぶ、ADR-0021 C カテゴリ)。

本モジュールは:

- Workspace template のロード (`<source>/<name>.md`)
- Workspace 名 / vcs / mode の検証
- list / show / check の CLI 提供

を行う。spawn-mind / kill-mind が **どの workspace** を使うかの解決順
(引数 → Guild → default) は本モジュールスコープ外 (PR #2 以降で実装)。
本 PR (#1) は **catalog lookup と検証** までを完成させる。

物理レイアウト (ADR-0020 と同じ 2 layer overlay):
  1. `$AI_ORG_OS_HOME/workspaces/<name>.md` (利用者 overlay、優先)
  2. `templates/workspaces/<name>.md` (ai-org-os 同梱、fallback)

設計の根拠:
- ADR-0022: Workspace = C 依存注入の新サブカテゴリ
- ADR-0020: 同梱テンプレ vs 実体の 2 層 overlay (Workspace も同パターン)
- ADR-0011: Pillar 編集不可。本ファイルは Registry Pillar 配下
- ADR-0005 / ADR-0009: 依存最小、標準ライブラリのみ

shadow consistency (registry.list_kinds / guild.list_guilds と同じ思想):
- higher-priority source の workspace が malformed の場合
  1. listing から除外する
  2. lower-priority source の同名にもフォールバックしない (shadow)
  3. stderr に WARN を出して configuration error を可視化
- 「list には現れるが load で fail する」不整合を作らない

Usage:
  python3 runtime/pillars/registry/workspace.py list           # 一覧
  python3 runtime/pillars/registry/workspace.py list --json    # JSON
  python3 runtime/pillars/registry/workspace.py show default   # 詳細
  python3 runtime/pillars/registry/workspace.py check default  # exit 0 if registered
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Locate runtime / repo root:
#   runtime/pillars/registry/workspace.py
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_DIR = _RUNTIME_DIR.parent
_TEMPLATES_DIR = _REPO_DIR / "templates"

# Workspace 名検証 (kinds / personas / guilds と同じ文字集合)
WORKSPACE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# ADR-0022 §2: vcs / mode の許容値
ALLOWED_VCS = ("git", "none")
ALLOWED_MODE = ("worktree", "shared", "")  # "" = mode 指定無し (vcs=none で許容)

DEFAULT_WORKSPACE_NAME = "default"


class WorkspaceError(Exception):
    """Workspace 関連の汎用エラー。具体的サブクラスを使う。"""


class WorkspaceNotFoundError(WorkspaceError):
    """指定 Workspace の template が存在しない。"""


class WorkspaceValidationError(WorkspaceError):
    """Workspace 名 / vcs / mode 等が形式に違反。"""


@dataclass(frozen=True)
class WorkspaceTemplate:
    """1 つの Workspace テンプレート (ADR-0022 §2 の形式)。

    `vcs`:           "git" or "none"
    `repo`:          vcs=git 時のみ意味を持つ (絶対 path or env var 参照を許容)
                     vcs=none では空文字
    `mode`:          "worktree" / "shared" / "" (vcs=none 時)
    `branch_prefix`: spawn 時の自動 branch 命名 prefix (vcs=git 時のヒント)
    `allowed_cli`:   利用想定 CLI のヒント (機械強制ではない、ADR-0022 §6)
    `purpose`:       人間向け説明 (CLAUDE.md に append される想定)
    """

    name: str
    schema_version: str
    vcs: str
    repo: str
    mode: str
    branch_prefix: str
    allowed_cli: tuple[str, ...]
    purpose: str
    path: Path
    raw_frontmatter: dict[str, str] = field(default_factory=dict)


# ---- path 解決 -----------------------------------------------------------


def _home_workspaces_dir() -> Path | None:
    """`$AI_ORG_OS_HOME/workspaces/` (ADR-0020 overlay 上層)。未設定なら None。"""
    home = os.environ.get("AI_ORG_OS_HOME")
    if home:
        return Path(home) / "workspaces"
    h = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if h:
        return Path(h) / ".ai-org-os" / "workspaces"
    return None


def _template_workspaces_dir() -> Path:
    """`templates/workspaces/` (ADR-0020 同梱テンプレ、fallback 層)。"""
    return _TEMPLATES_DIR / "workspaces"


def _search_dirs(workspaces_dir: Path | None) -> list[Path]:
    """lookup する dir を優先度順で返す (guild._search_dirs と同流儀)。

    - workspaces_dir 明示時はテスト override としてその 1 dir のみ
    - そうでなければ AI_ORG_OS_WORKSPACES_DIR env を最優先 (互換テスト用)
    - 最後に home (実体) → templates (同梱) の順
    """
    if workspaces_dir is not None:
        return [Path(workspaces_dir)]
    env = os.environ.get("AI_ORG_OS_WORKSPACES_DIR")
    if env:
        return [Path(env)]
    dirs: list[Path] = []
    home = _home_workspaces_dir()
    if home is not None and home.is_dir():
        dirs.append(home)
    dirs.append(_template_workspaces_dir())
    return dirs


# ---- 検証 ----------------------------------------------------------------


def _validate_workspace_name(name: str) -> None:
    if not isinstance(name, str) or not WORKSPACE_NAME_RE.match(name):
        raise WorkspaceValidationError(
            f"invalid workspace name: must match {WORKSPACE_NAME_RE.pattern}"
        )


# ---- frontmatter パーサ (guild.py から流用、依存ゼロ方針) -------------------


def _parse_yaml_list(value: str) -> tuple[str, ...]:
    """`[a, b, c]` 形式の最小パーサ。bare scalar は単一要素として扱う。"""
    s = value.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return (s,) if s else ()
    inner = s[1:-1]
    if not inner.strip():
        return ()
    items = [item.strip() for item in inner.split(",")]
    return tuple(item for item in items if item)


def _strip_yaml_quotes(value: str) -> str:
    """YAML scalar の外側の `"..."` / `'...'` を 1 段剥がす。

    Codex P2 (#99): ADR-0022 のテンプレ例は `schema_version: "0.1"` のように
    引用符付きで書かれている。本モジュールの最小 parser は値文字列を
    そのまま比較してしまうので `'"0.1"'` (引用符込み 5 文字) と `"0.1"`
    (3 文字) が食い違う → 公式例が即 reject される穴があった。
    本関数で外側の引用符を 1 段剥がすことで「ADR が示す形式 = 受理される」
    の整合性を保つ。
    """
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """`---` で囲まれた frontmatter を {key: value} dict に。

    guild._parse_manifest_frontmatter と同じ流儀。本文には立ち入らない
    (2 個目の `---` で終了)。listy な値は呼び出し側で `_parse_yaml_list`。

    値は `_strip_yaml_quotes` で外側の引用符 (`"..."` / `'...'`) を 1 段
    剥がす。YAML の標準的な scalar 表記を受理する (#99 Codex P2)。
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
        meta[key.strip()] = _strip_yaml_quotes(value)
    return meta


# ---- ロード / 検証 -------------------------------------------------------


def load_workspace(
    name: str,
    workspaces_dir: Path | None = None,
) -> WorkspaceTemplate:
    """`<source>/<name>.md` を読み、検証して WorkspaceTemplate を返す。

    2 layer overlay で最初に見つかった file を採用 (ADR-0020)。

    例外:
        WorkspaceValidationError: 名前形式違反 / frontmatter 不正 /
            schema_version 不一致 / vcs|mode の値違反 / vcs=git で repo 欠落
        WorkspaceNotFoundError:   どの source にも見つからない
    """
    _validate_workspace_name(name)
    sources = _search_dirs(workspaces_dir)
    workspace_path: Path | None = None
    for src in sources:
        candidate = src / f"{name}.md"
        if candidate.is_file():
            workspace_path = candidate
            break
    if workspace_path is None:
        attempted = ", ".join(str(s / f"{name}.md") for s in sources)
        raise WorkspaceNotFoundError(
            f"workspace '{name}' not found (looked at: {attempted})"
        )
    try:
        text = workspace_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # PR #97 で踏んだ Windows + utf-8 issue 系。本モジュールは file
        # を read_text するだけだが、念のため非 utf-8 ファイルを ill-formed
        # 扱いする。
        raise WorkspaceValidationError(
            f"workspace '{name}' at {workspace_path}: file is not valid utf-8: {exc}"
        )
    fm = _parse_frontmatter(text)
    if fm is None:
        raise WorkspaceValidationError(
            f"workspace '{name}' at {workspace_path}: no/invalid frontmatter"
        )

    # 必須フィールド: workspace / schema_version / vcs
    for required in ("workspace", "schema_version", "vcs"):
        if required not in fm:
            raise WorkspaceValidationError(
                f"workspace '{name}' missing required field '{required}'"
            )

    # workspace フィールドはファイル名 (拡張子除) と一致
    if fm["workspace"] != name:
        raise WorkspaceValidationError(
            f"workspace '{name}' declares workspace='{fm['workspace']}' (mismatch)"
        )

    if fm["schema_version"] != "0.1":
        raise WorkspaceValidationError(
            f"workspace '{name}' schema_version='{fm['schema_version']}' "
            f"unsupported (v0.1 expects '0.1')"
        )

    vcs = fm["vcs"]
    if vcs not in ALLOWED_VCS:
        raise WorkspaceValidationError(
            f"workspace '{name}' vcs='{vcs}' not in {list(ALLOWED_VCS)}"
        )

    mode = fm.get("mode", "")
    if mode not in ALLOWED_MODE:
        raise WorkspaceValidationError(
            f"workspace '{name}' mode='{mode}' not in {list(ALLOWED_MODE)}"
        )

    # vcs=git は repo 必須、mode は worktree か shared (空は許容しない)。
    # vcs=none は repo 空でよく、mode も任意 (空または "worktree"/"shared" 全て許容、
    # ただし実装側 PR #2 で no-op になる)。
    # Codex P2 (#100): ADR-0022 §2 で repo は "<path or env var>" と documented。
    # 利用者が repo: $TARGET_REPO や repo: ~/proj を書いた場合、これらは shell
    # ではなく workspace.py 側で展開する (= 表記の単一の真実)。
    # - expandvars: $VAR / ${VAR}
    # - expanduser: ~ / ~user
    # 未定義の env var は os.path.expandvars が literal を残すので、
    # 後段の repo dir 存在 check (spawn-mind.sh) で exit 13 になる
    # (= configuration error として顕在化)。
    repo = os.path.expanduser(os.path.expandvars(fm.get("repo", "")))
    if vcs == "git":
        if not repo:
            raise WorkspaceValidationError(
                f"workspace '{name}' vcs=git requires 'repo' field"
            )
        if mode == "":
            raise WorkspaceValidationError(
                f"workspace '{name}' vcs=git requires 'mode' "
                f"(worktree or shared)"
            )

    branch_prefix = fm.get("branch_prefix", "")
    allowed_cli = _parse_yaml_list(fm.get("allowed_cli", ""))
    purpose = fm.get("purpose", "")

    return WorkspaceTemplate(
        name=name,
        schema_version=fm["schema_version"],
        vcs=vcs,
        repo=repo,
        mode=mode,
        branch_prefix=branch_prefix,
        allowed_cli=allowed_cli,
        purpose=purpose,
        path=workspace_path,
        raw_frontmatter=fm,
    )


def list_workspaces(workspaces_dir: Path | None = None) -> list[str]:
    """登録済み Workspace 名を返す (parse 可能なもののみ、shadow consistent)。

    higher-priority source の file が malformed なら:
      1. listing から除外
      2. lower-priority source の同名にもフォールバックさせない (shadow)
      3. stderr に WARN
    registry.list_kinds / guild.list_guilds と同じ思想。
    """
    seen: set[str] = set()
    shadowed: set[str] = set()
    for source in _search_dirs(workspaces_dir):
        if not source.is_dir():
            continue
        local_names: set[str] = set()
        try:
            entries = sorted(source.iterdir())
        except OSError as exc:
            print(
                f"[WARN] workspace: iterdir failed at {source}: {exc}",
                file=sys.stderr,
            )
            continue
        for entry in entries:
            if not entry.is_file() or entry.suffix != ".md":
                continue
            if not WORKSPACE_NAME_RE.match(entry.stem):
                continue
            name = entry.stem
            local_names.add(name)
            if name in shadowed or name in seen:
                # higher-priority source に同名があった (malformed 含む) →
                # 下位 source の同名は shadow
                continue
            try:
                load_workspace(name, workspaces_dir=source)
            except (WorkspaceNotFoundError, WorkspaceValidationError) as exc:
                print(
                    f"[WARN] workspace '{name}' at {entry} is malformed, "
                    f"hiding from listing: {exc}",
                    file=sys.stderr,
                )
                continue
            seen.add(name)
        shadowed |= local_names
    return sorted(seen)


def is_registered(name: str, workspaces_dir: Path | None = None) -> bool:
    """Workspace が登録済 (= parse 可能なテンプレが存在) か。"""
    try:
        load_workspace(name, workspaces_dir=workspaces_dir)
    except (WorkspaceNotFoundError, WorkspaceValidationError):
        return False
    return True


# ---- CLI -----------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    names = list_workspaces()
    if args.json:
        out = []
        for n in names:
            try:
                w = load_workspace(n)
            except WorkspaceError:
                continue
            out.append(asdict(w) | {"path": str(w.path)})
        # path は dataclass の Path 型、asdict は Path のまま残すので文字列化
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    if not names:
        print("(no workspaces)")
        return 0
    for name in names:
        print(name)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        w = load_workspace(args.workspace)
    except WorkspaceNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    except WorkspaceValidationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 4
    if args.json:
        d = asdict(w)
        d["path"] = str(w.path)
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0
    print(f"workspace:      {w.name}")
    print(f"schema_version: {w.schema_version}")
    print(f"vcs:            {w.vcs}")
    print(f"repo:           {w.repo}")
    print(f"mode:           {w.mode}")
    print(f"branch_prefix:  {w.branch_prefix}")
    print(f"allowed_cli:    {list(w.allowed_cli)}")
    print(f"purpose:        {w.purpose}")
    print(f"path:           {w.path}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        load_workspace(args.workspace)
    except WorkspaceNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    except WorkspaceValidationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 4
    print(f"ok: workspace='{args.workspace}' registered")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workspace.py",
        description="Workspace catalog (ADR-0022 / Phase 5d-1)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="登録済 Workspace の一覧")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Workspace 詳細を表示")
    p_show.add_argument("workspace")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=_cmd_show)

    p_check = sub.add_parser(
        "check",
        help="Workspace が登録済かどうか (spawn-mind 用、exit 0/3/4)",
    )
    p_check.add_argument("workspace")
    p_check.set_defaults(func=_cmd_check)

    ns = parser.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
