"""
Unit tests for trace.py (ADR-0026 §7)。

stdlib のみ (unittest, tempfile, io, json, datetime)。
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trace import (  # noqa: E402
    cmd_trace,
    format_event,
    iter_event_files,
    iter_events,
    parse_since,
)


class TestParseSince(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_none_returns_none(self) -> None:
        self.assertIsNone(parse_since(None, now=self.now))
        self.assertIsNone(parse_since("", now=self.now))

    def test_relative_seconds(self) -> None:
        self.assertEqual(
            parse_since("10s", now=self.now), "2026-06-01T11:59:50.000Z"
        )

    def test_relative_minutes(self) -> None:
        self.assertEqual(
            parse_since("30m", now=self.now), "2026-06-01T11:30:00.000Z"
        )

    def test_relative_hours(self) -> None:
        self.assertEqual(
            parse_since("2h", now=self.now), "2026-06-01T10:00:00.000Z"
        )

    def test_relative_days(self) -> None:
        self.assertEqual(
            parse_since("1d", now=self.now), "2026-05-31T12:00:00.000Z"
        )

    def test_absolute_z_suffix(self) -> None:
        self.assertEqual(
            parse_since("2026-06-01T00:00:00Z"), "2026-06-01T00:00:00.000Z"
        )

    def test_absolute_naive_treated_as_utc(self) -> None:
        self.assertEqual(
            parse_since("2026-06-01T00:00:00"), "2026-06-01T00:00:00.000Z"
        )

    def test_absolute_with_offset(self) -> None:
        # +09:00 → UTC で 21:00 前日
        self.assertEqual(
            parse_since("2026-06-01T00:00:00+09:00"),
            "2026-05-31T15:00:00.000Z",
        )

    def test_malformed_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_since("not-a-timestamp")
        with self.assertRaises(ValueError):
            parse_since("1y")  # year は未サポート


class TestIterEventFiles(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name) / "logs"
        self.logs.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_dir_returns_empty(self) -> None:
        self.assertEqual(iter_event_files(self.logs / "missing"), [])

    def test_collects_top_level_jsonl(self) -> None:
        (self.logs / "dispatch.jsonl").write_text("")
        (self.logs / "conductor.jsonl").write_text("")
        (self.logs / "ignore.txt").write_text("not jsonl")
        files = iter_event_files(self.logs)
        names = sorted(f.name for f in files)
        self.assertEqual(names, ["conductor.jsonl", "dispatch.jsonl"])

    def test_collects_nested_mind_loop(self) -> None:
        nested = self.logs / "minds" / "alice"
        nested.mkdir(parents=True)
        (nested / "mind-loop.jsonl").write_text("")
        (self.logs / "dispatch.jsonl").write_text("")
        files = iter_event_files(self.logs)
        relatives = sorted(str(f.relative_to(self.logs)).replace("\\", "/") for f in files)
        self.assertIn("dispatch.jsonl", relatives)
        self.assertIn("minds/alice/mind-loop.jsonl", relatives)


class TestIterEvents(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name) / "logs"
        self.logs.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, lines: list[dict]) -> None:
        path = self.logs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n",
            encoding="utf-8",
        )

    def test_merge_sort_across_files(self) -> None:
        """複数 file の event が ts 昇順で 1 series になる。"""
        self._write(
            "dispatch.jsonl",
            [
                {"ts": "2026-06-01T00:00:02.000Z", "event": "dispatch.sent",
                 "actor": "conduit", "from": "warden", "to": "alice",
                 "topic": "t", "msg_id": "m1"},
            ],
        )
        self._write(
            "conductor.jsonl",
            [
                {"ts": "2026-06-01T00:00:00.000Z", "event": "cycle.start",
                 "actor": "conductor", "cycle": 1},
                {"ts": "2026-06-01T00:00:03.000Z", "event": "cycle.end",
                 "actor": "conductor", "cycle": 1, "duration_ms": 3000,
                 "judgment_status": "ok"},
            ],
        )
        self._write(
            "minds/alice/mind-loop.jsonl",
            [
                {"ts": "2026-06-01T00:00:01.000Z", "event": "mind_loop.start",
                 "actor": "alice", "cycle": 1, "pid": 100},
            ],
        )
        events = list(iter_events(self.logs))
        tss = [e["ts"] for e in events]
        self.assertEqual(
            tss,
            [
                "2026-06-01T00:00:00.000Z",
                "2026-06-01T00:00:01.000Z",
                "2026-06-01T00:00:02.000Z",
                "2026-06-01T00:00:03.000Z",
            ],
        )

    def test_skip_malformed_json_with_warn(self) -> None:
        path = self.logs / "broken.jsonl"
        path.write_text(
            '{"ts":"2026-06-01T00:00:00.000Z","event":"ok","actor":"x"}\n'
            "this is not json\n"
            '{"ts":"2026-06-01T00:00:01.000Z","event":"ok2","actor":"x"}\n',
            encoding="utf-8",
        )
        buf = io.StringIO()
        events = list(iter_events(self.logs, stderr=buf))
        # malformed 1 行が skip され、正常 2 行が残る
        self.assertEqual(len(events), 2)
        self.assertIn("WARN", buf.getvalue())
        self.assertIn("broken.jsonl", buf.getvalue())

    def test_skip_line_without_ts(self) -> None:
        path = self.logs / "no_ts.jsonl"
        path.write_text(
            '{"event":"missing","actor":"x"}\n'
            '{"ts":"2026-06-01T00:00:00.000Z","event":"good","actor":"x"}\n',
            encoding="utf-8",
        )
        buf = io.StringIO()
        events = list(iter_events(self.logs, stderr=buf))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "good")
        self.assertIn("WARN", buf.getvalue())

    def test_since_filter(self) -> None:
        self._write(
            "x.jsonl",
            [
                {"ts": "2026-06-01T00:00:00.000Z", "event": "a", "actor": "x"},
                {"ts": "2026-06-01T00:00:05.000Z", "event": "b", "actor": "x"},
                {"ts": "2026-06-01T00:00:10.000Z", "event": "c", "actor": "x"},
            ],
        )
        events = list(iter_events(self.logs, since_ts="2026-06-01T00:00:05.000Z"))
        self.assertEqual([e["event"] for e in events], ["b", "c"])

    def test_empty_lines_skipped(self) -> None:
        path = self.logs / "with_blanks.jsonl"
        path.write_text(
            '{"ts":"2026-06-01T00:00:00.000Z","event":"a","actor":"x"}\n'
            "\n"
            '   \n'
            '{"ts":"2026-06-01T00:00:01.000Z","event":"b","actor":"x"}\n',
            encoding="utf-8",
        )
        events = list(iter_events(self.logs))
        self.assertEqual(len(events), 2)


class TestFormatEvent(unittest.TestCase):
    """各 event 種別の format 出力を検証 (= ユーザーが見る文言)。"""

    def test_dispatch_sent(self) -> None:
        s = format_event({
            "ts": "T1", "event": "dispatch.sent", "actor": "conduit",
            "from": "warden", "to": "alice", "topic": "status?",
            "msg_id": "m1",
        })
        self.assertEqual(s, "[T1] warden→alice dispatch 'status?' (msg=m1)")

    def test_dispatch_acked(self) -> None:
        s = format_event({
            "ts": "T1", "event": "dispatch.acked", "actor": "conduit",
            "by": "alice", "msg_id": "m1",
        })
        self.assertEqual(s, "[T1] alice acked dispatch (msg=m1)")

    def test_cycle_start_end(self) -> None:
        s1 = format_event({"ts": "T1", "event": "cycle.start",
                           "actor": "conductor", "cycle": 7})
        self.assertEqual(s1, "[T1] conductor cycle 7 start")
        s2 = format_event({"ts": "T2", "event": "cycle.end",
                           "actor": "conductor", "cycle": 7,
                           "duration_ms": 1234, "judgment_status": "ok"})
        self.assertEqual(
            s2, "[T2] conductor cycle 7 end (duration=1234ms, status=ok)"
        )

    def test_judgment_invoked_and_result(self) -> None:
        s1 = format_event({"ts": "T1", "event": "judgment.invoked",
                           "actor": "conductor", "cycle": 2, "input_minds": 3})
        self.assertEqual(s1, "[T1] judgment invoked cycle 2 (minds=3)")
        s2 = format_event({"ts": "T2", "event": "judgment.result",
                           "actor": "conductor", "cycle": 2, "status": "ok",
                           "judgments_count": 3, "dispatches_planned": 1,
                           "warden_replies_read": 2})
        self.assertIn("status=ok", s2)
        self.assertIn("planned=1", s2)
        self.assertIn("warden_replies=2", s2)

    def test_warden_inbox(self) -> None:
        s1 = format_event({"ts": "T1", "event": "warden_inbox.read",
                           "actor": "conductor", "cycle": 5, "count": 2,
                           "msg_ids": ["a", "b"]})
        self.assertEqual(s1, "[T1] warden_inbox read cycle 5: 2 reply(s)")
        s2 = format_event({"ts": "T2", "event": "warden_inbox.ack",
                           "actor": "conductor", "cycle": 5, "msg_id": "a"})
        self.assertEqual(s2, "[T2] warden_inbox acked cycle 5 (msg=a)")

    def test_actuator_prompt(self) -> None:
        s = format_event({"ts": "T1", "event": "actuator.prompt",
                          "actor": "actuator", "cycle": 1, "target": "alice",
                          "topic": "hi", "msg_id": "m1", "result": "ok"})
        self.assertEqual(
            s, "[T1] actuator→alice prompt 'hi' (msg=m1, result=ok)"
        )

    def test_actuator_skipped_basic(self) -> None:
        s = format_event({"ts": "T1", "event": "actuator.skipped",
                          "actor": "actuator", "cycle": 1, "target": "alice",
                          "reason": "not_in_registry"})
        self.assertEqual(
            s, "[T1] actuator skipped alice (reason=not_in_registry)"
        )

    def test_actuator_skipped_with_error(self) -> None:
        s = format_event({"ts": "T1", "event": "actuator.skipped",
                          "actor": "actuator", "cycle": 1, "target": "alice",
                          "reason": "send_failed",
                          "error": "RuntimeError: boom"})
        self.assertIn("[RuntimeError: boom]", s)

    def test_mind_loop_start_end(self) -> None:
        s1 = format_event({"ts": "T1", "event": "mind_loop.start",
                           "actor": "alice", "cycle": 1, "pid": 1234})
        self.assertEqual(s1, "[T1] alice mind-loop cycle 1 start (pid=1234)")
        s2 = format_event({"ts": "T2", "event": "mind_loop.end",
                           "actor": "alice", "cycle": 1, "exit_code": 0,
                           "duration_s": 5})
        self.assertEqual(s2, "[T2] alice mind-loop cycle 1 end (exit=0, duration=5s)")

    def test_unknown_event_generic_format(self) -> None:
        s = format_event({"ts": "T1", "event": "future.unknown",
                          "actor": "x", "foo": "bar", "baz": 42})
        # generic: [ts] <event> actor=<actor> <sorted-extras>
        self.assertTrue(s.startswith("[T1] future.unknown actor=x"))
        self.assertIn("baz=42", s)
        self.assertIn("foo=bar", s)


class TestCmdTrace(unittest.TestCase):
    """cmd_trace のエントリ点を end-to-end 検証する。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name) / "logs"
        self.logs.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, lines: list[dict]) -> None:
        path = self.logs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n",
            encoding="utf-8",
        )

    def test_no_events_prints_hint_to_stderr(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        rc = cmd_trace(logs_dir=self.logs, out=out, stderr=err)
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("no events", err.getvalue())

    def test_outputs_formatted_lines_in_order(self) -> None:
        self._write(
            "a.jsonl",
            [
                {"ts": "2026-06-01T00:00:01.000Z", "event": "cycle.start",
                 "actor": "conductor", "cycle": 1},
                {"ts": "2026-06-01T00:00:00.000Z", "event": "dispatch.sent",
                 "actor": "conduit", "from": "warden", "to": "alice",
                 "topic": "t", "msg_id": "m1"},
            ],
        )
        out = io.StringIO()
        rc = cmd_trace(logs_dir=self.logs, out=out, stderr=io.StringIO())
        self.assertEqual(rc, 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        # 出力は ts 昇順 (dispatch.sent at 00:00:00 → cycle.start at 00:00:01)
        self.assertIn("dispatch", lines[0])
        self.assertIn("cycle 1 start", lines[1])

    def test_since_filter_applied(self) -> None:
        self._write(
            "a.jsonl",
            [
                {"ts": "2026-06-01T00:00:00.000Z", "event": "cycle.start",
                 "actor": "conductor", "cycle": 1},
                {"ts": "2026-06-01T00:00:10.000Z", "event": "cycle.start",
                 "actor": "conductor", "cycle": 2},
            ],
        )
        out = io.StringIO()
        rc = cmd_trace(
            since="2026-06-01T00:00:05.000Z",
            logs_dir=self.logs,
            out=out,
            stderr=io.StringIO(),
        )
        self.assertEqual(rc, 0)
        # cycle 2 のみ
        text = out.getvalue()
        self.assertIn("cycle 2 start", text)
        self.assertNotIn("cycle 1 start", text)

    def test_malformed_since_returns_2(self) -> None:
        err = io.StringIO()
        rc = cmd_trace(
            since="invalid",
            logs_dir=self.logs,
            out=io.StringIO(),
            stderr=err,
        )
        self.assertEqual(rc, 2)
        self.assertIn("ERROR", err.getvalue())


if __name__ == "__main__":
    unittest.main()
