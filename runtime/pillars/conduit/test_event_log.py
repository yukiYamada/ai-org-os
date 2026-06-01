"""
Unit tests for event_log.write_event (ADR-0026 §3 / §5)。

Standard library only (unittest, tempfile, json, re).

Run:
  python -m unittest discover runtime/pillars/conduit -p 'test_*.py'
  cd runtime/pillars/conduit && python -m unittest test_event_log
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from event_log import write_event, _iso_ms_z, _default_logs_dir  # noqa: E402


class TestIsoMsZ(unittest.TestCase):
    def test_format_shape(self) -> None:
        """'YYYY-MM-DDTHH:MM:SS.mmmZ' を満たす。"""
        ts = _iso_ms_z()
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class TestWriteEvent(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.log_path = self.tmp_dir / "test.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_lines(self) -> list[dict]:
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line]

    def test_envelope_shape(self) -> None:
        write_event(self.log_path, event="dispatch.sent", actor="conduit", msg_id="m1")
        rows = self._read_lines()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["event"], "dispatch.sent")
        self.assertEqual(row["actor"], "conduit")
        self.assertEqual(row["msg_id"], "m1")
        self.assertRegex(row["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

    def test_from_kwarg_supported(self) -> None:
        """`from` は Python 予約語 → **{"from": ...} で渡せること。"""
        write_event(
            self.log_path,
            event="dispatch.sent",
            actor="conduit",
            **{"from": "warden"},
            to="alice",
        )
        rows = self._read_lines()
        self.assertEqual(rows[0]["from"], "warden")
        self.assertEqual(rows[0]["to"], "alice")

    def test_append_semantics(self) -> None:
        """複数回呼び出しで append、過去 line を上書きしない。"""
        write_event(self.log_path, event="dispatch.sent", actor="conduit", n=1)
        write_event(self.log_path, event="dispatch.acked", actor="conduit", n=2)
        write_event(self.log_path, event="dispatch.sent", actor="conduit", n=3)
        rows = self._read_lines()
        self.assertEqual([r["n"] for r in rows], [1, 2, 3])
        self.assertEqual(
            [r["event"] for r in rows],
            ["dispatch.sent", "dispatch.acked", "dispatch.sent"],
        )

    def test_creates_parent_dirs(self) -> None:
        nested = self.tmp_dir / "a" / "b" / "c.jsonl"
        write_event(nested, event="dispatch.sent", actor="conduit")
        self.assertTrue(nested.exists())

    def test_non_ascii_body_preserved(self) -> None:
        """ensure_ascii=False で日本語が \\uXXXX 化されないこと。"""
        write_event(
            self.log_path, event="dispatch.sent", actor="conduit", topic="日本語"
        )
        # 生のテキストとして「日本語」が含まれる
        raw = self.log_path.read_text(encoding="utf-8")
        self.assertIn("日本語", raw)

    def test_write_failure_does_not_raise(self) -> None:
        """書き込み不可な path を渡しても例外は伝播せず stderr WARN のみ (F3 / ADR-0013 §1)。

        log_path をディレクトリ自身に向けて衝突させる。
        """
        dir_as_path = self.tmp_dir / "is_a_dir"
        dir_as_path.mkdir()
        buf = io.StringIO()
        with redirect_stderr(buf):
            # raise しないこと自体が assertion
            write_event(dir_as_path, event="dispatch.sent", actor="conduit")
        self.assertIn("event_log", buf.getvalue())
        self.assertIn("WARN", buf.getvalue())

    def test_encode_failure_does_not_raise(self) -> None:
        """JSON encode 不可な field でも例外は raise しない。"""

        class NotSerializable:
            pass

        buf = io.StringIO()
        with redirect_stderr(buf):
            write_event(
                self.log_path,
                event="dispatch.sent",
                actor="conduit",
                bad=NotSerializable(),
            )
        self.assertIn("WARN", buf.getvalue())
        # ファイルは作られない (or 空)
        if self.log_path.exists():
            self.assertEqual(self.log_path.read_text(encoding="utf-8"), "")

    def test_single_line_per_event(self) -> None:
        """1 event = 1 行。改行が body 等に混入しても JSON encode で \\n になる。"""
        write_event(
            self.log_path,
            event="dispatch.sent",
            actor="conduit",
            note="line1\nline2",
        )
        text = self.log_path.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n"), 1)  # 行末改行のみ
        row = json.loads(text)
        self.assertEqual(row["note"], "line1\nline2")


class TestDefaultLogsDir(unittest.TestCase):
    """ADR-0018 / ADR-0026 §1: AI_ORG_OS_HOME 配下 logs/ に解決する。"""

    def test_env_override(self) -> None:
        import os

        original = os.environ.get("AI_ORG_OS_HOME")
        try:
            os.environ["AI_ORG_OS_HOME"] = "/some/path"
            self.assertEqual(_default_logs_dir(), Path("/some/path") / "logs")
        finally:
            if original is None:
                os.environ.pop("AI_ORG_OS_HOME", None)
            else:
                os.environ["AI_ORG_OS_HOME"] = original


if __name__ == "__main__":
    unittest.main()
