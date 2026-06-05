"""Phase 5g.B #175: chain.py の unit test。

build_chain_view / format_text / format_mermaid / iter_dispatch_events /
cmd_chain を検証。
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

from chain import (  # noqa: E402
    build_chain_view,
    cmd_chain,
    format_mermaid,
    format_text,
    iter_dispatch_events,
)


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def _sent(ts: str, frm: str, to: str, topic: str, msg_id: str) -> dict:
    return {
        "ts": ts, "event": "dispatch.sent", "actor": "conduit",
        "from": frm, "to": to, "topic": topic, "msg_id": msg_id,
    }


def _ack(ts: str, by: str, msg_id: str) -> dict:
    return {
        "ts": ts, "event": "dispatch.acked", "actor": "conduit",
        "by": by, "msg_id": msg_id,
    }


class TestIterDispatchEvents(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_yields_sent_and_acked(self) -> None:
        _write_jsonl(
            self.logs / "dispatch.jsonl",
            [
                _sent("2026-06-05T01:00:00Z", "a", "b", "t", "m1"),
                _ack("2026-06-05T01:01:00Z", "b", "m1"),
            ],
        )
        events = list(iter_dispatch_events(self.logs))
        self.assertEqual(len(events), 2)
        self.assertEqual({e["event"] for e in events}, {"dispatch.sent", "dispatch.acked"})

    def test_skips_other_events(self) -> None:
        _write_jsonl(
            self.logs / "dispatch.jsonl",
            [
                _sent("2026-06-05T01:00:00Z", "a", "b", "t", "m1"),
                {"ts": "2026-06-05T01:00:01Z", "event": "dispatch.malformed"},
                _ack("2026-06-05T01:01:00Z", "b", "m1"),
            ],
        )
        events = list(iter_dispatch_events(self.logs))
        self.assertEqual(len(events), 2)

    def test_filter_by_from_only_affects_sent(self) -> None:
        _write_jsonl(
            self.logs / "dispatch.jsonl",
            [
                _sent("2026-06-05T01:00:00Z", "a", "b", "t1", "m1"),
                _sent("2026-06-05T01:01:00Z", "c", "b", "t2", "m2"),
                _ack("2026-06-05T01:02:00Z", "b", "m1"),
            ],
        )
        # from=a で sent は m1 のみ、acked は両方通る
        events = list(iter_dispatch_events(self.logs, from_mind="a"))
        sent = [e for e in events if e["event"] == "dispatch.sent"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["msg_id"], "m1")

    def test_filter_by_since(self) -> None:
        _write_jsonl(
            self.logs / "dispatch.jsonl",
            [
                _sent("2026-06-04T11:00:00Z", "a", "b", "old", "m_old"),
                _sent("2026-06-05T11:00:00Z", "a", "b", "new", "m_new"),
            ],
        )
        events = list(iter_dispatch_events(self.logs, since_ts="2026-06-05T00:00:00Z"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["msg_id"], "m_new")

    def test_malformed_lines_skipped(self) -> None:
        log = self.logs / "dispatch.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            "{ broken\n"
            + json.dumps(_sent("2026-06-05T01:00:00Z", "a", "b", "t", "m1"))
            + "\n",
            encoding="utf-8",
        )
        events = list(iter_dispatch_events(self.logs))
        self.assertEqual(len(events), 1)


class TestBuildChainView(unittest.TestCase):
    def test_empty(self) -> None:
        view = build_chain_view([])
        s = view["summary"]
        self.assertEqual(s["sent_count"], 0)
        self.assertEqual(s["acked_count"], 0)
        self.assertEqual(s["unacked_count"], 0)
        self.assertEqual(s["ack_rate"], 0.0)
        self.assertEqual(s["participants"], [])
        self.assertEqual(view["timeline"], [])

    def test_chain_with_acks(self) -> None:
        events = [
            _sent("2026-06-05T01:00:00Z", "gm", "alice", "issue", "m1"),
            _sent("2026-06-05T01:05:00Z", "alice", "bob", "design", "m2"),
            _ack("2026-06-05T01:01:00Z", "alice", "m1"),
            _ack("2026-06-05T01:06:00Z", "bob", "m2"),
        ]
        view = build_chain_view(events)
        s = view["summary"]
        self.assertEqual(s["sent_count"], 2)
        self.assertEqual(s["acked_count"], 2)
        self.assertEqual(s["unacked_count"], 0)
        self.assertEqual(s["ack_rate"], 1.0)
        self.assertEqual(s["participants"], ["alice", "bob", "gm"])
        # timeline is sent ascending by ts
        self.assertEqual(view["timeline"][0]["topic"], "issue")
        self.assertEqual(view["timeline"][1]["topic"], "design")
        for entry in view["timeline"]:
            self.assertTrue(entry["acked"])

    def test_unacked_dispatch(self) -> None:
        events = [
            _sent("2026-06-05T01:00:00Z", "alice", "bob", "ask", "m1"),
            # no ack
        ]
        view = build_chain_view(events)
        s = view["summary"]
        self.assertEqual(s["sent_count"], 1)
        self.assertEqual(s["acked_count"], 0)
        self.assertEqual(s["unacked_count"], 1)
        self.assertFalse(view["timeline"][0]["acked"])

    def test_period_window(self) -> None:
        events = [
            _sent("2026-06-05T03:00:00Z", "a", "b", "x", "m1"),
            _sent("2026-06-05T01:00:00Z", "a", "b", "y", "m2"),
            _sent("2026-06-05T05:00:00Z", "a", "b", "z", "m3"),
        ]
        s = build_chain_view(events)["summary"]
        self.assertEqual(s["first_ts"], "2026-06-05T01:00:00Z")
        self.assertEqual(s["last_ts"], "2026-06-05T05:00:00Z")


class TestFormatText(unittest.TestCase):
    def test_empty(self) -> None:
        view = build_chain_view([])
        out = format_text(view)
        self.assertIn("[Dispatch Chain]", out)
        self.assertIn("no dispatches", out)

    def test_populated(self) -> None:
        view = build_chain_view([
            _sent("2026-06-05T01:00:00Z", "alice", "bob", "design-please", "m1"),
            _ack("2026-06-05T01:01:00Z", "bob", "m1"),
        ])
        out = format_text(view)
        self.assertIn("alice", out)
        self.assertIn("bob", out)
        self.assertIn("design-please", out)
        self.assertIn("[ack]", out)  # ack marker

    def test_long_topic_truncated(self) -> None:
        long_topic = "X" * 200
        view = build_chain_view([
            _sent("2026-06-05T01:00:00Z", "a", "b", long_topic, "m1"),
        ])
        out = format_text(view)
        self.assertIn("...", out)
        self.assertNotIn("X" * 100, out)


class TestFormatMermaid(unittest.TestCase):
    def test_empty(self) -> None:
        view = build_chain_view([])
        out = format_mermaid(view)
        self.assertIn("sequenceDiagram", out)
        self.assertIn("```mermaid", out)

    def test_chain(self) -> None:
        view = build_chain_view([
            _sent("2026-06-05T01:00:00Z", "gm-default", "alice", "issue", "m1"),
            _ack("2026-06-05T01:01:00Z", "alice", "m1"),
        ])
        out = format_mermaid(view)
        # gm-default は mermaid 用に gm_default に変換
        self.assertIn("gm_default", out)
        self.assertIn("alice", out)
        # ack 済なので solid arrow ->>
        self.assertIn("->>", out)

    def test_unacked_uses_dashed_arrow(self) -> None:
        view = build_chain_view([
            _sent("2026-06-05T01:00:00Z", "a", "b", "x", "m1"),
        ])
        out = format_mermaid(view)
        self.assertIn("-->>", out)


class TestCmdChain(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name) / "logs"
        _write_jsonl(
            self.logs / "dispatch.jsonl",
            [_sent("2026-06-05T01:00:00Z", "alice", "bob", "t", "m1")],
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cmd_chain_text(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = cmd_chain(logs_dir=self.logs)
        self.assertEqual(rc, 0)
        self.assertIn("[Dispatch Chain]", out.getvalue())
        self.assertIn("alice", out.getvalue())

    def test_cmd_chain_mermaid(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = cmd_chain(logs_dir=self.logs, as_mermaid=True)
        self.assertEqual(rc, 0)
        self.assertIn("sequenceDiagram", out.getvalue())

    def test_cmd_chain_invalid_since(self) -> None:
        with patch("sys.stdout", new_callable=StringIO), \
             patch("sys.stderr", new_callable=StringIO) as err:
            rc = cmd_chain(logs_dir=self.logs, since="invalid")
        self.assertEqual(rc, 2)
        self.assertIn("ERROR", err.getvalue())


if __name__ == "__main__":
    unittest.main()
