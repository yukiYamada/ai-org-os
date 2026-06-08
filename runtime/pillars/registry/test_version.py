"""Phase 5g.A #170: version.py の unit test。

検証対象:
- Version parse (SemVer の triple、partial も受理)
- Constraint parse (`>=`, `>`, `<=`, `<`, `==`、カンマ AND)
- check_framework_version / warn_if_mismatch (= validator から呼ばれる API)
- CLI (print / check)
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

from version import (  # noqa: E402
    Constraint,
    Version,
    VersionCheck,
    VersionError,
    check_framework_version,
    main,
    parse_constraint,
    parse_version,
    read_framework_version,
    warn_if_mismatch,
)


class TestParseVersion(unittest.TestCase):
    def test_full_triple(self) -> None:
        self.assertEqual(parse_version("1.2.3"), Version(1, 2, 3))

    def test_partial_pads_patch(self) -> None:
        self.assertEqual(parse_version("1.2"), Version(1, 2, 0))

    def test_zero(self) -> None:
        self.assertEqual(parse_version("0.0.0"), Version(0, 0, 0))

    def test_large_numbers(self) -> None:
        self.assertEqual(parse_version("100.200.300"), Version(100, 200, 300))

    def test_invalid_letters(self) -> None:
        with self.assertRaises(VersionError):
            parse_version("1.0.x")

    def test_invalid_dash(self) -> None:
        with self.assertRaises(VersionError):
            parse_version("1.0-rc1")

    def test_empty_raises(self) -> None:
        with self.assertRaises(VersionError):
            parse_version("")

    def test_str_roundtrip(self) -> None:
        self.assertEqual(str(Version(1, 2, 3)), "1.2.3")


class TestVersionOrdering(unittest.TestCase):
    """Version の比較演算子が major / minor / patch の辞書順で動くこと。"""

    def test_lt(self) -> None:
        self.assertLess(Version(1, 0, 0), Version(1, 0, 1))
        self.assertLess(Version(1, 0, 9), Version(1, 1, 0))
        self.assertLess(Version(1, 99, 99), Version(2, 0, 0))

    def test_eq(self) -> None:
        self.assertEqual(Version(1, 2, 3), Version(1, 2, 3))

    def test_gt(self) -> None:
        self.assertGreater(Version(2, 0, 0), Version(1, 99, 99))


class TestParseConstraint(unittest.TestCase):
    def test_empty_is_universal(self) -> None:
        c = parse_constraint("")
        self.assertEqual(c.bounds, ())

    def test_star_is_universal(self) -> None:
        c = parse_constraint("*")
        self.assertEqual(c.bounds, ())

    def test_ge(self) -> None:
        c = parse_constraint(">=1.0")
        self.assertTrue(c.satisfies(Version(1, 0, 0)))
        self.assertTrue(c.satisfies(Version(1, 0, 1)))
        self.assertTrue(c.satisfies(Version(2, 5, 9)))
        self.assertFalse(c.satisfies(Version(0, 9, 99)))

    def test_gt(self) -> None:
        c = parse_constraint(">1.0")
        self.assertFalse(c.satisfies(Version(1, 0, 0)))
        self.assertTrue(c.satisfies(Version(1, 0, 1)))

    def test_le(self) -> None:
        c = parse_constraint("<=1.5.0")
        self.assertTrue(c.satisfies(Version(1, 5, 0)))
        self.assertTrue(c.satisfies(Version(1, 4, 99)))
        self.assertFalse(c.satisfies(Version(1, 5, 1)))

    def test_lt(self) -> None:
        c = parse_constraint("<2.0")
        self.assertTrue(c.satisfies(Version(1, 99, 99)))
        self.assertFalse(c.satisfies(Version(2, 0, 0)))

    def test_eq(self) -> None:
        c = parse_constraint("==1.0.0")
        self.assertTrue(c.satisfies(Version(1, 0, 0)))
        self.assertFalse(c.satisfies(Version(1, 0, 1)))

    def test_and_range(self) -> None:
        c = parse_constraint(">=1.0,<2.0")
        self.assertTrue(c.satisfies(Version(1, 0, 0)))
        self.assertTrue(c.satisfies(Version(1, 99, 99)))
        self.assertFalse(c.satisfies(Version(2, 0, 0)))
        self.assertFalse(c.satisfies(Version(0, 9, 99)))

    def test_invalid_op_raises(self) -> None:
        with self.assertRaises(VersionError):
            parse_constraint("~=1.0")

    def test_invalid_clause_raises(self) -> None:
        with self.assertRaises(VersionError):
            parse_constraint("bogus")

    def test_str(self) -> None:
        c = parse_constraint(">=1.0,<2.0")
        # `1.0` → `1.0.0` の正規化を経て str に
        self.assertEqual(str(c), ">=1.0.0,<2.0.0")

    def test_empty_clause_in_list_ignored(self) -> None:
        # ",>=1.0," のような末尾カンマも許容
        c = parse_constraint(">=1.0,")
        self.assertEqual(len(c.bounds), 1)


class TestReadFrameworkVersion(unittest.TestCase):
    def test_reads_real_version_file(self) -> None:
        v = read_framework_version()
        # 現 repo の VERSION が parse 可能であること (= 健全性)
        self.assertGreaterEqual(v, Version(1, 0, 0))

    def test_reads_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "VERSION"
            p.write_text("2.5.3\n", encoding="utf-8")
            v = read_framework_version(version_file=p)
            self.assertEqual(v, Version(2, 5, 3))

    def test_missing_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nonexistent"
            with self.assertRaises(VersionError):
                read_framework_version(version_file=p)

    def test_empty_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "VERSION"
            p.write_text("", encoding="utf-8")
            with self.assertRaises(VersionError):
                read_framework_version(version_file=p)

    def test_garbage_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "VERSION"
            p.write_text("not-a-version\n", encoding="utf-8")
            with self.assertRaises(VersionError):
                read_framework_version(version_file=p)


class TestCheckFrameworkVersion(unittest.TestCase):
    def test_empty_constraint_ok(self) -> None:
        result = check_framework_version(
            "", runtime_version=Version(1, 0, 0),
        )
        self.assertTrue(result.ok)

    def test_satisfied(self) -> None:
        result = check_framework_version(
            ">=1.0", runtime_version=Version(1, 5, 0),
        )
        self.assertTrue(result.ok)
        self.assertIn("satisfies", result.detail)

    def test_not_satisfied(self) -> None:
        result = check_framework_version(
            ">=2.0", runtime_version=Version(1, 0, 0),
        )
        self.assertFalse(result.ok)
        self.assertIn("does NOT satisfy", result.detail)

    def test_invalid_constraint_not_ok(self) -> None:
        result = check_framework_version(
            "bogus", runtime_version=Version(1, 0, 0),
        )
        self.assertFalse(result.ok)
        self.assertIn("invalid constraint", result.detail)


class TestWarnIfMismatch(unittest.TestCase):
    def test_no_warn_for_empty(self) -> None:
        buf = StringIO()
        result = warn_if_mismatch(
            "", source_label="kind:test",
            stream=buf, runtime_version=Version(1, 0, 0),
        )
        self.assertTrue(result.ok)
        self.assertEqual(buf.getvalue(), "")

    def test_no_warn_when_satisfied(self) -> None:
        buf = StringIO()
        result = warn_if_mismatch(
            ">=1.0", source_label="kind:test",
            stream=buf, runtime_version=Version(1, 0, 0),
        )
        self.assertTrue(result.ok)
        self.assertEqual(buf.getvalue(), "")

    def test_warn_when_mismatch(self) -> None:
        buf = StringIO()
        result = warn_if_mismatch(
            ">=2.0", source_label="kind:test",
            stream=buf, runtime_version=Version(1, 0, 0),
        )
        self.assertFalse(result.ok)
        self.assertIn("[WARN]", buf.getvalue())
        self.assertIn("kind:test", buf.getvalue())
        self.assertIn(">=2.0", buf.getvalue())

    def test_warn_when_invalid_constraint(self) -> None:
        buf = StringIO()
        result = warn_if_mismatch(
            "bogus", source_label="guild:test",
            stream=buf, runtime_version=Version(1, 0, 0),
        )
        self.assertFalse(result.ok)
        self.assertIn("[WARN]", buf.getvalue())
        self.assertIn("invalid constraint", buf.getvalue())


class TestCli(unittest.TestCase):
    def test_print_text(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["version.py", "print"])
        self.assertEqual(rc, 0)
        # 形式は "X.Y.Z"
        printed = out.getvalue().strip()
        v = parse_version(printed)
        self.assertIsInstance(v, Version)

    def test_print_json(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["version.py", "print", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("framework_version", payload)
        parse_version(payload["framework_version"])  # parsable

    def test_check_ok(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = main(["version.py", "check", ">=1.0"])
        self.assertEqual(rc, 0)
        self.assertIn("ok", out.getvalue())

    def test_check_mismatch(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["version.py", "check", ">=99.0"])
        self.assertEqual(rc, 1)
        self.assertIn("mismatch", err.getvalue())

    def test_check_invalid_constraint(self) -> None:
        with patch("sys.stderr", new_callable=StringIO):
            rc = main(["version.py", "check", "bogus"])
        # invalid constraint → mismatch (= ok=False) → exit 1
        self.assertEqual(rc, 1)

    def test_check_missing_arg(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["version.py", "check"])
        self.assertEqual(rc, 2)
        self.assertIn("requires", err.getvalue())

    def test_unknown_command(self) -> None:
        with patch("sys.stderr", new_callable=StringIO) as err:
            rc = main(["version.py", "magic"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown command", err.getvalue())

    def test_no_args(self) -> None:
        with patch("sys.stderr", new_callable=StringIO):
            rc = main(["version.py"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
