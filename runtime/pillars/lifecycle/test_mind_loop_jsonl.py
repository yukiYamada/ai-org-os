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
import sys
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


@unittest.skipUnless(_bash_available(), "bash not available in PATH")
class TestMindLoopNudge(unittest.TestCase):
    """Fix #136: mind-loop.sh の sleep loop が .mind-loop.nudge を見て即時抜ける。

    本クラスは長い period (= 10s) で loop を background 起動し、別 thread で
    nudge file を touch し、cycle 2 開始時刻が period より大きく早いことを
    assertion する。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "ai-org-os-home"
        self.home.mkdir()
        self.mind_name = "alice"
        self.mind_dir = self.home / "minds" / self.mind_name
        self.mind_dir.mkdir(parents=True)
        self.nudge_file = self.mind_dir / ".mind-loop.nudge"
        # stub claude: exit 0 even faster than the default stub
        self.stub_bin = self.tmp / "stub-claude"
        self.stub_bin.write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        self.stub_bin.chmod(0o755)
        self.event_log = self.home / "logs" / "minds" / self.mind_name / "mind-loop.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_events(self) -> list[dict]:
        if not self.event_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.event_log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def test_nudge_shortens_sleep_between_cycles(self) -> None:
        """cycle 1 終了後の sleep (period=20s) を nudge で短縮する。

        max_cycles=2 で 2 cycle 走る。cycle 1 → cycle 2 の間に nudge file を
        touch すると sleep が即時抜ける。Windows MSYS bash の subprocess fork
        overhead (date / mkdir / printf がそれぞれ fork) で cycle 2 prep に
        ~9s かかるため、gap = sleep_time + ~9s prep。period=20s だと:
        - with-nudge: ~1-2s sleep + ~9s prep = ~10-15s gap
        - no-nudge:   ~20s sleep + ~9s prep = ~30s gap
        閾値 18s で確実に分離。Linux CI ではどちらも更に短いので余裕で pass。
        """
        import threading
        import time as _time

        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        env["AI_ORG_OS_CLAUDE_BIN"] = str(self.stub_bin)
        env["AI_ORG_OS_LOOP_PERIOD"] = "20"
        env["AI_ORG_OS_LOOP_MAX_CYCLES"] = "2"

        # subprocess.Popen で非同期起動、別 thread で nudge を打つ
        proc = subprocess.Popen(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def _nudge_after_cycle1_ends() -> None:
            # cycle 1 の mind_loop.end event が現れるまで poll、その後 nudge を touch
            deadline = _time.time() + 90  # Windows bash 想定で余裕を持って 90s
            while _time.time() < deadline:
                evts = self._read_events()
                ended = [e for e in evts if e["event"] == "mind_loop.end" and e["cycle"] == 1]
                if ended:
                    # cycle 1 が終わった直後に nudge を打つ
                    self.nudge_file.touch()
                    return
                _time.sleep(0.2)

        nudger = threading.Thread(target=_nudge_after_cycle1_ends, daemon=True)
        nudger.start()

        try:
            proc.wait(timeout=180)
        finally:
            if proc.poll() is None:
                proc.kill()
            nudger.join(timeout=5)

        self.assertEqual(proc.returncode, 0, f"loop failed:\n{proc.stderr.read() if proc.stderr else ''}")
        events = self._read_events()
        starts = sorted([e for e in events if e["event"] == "mind_loop.start"], key=lambda e: e["cycle"])
        ends = sorted([e for e in events if e["event"] == "mind_loop.end"], key=lambda e: e["cycle"])
        self.assertEqual(len(starts), 2)
        self.assertEqual(len(ends), 2)

        # cycle 1 end → cycle 2 start の sleep を測る
        from datetime import datetime as _dt
        def _parse(ts: str) -> _dt:
            return _dt.fromisoformat(ts.replace("Z", "+00:00"))
        gap_s = (_parse(starts[1]["ts"]) - _parse(ends[0]["ts"])).total_seconds()
        # period=20s に対し閾値 18s。
        # - with-nudge: 1-2s sleep + ~9s cycle 2 prep (Windows bash overhead) = ~10-15s
        # - no-nudge:   20s sleep + ~9s prep = ~30s (regression を確実に catch)
        # Linux CI では bash overhead が ~1s 程度なので with-nudge gap ~2-3s。
        # 閾値 18s は no-nudge 退行が混入した場合に確実に fail する設計値。
        self.assertLess(
            gap_s, 18.0,
            f"nudge should shorten sleep below 18s (period=20s) but observed {gap_s:.2f}s gap"
        )

    def test_stale_nudge_is_cleaned_at_cycle_start(self) -> None:
        """前 cycle 終了直後に到着した nudge が次 cycle 開始時に削除される。

        max_cycles=1 で 1 cycle 走る前に nudge を仕込む → cycle 開始時の
        rm -f で消える → cycle 終了後にも file は無い。
        """
        # nudge を pre-touch
        self.nudge_file.touch()
        self.assertTrue(self.nudge_file.exists())

        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        env["AI_ORG_OS_CLAUDE_BIN"] = str(self.stub_bin)
        env["AI_ORG_OS_LOOP_PERIOD"] = "0"
        env["AI_ORG_OS_LOOP_MAX_CYCLES"] = "1"

        result = subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, f"loop failed:\n{result.stderr}")
        # cycle 完走後、nudge は消えているはず (cycle 開始時に rm -f された)
        self.assertFalse(
            self.nudge_file.exists(),
            "stale nudge file should be cleaned at next cycle start"
        )


@unittest.skipUnless(_bash_available(), "bash not available in PATH")
class TestMindLoopPeekInbox(unittest.TestCase):
    """Fix #144 case A: mind-loop が claude -p 起動前に inbox を peek して
    prompt 冒頭に dispatch 概要を挿入する。

    stub claude を「prompt 引数を file に dump するだけ」のものに差し替え、
    実機 inbox 状態に応じて prompt が変化することを assertion する。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "ai-org-os-home"
        self.home.mkdir()
        # config.env を空で作って host setup 済扱い (mind-loop は他の項目を
        # 必要としないので空でも問題ない)。
        (self.home / "config.env").write_text("", encoding="utf-8")
        self.mind_name = "alice"
        self.mind_dir = self.home / "minds" / self.mind_name
        self.mind_dir.mkdir(parents=True)
        # stub claude: 引数 "-p" の次の文字列を /tmp/last-prompt に dump する。
        # POSIX bash で "$@" を file に出すだけのシンプルなものでよい。
        self.prompt_dump = self.tmp / "last-prompt.txt"
        self.stub_bin = self.tmp / "stub-claude"
        self.stub_bin.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$@" > "{self.prompt_dump.as_posix()}"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        self.stub_bin.chmod(0o755)
        self.event_log = self.home / "logs" / "minds" / self.mind_name / "mind-loop.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_loop(self, max_cycles: int = 1, period: int = 0) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        env["AI_ORG_OS_CLAUDE_BIN"] = str(self.stub_bin)
        env["AI_ORG_OS_LOOP_PERIOD"] = str(period)
        env["AI_ORG_OS_LOOP_MAX_CYCLES"] = str(max_cycles)
        return subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def _send_dispatch_to_alice(self, from_mind: str, topic: str, body: str) -> None:
        """Nexus を直接使って alice の inbox に dispatch を投入する。
        bash 経由ではなく Python で行うことで、テスト時間を最小化する。"""
        conduit_dir = MIND_LOOP_SH.parent.parent / "conduit"
        # 一時的に sys.path 注入して storage import
        original = list(sys.path)
        sys.path.insert(0, str(conduit_dir))
        try:
            from storage import Nexus  # noqa: PLC0415

            nx = Nexus(
                storage_dir=self.home / "conduit-storage",
                logs_dir=self.home / "logs",
                minds_dir=self.home / "minds",
            )
            nx.send_dispatch(
                from_mind=from_mind, to_mind="alice",
                topic=topic, body=body,
            )
        finally:
            sys.path = original

    def test_empty_inbox_prompt_unchanged(self) -> None:
        """inbox 空のときは prompt に INBOX 句が挿入されない (= 既存挙動と互換)。"""
        result = self._run_loop(max_cycles=1)
        self.assertEqual(result.returncode, 0, f"loop failed:\n{result.stderr}")
        prompt = self.prompt_dump.read_text(encoding="utf-8")
        self.assertIn("cycle 1 for mind alice", prompt)
        self.assertNotIn("INBOX:", prompt)

    def test_inbox_with_dispatch_injects_summary(self) -> None:
        """inbox に dispatch があれば prompt に「N pending dispatch(es): from X 'topic'」
        が挿入される。"""
        self._send_dispatch_to_alice(
            from_mind="gm-default",
            topic="Issue ready — start designing",
            body="please design X",
        )
        result = self._run_loop(max_cycles=1)
        self.assertEqual(result.returncode, 0, f"loop failed:\n{result.stderr}")
        prompt = self.prompt_dump.read_text(encoding="utf-8")
        self.assertIn("INBOX: 1 pending dispatch(es)", prompt)
        self.assertIn("from gm-default", prompt)
        self.assertIn("Issue ready — start designing", prompt)

    def test_multiple_dispatches_summary(self) -> None:
        """複数 dispatch があれば全部 summary に並ぶ (5 件まで)。"""
        for i in range(3):
            self._send_dispatch_to_alice(
                from_mind=f"sender-{i}", topic=f"topic-{i}", body="b",
            )
        result = self._run_loop(max_cycles=1)
        self.assertEqual(result.returncode, 0, f"loop failed:\n{result.stderr}")
        prompt = self.prompt_dump.read_text(encoding="utf-8")
        self.assertIn("3 pending dispatch(es)", prompt)
        self.assertIn("topic-0", prompt)
        self.assertIn("topic-1", prompt)
        self.assertIn("topic-2", prompt)

    def test_summary_capped_at_5(self) -> None:
        """6 件以上の dispatch は最初 5 件 + '(+N more)' 表記。"""
        for i in range(7):
            self._send_dispatch_to_alice(
                from_mind=f"s{i:02d}", topic=f"t{i:02d}", body="b",
            )
        result = self._run_loop(max_cycles=1)
        self.assertEqual(result.returncode, 0, f"loop failed:\n{result.stderr}")
        prompt = self.prompt_dump.read_text(encoding="utf-8")
        self.assertIn("7 pending dispatch(es)", prompt)
        # 先頭 5 件は含まれる
        self.assertIn("t00", prompt)
        self.assertIn("t04", prompt)
        # +2 more
        self.assertIn("(+2 more)", prompt)

    def test_long_topic_is_truncated(self) -> None:
        """Codex P2 (PR #145): 巨大 topic は argv length blowup 防止のため
        切り詰められる。\`MAX_TOPIC_CHARS_PER_ENTRY=80\` に揃う。"""
        long_topic = "X" * 500  # 80 字制限を大きく超える
        self._send_dispatch_to_alice(
            from_mind="sender", topic=long_topic, body="b",
        )
        result = self._run_loop(max_cycles=1)
        self.assertEqual(result.returncode, 0, f"loop failed:\n{result.stderr}")
        prompt = self.prompt_dump.read_text(encoding="utf-8")
        self.assertIn("INBOX: 1 pending dispatch(es)", prompt)
        # 500 字の "X" がそのまま流れていないこと
        # (80 字制限なので "X" * 77 + "..." = 80 字)
        self.assertNotIn("X" * 200, prompt)
        # 切り詰め痕跡 "..." が現れる
        self.assertIn("X...", prompt)


