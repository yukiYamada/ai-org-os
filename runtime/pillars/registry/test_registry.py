"""
Unit tests for the Registry Pillar.

Standard library only (unittest + tempfile). Each test fabricates a temporary
`kinds_dir` to keep the suite independent from the real runtime/kinds/.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from registry import (  # noqa: E402
    KindInfo,
    _parse_frontmatter,
    get_kind,
    is_registered,
    list_kinds,
)


def _write_kind(dir_path: Path, name: str, *, version: str = "0.1",
                status: str = "experimental", body: str = "body") -> Path:
    """Helper: write a minimal Kind .md file with frontmatter."""
    path = dir_path / f"{name}.md"
    path.write_text(
        f"---\nkind: {name}\nversion: {version}\nstatus: {status}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


class TestParseFrontmatter(unittest.TestCase):
    def test_basic(self) -> None:
        text = "---\nkind: generic\nversion: 0.1\nstatus: experimental\n---\nbody"
        self.assertEqual(
            _parse_frontmatter(text),
            {"kind": "generic", "version": "0.1", "status": "experimental"},
        )

    def test_no_frontmatter(self) -> None:
        self.assertEqual(_parse_frontmatter("# heading\nbody only\n"), {})

    def test_unterminated_frontmatter(self) -> None:
        # 閉じ `---` が無い場合は保守的に空 dict
        text = "---\nkind: generic\nversion: 0.1\n# no closing fence"
        self.assertEqual(_parse_frontmatter(text), {})

    def test_empty_file(self) -> None:
        self.assertEqual(_parse_frontmatter(""), {})

    def test_skips_comments_and_blank_lines(self) -> None:
        text = "---\n# a comment\n\nkind: foo\n\nversion: 1.0\n---\n"
        self.assertEqual(_parse_frontmatter(text), {"kind": "foo", "version": "1.0"})

    def test_handles_value_with_colon(self) -> None:
        # split(":", 1) で 1 回しか分割しないので value 中の : は保持される
        text = "---\nkind: foo\nnote: a:b:c\n---\n"
        self.assertEqual(
            _parse_frontmatter(text),
            {"kind": "foo", "note": "a:b:c"},
        )


class TestListKinds(unittest.TestCase):
    def test_returns_empty_for_missing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nonexistent"
            self.assertEqual(list_kinds(missing), [])

    def test_returns_empty_for_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(list_kinds(Path(td)), [])

    def test_lists_single_kind(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "generic")
            kinds = list_kinds(td_path)
            self.assertEqual(len(kinds), 1)
            k = kinds[0]
            self.assertEqual(k.name, "generic")
            self.assertEqual(k.version, "0.1")
            self.assertEqual(k.status, "experimental")
            self.assertEqual(k.path, td_path / "generic.md")

    def test_lists_multiple_kinds_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "zebra")
            _write_kind(td_path, "alpha")
            _write_kind(td_path, "middle")
            kinds = list_kinds(td_path)
            self.assertEqual([k.name for k in kinds], ["alpha", "middle", "zebra"])

    def test_skips_non_md_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "generic")
            (td_path / "README.txt").write_text("readme", encoding="utf-8")
            (td_path / "notes.json").write_text("{}", encoding="utf-8")
            kinds = list_kinds(td_path)
            self.assertEqual([k.name for k in kinds], ["generic"])

    def test_skips_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "generic")
            (td_path / "subdir").mkdir()
            (td_path / "subdir" / "nested.md").write_text(
                "---\nkind: nested\n---\n", encoding="utf-8"
            )
            kinds = list_kinds(td_path)
            self.assertEqual([k.name for k in kinds], ["generic"])

    def test_skips_files_without_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "good")
            (td_path / "bad.md").write_text("# no frontmatter here\n", encoding="utf-8")
            kinds = list_kinds(td_path)
            self.assertEqual([k.name for k in kinds], ["good"])

    def test_idempotent(self) -> None:
        # 同じディレクトリを 2 回叩いても完全に同じ結果（順序含む）。
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "a")
            _write_kind(td_path, "b")
            first = list_kinds(td_path)
            second = list_kinds(td_path)
            self.assertEqual(first, second)

    def test_missing_optional_keys_get_question_mark(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            (td_path / "minimal.md").write_text(
                "---\nkind: minimal\n---\nbody", encoding="utf-8"
            )
            kinds = list_kinds(td_path)
            self.assertEqual(len(kinds), 1)
            self.assertEqual(kinds[0].version, "?")
            self.assertEqual(kinds[0].status, "?")


class TestGetKind(unittest.TestCase):
    def test_returns_kind_info(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "generic")
            info = get_kind("generic", kinds_dir=td_path)
            self.assertIsNotNone(info)
            assert info is not None  # mypy / type checker hint
            self.assertEqual(info.name, "generic")

    def test_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(get_kind("nonexistent", kinds_dir=Path(td)))

    def test_rejects_path_traversal_dotdot(self) -> None:
        # `../etc` のような名前は不正として None を返す（攻撃の足がかりにしない）
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(get_kind("../etc", kinds_dir=Path(td)))

    def test_rejects_path_traversal_slash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(get_kind("foo/bar", kinds_dir=Path(td)))

    def test_rejects_path_traversal_backslash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(get_kind("foo\\bar", kinds_dir=Path(td)))

    def test_rejects_empty_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(get_kind("", kinds_dir=Path(td)))

    def test_rejects_too_long_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # 65 文字（_VALID_NAME_RE の上限 64 を 1 文字超える）
            long_name = "a" * 65
            self.assertIsNone(get_kind(long_name, kinds_dir=Path(td)))

    def test_accepts_boundary_64_chars(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            name = "a" * 64
            _write_kind(td_path, name)
            info = get_kind(name, kinds_dir=td_path)
            self.assertIsNotNone(info)


class TestIsRegistered(unittest.TestCase):
    def test_true_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            _write_kind(td_path, "generic")
            self.assertTrue(is_registered("generic", kinds_dir=td_path))

    def test_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(is_registered("nonexistent", kinds_dir=Path(td)))

    def test_false_for_invalid_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(is_registered("../etc", kinds_dir=Path(td)))


class TestRealRuntimeKinds(unittest.TestCase):
    """Sanity check against the actual runtime/kinds/ directory.

    spawn-mind.sh と Registry の判定ロジックが食い違わないことの確認も兼ねる。
    """

    def test_default_kinds_dir_has_generic(self) -> None:
        # CI でも開発環境でも runtime/kinds/generic.md は必ず存在する想定。
        kinds = list_kinds()
        names = [k.name for k in kinds]
        self.assertIn("generic", names, f"expected 'generic' in {names}")

    def test_get_generic_returns_info(self) -> None:
        info = get_kind("generic")
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.name, "generic")

    def test_is_registered_matches_spawn_mind_check(self) -> None:
        # spawn-mind.sh: `if [ ! -f "${KIND_FILE}" ]; then ... exit 2`
        # Registry: is_registered() が同じ判定を返すこと。
        self.assertTrue(is_registered("generic"))
        self.assertFalse(is_registered("definitely-not-a-real-kind"))


class TestOSErrorHandling(unittest.TestCase):
    def test_unreadable_file_is_skipped(self) -> None:
        # POSIX のみ chmod が効くので非 Windows でのみ実施。
        if os.name != "posix":
            self.skipTest("chmod-based unreadable file simulation requires POSIX")
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            good = _write_kind(td_path, "good")
            bad = _write_kind(td_path, "bad")
            # bad.md を読めなくする
            os.chmod(bad, 0)
            try:
                # root だと chmod を無視するので、root の時はスキップ
                if os.geteuid() == 0:
                    self.skipTest("running as root bypasses chmod, skip")
                kinds = list_kinds(td_path)
                # good は読めて、bad は warning ログ + skip
                self.assertIn("good", [k.name for k in kinds])
                # bad は OSError で skip されているので含まれない
                self.assertNotIn("bad", [k.name for k in kinds])
            finally:
                # cleanup できるように戻す
                os.chmod(bad, stat.S_IRUSR | stat.S_IWUSR)
                self.assertEqual(good, td_path / "good.md")  # smoke: path 整合


if __name__ == "__main__":
    unittest.main()
