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
    PersonaInfo,
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


if __name__ == "__main__":
    unittest.main()