@unittest.skipUnless(_bash_available() and shutil.which("timeout") is not None,
                     "bash + GNU timeout required")
class TestMindLoopPerCycleTimeout(unittest.TestCase):
    """ADR-0028 §2.1: per-cycle timeout で claude が hang した時に救う。

    stub claude が長時間 sleep → mind-loop の `timeout` wrapper が SIGTERM
    → 10s 経過で SIGKILL。mind_loop.timeout event が emit され、streak が
    count される。streak >= max で auto_kill event + exit 5。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "ai-org-os-home"
        self.home.mkdir()
        (self.home / "config.env").write_text("", encoding="utf-8")
        self.mind_name = "alice"
        self.mind_dir = self.home / "minds" / self.mind_name
        self.mind_dir.mkdir(parents=True)
        # stub: 60 秒 sleep して exit (= 強制的に hang を模す)
        self.slow_stub = self.tmp / "slow-stub"
        self.slow_stub.write_text(
            "#!/usr/bin/env bash\nsleep 60\nexit 0\n", encoding="utf-8"
        )
        self.slow_stub.chmod(0o755)
        self.event_log = self.home / "logs" / "minds" / self.mind_name / "mind-loop.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_events(self) -> list[dict]:
        if not self.event_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.event_log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _run(self, max_cycles: int, timeout_s: int, streak_max: int) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        env["AI_ORG_OS_CLAUDE_BIN"] = str(self.slow_stub)
        env["AI_ORG_OS_LOOP_PERIOD"] = "0"
        env["AI_ORG_OS_LOOP_MAX_CYCLES"] = str(max_cycles)
        env["AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT"] = str(timeout_s)
        env["AI_ORG_OS_MIND_LOOP_TIMEOUT_STREAK"] = str(streak_max)
        return subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_timeout_event_emitted_on_slow_claude(self) -> None:
        """timeout=3s で stub が 60s sleep → mind_loop.timeout event が emit。"""
        # streak_max=99 にして auto-kill 経路を回避、1 cycle で観察
        result = self._run(max_cycles=1, timeout_s=3, streak_max=99)
        events = self._read_events()
        timeouts = [e for e in events if e["event"] == "mind_loop.timeout"]
        self.assertEqual(len(timeouts), 1, f"expected 1 timeout event, got {len(timeouts)}\nevents={events}")
        t = timeouts[0]
        self.assertEqual(t["cycle"], 1)
        self.assertEqual(t["timeout_s"], 3)
        # GNU timeout 規約: 最初 SIGTERM (RC 124)、kill-after=10 経過で SIGKILL (RC 137)。
        # stub は exit せず sleep 60 なので、SIGTERM では完了せず SIGKILL に至る可能性が高い。
        self.assertIn(t["signal"], ("SIGTERM", "SIGKILL"))

    def test_streak_increments_on_consecutive_timeouts(self) -> None:
        """連続 timeout で streak が積み上がる。"""
        result = self._run(max_cycles=3, timeout_s=2, streak_max=99)
        events = self._read_events()
        timeouts = [e for e in events if e["event"] == "mind_loop.timeout"]
        # 3 cycle 全て timeout → streak = 1, 2, 3
        self.assertEqual(len(timeouts), 3)
        streaks = [e["streak"] for e in timeouts]
        self.assertEqual(streaks, [1, 2, 3])

    def test_auto_kill_when_streak_reaches_max(self) -> None:
        """streak が max に到達 → mind_loop.auto_kill event + exit 5。"""
        result = self._run(max_cycles=99, timeout_s=2, streak_max=2)
        events = self._read_events()
        # streak=2 で auto_kill → cycle 2 で抜ける
        auto_kills = [e for e in events if e["event"] == "mind_loop.auto_kill"]
        self.assertEqual(len(auto_kills), 1)
        self.assertEqual(auto_kills[0]["reason"], "timeout_streak")
        self.assertEqual(auto_kills[0]["streak"], 2)
        self.assertEqual(auto_kills[0]["max"], 2)
        # exit code 5
        self.assertEqual(result.returncode, 5)

    def test_streak_resets_on_success(self) -> None:
        """1 cycle 成功すれば streak は 0 に戻る。

        stub を「最初の cycle は遅い、2 回目以降は即 exit」に切り替えるのは複雑
        なので、ここでは timeout を大きく取って claude が間に合うケースで
        streak が積まれないことだけ確認する。
        """
        # stub を即 exit に差し替え
        self.slow_stub.write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        self.slow_stub.chmod(0o755)
        result = self._run(max_cycles=2, timeout_s=5, streak_max=99)
        events = self._read_events()
        timeouts = [e for e in events if e["event"] == "mind_loop.timeout"]
        self.assertEqual(len(timeouts), 0)  # どの cycle も timeout していない


@unittest.skipUnless(_bash_available(), "bash required")
class TestMindLoopErrorEventStreak(unittest.TestCase):
    """ADR-0028 §2.2: cycle error event + streak。

    stub claude を意図的に exit non-zero にして、mind_loop.error event 発火と
    streak 連続超過で mind_loop.error_streak_exceeded event 発火を検証。
    timeout streak と違い auto-kill **しない** ことも確認。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "ai-org-os-home"
        self.home.mkdir()
        (self.home / "config.env").write_text("", encoding="utf-8")
        self.mind_name = "alice"
        self.mind_dir = self.home / "minds" / self.mind_name
        self.mind_dir.mkdir(parents=True)
        # stub: 即 exit 2 (= timeout 以外の error をシミュレート)
        self.err_stub = self.tmp / "err-stub"
        self.err_stub.write_text(
            "#!/usr/bin/env bash\nexit 2\n", encoding="utf-8"
        )
        self.err_stub.chmod(0o755)
        self.event_log = self.home / "logs" / "minds" / self.mind_name / "mind-loop.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_events(self) -> list[dict]:
        if not self.event_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.event_log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _run(self, max_cycles: int, error_streak_max: int, claude_bin: Path | None = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        env["AI_ORG_OS_CLAUDE_BIN"] = str(claude_bin or self.err_stub)
        env["AI_ORG_OS_LOOP_PERIOD"] = "0"
        env["AI_ORG_OS_LOOP_MAX_CYCLES"] = str(max_cycles)
        # timeout を無効化して error 経路だけ走らせる
        env["AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT"] = "0"
        env["AI_ORG_OS_MIND_LOOP_ERROR_STREAK"] = str(error_streak_max)
        return subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_error_event_emitted_on_non_zero_exit(self) -> None:
        """stub exit 2 で mind_loop.error event が 1 件 emit される。"""
        result = self._run(max_cycles=1, error_streak_max=99)
        events = self._read_events()
        errs = [e for e in events if e["event"] == "mind_loop.error"]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["cycle"], 1)
        self.assertEqual(errs[0]["exit_code"], 2)
        self.assertEqual(errs[0]["streak"], 1)

    def test_error_streak_increments_consecutive(self) -> None:
        """連続 error で streak が 1,2,3 と積み上がる。"""
        result = self._run(max_cycles=3, error_streak_max=99)
        events = self._read_events()
        errs = [e for e in events if e["event"] == "mind_loop.error"]
        self.assertEqual(len(errs), 3)
        self.assertEqual([e["streak"] for e in errs], [1, 2, 3])

    def test_error_streak_exceeded_event_fires_at_threshold(self) -> None:
        """streak が max に到達で mind_loop.error_streak_exceeded event が emit。
        auto-kill **しない** (= exit 5 ではない)。"""
        result = self._run(max_cycles=2, error_streak_max=2)
        events = self._read_events()
        exceeded = [e for e in events if e["event"] == "mind_loop.error_streak_exceeded"]
        self.assertGreaterEqual(len(exceeded), 1)
        self.assertEqual(exceeded[0]["streak"], 2)
        self.assertEqual(exceeded[0]["max"], 2)
        # auto-kill しないので exit code は 0 (= max_cycles 到達で正常終了)
        self.assertEqual(result.returncode, 0)
        # auto_kill event は無い
        auto_kills = [e for e in events if e["event"] == "mind_loop.auto_kill"]
        self.assertEqual(auto_kills, [])

    def test_error_streak_resets_on_success(self) -> None:
        """成功 (exit 0) で streak が reset、再度 error すると 1 から数え直し。
        single test では切替できないので、ここは「成功 stub では error event ゼロ」を確認。"""
        ok_stub = self.tmp / "ok-stub"
        ok_stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        ok_stub.chmod(0o755)
        result = self._run(max_cycles=3, error_streak_max=99, claude_bin=ok_stub)
        events = self._read_events()
        errs = [e for e in events if e["event"] == "mind_loop.error"]
        self.assertEqual(len(errs), 0)


