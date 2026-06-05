"""Persona Registry — `templates/personas/<name>.md` および
`$AI_ORG_OS_HOME/personas/<name>.md` の overlay lookup と frontmatter 検証。

Phase 5g.A (#167): C 層 schema validation の一環。Kind / Guild / Workspace
には既に Registry Pillar の validation があったが、Persona は spawn-mind 内で
ファイル存在チェックのみで通過していた (= frontmatter typo / 構文崩れが silent
に通り、Mind が起動した後に CLAUDE.md として読まれる時点で初めて気付くケース)。
本モジュールが spawn 前の早期 abort 経路を提供する。

検証する schema (= ADR-0020 / ADR-0022 を基準):
- 必須: `persona` (filename と一致)、`version` (string)、`status` (string)
- 任意: 任意の追加 key (= 拡張余地、warning 無し)

stdlib only。registry.py / guild.py / workspace.py と同じ流儀。
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_REQUIRED_KEYS = ("persona", "version", "status")


class PersonaError(Exception):
    """Persona 層の汎用エラー。"""


@dataclass(frozen=True)
class PersonaInfo:
    """Persona 1 件のメタデータ。"""

    name: str
    path: Path
    version: str
    status: str


def _home_personas_dir() -> Path | None:
    """利用者の Persona 実体 dir (`$AI_ORG_OS_HOME/personas`)。"""
    home = os.environ.get("AI_ORG_OS_HOME")
    if home:
        return Path(home) / "personas"
    h = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if h:
        return Path(h) / ".ai-org-os" / "personas"
    return None


def _template_personas_dir() -> Path:
    """同梱テンプレ Persona dir (`templates/personas`)。"""
    return _TEMPLATES_DIR / "personas"


def _search_dirs(personas_dir: Path | None) -> list[Path]:
    """lookup 候補 dir を「優先度が高い順」で返す。"""
    if personas_dir is not None:
        return [Path(personas_dir)]
    env = os.environ.get("AI_ORG_OS_PERSONAS_DIR")
    if env:
        return [Path(env)]
    dirs: list[Path] = []
    home = _home_personas_dir()
    if home is not None and home.is_dir():
        dirs.append(home)
    dirs.append(_template_personas_dir())
    return dirs


def _is_valid_name(name: str) -> bool:
    return bool(_VALID_NAME_RE.match(name))


def _parse_frontmatter(text: str) -> dict[str, str]:
    """先頭の `---` で挟まれた frontmatter を最小パース。

    registry.py / workspace.py と同じ仕様: 単純 key: value のみ、quoted は
    そのまま保持 (= 呼び出し側で strip)、閉じ `---` 無しは空 dict。
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
    # 閉じ無し → 空
    return {}


def _strip_quotes(value: str) -> str:
    """YAML scalar の外側 `"..."` / `'...'` を 1 段剥がす。"""
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def _read_persona_file(path: Path) -> PersonaInfo | None:
    """1 ファイルを PersonaInfo に変換。

    frontmatter 無し / 必須 key 欠落 / persona フィールドとファイル名不一致
    → None + stderr WARN。
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

    # 必須キーチェック
    missing = [k for k in _REQUIRED_KEYS if k not in fm]
    if missing:
        print(
            f"[WARN] frontmatter missing required keys {missing} in {path}, skipping",
            file=sys.stderr,
        )
        return None

    persona_name = _strip_quotes(fm["persona"])
    file_stem = path.stem

    # filename と persona フィールドの一致 (= 攻撃的注入 / typo の検知)
    if persona_name != file_stem:
        print(
            f"[WARN] frontmatter persona '{persona_name}' does not match filename "
            f"'{file_stem}' in {path}",
            file=sys.stderr,
        )
        return None

    if not _is_valid_name(persona_name):
        print(
            f"[WARN] persona name '{persona_name}' from {path} is not a valid identifier",
            file=sys.stderr,
        )
        return None

    return PersonaInfo(
        name=persona_name,
        path=path,
        version=_strip_quotes(fm["version"]),
        status=_strip_quotes(fm["status"]),
    )


def list_personas(personas_dir: Path | None = None) -> list[PersonaInfo]:
    """Persona 一覧。home (実体) → templates (同梱) の overlay。

    Codex P2 (#88) と同じ shadow consistency: home に同名 .md があれば
    templates 側は隠れる (= malformed home エントリは下位に fallback しない)。
    """
    seen_stems: set[str] = set()
    results: list[PersonaInfo] = []
    for source in _search_dirs(personas_dir):
        if not source.is_dir():
            continue
        try:
            entries = sorted(source.glob("*.md"))
        except OSError:
            continue
        for entry in entries:
            stem = entry.stem
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            info = _read_persona_file(entry)
            if info is not None:
                results.append(info)
    return results


def get_persona(name: str, personas_dir: Path | None = None) -> PersonaInfo | None:
    """指定 Persona の情報を返す。無効名 / 不在 → None。"""
    if not _is_valid_name(name):
        return None
    for source in _search_dirs(personas_dir):
        candidate = source / f"{name}.md"
        if candidate.is_file():
            return _read_persona_file(candidate)
    return None


def is_registered(name: str, personas_dir: Path | None = None) -> bool:
    """Persona が登録されているか (= valid frontmatter を持つか)。"""
    return get_persona(name, personas_dir=personas_dir) is not None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _persona_to_dict(p: PersonaInfo) -> dict[str, str]:
    d = asdict(p)
    d["path"] = str(p.path)
    return d


def _format_table(personas: list[PersonaInfo]) -> str:
    if not personas:
        return "No personas registered."
    lines = [
        "=== Mind Persona Registry ===",
        f"  total: {len(personas)}",
        "",
        f"{'NAME':<20} {'VERSION':<10} {'STATUS':<14} PATH",
    ]
    for p in personas:
        lines.append(f"{p.name:<20} {p.version:<10} {p.status:<14} {p.path}")
    return "\n".join(lines)


def _cmd_list(argv: list[str]) -> int:
    as_json = "--json" in argv
    personas = list_personas()
    if as_json:
        print(json.dumps({"personas": [_persona_to_dict(p) for p in personas]},
                         indent=2, ensure_ascii=False))
    else:
        print(_format_table(personas))
    return 0


def _cmd_get(argv: list[str]) -> int:
    if not argv:
        print("[ERROR] 'get' requires a persona name", file=sys.stderr)
        return 2
    name = argv[0]
    as_json = "--json" in argv
    info = get_persona(name)
    if info is None:
        print(f"[ERROR] persona '{name}' is not registered", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(_persona_to_dict(info), indent=2, ensure_ascii=False))
    else:
        print(f"name:    {info.name}")
        print(f"version: {info.version}")
        print(f"status:  {info.status}")
        print(f"path:    {info.path}")
    return 0


def _cmd_check(argv: list[str]) -> int:
    """spawn-mind から呼ぶ用。0 = ok、1 = unregistered。"""
    if not argv:
        print("[ERROR] 'check' requires a persona name", file=sys.stderr)
        return 2
    name = argv[0]
    info = get_persona(name)
    if info is None:
        print(f"[ERROR] persona '{name}' is not registered or has invalid frontmatter",
              file=sys.stderr)
        return 1
    print(f"[ok] persona '{name}' registered ({info.path})")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "Usage: persona.py {list|get|check} [<name>] [--json]\n"
            "Phase 5g.A #167: Persona Registry validator.",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    rest = argv[2:]
    if cmd == "list":
        return _cmd_list(rest)
    if cmd == "get":
        return _cmd_get(rest)
    if cmd == "check":
        return _cmd_check(rest)
    print(f"[ERROR] unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
