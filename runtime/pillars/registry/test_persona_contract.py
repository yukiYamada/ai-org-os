"""Phase 5g.A #168: persona_contract.py の unit test。

検証対象:
- load_contract / detect_drift / VirtualDispatch / CLI (show / check)
- **既存 4 Persona (designer / implementer / reviewer / guildmaster) に対する
  deterministic な contract assertion** (= 完了基準: 5 件以上)
- Persona 改訂で test が red になる demo (= fixture で簡易再現)
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from persona import PersonaError  # noqa: E402
from persona_contract import (  # noqa: E402
    PersonaContract,
    VirtualDispatch,
    detect_drift,
    load_contract,
    main,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_persona_with_contract(
    dir_path: Path,
    name: str,
    *,
    inbound: str = "",
    outbound: str = "",
    forbidden: str = "",
    cycle_budget: str = "",
    trust_layer: str = "",
    body: str = "",
    extra_fm: str = "",
) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        f"persona: {name}",
        "version: 0.1",
        "status: experimental",
    ]
    if inbound:
        fm.append(f"inbound_topics: {inbound}")
    if outbound:
        fm.append(f"outbound_topics: {outbound}")
    if forbidden:
        fm.append(f"forbidden_ops: {forbidden}")
    if cycle_budget:
        fm.append(f"cycle_budget_seconds_max: {cycle_budget}")
    if trust_layer:
        fm.append(f"trust_layer: {trust_layer}")
    if extra_fm:
        fm.append(extra_fm)
    fm.append("---")
    content = "\n".join(fm) + "\n\n" + (body or f"# Persona: {name}\n")
    p = dir_path / f"{name}.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Synthetic contract tests (= harness 単体検証)
# ---------------------------------------------------------------------------


class TestLoadContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_all_fields_parsed(self) -> None:
        _write_persona_with_contract(
            self.dir,
            "full",
            inbound="[review-request, spec-question]",
            outbound="[review-reply]",
            forbidden="[gh pr merge, git push --force]",
            cycle_budget="60",
            trust_layer="L1",
            body="禁止: gh pr merge / git push --force",
        )
        c = load_contract("full", personas_dir=self.dir)
        self.assertEqual(c.inbound_topics, ("review-request", "spec-question"))
        self.assertEqual(c.outbound_topics, ("review-reply",))
        self.assertEqual(c.forbidden_ops, ("gh pr merge", "git push --force"))
        self.assertEqual(c.cycle_budget_seconds_max, 60)
        self.assertEqual(c.trust_layer, "L1")

    def test_missing_optional_fields_yields_empty(self) -> None:
        _write_persona_with_contract(self.dir, "minimal")
        c = load_contract("minimal", personas_dir=self.dir)
        self.assertEqual(c.inbound_topics, ())
        self.assertEqual(c.outbound_topics, ())
        self.assertEqual(c.forbidden_ops, ())
        self.assertIsNone(c.cycle_budget_seconds_max)
        self.assertIsNone(c.trust_layer)

    def test_non_integer_budget_raises(self) -> None:
        _write_persona_with_contract(self.dir, "bad", cycle_budget="abc")
        with self.assertRaises(PersonaError) as ctx:
            load_contract("bad", personas_dir=self.dir)
        self.assertIn("non-integer", str(ctx.exception))

    def test_unknown_persona_raises(self) -> None:
        with self.assertRaises(PersonaError):
            load_contract("ghost", personas_dir=self.dir)

    def test_quoted_int_accepted(self) -> None:
        """`cycle_budget_seconds_max: "60"` も受け取れる。"""
        _write_persona_with_contract(self.dir, "q", cycle_budget='"60"')
        c = load_contract("q", personas_dir=self.dir)
        self.assertEqual(c.cycle_budget_seconds_max, 60)


class TestContractQueries(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        _write_persona_with_contract(
            self.dir,
            "demo",
            inbound="[review-request]",
            outbound="[review-reply]",
            forbidden="[gh pr merge]",
            cycle_budget="60",
            body="禁止: gh pr merge — 本文に説明文",
        )
        self.contract = load_contract("demo", personas_dir=self.dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_fires_true_for_declared_inbound(self) -> None:
        self.assertTrue(self.contract.fires("review-request"))

    def test_fires_false_for_undeclared(self) -> None:
        self.assertFalse(self.contract.fires("unknown-topic"))

    def test_produces_true_for_declared_outbound(self) -> None:
        self.assertTrue(self.contract.produces("review-reply"))

    def test_forbids_true_for_declared_op(self) -> None:
        self.assertTrue(self.contract.forbids("gh pr merge"))

    def test_body_mentions_op(self) -> None:
        self.assertTrue(self.contract.body_mentions("gh pr merge"))

    def test_body_does_not_mention_random(self) -> None:
        self.assertFalse(self.contract.body_mentions("kubectl apply -f /etc/shadow"))


class TestVirtualDispatch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        _write_persona_with_contract(
            self.dir,
            "vd",
            inbound="[review-request]",
            outbound="[review-reply]",
        )
        self.contract = load_contract("vd", personas_dir=self.dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_handled_for_declared_topic(self) -> None:
        resp = self.contract.virtual_dispatch(VirtualDispatch(topic="review-request"))
        self.assertTrue(resp.handled)
        self.assertEqual(resp.outbound_topics, ("review-reply",))

    def test_not_handled_for_undeclared_topic(self) -> None:
        resp = self.contract.virtual_dispatch(VirtualDispatch(topic="random"))
        self.assertFalse(resp.handled)
        self.assertEqual(resp.outbound_topics, ())


class TestDetectDrift(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_drift_when_op_mentioned(self) -> None:
        _write_persona_with_contract(
            self.dir,
            "ok",
            forbidden="[gh pr merge]",
            body="本文中で gh pr merge を禁止と説明している",
        )
        c = load_contract("ok", personas_dir=self.dir)
        self.assertEqual(detect_drift(c), [])

    def test_drift_found_when_op_missing_from_body(self) -> None:
        _write_persona_with_contract(
            self.dir,
            "drift",
            forbidden="[gh pr merge, missing-op-X]",
            body="本文は gh pr merge のみ説明している",
        )
        c = load_contract("drift", personas_dir=self.dir)
        findings = detect_drift(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].persona, "drift")
        self.assertEqual(findings[0].kind, "forbidden_op_missing_in_body")
        self.assertIn("missing-op-X", findings[0].detail)


# ---------------------------------------------------------------------------
# Real Persona tests (= 完了基準: 既存 4 Persona x 5+ cases)
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TEMPLATES_PERSONAS = _REPO_ROOT / "templates" / "personas"
_TEMPLATE_PERSONA_NAMES = (
    "designer",
    "implementer",
    "reviewer",
    "guildmaster",
    # Phase 5g.A #169: deterministic Kind reference Persona
    "watcher",
)


class TestRealPersonas(unittest.TestCase):
    """templates/personas/ の 4 Persona に対する deterministic contract assertion。

    Persona 改訂で contract / prose の整合性が崩れたら ここが red になる。
    """

    def test_reviewer_inbound_includes_review_request(self) -> None:
        c = load_contract("reviewer", personas_dir=_TEMPLATES_PERSONAS)
        self.assertIn(
            "review-request", c.inbound_topics,
            "reviewer は implementer からの review-request を受け取る (運用上の前提)",
        )

    def test_reviewer_outbound_includes_review_reply(self) -> None:
        c = load_contract("reviewer", personas_dir=_TEMPLATES_PERSONAS)
        self.assertIn("review-reply", c.outbound_topics)

    def test_reviewer_forbids_pr_merge(self) -> None:
        c = load_contract("reviewer", personas_dir=_TEMPLATES_PERSONAS)
        self.assertTrue(
            c.forbids("gh pr merge"),
            "ADR-0027 L1: reviewer は merge bypass 不可",
        )

    def test_implementer_outbound_includes_review_request(self) -> None:
        c = load_contract("implementer", personas_dir=_TEMPLATES_PERSONAS)
        self.assertIn(
            "review-request", c.outbound_topics,
            "implementer は reviewer へ review-request を送る (= chain trigger)",
        )

    def test_implementer_forbids_force_push(self) -> None:
        c = load_contract("implementer", personas_dir=_TEMPLATES_PERSONAS)
        self.assertTrue(
            c.forbids("git push --force"),
            "ADR-0027 L1: implementer は force push 禁止",
        )

    def test_designer_outbound_declares_design_topic(self) -> None:
        c = load_contract("designer", personas_dir=_TEMPLATES_PERSONAS)
        # designer は dispatch で 設計案 を流す。topic 名は将来揺れる可能性が
        # あるので「design を含む topic が 1 つ以上」を assert する。
        has_design_topic = any("design" in t for t in c.outbound_topics)
        self.assertTrue(
            has_design_topic,
            f"designer outbound_topics must include a 'design'-bearing topic; "
            f"got {list(c.outbound_topics)}",
        )

    def test_guildmaster_cycle_budget_declared(self) -> None:
        c = load_contract("guildmaster", personas_dir=_TEMPLATES_PERSONAS)
        # #134 由来: guildmaster は cycle body 爆発が起きやすい。budget を
        # 明示宣言することで「観察対象を絞る」 規範を機械可読化。
        self.assertIsNotNone(c.cycle_budget_seconds_max)
        self.assertLessEqual(c.cycle_budget_seconds_max, 60)

    def test_all_template_personas_have_cycle_budget(self) -> None:
        """governance: 同梱 Persona は全員 cycle_budget を宣言すること。"""
        for name in _TEMPLATE_PERSONA_NAMES:
            c = load_contract(name, personas_dir=_TEMPLATES_PERSONAS)
            self.assertIsNotNone(
                c.cycle_budget_seconds_max,
                f"template persona '{name}' missing cycle_budget_seconds_max",
            )

    def test_no_template_persona_has_drift(self) -> None:
        """すべての同梱 Persona で contract <-> body の drift が無いこと。"""
        all_findings: list[str] = []
        for name in _TEMPLATE_PERSONA_NAMES:
            c = load_contract(name, personas_dir=_TEMPLATES_PERSONAS)
            findings = detect_drift(c)
            for f in findings:
                all_findings.append(f"{f.persona}: {f.detail}")
        self.assertEqual(
            all_findings, [],
            msg="contract と persona body に drift があります:\n" + "\n".join(all_findings),
        )


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        _write_persona_with_contract(
            self.dir,
            "cli_ok",
            forbidden="[gh pr merge]",
            body="本文に gh pr merge を含む",
        )
        _write_persona_with_contract(
            self.dir,
            "cli_drift",
            forbidden="[gh pr merge, drift-op-Y]",
            body="本文に gh pr merge のみ",
        )
        import os
        self._old = os.environ.get("AI_ORG_OS_PERSONAS_DIR")
        os.environ["AI_ORG_OS_PERSONAS_DIR"] = str(self.dir)

    def tearDown(self) -> None:
        import os
        if self._old is None:
            os.environ.pop("AI_ORG_OS_PERSONAS_DIR", None)
        else:
            os.environ["AI_ORG_OS_PERSONAS_DIR"] = self._old
        self._tmp.cleanup()

    def test_show_ok(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["persona_contract.py", "show", "cli_ok"])
        self.assertEqual(rc, 0)
        self.assertIn("cli_ok", out.getvalue())
        self.assertIn("gh pr merge", out.getvalue())

    def test_show_unknown_persona_returns_1(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["persona_contract.py", "show", "ghost"])
        self.assertEqual(rc, 1)
        self.assertIn("not registered", err.getvalue())

    def test_check_no_drift_returns_0(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["persona_contract.py", "check", "cli_ok"])
        self.assertEqual(rc, 0)
        self.assertIn("in sync", out.getvalue())

    def test_check_drift_returns_1(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["persona_contract.py", "check", "cli_drift"])
        self.assertEqual(rc, 1)
        self.assertIn("DRIFT", err.getvalue())
        self.assertIn("drift-op-Y", err.getvalue())

    def test_unknown_command(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["persona_contract.py", "magic"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown command", err.getvalue())

    def test_no_args(self) -> None:
        with patch("sys.stderr", new_callable=StringIO):
            rc = main(["persona_contract.py"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
