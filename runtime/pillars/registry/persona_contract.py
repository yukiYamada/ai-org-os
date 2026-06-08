"""Persona Contract — Persona の declarative ルールを machine-readable に取り出す層。

Phase 5g.A (#168): test harness の基盤。Persona 改訂で contract が壊れたら
unit test が red になる。LLM は呼ばない (= deterministic) ので CI で回せる。

設計判断 (= ADR-0021 / ADR-0027 を参照):

- Persona prose は B 宣言 (= 機械強制されない、LLM 向け prose)。
- Contract は **同じ Persona ファイル** の frontmatter に **machine-readable な
  形で同じ情報の subset を再宣言** したもの。
- cross-check: contract の forbidden_ops に書いた string は Persona body に
  substring として現れる (= prose と contract の drift 検出)。これにより
  「prose は更新したが contract は古いまま」 / その逆を検知できる。
- Contract は **opt-out 不可** に近い (= 全 Persona に最低 cycle_budget を
  要求する。default を持たない、書き忘れは reject)。これは「Persona を
  書いたら test を書く」規範を機械的に enforce するため。

検証する schema:

- 必須: なし (= contract 自体は opt-in。test harness 側で `all_personas_have_*`
  test が個別フィールドの存在を要求する)
- 任意フィールド:
  - `inbound_topics: [topic1, topic2]` — この Persona が dispatch として
    受け取る topic 一覧
  - `outbound_topics: [topic1, topic2]` — この Persona が dispatch として
    送る topic 一覧
  - `forbidden_ops: [op1, op2]` — この Persona が実行してはいけない
    operation 一覧 (= ADR-0027 L1 の machine-readable 化)
  - `cycle_budget_seconds_max: 60` — 1 cycle 上限目安 (= #144 / #134 由来の
    B 宣言の数値化)
  - `trust_layer: L1` — ADR-0027 の信頼境界 layer

stdlib only。persona.py / registry.py / guild.py / workspace.py と同じ流儀。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from persona import (  # noqa: E402
    PersonaError,
    _parse_frontmatter,
    _parse_yaml_list,
    _strip_quotes,
    get_persona,
)


_INT_RE = re.compile(r"^-?\d+$")


@dataclass(frozen=True)
class VirtualDispatch:
    """Persona に投げる仮想 dispatch (= LLM を呼ばずに contract に照会)。"""

    topic: str
    from_mind: str = "alice"
    to_mind: str = "bob"


@dataclass(frozen=True)
class VirtualResponse:
    """Virtual dispatch に対する期待 response の宣言。

    `outbound_topics` は contract が宣言した「この dispatch に対して送る
    可能性のある topic」のうち、prose の運用ルールから対応する subset。
    現状の最小版では outbound 全体を返す。
    """

    handled: bool
    outbound_topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class PersonaContract:
    """Persona 1 件の machine-readable contract。"""

    name: str
    path: Path
    inbound_topics: tuple[str, ...] = ()
    outbound_topics: tuple[str, ...] = ()
    forbidden_ops: tuple[str, ...] = ()
    cycle_budget_seconds_max: int | None = None
    trust_layer: str | None = None
    body: str = field(default="", repr=False)

    # ---- query API ----

    def fires(self, topic: str) -> bool:
        """この Persona が `topic` の inbound dispatch を受けることを宣言しているか。"""
        return topic in self.inbound_topics

    def produces(self, topic: str) -> bool:
        """この Persona が `topic` を outbound dispatch として送ることを宣言しているか。"""
        return topic in self.outbound_topics

    def forbids(self, op: str) -> bool:
        """この Persona が `op` を禁止 operation として宣言しているか。"""
        return op in self.forbidden_ops

    def body_mentions(self, op: str) -> bool:
        """`op` が Persona body に substring として現れるか (= prose 整合性 cross-check)。"""
        return op in self.body

    def virtual_dispatch(self, dispatch: VirtualDispatch) -> VirtualResponse:
        """仮想 dispatch を投げて期待 response を返す。

        現状の最小版では inbound_topics に topic が含まれていれば handled=True、
        その時の outbound_topics 全体を candidate として返す。
        """
        if not self.fires(dispatch.topic):
            return VirtualResponse(handled=False, outbound_topics=())
        return VirtualResponse(handled=True, outbound_topics=self.outbound_topics)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_int(value: str) -> int | None:
    """`"60"` / `60` を int に。失敗時 None。"""
    s = _strip_quotes(value)
    if not _INT_RE.match(s):
        return None
    return int(s)


def _parse_list_field(value: str) -> tuple[str, ...]:
    """list 形式の frontmatter value を tuple of stripped strings に。"""
    raw = _parse_yaml_list(_strip_quotes(value))
    return tuple(_strip_quotes(item) for item in raw)


def _read_body(text: str) -> str:
    """frontmatter を除いた本文。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :])
    return ""


