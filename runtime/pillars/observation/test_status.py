"""Phase 5g.B #174: status.py の unit test。

`gather_status` / `format_text` / `format_json` / `cmd_status` を検証。
fixture は tempfile で擬似 AI_ORG_OS_HOME を組み立て、I/O 経路を確認する。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from status import (  # noqa: E402
    cmd_status,
    format_json,
    format_text,
    gather_status,
)


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestGatherStatus(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.now = dt.datetime(2026, 6, 5, 12, 0, 0, tzinfo=dt.timezone.utc)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_home(self) -> None:
        """無 spawn / 無 issue / 無 cycle の空 home で agg が NULL 系の値を返す。"""
        agg = gather_status(self.home, now=self.now)
        s = agg["summary"]
        self.assertEqual(s["total_minds"], 0)
        self.assertEqual(s["alive_minds"], 0)
        self.assertEqual(s["open_issues"], 0)
        self.assertEqual(s["total_cost_usd"], 0)
        self.assertEqual(s["notify_critical_count"], 0)
        self.assertEqual(s["notify_warning_count"], 0)
        self.assertEqual(agg["minds"], [])

    def test_alive_mind_via_pid_file(self) -> None:
        """pidfile が存在する Mind は alive 扱い。"""
        mind_dir = self.home / "minds" / "alice"
        mind_dir.mkdir(parents=True)
        (mind_dir / ".mind-loop.pid").write_text("12345\n", encoding="utf-8")
        agg = gather_status(self.home, now=self.now)
        self.assertEqual(agg["summary"]["alive_minds"], 1)
        self.assertTrue(agg["minds"][0]["alive"])

    def test_dead_mind_no_pid_file(self) -> None:
        """pidfile 無し → dead 扱い (Mindspace は残っていても)。"""
        (self.home / "minds" / "alice").mkdir(parents=True)
        agg = gather_status(self.home, now=self.now)
        self.assertEqual(agg["summary"]["total_minds"], 1)
        self.assertEqual(agg["summary"]["alive_minds"], 0)
        self.assertFalse(agg["minds"][0]["alive"])

    def test_conductor_status_loaded(self) -> None:
        """conductor-status.json から cycle 番号と age が反映される。"""
        cond = {
            "last_cycle": {
                "cycle": 172,
                "ended_at": "2026-06-05T11:50:00Z",
                "judgment_status": "ok",
            },
            "total_cycles": 172,
        }
        (self.home / "conductor-status.json").write_text(
            json.dumps(cond), encoding="utf-8"
        )
        agg = gather_status(self.home, now=self.now)
        s = agg["summary"]
        self.assertEqual(s["conductor_cycle"], 172)
        # 10 分前なので 600s
        self.assertEqual(s["conductor_cycle_age_s"], 600)
        self.assertEqual(s["conductor_judgment_status"], "ok")

    def test_per_mind_cost_aggregated(self) -> None:
        """mind_loop.cost event を読んで cost を合算。"""
        mind_dir = self.home / "minds" / "alice"
        mind_dir.mkdir(parents=True)
        log = self.home / "logs" / "minds" / "alice" / "mind-loop.jsonl"
        _write_jsonl(
            log,
            [
                {
                    "ts": "2026-06-05T11:00:00Z", "event": "mind_loop.cost",
                    "mind": "alice", "cycle": 1, "cost_usd": 0.05,
                },
                {
                    "ts": "2026-06-05T11:01:00Z", "event": "mind_loop.cost",
                    "mind": "alice", "cycle": 2, "cost_usd": 0.03,
                },
            ],
        )
        agg = gather_status(self.home, now=self.now)
        m = agg["minds"][0]
        self.assertAlmostEqual(m["total_cost_usd"], 0.08, places=6)
        self.assertEqual(m["cost_cycles"], 2)
        self.assertAlmostEqual(agg["summary"]["total_cost_usd"], 0.08, places=6)

    def test_error_and_timeout_streak(self) -> None:
        """mind_loop.error / mind_loop.timeout event の streak を pickup。"""
        mind_dir = self.home / "minds" / "alice"
        mind_dir.mkdir(parents=True)
        log = self.home / "logs" / "minds" / "alice" / "mind-loop.jsonl"
        _write_jsonl(
            log,
            [
                {"ts": "2026-06-05T11:00:00Z", "event": "mind_loop.error",
                 "cycle": 1, "streak": 1, "exit_code": 2},
                {"ts": "2026-06-05T11:01:00Z", "event": "mind_loop.timeout",
                 "cycle": 2, "streak": 1, "signal": "SIGTERM"},
            ],
        )
        m = gather_status(self.home, now=self.now)["minds"][0]
        self.assertEqual(m["error_streak"], 1)
        self.assertEqual(m["timeout_streak"], 1)

    def test_streak_resets_on_successful_cycle_end(self) -> None:
        """exit_code=0 の mind_loop.end で streak が reset (= per-cycle 観点)。"""
        mind_dir = self.home / "minds" / "alice"
        mind_dir.mkdir(parents=True)
        log = self.home / "logs" / "minds" / "alice" / "mind-loop.jsonl"
        _write_jsonl(
            log,
            [
                {"ts": "2026-06-05T11:00:00Z", "event": "mind_loop.error",
                 "cycle": 1, "streak": 2, "exit_code": 2},
                {"ts": "2026-06-05T11:01:00Z", "event": "mind_loop.end",
                 "cycle": 2, "exit_code": 0, "duration_s": 5},
            ],
        )
        m = gather_status(self.home, now=self.now)["minds"][0]
        self.assertEqual(m["error_streak"], 0)
        self.assertEqual(m["last_event"], "mind_loop.end")
        self.assertEqual(m["last_cycle"], 2)

    def test_notify_counts(self) -> None:
        """logs/notify.jsonl の critical / warning 数。"""
        notify = self.home / "logs" / "notify.jsonl"
        _write_jsonl(
            notify,
            [
                {"ts": "x", "severity": "warning", "event": "a"},
                {"ts": "x", "severity": "warning", "event": "b"},
                {"ts": "x", "severity": "critical", "event": "c"},
            ],
        )
        s = gather_status(self.home, now=self.now)["summary"]
        self.assertEqual(s["notify_warning_count"], 2)
        self.assertEqual(s["notify_critical_count"], 1)

    def test_pending_issues_counted(self) -> None:
        """issues/inbox/ の entry 数 = pending count。"""
        inbox = self.home / "issues" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "20260605-001-foo.json").write_text("{}", encoding="utf-8")
        (inbox / "20260605-002-bar.json").write_text("{}", encoding="utf-8")
        s = gather_status(self.home, now=self.now)["summary"]
        self.assertEqual(s["open_issues"], 2)

    def test_malformed_jsonl_skipped_silently(self) -> None:
        """壊れた JSONL 行は skip して agg は壊れない。"""
        mind_dir = self.home / "minds" / "alice"
        mind_dir.mkdir(parents=True)
        log = self.home / "logs" / "minds" / "alice" / "mind-loop.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            "{ broken json\n"
            + json.dumps({
                "ts": "2026-06-05T11:00:00Z", "event": "mind_loop.cost",
                "mind": "alice", "cycle": 1, "cost_usd": 0.01,
            })
            + "\n",
            encoding="utf-8",
        )
        m = gather_status(self.home, now=self.now)["minds"][0]
        self.assertAlmostEqual(m["total_cost_usd"], 0.01, places=6)


class TestFormatText(unittest.TestCase):
    def test_empty_minds_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agg = gather_status(Path(tmp), now=dt.datetime(2026, 6, 5, tzinfo=dt.timezone.utc))
        out = format_text(agg)
        self.assertIn("[Realm Health]", out)
        self.assertIn("(no Minds spawned)", out)

    def test_populated_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mind_dir = home / "minds" / "alice"
            mind_dir.mkdir(parents=True)
            (mind_dir / ".mind-loop.pid").write_text("123", encoding="utf-8")
            log = home / "logs" / "minds" / "alice" / "mind-loop.jsonl"
            _write_jsonl(
                log,
                [{
                    "ts": "2026-06-05T11:00:00Z", "event": "mind_loop.cost",
                    "mind": "alice", "cycle": 1, "cost_usd": 0.0123,
                }],
            )
            agg = gather_status(
                home, now=dt.datetime(2026, 6, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
            )
        out = format_text(agg)
        self.assertIn("alice", out)
        self.assertIn("yes", out)  # alive
        self.assertIn("$0.0123", out)


class TestFormatJson(unittest.TestCase):
    def test_parses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agg = gather_status(Path(tmp), now=dt.datetime(2026, 6, 5, tzinfo=dt.timezone.utc))
        parsed = json.loads(format_json(agg))
        self.assertIn("summary", parsed)
        self.assertIn("minds", parsed)


class TestCmdStatus(unittest.TestCase):
    def test_cmd_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("sys.stdout", new_callable=StringIO) as out:
                rc = cmd_status(
                    home=Path(tmp),
                    now=dt.datetime(2026, 6, 5, tzinfo=dt.timezone.utc),
                )
        self.assertEqual(rc, 0)
        self.assertIn("[Realm Health]", out.getvalue())

    def test_cmd_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("sys.stdout", new_callable=StringIO) as out:
                rc = cmd_status(
                    home=Path(tmp),
                    as_json=True,
                    now=dt.datetime(2026, 6, 5, tzinfo=dt.timezone.utc),
                )
        self.assertEqual(rc, 0)
        parsed = json.loads(out.getvalue())
        self.assertEqual(parsed["summary"]["total_minds"], 0)


if __name__ == "__main__":
    unittest.main()
