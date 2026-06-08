"""Framework version + constraint — `runtime/VERSION` を読み、C 層 manifest が
宣言する `framework_version` 制約 (`>=X.Y` 等) と比較する。

Phase 5g.A (#170): publish 可能な framework foundation v2 の最後の primitive。
他人が clone した古い org が新 VERSION で壊れる時 (= breaking change を踏んだ
時) に **WARN を出す** ことで「いつ壊れるか分からない」状態を解消する。

設計判断:

- VERSION は **single source of truth** として `runtime/VERSION` に置く
  (pyproject.toml は本 repo が pip package ではないので不要)
- SemVer (`MAJOR.MINOR.PATCH`) に従う。詳細は `CHANGELOG.md`
- Constraint は **subset of PEP 440**: `>=`, `>`, `<=`, `<`, `==` のみ
  対応。カンマ区切りで AND (`">=1.0,<2.0"`)。`~=` (compatible release) は
  必要になったら追加する (= YAGNI、現状の利用 case で十分)
- mismatch は **WARN** にとどめる (= ABORT は厳しすぎる)。abort path は
  将来 `AI_ORG_OS_STRICT_VERSION=1` で opt-in 可能にする (= 将来拡張)

stdlib only。registry.py / persona.py と同じ流儀。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# runtime/pillars/registry/version.py → runtime/VERSION
_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"

# SemVer の最小 form。`pre-release` / `build metadata` は本 framework では
# 使わない (= release cadence が monthly レベル、CHANGELOG で表現する)。
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")
_CONSTRAINT_RE = re.compile(r"^(>=|>|<=|<|==)\s*(\d+\.\d+(?:\.\d+)?)$")


class VersionError(Exception):
    """version 層の汎用エラー。"""


@dataclass(frozen=True, order=True)
class Version:
    """SemVer の triple。順序比較は (major, minor, patch) で。"""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class _Bound:
    op: str  # ">=" / ">" / "<=" / "<" / "=="
    version: Version

    def satisfies(self, v: Version) -> bool:
        if self.op == ">=":
            return v >= self.version
        if self.op == ">":
            return v > self.version
        if self.op == "<=":
            return v <= self.version
        if self.op == "<":
            return v < self.version
        if self.op == "==":
            return v == self.version
        # parse_constraint が op を検査しているのでここには来ない
        raise VersionError(f"unsupported operator: {self.op}")


@dataclass(frozen=True)
class Constraint:
    """`>=1.0,<2.0` のような AND の集合。空 = 何でも match。"""

    bounds: tuple[_Bound, ...]

    def satisfies(self, v: Version) -> bool:
        return all(b.satisfies(v) for b in self.bounds)

    def __str__(self) -> str:
        if not self.bounds:
            return "*"
        return ",".join(f"{b.op}{b.version}" for b in self.bounds)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_version(s: str) -> Version:
    """`"1.0"` / `"1.0.0"` を Version に。

    Raises:
        VersionError: 構文不正
    """
    m = _VERSION_RE.match(s.strip())
    if not m:
        raise VersionError(f"invalid version: {s!r} (expected MAJOR.MINOR[.PATCH])")
    major, minor, patch = m.group(1), m.group(2), m.group(3) or "0"
    return Version(int(major), int(minor), int(patch))


def parse_constraint(s: str) -> Constraint:
    """`">=1.0"` / `">=1.0,<2.0"` を Constraint に。

    空文字 / `"*"` → 空 bounds (= 何でも match)。

    Raises:
        VersionError: 構文不正
    """
    s = s.strip()
    if not s or s == "*":
        return Constraint(bounds=())
    parts = [p.strip() for p in s.split(",")]
    bounds: list[_Bound] = []
    for part in parts:
        if not part:
            continue
        m = _CONSTRAINT_RE.match(part)
        if not m:
            raise VersionError(
                f"invalid constraint clause: {part!r} "
                f"(expected one of '>=' / '>' / '<=' / '<' / '==' followed by version)"
            )
        op, ver = m.group(1), m.group(2)
        bounds.append(_Bound(op=op, version=parse_version(ver)))
    return Constraint(bounds=tuple(bounds))


def read_framework_version(version_file: Path | None = None) -> Version:
    """`runtime/VERSION` を読み込む。

    Raises:
        VersionError: ファイル無し / 不正
    """
    path = version_file if version_file is not None else _VERSION_FILE
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise VersionError(f"failed to read VERSION file at {path}: {exc}") from exc
    if not raw:
        raise VersionError(f"VERSION file at {path} is empty")
    return parse_version(raw)


# ---------------------------------------------------------------------------
# Mismatch check (= 各 C 層 validator が呼ぶ)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionCheck:
    """check_framework_version の結果。"""

    ok: bool
    runtime: Version
    constraint: Constraint
    detail: str  # human-readable explanation, 失敗時は理由を含む


def check_framework_version(
    constraint_str: str,
    *,
    runtime_version: Version | None = None,
) -> VersionCheck:
    """C 層 manifest が宣言する `framework_version` constraint を検証。

    - constraint 空 / `*` → ok=True (= 無制約)
    - constraint 不正構文 → ok=False (parse error を detail に)
    - constraint 満たさない → ok=False (現 VERSION と constraint を detail に)
    - 満たす → ok=True
    """
    rt = runtime_version if runtime_version is not None else read_framework_version()
    try:
        constraint = parse_constraint(constraint_str)
    except VersionError as exc:
        return VersionCheck(
            ok=False,
            runtime=rt,
            constraint=Constraint(bounds=()),
            detail=f"invalid constraint {constraint_str!r}: {exc}",
        )

    if not constraint.bounds:
        return VersionCheck(
            ok=True,
            runtime=rt,
            constraint=constraint,
            detail=f"no constraint (runtime={rt})",
        )

    if constraint.satisfies(rt):
        return VersionCheck(
            ok=True,
            runtime=rt,
            constraint=constraint,
            detail=f"runtime {rt} satisfies {constraint}",
        )
    return VersionCheck(
        ok=False,
        runtime=rt,
        constraint=constraint,
        detail=f"runtime {rt} does NOT satisfy constraint {constraint}",
    )


def warn_if_mismatch(
    constraint_str: str,
    *,
    source_label: str,
    stream=sys.stderr,
    runtime_version: Version | None = None,
) -> VersionCheck:
    """check_framework_version の wrapper。mismatch なら WARN を出す。

    `source_label` は manifest を識別する短い tag (例: "kind:generic" /
    "guild:my-guild")。空 constraint は何も出さない (= 既存 manifest は
    黙って通る)。
    """
    if not constraint_str.strip():
        return VersionCheck(
            ok=True,
            runtime=runtime_version or read_framework_version(),
            constraint=Constraint(bounds=()),
            detail="no constraint",
        )
    result = check_framework_version(
        constraint_str, runtime_version=runtime_version,
    )
    if not result.ok:
        print(
            f"[WARN] {source_label}: framework_version mismatch "
            f"({result.detail})",
            file=stream,
        )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_print(argv: list[str]) -> int:
    """現 framework version を stdout に。"""
    as_json = "--json" in argv
    try:
        v = read_framework_version()
    except VersionError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({"framework_version": str(v)}))
    else:
        print(v)
    return 0


def _cmd_check(argv: list[str]) -> int:
    """指定 constraint を現 VERSION で評価。0 = ok / 1 = mismatch / 2 = error。"""
    if not argv:
        print("[ERROR] 'check' requires a constraint", file=sys.stderr)
        return 2
    constraint_str = argv[0]
    try:
        rt = read_framework_version()
    except VersionError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    result = check_framework_version(constraint_str, runtime_version=rt)
    if result.ok:
        print(f"[ok] {result.detail}")
        return 0
    print(f"[mismatch] {result.detail}", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "Usage: version.py {print|check} [<constraint>] [--json]\n"
            "Phase 5g.A #170: Framework versioning.",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    rest = argv[2:]
    if cmd == "print":
        return _cmd_print(rest)
    if cmd == "check":
        return _cmd_check(rest)
    print(f"[ERROR] unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
