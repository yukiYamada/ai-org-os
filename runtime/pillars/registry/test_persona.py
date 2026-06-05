"""Phase 5g.A #167: persona.py の unit test。

list_personas / get_persona / is_registered / CLI (check / list / get) を検証。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from persona import (  # noqa: E402
    PersonaError,
    PersonaInfo,
    compose_persona,
    get_persona,
    is_registered,
    list_personas,
    main,
)


def _write_persona(
    dir_path: Path,
    name: str,
    *,
    persona_field: str | None = None,
    version: str = "0.1",
    status: str = "experimental",
    include_frontmatter: bool = True,
    extra_lines: str = "",
) -> Path:
    """Persona file を fixture として書く。"""
    dir_path.mkdir(parents=True, exist_ok=True)
    if persona_field is None:
        persona_field = name
    if include_frontmatter:
        content = (
            f"---\npersona: {persona_field}\nversion: {version}\n"
            f"status: {status}\n{extra_lines}---\n\n# Persona: {name}\n"
        )
    else:
        content = f"# Persona: {name} (no frontmatter)\n"
    p = dir_path / f"{name}.md"
    p.write_text(content, encoding="utf-8")
    return p


class TestGetPersona(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_valid_persona_loads(self) -> None:
        _write_persona(self.dir, "designer")
        info = get_persona("designer", personas_dir=self.dir)
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "designer")
        self.assertEqual(info.version, "0.1")
        self.assertEqual(info.status, "experimental")

    def test_missing_persona_returns_none(self) -> None:
        self.assertIsNone(get_persona("ghost", personas_dir=self.dir))

    def test_invalid_name_returns_none(self) -> None:
        # path traversal 等
        self.assertIsNone(get_persona("../etc/passwd", personas_dir=self.dir))
        self.assertIsNone(get_persona("name with space", personas_dir=self.dir))

    def test_persona_without_frontmatter_returns_none(self) -> None:
        _write_persona(self.dir, "broken", include_frontmatter=False)
        with patch("sys.stderr", new_callable=StringIO):
            info = get_persona("broken", personas_dir=self.dir)
        self.assertIsNone(info)

    def test_persona_with_missing_required_key_returns_none(self) -> None:
        """version key 欠落 → reject。"""
        p = self.dir / "incomplete.md"
        p.write_text("---\npersona: incomplete\nstatus: x\n---\n", encoding="utf-8")
        with patch("sys.stderr", new_callable=StringIO):
            info = get_persona("incomplete", personas_dir=self.dir)
        self.assertIsNone(info)

    def test_persona_field_must_match_filename(self) -> None:
        """frontmatter `persona: foo` だがファイル名は bar.md → reject (typo / 攻撃検知)。"""
        p = self.dir / "bar.md"
        p.write_text(
            "---\npersona: foo\nversion: 0.1\nstatus: x\n---\n",
            encoding="utf-8",
        )
        with patch("sys.stderr", new_callable=StringIO):
            info = get_persona("bar", personas_dir=self.dir)
        self.assertIsNone(info)

    def test_quoted_values_stripped(self) -> None:
        """`version: "0.1"` の引用符は剥がされて value だけ返る。"""
        _write_persona(self.dir, "quoted", version='"0.1"', status='"stable"')
        info = get_persona("quoted", personas_dir=self.dir)
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "0.1")
        self.assertEqual(info.status, "stable")


class TestListPersonas(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_lists_all_valid(self) -> None:
        _write_persona(self.dir, "a")
        _write_persona(self.dir, "b")
        _write_persona(self.dir, "c")
        ps = list_personas(personas_dir=self.dir)
        self.assertEqual([p.name for p in ps], ["a", "b", "c"])

    def test_skips_malformed(self) -> None:
        _write_persona(self.dir, "good")
        # 不正な persona (frontmatter なし)
        (self.dir / "bad.md").write_text("not a frontmatter", encoding="utf-8")
        with patch("sys.stderr", new_callable=StringIO):
            ps = list_personas(personas_dir=self.dir)
        self.assertEqual([p.name for p in ps], ["good"])

    def test_empty_dir(self) -> None:
        self.assertEqual(list_personas(personas_dir=self.dir), [])


class TestIsRegistered(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_registered_true(self) -> None:
        _write_persona(self.dir, "designer")
        self.assertTrue(is_registered("designer", personas_dir=self.dir))

    def test_unknown_false(self) -> None:
        self.assertFalse(is_registered("ghost", personas_dir=self.dir))

    def test_malformed_false(self) -> None:
        _write_persona(self.dir, "broken", include_frontmatter=False)
        with patch("sys.stderr", new_callable=StringIO):
            self.assertFalse(is_registered("broken", personas_dir=self.dir))


class TestCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        _write_persona(self.dir, "designer")
        # CLI は env var 経由で dir を指定する
        self._old = self._env_set(self.dir)

    def tearDown(self) -> None:
        self._env_restore(self._old)
        self._tmp.cleanup()

    def _env_set(self, dir_path: Path) -> str | None:
        import os
        old = os.environ.get("AI_ORG_OS_PERSONAS_DIR")
        os.environ["AI_ORG_OS_PERSONAS_DIR"] = str(dir_path)
        return old

    def _env_restore(self, old: str | None) -> None:
        import os
        if old is None:
            os.environ.pop("AI_ORG_OS_PERSONAS_DIR", None)
        else:
            os.environ["AI_ORG_OS_PERSONAS_DIR"] = old

    def test_check_ok(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["persona.py", "check", "designer"])
        self.assertEqual(rc, 0)
        self.assertIn("registered", out.getvalue())

    def test_check_unknown(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["persona.py", "check", "ghost"])
        self.assertEqual(rc, 1)
        self.assertIn("not registered", err.getvalue())

    def test_list_text(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["persona.py", "list"])
        self.assertEqual(rc, 0)
        self.assertIn("designer", out.getvalue())
        self.assertIn("Persona Registry", out.getvalue())

    def test_list_json(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["persona.py", "list", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload["personas"]), 1)
        self.assertEqual(payload["personas"][0]["name"], "designer")

    def test_get(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["persona.py", "get", "designer"])
        self.assertEqual(rc, 0)
        self.assertIn("name:    designer", out.getvalue())

    def test_unknown_command(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["persona.py", "magic"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown command", err.getvalue())

    def test_no_args(self) -> None:
        with patch("sys.stderr", new_callable=StringIO):
            rc = main(["persona.py"])
        self.assertEqual(rc, 2)


class TestComposePersona(unittest.TestCase):
    """Phase 5g.A #166: mixins を body 末尾に append する composer。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.personas = Path(self._tmp.name) / "personas"
        self.mixins = Path(self._tmp.name) / "mixins"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_mixin(self, name: str, body: str, with_frontmatter: bool = True) -> Path:
        self.mixins.mkdir(parents=True, exist_ok=True)
        if with_frontmatter:
            content = f"---\nmixin: {name}\nversion: 0.1\n---\n\n{body}\n"
        else:
            content = body + "\n"
        p = self.mixins / f"{name}.md"
        p.write_text(content, encoding="utf-8")
        return p

    def _write_persona_with_body(self, name: str, body: str, mixins_str: str = "") -> Path:
        self.personas.mkdir(parents=True, exist_ok=True)
        if mixins_str:
            fm_extra = f"mixins: {mixins_str}\n"
        else:
            fm_extra = ""
        content = (
            f"---\npersona: {name}\nversion: 0.1\nstatus: experimental\n{fm_extra}---\n\n{body}\n"
        )
        p = self.personas / f"{name}.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_no_mixins_returns_body_unchanged(self) -> None:
        """mixins 無しなら本文がそのまま返る。"""
        self._write_persona_with_body("plain", "## Role\nPlain text body.")
        out = compose_persona("plain", personas_dir=self.personas, mixins_dir=self.mixins)
        self.assertIn("## Role", out)
        self.assertIn("Plain text body.", out)
        # frontmatter も保持される (= spawn-mind が CLAUDE.md に置く前提)
        self.assertIn("persona: plain", out)

    def test_single_mixin_appended_to_end(self) -> None:
        """mixin が body の末尾に append される (= frontmatter 剥がし + body のみ)。"""
        self._write_mixin("foot", "## Foot Section\nFoot content.")
        self._write_persona_with_body(
            "withfoot",
            "## Main\nMain content.",
            mixins_str="[foot]",
        )
        out = compose_persona(
            "withfoot", personas_dir=self.personas, mixins_dir=self.mixins,
        )
        self.assertIn("## Main", out)
        self.assertIn("## Foot Section", out)
        # foot は main の後
        self.assertLess(out.find("## Main"), out.find("## Foot Section"))
        # mixin frontmatter は剥がれている
        self.assertNotIn("mixin: foot", out)

    def test_multiple_mixins_in_order(self) -> None:
        """複数 mixin は順序通り append される。"""
        self._write_mixin("a", "## A")
        self._write_mixin("b", "## B")
        self._write_mixin("c", "## C")
        self._write_persona_with_body(
            "multi", "## Main", mixins_str="[a, b, c]",
        )
        out = compose_persona(
            "multi", personas_dir=self.personas, mixins_dir=self.mixins,
        )
        a_pos = out.find("## A")
        b_pos = out.find("## B")
        c_pos = out.find("## C")
        self.assertGreater(a_pos, 0)
        self.assertGreater(b_pos, a_pos)
        self.assertGreater(c_pos, b_pos)

    def test_missing_mixin_raises(self) -> None:
        """mixin が見つからない → PersonaError (= silent fail せず spawn を止める)。"""
        self._write_persona_with_body(
            "bad", "## Main", mixins_str="[nonexistent]",
        )
        with self.assertRaises(PersonaError) as ctx:
            compose_persona(
                "bad", personas_dir=self.personas, mixins_dir=self.mixins,
            )
        self.assertIn("unknown mixin", str(ctx.exception))

    def test_persona_not_found_raises(self) -> None:
        with self.assertRaises(PersonaError):
            compose_persona(
                "ghost", personas_dir=self.personas, mixins_dir=self.mixins,
            )

    def test_mixin_without_frontmatter(self) -> None:
        """mixin に frontmatter が無くても body は append される。"""
        self._write_mixin("nofm", "## NoFm\nbody", with_frontmatter=False)
        self._write_persona_with_body("withnofm", "## Main", mixins_str="[nofm]")
        out = compose_persona(
            "withnofm", personas_dir=self.personas, mixins_dir=self.mixins,
        )
        self.assertIn("## NoFm", out)

    def test_empty_mixins_list(self) -> None:
        """mixins: [] (空 list) → 本文そのまま。"""
        self._write_persona_with_body("empty", "## Main", mixins_str="[]")
        out = compose_persona(
            "empty", personas_dir=self.personas, mixins_dir=self.mixins,
        )
        self.assertIn("## Main", out)


class TestComposeCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.personas_dir = Path(self._tmp.name) / "personas"
        self.mixins_dir = Path(self._tmp.name) / "mixins"
        # 既存 fixture を再利用
        _write_persona(self.personas_dir, "demo")
        import os
        self._old_p = os.environ.get("AI_ORG_OS_PERSONAS_DIR")
        self._old_m = os.environ.get("AI_ORG_OS_PERSONA_MIXINS_DIR")
        os.environ["AI_ORG_OS_PERSONAS_DIR"] = str(self.personas_dir)
        os.environ["AI_ORG_OS_PERSONA_MIXINS_DIR"] = str(self.mixins_dir)

    def tearDown(self) -> None:
        import os
        if self._old_p is None:
            os.environ.pop("AI_ORG_OS_PERSONAS_DIR", None)
        else:
            os.environ["AI_ORG_OS_PERSONAS_DIR"] = self._old_p
        if self._old_m is None:
            os.environ.pop("AI_ORG_OS_PERSONA_MIXINS_DIR", None)
        else:
            os.environ["AI_ORG_OS_PERSONA_MIXINS_DIR"] = self._old_m
        self._tmp.cleanup()

    def test_compose_cli_ok(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["persona.py", "compose", "demo"])
        self.assertEqual(rc, 0)
        self.assertIn("persona: demo", out.getvalue())

    def test_compose_cli_missing_persona(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["persona.py", "compose", "ghost"])
        self.assertEqual(rc, 1)
        self.assertIn("not registered", err.getvalue())


if __name__ == "__main__":
    unittest.main()
