"""
Regression tests for kill-mind.sh の子プロセスツリー teardown (#133)。

bug 概要:
  mind-loop.sh は subshell `(cd ...; claude -p ...)` で claude を起動する。
  mind-loop の PID にだけ SIGTERM/SIGKILL を送ると、Windows + MSYS bash 環境
  では subshell の死で claude.exe が orphan (parent=init=1) として残る。
  結果 kill-mind.sh の `rm -rf $MIND_DIR` が "Device or resource busy" で失敗。

fix:
  - kill_process_tree() で root PID + 全子孫を kill (taskkill //T or ps PPID 降下)
  - sweep_orphan_minds_for() で MIND_DIR を cwd に持つ orphan も掃除
  - rm -rf 失敗時は clear な error + non-zero exit (F3 / ADR-0013 §1)

test 戦略:
  - spawn-mind.sh は使わず、kill-mind.sh が期待する Mindspace + registry を
    手で組み立てる (= test 対象を kill-mind に絞る)
  - stub claude は `sleep 30` で長時間生存
  - mind-loop.sh を background で起動 → cycle が走り始めるのを待つ
  - kill-mind.sh を実行 → 全プロセス消滅 + Mindspace 削除を assert

Standard library only。

Run:
  cd runtime/pillars/lifecycle && python -m unittest test_kill_mind_orphans
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MIND_LOOP_SH = SCRIPT_DIR / "mind-loop.sh"
KILL_MIND_SH = SCRIPT_DIR / "kill-mind.sh"


def _bash_available() -> bool:
    """bash が PATH に居るか。Windows GitHub Actions runner には居る。"""
    return shutil.which("bash") is not None


def _bash_pid_alive(pid: int) -> bool:
    """
    bash の `kill -0 <pid>` で PID 生存を確認する。

    Windows + MSYS bash 環境で `$$` が MSYS PID を返し、native Python から
    そのまま見えない問題を回避する。bash 経由で kill -0 を呼ぶと bash の
    name space で評価されるので、mind-loop が pidfile に書いた MSYS PID と
    一致する。
    """
    if pid <= 0:
        return False
    try:
        rc = subprocess.run(
            ["bash", "-c", f"kill -0 {int(pid)} 2>/dev/null"],
            capture_output=True,
            timeout=10,
        )
        return rc.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@unittest.skipUnless(_bash_available(), "bash not available in PATH")
class TestKillMindOrphans(unittest.TestCase):
    """kill-mind.sh が mind-loop の子孫 (claude.exe) も含めて teardown する。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "ai-org-os-home"
        self.home.mkdir()
        self.mind_name = "orphan-test-mind"

        # Mindspace を手動で組み立てる (spawn-mind.sh は使わない:
        # workspace/persona/guild 等の依存を増やしたくないため)。
        self.mind_dir = self.home / "minds" / self.mind_name
        self.mind_dir.mkdir(parents=True)

        # registry entry も手で作る (kill-mind が registry を削除する path も
        # 覆うため)。Pillar registry の最小 frontmatter。
        self.registry_dir = self.home / "registry" / "minds"
        self.registry_dir.mkdir(parents=True)
        self.registry_entry = self.registry_dir / f"{self.mind_name}.md"
        self.registry_entry.write_text(
            "---\nname: " + self.mind_name + "\n---\n", encoding="utf-8"
        )

        # stub claude binary: 長時間 sleep する (= mind-loop の cycle 中に
        # 「ぶら下がる」状態を再現)。
        # POSIX (含む MSYS bash) で実行されるので bash shebang で OK。
        self.stub_bin = self.tmp / "stub-claude-sleeper"
        self.stub_bin.write_text(
            "#!/usr/bin/env bash\n"
            "# 長時間 sleep して mind-loop の cycle を「ぶら下げる」。\n"
            "# kill-mind が来たらこの sleep ごと殺されることを期待。\n"
            "echo 'stub-claude-sleeper started'\n"
            "sleep 30\n",
            encoding="utf-8",
        )
        self.stub_bin.chmod(0o755)

        self._loop_proc: subprocess.Popen[str] | None = None

    def tearDown(self) -> None:
        # safeguard: もし test 失敗で loop が残っていれば掃除する。
        if self._loop_proc and self._loop_proc.poll() is None:
            try:
                self._loop_proc.kill()
                self._loop_proc.wait(timeout=5)
            except subprocess.SubprocessError:
                pass
        # Close lingering pipe FDs to avoid ResourceWarning.
        if self._loop_proc:
            for fd in (self._loop_proc.stdout, self._loop_proc.stderr, self._loop_proc.stdin):
                if fd is not None:
                    try:
                        fd.close()
                    except OSError:
                        pass
        self._tmp.cleanup()

    def _start_loop(self) -> subprocess.Popen[str]:
        """mind-loop.sh を background で起動。"""
        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        env["AI_ORG_OS_CLAUDE_BIN"] = str(self.stub_bin)
        env["AI_ORG_OS_LOOP_PERIOD"] = "1"
        env["AI_ORG_OS_LOOP_MAX_CYCLES"] = "0"  # 無限
        # close_fds は POSIX default True、Windows でも問題なし。
        # Windows の Japanese locale (cp932) で stub claude の出力を decode する
        # 際に Unicode error が出るのを防ぐため、明示的に utf-8 + errors=replace。
        proc = subprocess.Popen(
            ["bash", str(MIND_LOOP_SH), self.mind_name],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._loop_proc = proc
        return proc

    def _wait_for_pidfile(self, timeout_s: float = 10.0) -> int:
        """mind-loop が pidfile を書くのを待ち、PID を返す。"""
        pidfile = self.mind_dir / ".mind-loop.pid"
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if pidfile.exists():
                txt = pidfile.read_text(encoding="utf-8").strip()
                if txt:
                    try:
                        return int(txt)
                    except ValueError:
                        pass
            time.sleep(0.2)
        raise AssertionError(f"pidfile {pidfile} did not appear within {timeout_s}s")

    def _wait_for_stub_to_run(self, timeout_s: float = 15.0) -> None:
        """stub claude が起動して mind-loop.log に痕跡を残すのを待つ。"""
        log = self.mind_dir / "mind-loop.log"
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if log.exists():
                content = log.read_text(encoding="utf-8", errors="replace")
                if "stub-claude-sleeper started" in content:
                    return
            time.sleep(0.5)
        raise AssertionError(
            f"stub claude did not start within {timeout_s}s; log={log.read_text(encoding='utf-8', errors='replace') if log.exists() else '<missing>'}"
        )

    def _run_kill_mind(self) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["AI_ORG_OS_HOME"] = str(self.home)
        return subprocess.run(
            ["bash", str(KILL_MIND_SH), self.mind_name],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    def test_kill_mind_removes_mindspace_with_running_stub(self) -> None:
        """
        Full lifecycle: mind-loop + stub claude が走っている状態で kill-mind を
        実行し、(a) loop が消える、(b) Mindspace が消える、(c) registry が消える、
        (d) exit code 0 を assert する。
        """
        self._start_loop()
        loop_pid = self._wait_for_pidfile()
        self._wait_for_stub_to_run()

        # この時点で loop_pid と stub claude の両方が生存しているはず。
        self.assertTrue(_bash_pid_alive(loop_pid), "mind-loop should be alive before kill")

        # kill-mind 実行。
        result = self._run_kill_mind()

        # (d) exit code 0
        self.assertEqual(
            result.returncode,
            0,
            f"kill-mind failed:\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        # (b) Mindspace が消えている
        self.assertFalse(
            self.mind_dir.exists(),
            f"Mindspace {self.mind_dir} should be gone after kill-mind",
        )

        # (c) registry entry が消えている
        self.assertFalse(
            self.registry_entry.exists(),
            f"registry entry {self.registry_entry} should be gone after kill-mind",
        )

        # (a) loop が消えている — kill-mind 終了直後は OS の reap が遅延するので
        #     最大 5s 待つ。
        deadline = time.time() + 5.0
        while time.time() < deadline and _bash_pid_alive(loop_pid):
            time.sleep(0.2)
        self.assertFalse(
            _bash_pid_alive(loop_pid), f"mind-loop pid {loop_pid} should be gone after kill-mind"
        )

        # loop_proc は kill-mind が始末してくれたはず。wait で reap する。
        if self._loop_proc:
            try:
                self._loop_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.fail(
                    f"loop_proc {self._loop_proc.pid} did not exit even after kill-mind"
                )

    def test_kill_mind_idempotent_when_pidfile_missing(self) -> None:
        """
        PID file が無い (mind-loop が走っていない) Mindspace でも kill-mind は
        正常に Mindspace を削除する (regression guard: sweep が PID file 不在で
        skip しないことを保証)。
        """
        # mind-loop は起動しない。PID file も書かない。
        # ただし Mindspace 内に何か file は置く (rm -rf 動作確認)。
        (self.mind_dir / "dummy.txt").write_text("hello", encoding="utf-8")

        result = self._run_kill_mind()
        self.assertEqual(
            result.returncode,
            0,
            f"kill-mind failed:\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertFalse(self.mind_dir.exists())
        self.assertFalse(self.registry_entry.exists())


if __name__ == "__main__":
    unittest.main()
