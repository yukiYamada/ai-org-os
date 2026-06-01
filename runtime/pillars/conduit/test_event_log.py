"""
Unit tests for event_log.write_event (ADR-0026 §3 / §5 / §6)。

Standard library only (unittest, tempfile, json, re, os).

Run:
  python -m unittest discover runtime/pillars/conduit -p 'test_*.py'
  cd runtime/pillars/conduit && python -m unittest test_event_log
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

from event_log import (  # noqa: E402
    write_event,
    _iso_ms_z,
    _default_logs_dir,
    _rotate_if_needed,
)


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


class TestRotation(unittest.TestCase):
    """ADR-0026 §6 / Issue #135: size-based rotation。

    - 閾値超過時に `<name>.jsonl` → `.1` → `.2` → ... → `.N` に shift
    - 環境変数 `AI_ORG_OS_LOG_MAX_BYTES` / `AI_ORG_OS_LOG_RETAIN` で上書き可
    - rotation 失敗時も F3 準拠で append は続行
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.log_path = self.tmp_dir / "test.jsonl"
        # env スナップショット (test 毎に元に戻す)
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("AI_ORG_OS_LOG_MAX_BYTES", "AI_ORG_OS_LOG_RETAIN")
        }

    def tearDown(self) -> None:
        # env を元に戻す
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _suffixed(self, n: int) -> Path:
        return self.tmp_dir / f"test.jsonl.{n}"

    def test_threshold_triggers_rotation(self) -> None:
        """閾値以上に達したら rotation が走り、新 event は新規 file に着地。"""
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "100"
        # 100 bytes 以上のダミー content を put して閾値超過させる
        self.log_path.write_text("x" * 200, encoding="utf-8")
        self.assertGreaterEqual(self.log_path.stat().st_size, 100)

        write_event(self.log_path, event="dispatch.sent", actor="conduit", n=1)

        # rotation 後: .1 に旧 content、 base file には新 event 1 行のみ
        self.assertTrue(self._suffixed(1).exists())
        self.assertEqual(self._suffixed(1).read_text(encoding="utf-8"), "x" * 200)

        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["event"], "dispatch.sent")
        self.assertEqual(row["n"], 1)

    def test_below_threshold_no_rotation(self) -> None:
        """閾値未満なら rotation は起きず append のみ。"""
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "10000"
        write_event(self.log_path, event="dispatch.sent", actor="conduit", n=1)
        write_event(self.log_path, event="dispatch.sent", actor="conduit", n=2)

        self.assertFalse(self._suffixed(1).exists())
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)

    def test_existing_rotated_files_shift(self) -> None:
        """既存の .1, .2 が正しく shift される。"""
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "100"
        os.environ["AI_ORG_OS_LOG_RETAIN"] = "5"

        # 既存 state を仕込む
        self._suffixed(1).write_text("old-1", encoding="utf-8")
        self._suffixed(2).write_text("old-2", encoding="utf-8")
        self._suffixed(3).write_text("old-3", encoding="utf-8")
        self.log_path.write_text("y" * 200, encoding="utf-8")

        write_event(self.log_path, event="dispatch.sent", actor="conduit")

        # 期待: current → .1 / 旧 .1 → .2 / 旧 .2 → .3 / 旧 .3 → .4
        self.assertEqual(self._suffixed(1).read_text(encoding="utf-8"), "y" * 200)
        self.assertEqual(self._suffixed(2).read_text(encoding="utf-8"), "old-1")
        self.assertEqual(self._suffixed(3).read_text(encoding="utf-8"), "old-2")
        self.assertEqual(self._suffixed(4).read_text(encoding="utf-8"), "old-3")
        self.assertFalse(self._suffixed(5).exists())

        # base file には新 event のみ
        rows = [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], "dispatch.sent")

    def test_retain_limit_drops_oldest(self) -> None:
        """retain=N のとき、.N+1 に当たる最古は削除される。"""
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "100"
        os.environ["AI_ORG_OS_LOG_RETAIN"] = "3"

        # retain=3 想定で 1..3 を埋めておく (= .3 が最古 → 次の rotation で消える)
        self._suffixed(1).write_text("old-1", encoding="utf-8")
        self._suffixed(2).write_text("old-2", encoding="utf-8")
        self._suffixed(3).write_text("old-3-OLDEST", encoding="utf-8")
        self.log_path.write_text("z" * 200, encoding="utf-8")

        write_event(self.log_path, event="dispatch.sent", actor="conduit")

        # 期待: .3 (OLDEST) は削除、.1→.2, .2→.3, current→.1
        self.assertEqual(self._suffixed(1).read_text(encoding="utf-8"), "z" * 200)
        self.assertEqual(self._suffixed(2).read_text(encoding="utf-8"), "old-1")
        self.assertEqual(self._suffixed(3).read_text(encoding="utf-8"), "old-2")
        # .4 は無いまま
        self.assertFalse(self._suffixed(4).exists())

    def test_env_override_triggers_early_rotation(self) -> None:
        """AI_ORG_OS_LOG_MAX_BYTES=100 で早期 rotation。"""
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "100"

        # default 10MB なら絶対 rotate しない量を、100 bytes 設定で trip させる
        for i in range(5):
            write_event(
                self.log_path,
                event="dispatch.sent",
                actor="conduit",
                payload="A" * 60,  # 1 line ≒ 100+ bytes
                n=i,
            )

        # .1 が生成されていれば rotation が走った証拠
        self.assertTrue(self._suffixed(1).exists())

    def test_rotation_failure_still_appends(self) -> None:
        """rotation が失敗しても新 event の append は試みる (F3)。

        `log_path.replace(...)` が OSError を投げる状況をモックで作る。
        """
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "100"
        self.log_path.write_text("x" * 200, encoding="utf-8")

        original_replace = Path.replace

        def boom_replace(self_path: Path, target):  # type: ignore[no-untyped-def]
            # current → .1 の段で必ず失敗させる
            raise OSError("simulated rename failure")

        buf = io.StringIO()
        with redirect_stderr(buf):
            with mock.patch.object(Path, "replace", boom_replace):
                write_event(
                    self.log_path,
                    event="dispatch.sent",
                    actor="conduit",
                    note="after-failure",
                )

        # WARN が出ている
        stderr = buf.getvalue()
        self.assertIn("WARN", stderr)
        self.assertIn("rotation failed", stderr)

        # base file に新 event がちゃんと追記されている (= rotation 失敗でも append 続行)
        text = self.log_path.read_text(encoding="utf-8")
        self.assertIn("after-failure", text)
        # 旧 content (x*200) も残っている (rotation は走らず append された結果)
        self.assertTrue(text.startswith("x" * 200))

        # restore (mock.patch のスコープ外でも念のため)
        Path.replace = original_replace  # type: ignore[method-assign]

    def test_rotate_if_needed_noop_when_file_missing(self) -> None:
        """log_path が存在しない場合は rotation 関数は no-op。"""
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "100"
        # ファイル無し
        self.assertFalse(self.log_path.exists())
        # raise しないこと
        _rotate_if_needed(self.log_path)
        # 何も作られていない
        self.assertFalse(self._suffixed(1).exists())

    def test_invalid_env_falls_back_to_default(self) -> None:
        """env が int parse 不能 / 非正値なら default にフォールバック (= 10MB)。"""
        os.environ["AI_ORG_OS_LOG_MAX_BYTES"] = "not-a-number"
        # 200 bytes の current file。default 10MB 閾値なら rotation は起きない
        self.log_path.write_text("x" * 200, encoding="utf-8")
        write_event(self.log_path, event="dispatch.sent", actor="conduit")
        # rotation は起きていない
        self.assertFalse(self._suffixed(1).exists())


if __name__ == "__main__":
    unittest.main()