def load_contract(name: str, *, personas_dir: Path | None = None) -> PersonaContract:
    """Persona 1 件の contract を読み込む。

    Raises:
        PersonaError: persona 不在 / frontmatter 不正 / cycle_budget が non-int
    """
    info = get_persona(name, personas_dir=personas_dir)
    if info is None:
        raise PersonaError(f"persona '{name}' not registered or invalid")
    text = info.path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    body = _read_body(text)

    inbound = _parse_list_field(fm.get("inbound_topics", ""))
    outbound = _parse_list_field(fm.get("outbound_topics", ""))
    forbidden = _parse_list_field(fm.get("forbidden_ops", ""))

    budget_raw = fm.get("cycle_budget_seconds_max", "").strip()
    budget: int | None
    if not budget_raw:
        budget = None
    else:
        budget = _parse_int(budget_raw)
        if budget is None:
            raise PersonaError(
                f"persona '{name}' has non-integer cycle_budget_seconds_max: "
                f"{budget_raw!r}"
            )

    layer_raw = _strip_quotes(fm.get("trust_layer", "")).strip()
    layer: str | None = layer_raw if layer_raw else None

    return PersonaContract(
        name=info.name,
        path=info.path,
        inbound_topics=inbound,
        outbound_topics=outbound,
        forbidden_ops=forbidden,
        cycle_budget_seconds_max=budget,
        trust_layer=layer,
        body=body,
    )


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftFinding:
    """contract と prose の drift 1 件。"""

    persona: str
    kind: str  # "forbidden_op_missing_in_body"
    detail: str


def detect_drift(contract: PersonaContract) -> list[DriftFinding]:
    """contract と Persona body の drift を検出。

    現状の検査:
    - forbidden_ops に挙げた各 op が body に substring として現れない場合
      → drift (= contract に書いたが prose で説明していない / または逆に
      prose から削除されたのに contract が古いまま)
    """
    findings: list[DriftFinding] = []
    for op in contract.forbidden_ops:
        if not contract.body_mentions(op):
            findings.append(
                DriftFinding(
                    persona=contract.name,
                    kind="forbidden_op_missing_in_body",
                    detail=(
                        f"forbidden_op '{op}' declared in contract but not "
                        f"found verbatim in persona body"
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _contract_to_dict(c: PersonaContract) -> dict[str, object]:
    d = asdict(c)
    # body は出力しない (= 長い)。path は str に。
    d.pop("body", None)
    d["path"] = str(c.path)
    return d


def _cmd_show(argv: list[str]) -> int:
    if not argv:
        print("[ERROR] 'show' requires a persona name", file=sys.stderr)
        return 2
    name = argv[0]
    as_json = "--json" in argv
    try:
        c = load_contract(name)
    except PersonaError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(_contract_to_dict(c), indent=2, ensure_ascii=False))
    else:
        print(f"name:                       {c.name}")
        print(f"inbound_topics:             {list(c.inbound_topics)}")
        print(f"outbound_topics:            {list(c.outbound_topics)}")
        print(f"forbidden_ops:              {list(c.forbidden_ops)}")
        print(f"cycle_budget_seconds_max:   {c.cycle_budget_seconds_max}")
        print(f"trust_layer:                {c.trust_layer}")
        print(f"path:                       {c.path}")
    return 0


def _cmd_check(argv: list[str]) -> int:
    """指定 Persona の drift を検査。0 = no drift、1 = drift detected。"""
    if not argv:
        print("[ERROR] 'check' requires a persona name", file=sys.stderr)
        return 2
    name = argv[0]
    try:
        c = load_contract(name)
    except PersonaError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    findings = detect_drift(c)
    if not findings:
        print(f"[ok] persona '{name}' contract <-> body in sync")
        return 0
    print(f"[DRIFT] persona '{name}' has {len(findings)} drift finding(s):",
          file=sys.stderr)
    for f in findings:
        print(f"  - [{f.kind}] {f.detail}", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "Usage: persona_contract.py {show|check} <name> [--json]\n"
            "Phase 5g.A #168: Persona contract harness.",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    rest = argv[2:]
    if cmd == "show":
        return _cmd_show(rest)
    if cmd == "check":
        return _cmd_check(rest)
    print(f"[ERROR] unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