@unittest.skipUnless(_bash_available(), "bash required")
class TestMindLoopNotifyHuman(unittest.TestCase):
    """ADR-0028 §2.3 L1: notify-human channel が `$AI_ORG_OS_HOME/logs/notify.jsonl`
    に書かれる。

    error_streak_exceeded (warning) と auto_kill (critical) の 2 経路を検証。
    schema: { ts, severity, source, actor, event, message, ...event-specific... }
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "ai-org-os-home"
        self.home.mkdir()
        (self.home / "config.env").write_text("", encoding="utf-8")
        self.mind_name = "alice"
        self.mind_dir = self.home / "minds" / self.mind_name
        self.mind_dir.mkdir(parents=True)
        self.notify_log = self.home / "logs" / "notify.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_notify(self) -> list[dict]:
        if not self.notify_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.notify_log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _make_stub(self, content: str) -> Path:
        p = self.tmp / "stub"
        p.write_text(content, encoding="utf-8")
        p.chmod(0o755)
        return p

    def test_no_notify_on_normal_cycles(self) -> None:
        """successful cycle では notify.jsonl は作られない / 空。"""
        stub = self._make_stub("#!/usr/bin/env bash\nexit 0\n")
        env = os.environ.copy()
        env.update(
            AI_ORG_OS_HOME=str(self.home),
            AI_ORG_OS_CLAUDE_BIN=str(stub),
            AI_ORG_OS_LOOP_PERIOD="0",
            AI_ORG_OS_LOOP_MAX_CYCLES="2",
            AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT="0",
        )
        subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(self._read_notify(), [])

    def test_notify_warning_on_error_streak(self) -> None:
        """error streak 超過で notify.jsonl に severity=warning entry。"""
        stub = self._make_stub("#!/usr/bin/env bash\nexit 2\n")
        env = os.environ.copy()
        env.update(
            AI_ORG_OS_HOME=str(self.home),
            AI_ORG_OS_CLAUDE_BIN=str(stub),
            AI_ORG_OS_LOOP_PERIOD="0",
            AI_ORG_OS_LOOP_MAX_CYCLES="2",
            AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT="0",
            AI_ORG_OS_MIND_LOOP_ERROR_STREAK="2",
        )
        subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env, capture_output=True, text=True, timeout=60,
        )
        notify = self._read_notify()
        self.assertGreaterEqual(len(notify), 1)
        # 最初の notify entry を検証
        n = notify[0]
        self.assertEqual(n["severity"], "warning")
        self.assertEqual(n["source"], "mind-loop")
        self.assertEqual(n["actor"], "alice")
        self.assertEqual(n["event"], "mind_loop.error_streak_exceeded")
        self.assertIn("Mind 'alice'", n["message"])
        self.assertEqual(n["streak"], 2)
        self.assertEqual(n["max"], 2)
        # ts は ISO-8601 ms precision Z 形式
        self.assertRegex(n["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

    @unittest.skipUnless(shutil.which("timeout") is not None, "GNU timeout required")
    def test_notify_critical_on_auto_kill(self) -> None:
        """timeout streak で auto-kill 経路、notify.jsonl に severity=critical。"""
        slow_stub = self._make_stub("#!/usr/bin/env bash\nsleep 60\nexit 0\n")
        env = os.environ.copy()
        env.update(
            AI_ORG_OS_HOME=str(self.home),
            AI_ORG_OS_CLAUDE_BIN=str(slow_stub),
            AI_ORG_OS_LOOP_PERIOD="0",
            AI_ORG_OS_LOOP_MAX_CYCLES="99",
            AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT="2",
            AI_ORG_OS_MIND_LOOP_TIMEOUT_STREAK="2",
        )
        result = subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env, capture_output=True, text=True, timeout=120,
        )
        # auto-kill で exit 5
        self.assertEqual(result.returncode, 5)
        notify = self._read_notify()
        criticals = [n for n in notify if n["severity"] == "critical"]
        self.assertEqual(len(criticals), 1)
        n = criticals[0]
        self.assertEqual(n["event"], "mind_loop.auto_kill")
        self.assertEqual(n["actor"], "alice")
        self.assertIn("auto-killed", n["message"])
        self.assertEqual(n["reason"], "timeout_streak")
        self.assertEqual(n["streak"], 2)

    def test_notify_jsonl_valid_json_per_line(self) -> None:
        """notify.jsonl の各行が valid JSON (= 1 line 1 event)。"""
        stub = self._make_stub("#!/usr/bin/env bash\nexit 2\n")
        env = os.environ.copy()
        env.update(
            AI_ORG_OS_HOME=str(self.home),
            AI_ORG_OS_CLAUDE_BIN=str(stub),
            AI_ORG_OS_LOOP_PERIOD="0",
            AI_ORG_OS_LOOP_MAX_CYCLES="3",
            AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT="0",
            AI_ORG_OS_MIND_LOOP_ERROR_STREAK="1",
        )
        subprocess.run(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env, capture_output=True, text=True, timeout=60,
        )
        raw = self.notify_log.read_text(encoding="utf-8")
        lines = [line for line in raw.splitlines() if line]
        # 3 cycle 全 error、streak_max=1 なので 3 件 notify
        self.assertEqual(len(lines), 3)
        for line in lines:
            json.loads(line)  # parse 失敗で test fail


class TestPeekInboxUnit(unittest.TestCase):
    """peek_inbox.py の pure helper (_truncate / _summarize) を単体テスト。
    bash subprocess を回さないので速い。
    """

    def setUp(self) -> None:
        # peek_inbox.py を import するために conduit dir を sys.path に追加
        conduit = Path(__file__).resolve().parent.parent / "conduit"
        if str(conduit) not in sys.path:
            sys.path.insert(0, str(conduit))

    def test_truncate_below_limit_unchanged(self) -> None:
        from peek_inbox import _truncate  # noqa: PLC0415
        self.assertEqual(_truncate("hello", 10), "hello")

    def test_truncate_above_limit_with_ellipsis(self) -> None:
        from peek_inbox import _truncate  # noqa: PLC0415
        # limit=8 → "abcde..." (5 + "...")
        self.assertEqual(_truncate("abcdefghij", 8), "abcde...")
        self.assertEqual(len(_truncate("abcdefghij", 8)), 8)

    def test_truncate_zero_limit_returns_empty(self) -> None:
        from peek_inbox import _truncate  # noqa: PLC0415
        self.assertEqual(_truncate("x" * 100, 0), "")
        self.assertEqual(_truncate("x" * 100, -1), "")

    def test_truncate_limit_le_3_no_ellipsis(self) -> None:
        """limit <= 3 では '...' すら入らないので素直に切る。"""
        from peek_inbox import _truncate  # noqa: PLC0415
        self.assertEqual(_truncate("hello", 3), "hel")
        self.assertEqual(_truncate("hello", 1), "h")

    def test_summarize_truncates_long_topic(self) -> None:
        from peek_inbox import _summarize, MAX_TOPIC_CHARS_PER_ENTRY  # noqa: PLC0415
        entries = [("sender", "X" * 500)]
        result = _summarize(entries, total=1)
        # topic 部分は 80 文字以内 (... 末尾込み)
        self.assertIn(f"from sender '{'X' * (MAX_TOPIC_CHARS_PER_ENTRY - 3)}...", result)
        self.assertNotIn("X" * 200, result)

    def test_summarize_bounded_total_size(self) -> None:
        """5 件全部 100 字 topic でも合計 MAX_TOTAL_SUMMARY_CHARS を超えない。"""
        from peek_inbox import _summarize, MAX_TOTAL_SUMMARY_CHARS  # noqa: PLC0415
        entries = [(f"s{i}", "Y" * 100) for i in range(5)]
        result = _summarize(entries, total=5)
        self.assertLessEqual(len(result), MAX_TOTAL_SUMMARY_CHARS)

    def test_summarize_uses_total_for_more_marker(self) -> None:
        """entries は 5 件しか持たないが total は実件数、'(+N more)' は total ベース。"""
        from peek_inbox import _summarize  # noqa: PLC0415
        entries = [(f"s{i}", f"t{i}") for i in range(5)]
        result = _summarize(entries, total=12)  # 12 件中 5 件表示
        self.assertIn("12 pending dispatch(es)", result)
        self.assertIn("(+7 more)", result)

    def test_parse_frontmatter_skips_body(self) -> None:
        """Codex P2 fixup-2: _parse_frontmatter_line は frontmatter 終了 (2 度目の
        ---) で読み込みを止め、巨大 body には触れない。
        """
        import tempfile  # noqa: PLC0415
        from peek_inbox import _parse_frontmatter_line  # noqa: PLC0415
        # 10MB の body を仕込む — フルロードしたら遅い / メモリ食う
        body_size = 10 * 1024 * 1024
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tf:
            tf.write("---\n")
            tf.write("from: sender-big\n")
            tf.write("topic: small topic\n")
            tf.write("---\n\n")
            tf.write("X" * body_size)
            path = Path(tf.name)
        try:
            from_, topic = _parse_frontmatter_line(path)
            self.assertEqual(from_, "sender-big")
            self.assertEqual(topic, "small topic")
        finally:
            path.unlink(missing_ok=True)

    def test_main_rejects_invalid_mind_name(self) -> None:
        """path traversal / 規格外 mind_name は validate されて silent skip。"""
        from peek_inbox import main  # noqa: PLC0415
        # 通常は print が走るが、invalid name では走らない (= 戻り値 0、stdout 空)
        # 直接呼ぶ場合、sys.stdout.write を見ないと出力検証は難しいので、
        # main の戻り値だけ確認 (silent skip でも 0 を返す契約)。
        self.assertEqual(main(["peek_inbox.py", "../escape"]), 0)
        self.assertEqual(main(["peek_inbox.py", ""]), 0)
        self.assertEqual(main(["peek_inbox.py", "a" * 100]), 0)  # > 64 chars


if __name__ == "__main__":
    unittest.main()
