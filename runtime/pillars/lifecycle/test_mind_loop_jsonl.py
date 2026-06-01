"""
Unit tests for mind-loop.sh の JSONL event 書き込み (ADR-0026 §4.5)。

bash script に対する subprocess test。stub claude binary を介してループを
1 cycle 走らせ、$AI_ORG_OS_HOME/logs/minds/<mind>/mind-loop.jsonl の
内容を検証する。

Standard library only (unittest, subprocess, tempfile, json, os).

Run:
  cd runtime/pillars/lifecycle && python -m unittest test_mind_loop_jsonl
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MIND_LOOP_SH = SCRIPT_DIR / "mind-loop.sh"


def _bash_available() -> bool:
    """bash が PATH に居るか。Windows GitHub Actions runner には居る。"""
    return shutil.which("bash") is not None


@unittest.skipUnless(_bash_available(), "bash not available in PATH")
class TestMindLoopJsonl(unittest.TestCase):
    """ADR-0026 §4.5: mind-loop.sh が mind-loop.jsonl に start/end event を書く。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "ai-org-os-home"
        self.home.mkdir()
        self.mind_name = "alice"
        # mind-loop.sh は $AI_ORG_OS_HOME/minds/<name>/ の存在を要求する。
        self.mind_dir = self.home / "minds" / self.mind_name
        self.mind_dir.mkdir(parents=True)
        # stub claude binary: exit 0 で何もしない (echo だけ)。
        self.stub_bin = self.tmp / "stub-claude"
        self.stub_bin.write_text(
            "#!/usr/bin/env bash\necho 'stub-claude called'\nexit 0\n",
            encoding="utf-8",
        )
        self.stub_bin.chmod(0o755)
        # 期待される log path (ADR-0026 §1)
        self.event_log = self.home / "logs" / "minds" / self.mind_name / "mind-loop.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_loop(self, max_cycles: int = 1, period: int = 0) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        env["AI_ORG_OS_CLAUDE_BIN"] = str(self.stub_bin)
        env["AI_ORG_OS_LOOP_PERIOD"] = str(period)
        env["AI_ORG_OS_LOOP_MAX_CYCLES"] = str(max_cycles)
        # Windows bash (MSYS/Git Bash) は subprocess fork が遅く 1 cycle で
        # 20-30s 食うことがある。CI (Linux) では数秒で済むが、ローカル夜の
        # 反復を許すため 120s に余裕を持たせる。
        return subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def _read_events(self) -> list[dict]:
        if not self.event_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.event_log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def test_single_cycle_emits_start_and_end(self) -> None:
        """1 cycle で mind_loop.start + mind_loop.end が 1 件ずつ書かれる。"""
        result = self._run_loop(max_cycles=1)
        self.assertEqual(result.returncode, 0, f"loop failed:\n{result.stderr}")
        events = self._read_events()
        starts = [e for e in events if e["event"] == "mind_loop.start"]
        ends = [e for e in events if e["event"] == "mind_loop.end"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)

    def test_envelope_fields(self) -> None:
        """envelope に ts / event / actor、event 固有に cycle / pid (start)
        / exit_code / duration_s (end) が含まれる。"""
        self._run_loop(max_cycles=1)
        events = self._read_events()
        start = next(e for e in events if e["event"] == "mind_loop.start")
        end = next(e for e in events if e["event"] == "mind_loop.end")

        # start
        self.assertEqual(start["actor"], self.mind_name)
        self.assertEqual(start["cycle"], 1)
        self.assertIsInstance(start["pid"], int)
        self.assertGreater(start["pid"], 0)
        self.assertRegex(
            start["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
        )

        # end
        self.assertEqual(end["actor"], self.mind_name)
        self.assertEqual(end["cycle"], 1)
        self.assertEqual(end["exit_code"], 0)
        self.assertIsInstance(end["duration_s"], int)
        self.assertGreaterEqual(end["duration_s"], 0)

    def test_order_start_before_end(self) -> None:
        """append 順: start → end。"""
        self._run_loop(max_cycles=1)
        events = self._read_events()
        # 最初の event は start、最後は end
        self.assertEqual(events[0]["event"], "mind_loop.start")
        self.assertEqual(events[-1]["event"], "mind_loop.end")

    def test_two_cycles_append_to_same_file(self) -> None:
        """2 cycle で 4 行 (start + end x2) が同 file に append される。"""
        self._run_loop(max_cycles=2)
        events = self._read_events()
        self.assertEqual(len(events), 4)
        cycles = [e["cycle"] for e in events]
        # cycle 番号は 1,1,2,2 の順
        self.assertEqual(cycles, [1, 1, 2, 2])

    def test_exit_code_propagated_on_stub_failure(self) -> None:
        """stub claude が exit 7 を返すと end.exit_code = 7。"""
        # stub を exit 7 に差し替え
        self.stub_bin.write_text(
            "#!/usr/bin/env bash\nexit 7\n", encoding="utf-8"
        )
        self.stub_bin.chmod(0o755)
        self._run_loop(max_cycles=1)
        events = self._read_events()
        end = next(e for e in events if e["event"] == "mind_loop.end")
        self.assertEqual(end["exit_code"], 7)

    def test_log_file_located_under_runtime_home(self) -> None:
        """log path: $AI_ORG_OS_HOME/logs/minds/<mind>/mind-loop.jsonl
        (ADR-0026 §1 file layout)。"""
        self._run_loop(max_cycles=1)
        self.assertTrue(self.event_log.exists())
        # 既存の mindspace 内 mind-loop.log とは別ファイル
        legacy = self.mind_dir / "mind-loop.log"
        self.assertTrue(legacy.exists())
        self.assertNotEqual(self.event_log, legacy)

    def test_each_line_is_valid_json(self) -> None:
        """壊れた JSON 行が混ざらない (parse できる)。"""
        self._run_loop(max_cycles=2)
        raw = self.event_log.read_text(encoding="utf-8")
        lines = [line for line in raw.splitlines() if line]
        self.assertEqual(len(lines), 4)
        for line in lines:
            # parse error は assertion で expose
            json.loads(line)

    def test_ts_monotonic_within_cycle(self) -> None:
        """同 cycle 内では start.ts <= end.ts。"""
        self._run_loop(max_cycles=1)
        events = self._read_events()
        start_ts = events[0]["ts"]
        end_ts = events[1]["ts"]
        # ISO-8601 lexical sort is chronological sort
        self.assertLessEqual(start_ts, end_ts)


if __name__ == "__main__":
    unittest.main()
