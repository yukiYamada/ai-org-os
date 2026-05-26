"""
test_resource_usage.py — resource_usage.py のユニットテスト (#66)。

検証する性質:
- _scan_dir_size: 単純な集計、再帰、空 dir
- per_mind_usage: minds/ 配下のみ走査、不正名 / symlink dir の skip
- conduit_storage_usage: inbox + archive 合算
- symlink ファイルが集計に入らない
- OSError ハンドリング (個別 file の stat 失敗で走査全体は止めない)
- _human_bytes の単位境界

標準ライブラリのみ。
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import resource_usage as ru  # noqa: E402


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestScanDirSize(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _silent(self, *a, **kw) -> tuple[int, int]:
        with redirect_stderr(io.StringIO()):
            return ru._scan_dir_size(*a, **kw)

    def test_empty_dir(self) -> None:
        d = self.root / "empty"
        d.mkdir()
        self.assertEqual(self._silent(d), (0, 0))

    def test_nonexistent_dir(self) -> None:
        self.assertEqual(self._silent(self.root / "missing"), (0, 0))

    def test_flat_files(self) -> None:
        _write(self.root / "a.txt", b"hello")  # 5
        _write(self.root / "b.txt", b"world!")  # 6
        self.assertEqual(self._silent(self.root), (2, 11))

    def test_nested_recursion(self) -> None:
        _write(self.root / "a.txt", b"x" * 10)
        _write(self.root / "sub" / "b.txt", b"y" * 20)
        _write(self.root / "sub" / "deep" / "c.txt", b"z" * 30)
        files, total = self._silent(self.root)
        self.assertEqual(files, 3)
        self.assertEqual(total, 60)

    def test_symlink_file_not_counted(self) -> None:
        _write(self.root / "real.txt", b"abc")
        link = self.root / "link.txt"
        try:
            os.symlink(self.root / "real.txt", link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not supported")
        files, total = self._silent(self.root)
        # real.txt 1 件のみ、link.txt は集計に入らない
        self.assertEqual(files, 1)
        self.assertEqual(total, 3)

    def test_symlink_dir_not_traversed(self) -> None:
        _write(self.root / "real" / "a.txt", b"hello")
        link = self.root / "link"
        try:
            os.symlink(self.root / "real", link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not supported")
        files, total = self._silent(self.root)
        # real 経由で 1 件、link 経由は無視
        self.assertEqual(files, 1)
        self.assertEqual(total, 5)


class TestPerMindUsage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.minds = self.home / "minds"
        self.minds.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _silent(self) -> list[ru.UsageBucket]:
        with redirect_stderr(io.StringIO()):
            return ru.per_mind_usage(self.home)

    def test_empty_minds_dir(self) -> None:
        self.assertEqual(self._silent(), [])

    def test_minds_root_missing(self) -> None:
        # minds/ が無いと空リスト
        empty_home = Path(tempfile.mkdtemp())
        try:
            with redirect_stderr(io.StringIO()):
                out = ru.per_mind_usage(empty_home)
            self.assertEqual(out, [])
        finally:
            import shutil  # noqa: PLC0415
            shutil.rmtree(empty_home, ignore_errors=True)

    def test_two_minds(self) -> None:
        _write(self.minds / "alice" / "CLAUDE.md", b"a" * 100)
        _write(self.minds / "alice" / ".mind-meta.md", b"m" * 50)
        _write(self.minds / "bob" / "CLAUDE.md", b"b" * 200)
        buckets = self._silent()
        self.assertEqual(len(buckets), 2)
        names = {b.name for b in buckets}
        self.assertEqual(names, {"alice", "bob"})
        by_name = {b.name: b for b in buckets}
        self.assertEqual(by_name["alice"].file_count, 2)
        self.assertEqual(by_name["alice"].byte_count, 150)
        self.assertEqual(by_name["alice"].category, "mindspace")
        self.assertEqual(by_name["bob"].file_count, 1)
        self.assertEqual(by_name["bob"].byte_count, 200)

    def test_skips_malformed_mind_dir_name(self) -> None:
        _write(self.minds / "alice" / "x", b"ok")
        bad = self.minds / "has space"
        bad.mkdir()
        _write(bad / "x", b"bad")
        buckets = self._silent()
        # 'has space' は skip、alice のみ
        self.assertEqual([b.name for b in buckets], ["alice"])

    def test_skips_symlinked_mind_dir(self) -> None:
        _write(self.minds / "alice" / "x", b"ok")
        link = self.minds / "alice-link"
        try:
            os.symlink(self.minds / "alice", link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not supported")
        buckets = self._silent()
        self.assertEqual([b.name for b in buckets], ["alice"])


class TestConduitStorageUsage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _silent(self) -> ru.UsageBucket:
        with redirect_stderr(io.StringIO()):
            return ru.conduit_storage_usage(self.home)

    def test_no_storage_dir(self) -> None:
        b = self._silent()
        self.assertEqual(b.file_count, 0)
        self.assertEqual(b.byte_count, 0)
        self.assertEqual(b.category, "conduit-storage")
        self.assertEqual(b.name, "conduit-storage")

    def test_inbox_and_archive_combined(self) -> None:
        storage = self.home / "conduit-storage"
        _write(storage / "inbox" / "bob" / "m1.md", b"x" * 100)
        _write(storage / "archive" / "bob" / "m2.md", b"y" * 50)
        b = self._silent()
        self.assertEqual(b.file_count, 2)
        self.assertEqual(b.byte_count, 150)


class TestAllUsageFormatting(unittest.TestCase):
    def test_all_usage_returns_minds_then_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write(home / "minds" / "alice" / "x", b"abc")
            _write(home / "conduit-storage" / "inbox" / "bob" / "m.md", b"yz")
            with redirect_stderr(io.StringIO()):
                out = ru.all_usage(home)
            self.assertEqual([b.name for b in out], ["alice", "conduit-storage"])
            self.assertEqual([b.category for b in out],
                             ["mindspace", "conduit-storage"])

    def test_format_usage_table_empty(self) -> None:
        self.assertEqual(ru.format_usage_table([]), "(no resources)")

    def test_format_usage_table_has_columns(self) -> None:
        buckets = [
            ru.UsageBucket("alice", "mindspace", 2, 150),
            ru.UsageBucket("conduit-storage", "conduit-storage", 5, 1024),
        ]
        text = ru.format_usage_table(buckets)
        self.assertIn("category", text)
        self.assertIn("alice", text)
        self.assertIn("150", text)
        self.assertIn("1024", text)
        self.assertIn("1.0KiB", text)

    def test_human_bytes_units(self) -> None:
        self.assertEqual(ru._human_bytes(0), "0B")
        self.assertEqual(ru._human_bytes(1023), "1023B")
        self.assertEqual(ru._human_bytes(1024), "1.0KiB")
        self.assertEqual(ru._human_bytes(1024 * 1024), "1.0MiB")
        self.assertEqual(ru._human_bytes(1024 ** 3), "1.0GiB")


if __name__ == "__main__":
    unittest.main()
