"""Phase 5g.B #172 chunk 2: cost.py の unit test。

aggregate / iter_cost_events / format_text / format_json / cmd_cost を検証。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# このディレクトリを path に入れて cost.py / trace.py を import 可能に
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cost import (  # noqa: E402
    aggregate,
    cmd_cost,
    format_json,
    format_text,
    iter_cost_events,
)


def _cost_event(
    *,
    ts: str,
    mind: str,
    cycle: int,
    cost: float,
    in_tok: int = 100,
    out_tok: int = 50,
    cache_creation: int = 0,
    cache_read: int = 0,
    model: str = "claude-opus-test",
    is_error: bool = False,
) -> dict:
    return {
        "ts": ts,
        "event": "mind_loop.cost",
        "mind": mind,
        "cycle": cycle,
        "cost_usd": cost,
        "duration_api_ms": 100,
        "num_turns": 1,
        "tokens": {
            "input": in_tok,
            "output": out_tok,
            "cache_creation": cache_creation,
            "cache_read": cache_read,
        },
        "models": {model: cost},
        "session_id": f"sess-{mind}-{cycle}",
        "is_error": is_error,
    }


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


class TestIterCostEvents(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name) / "logs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_iter_from_single_mind(self) -> None:
        log = self.logs / "minds" / "alice" / "mind-loop.jsonl"
        _write_log(
            log,
            [
                _cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.01),
                _cost_event(ts="2026-06-05T01:01:00Z", mind="alice", cycle=2, cost=0.02),
            ],
        )
        events = list(iter_cost_events(self.logs))
        self.assertEqual(len(events), 2)
        self.assertEqual([e["cycle"] for e in events], [1, 2])

    def test_iter_skips_non_cost_events(self) -> None:
        log = self.logs / "minds" / "alice" / "mind-loop.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps({"ts": "2026-06-05T01:00:00Z", "event": "mind_loop.start", "cycle": 1}),
            json.dumps(_cost_event(ts="2026-06-05T01:00:01Z", mind="alice", cycle=1, cost=0.01)),
            json.dumps({"ts": "2026-06-05T01:00:02Z", "event": "mind_loop.end", "cycle": 1}),
        ]
        log.write_text("\n".join(lines), encoding="utf-8")
        events = list(iter_cost_events(self.logs))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "mind_loop.cost")

    def test_iter_filter_by_mind(self) -> None:
        _write_log(
            self.logs / "minds" / "alice" / "mind-loop.jsonl",
            [_cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.01)],
        )
        _write_log(
            self.logs / "minds" / "bob" / "mind-loop.jsonl",
            [_cost_event(ts="2026-06-05T01:00:00Z", mind="bob", cycle=1, cost=0.02)],
        )
        a_only = list(iter_cost_events(self.logs, mind="alice"))
        self.assertEqual(len(a_only), 1)
        self.assertEqual(a_only[0]["mind"], "alice")

    def test_iter_filter_by_since(self) -> None:
        _write_log(
            self.logs / "minds" / "alice" / "mind-loop.jsonl",
            [
                _cost_event(ts="2026-06-04T12:00:00Z", mind="alice", cycle=1, cost=0.01),
                _cost_event(ts="2026-06-05T12:00:00Z", mind="alice", cycle=2, cost=0.02),
            ],
        )
        # since が前者より後、後者より前 → 1 件のみ
        events = list(iter_cost_events(self.logs, since_ts="2026-06-05T00:00:00.000Z"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["cycle"], 2)

    def test_iter_silently_skips_malformed_lines(self) -> None:
        log = self.logs / "minds" / "alice" / "mind-loop.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            "{ broken json\n"
            + json.dumps(_cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.01))
            + "\nnot-an-object-just-string\n",
            encoding="utf-8",
        )
        events = list(iter_cost_events(self.logs))
        self.assertEqual(len(events), 1)

    def test_iter_empty_logs_dir(self) -> None:
        events = list(iter_cost_events(self.logs))
        self.assertEqual(events, [])


class TestAggregate(unittest.TestCase):
    def test_empty(self) -> None:
        agg = aggregate([])
        self.assertEqual(agg["summary"]["total_cost_usd"], 0)
        self.assertEqual(agg["summary"]["total_cycles"], 0)
        self.assertEqual(agg["summary"]["minds"], 0)
        self.assertEqual(agg["per_mind"], {})
        self.assertEqual(agg["per_day"], {})
        self.assertEqual(agg["per_model"], {})

    def test_per_mind_summation(self) -> None:
        events = [
            _cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.01,
                        in_tok=10, out_tok=5, cache_read=100),
            _cost_event(ts="2026-06-05T01:01:00Z", mind="alice", cycle=2, cost=0.03,
                        in_tok=20, out_tok=10, cache_read=200),
            _cost_event(ts="2026-06-05T01:02:00Z", mind="bob", cycle=1, cost=0.02,
                        in_tok=15, out_tok=8, cache_read=150),
        ]
        agg = aggregate(events)
        self.assertAlmostEqual(agg["summary"]["total_cost_usd"], 0.06, places=6)
        self.assertEqual(agg["summary"]["total_cycles"], 3)
        self.assertEqual(agg["summary"]["minds"], 2)
        a = agg["per_mind"]["alice"]
        self.assertAlmostEqual(a["cost_usd"], 0.04, places=6)
        self.assertEqual(a["cycles"], 2)
        self.assertEqual(a["tokens"]["input"], 30)
        self.assertEqual(a["tokens"]["output"], 15)
        self.assertEqual(a["tokens"]["cache_read"], 300)
        self.assertAlmostEqual(a["max_cycle_cost"], 0.03, places=6)

    def test_per_day_grouping(self) -> None:
        events = [
            _cost_event(ts="2026-06-04T23:59:00Z", mind="alice", cycle=1, cost=0.01),
            _cost_event(ts="2026-06-05T00:00:01Z", mind="alice", cycle=2, cost=0.02),
            _cost_event(ts="2026-06-05T12:00:00Z", mind="bob", cycle=1, cost=0.03),
        ]
        agg = aggregate(events)
        self.assertEqual(set(agg["per_day"].keys()), {"2026-06-04", "2026-06-05"})
        self.assertAlmostEqual(agg["per_day"]["2026-06-04"]["cost_usd"], 0.01, places=6)
        self.assertAlmostEqual(agg["per_day"]["2026-06-05"]["cost_usd"], 0.05, places=6)
        self.assertEqual(agg["per_day"]["2026-06-05"]["cycles"], 2)
        self.assertEqual(agg["per_day"]["2026-06-05"]["minds"], ["alice", "bob"])

    def test_per_model_share(self) -> None:
        events = [
            _cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.08,
                        model="opus"),
            _cost_event(ts="2026-06-05T01:01:00Z", mind="alice", cycle=2, cost=0.02,
                        model="haiku"),
        ]
        agg = aggregate(events)
        self.assertAlmostEqual(agg["per_model"]["opus"]["cost_usd"], 0.08, places=6)
        self.assertAlmostEqual(agg["per_model"]["haiku"]["cost_usd"], 0.02, places=6)
        self.assertAlmostEqual(agg["per_model"]["opus"]["share"], 0.8, places=6)
        self.assertAlmostEqual(agg["per_model"]["haiku"]["share"], 0.2, places=6)

    def test_is_error_counts(self) -> None:
        events = [
            _cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.01,
                        is_error=False),
            _cost_event(ts="2026-06-05T01:01:00Z", mind="alice", cycle=2, cost=0.01,
                        is_error=True),
            _cost_event(ts="2026-06-05T01:02:00Z", mind="alice", cycle=3, cost=0.01,
                        is_error=True),
        ]
        agg = aggregate(events)
        self.assertEqual(agg["per_mind"]["alice"]["errors"], 2)

    def test_ts_window_first_last(self) -> None:
        events = [
            _cost_event(ts="2026-06-05T03:00:00Z", mind="alice", cycle=1, cost=0.01),
            _cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=2, cost=0.01),
            _cost_event(ts="2026-06-05T05:00:00Z", mind="alice", cycle=3, cost=0.01),
        ]
        agg = aggregate(events)
        self.assertEqual(agg["summary"]["first_ts"], "2026-06-05T01:00:00Z")
        self.assertEqual(agg["summary"]["last_ts"], "2026-06-05T05:00:00Z")


class TestFormatText(unittest.TestCase):
    def test_empty_message(self) -> None:
        agg = aggregate([])
        out = format_text(agg)
        self.assertIn("No mind_loop.cost events found", out)

    def test_non_empty_sections(self) -> None:
        events = [
            _cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.0123),
        ]
        agg = aggregate(events)
        out = format_text(agg)
        self.assertIn("[Cost Summary]", out)
        self.assertIn("[Per-Mind]", out)
        self.assertIn("[Per-Day]", out)
        self.assertIn("[Per-Model]", out)
        self.assertIn("alice", out)
        self.assertIn("$0.0123", out)


class TestFormatJson(unittest.TestCase):
    def test_valid_json(self) -> None:
        events = [
            _cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.0123),
        ]
        agg = aggregate(events)
        s = format_json(agg)
        parsed = json.loads(s)  # parse 失敗で test fail
        self.assertEqual(parsed["summary"]["total_cycles"], 1)


class TestCmdCost(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name) / "logs"
        log = self.logs / "minds" / "alice" / "mind-loop.jsonl"
        _write_log(
            log,
            [_cost_event(ts="2026-06-05T01:00:00Z", mind="alice", cycle=1, cost=0.05)],
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cmd_cost_text_output(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = cmd_cost(logs_dir=self.logs)
        self.assertEqual(rc, 0)
        self.assertIn("alice", out.getvalue())
        self.assertIn("$0.0500", out.getvalue())

    def test_cmd_cost_json_output(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            rc = cmd_cost(logs_dir=self.logs, as_json=True)
        self.assertEqual(rc, 0)
        parsed = json.loads(out.getvalue())
        self.assertEqual(parsed["per_mind"]["alice"]["cycles"], 1)

    def test_cmd_cost_invalid_since(self) -> None:
        with patch("sys.stdout", new_callable=StringIO), \
             patch("sys.stderr", new_callable=StringIO) as err:
            rc = cmd_cost(logs_dir=self.logs, since="invalid-spec")
        self.assertEqual(rc, 2)
        self.assertIn("ERROR", err.getvalue())


if __name__ == "__main__":
    unittest.main()
