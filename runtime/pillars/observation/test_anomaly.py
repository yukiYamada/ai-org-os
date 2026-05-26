"""
test_anomaly.py — anomaly.py の各シグナル検知のユニットテスト (Observation v0.3 / #67)。

検証する性質 (各シグナル true / false ケース):
- W2: 他 Mind 名のディレクトリ/ファイルが Mindspace に紛れ込んでいる
- W3: .mind-meta.md の kind が registered kinds に無い (孤児 Mind)
- W1: Mindspace mtime 更新あり / dispatch 無し → info で警告
- I1: snapshot diff で stale 新規遷移
- I2: unread inbox 蓄積閾値超
- diff_snapshots: added / removed / changed のキー整合

標準ライブラリのみ。
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import anomaly  # noqa: E402


def _mk_mind(
    home: Path,
    name: str,
    *,
    kind: str = "generic",
    persona: str = "designer",
    guild: str = "default",
    with_meta: bool = True,
    spawned_at: str = "2026-05-26T00:00:00Z",
    extra_files: list[tuple[str, bytes]] | None = None,
) -> Path:
    """tmp $AI_ORG_OS_HOME に Mind dir を作る。"""
    d = home / "minds" / name
    d.mkdir(parents=True, exist_ok=True)
    if with_meta:
        (d / ".mind-meta.md").write_text(
            f"---\nmind_name: {name}\nkind: {kind}\npersona: {persona}\n"
            f"guild: {guild}\nspawned_at: {spawned_at}\n---\n",
            encoding="utf-8",
        )
        reg = home / "registry" / "minds"
        reg.mkdir(parents=True, exist_ok=True)
        (reg / f"{name}.md").write_text(
            f"---\nmind_name: {name}\nkind: {kind}\npersona: {persona}\n"
            f"guild: {guild}\nspawned_at: {spawned_at}\n---\n",
            encoding="utf-8",
        )
    if extra_files:
        for rel, content in extra_files:
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
    return d


def _write_dispatch(
    home: Path, sender: str, recipient: str,
    *, dispatched_at: str, msg_id: str = "m1", state: str = "inbox",
) -> Path:
    rec_dir = home / "conduit-storage" / state / recipient
    rec_dir.mkdir(parents=True, exist_ok=True)
    p = rec_dir / f"{msg_id}.md"
    p.write_text(
        f"---\nfrom: {sender}\nto: {recipient}\ntopic: t\n"
        f"dispatched_at: {dispatched_at}\nmsg_id: {msg_id}\n---\nbody\n",
        encoding="utf-8",
    )
    return p


class _HomeFixture(unittest.TestCase):
    """AI_ORG_OS_HOME を tmp に切り替える共通 fixture。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        self.tmp.cleanup()


class TestDetectW2ForeignMindDir(_HomeFixture):

    def test_no_foreign_dir_yields_no_signal(self) -> None:
        _mk_mind(self.home, "alice")
        _mk_mind(self.home, "bob")
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w2_foreign_mind_dir(self.home)
        self.assertEqual(signals, [])

    def test_foreign_mind_dir_detected(self) -> None:
        """alice の Mindspace 直下に bob/ がある → W2 warning"""
        _mk_mind(self.home, "alice")
        _mk_mind(self.home, "bob")
        # alice の Mindspace に bob/ を作る
        (self.home / "minds" / "alice" / "bob").mkdir()
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w2_foreign_mind_dir(self.home)
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s.code, "W2")
        self.assertEqual(s.level, "warning")
        self.assertEqual(s.mind, "alice")
        self.assertIn("bob", s.message)

    def test_foreign_mind_file_detected(self) -> None:
        """dir でも file でも他 Mind 名の entry は W2"""
        _mk_mind(self.home, "alice")
        _mk_mind(self.home, "bob")
        (self.home / "minds" / "alice" / "bob").write_text("x", encoding="utf-8")
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w2_foreign_mind_dir(self.home)
        self.assertEqual(len(signals), 1)

    def test_self_named_dir_ignored(self) -> None:
        """alice の Mindspace 内に alice/ があっても自己名なので除外"""
        _mk_mind(self.home, "alice")
        _mk_mind(self.home, "bob")
        (self.home / "minds" / "alice" / "alice").mkdir()
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w2_foreign_mind_dir(self.home)
        self.assertEqual(signals, [])


class TestDetectW3OrphanKind(_HomeFixture):

    def test_registered_kind_no_signal(self) -> None:
        # generic は templates/kinds/generic.md に存在する
        _mk_mind(self.home, "alice", kind="generic")
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w3_orphan_kind(self.home)
        # 他の signal も無いはず
        w3 = [s for s in signals if s.code == "W3"]
        self.assertEqual(w3, [])

    def test_orphan_kind_detected(self) -> None:
        _mk_mind(self.home, "alice", kind="nonexistent-kind")
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w3_orphan_kind(self.home)
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s.code, "W3")
        self.assertEqual(s.level, "warning")
        self.assertEqual(s.mind, "alice")
        self.assertIn("nonexistent-kind", s.message)


class TestDetectW1MtimeWithoutDispatch(_HomeFixture):

    def test_no_recent_mtime_no_signal(self) -> None:
        # Mind は居るが、mtime が古い (window 外) → 検知しない
        _mk_mind(self.home, "alice")
        old_time = time.time() - 86400  # 1 day ago
        for p in (self.home / "minds" / "alice").iterdir():
            os.utime(p, (old_time, old_time))
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w1_mtime_without_dispatch(
                self.home, window_seconds=3600,
            )
        self.assertEqual(signals, [])

    def test_recent_mtime_with_dispatch_no_signal(self) -> None:
        _mk_mind(self.home, "alice")
        # Mind alice 宛に最近の dispatch 1 件 → W1 出ない
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_dispatch(
            self.home, "bob", "alice", dispatched_at=now_iso,
        )
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w1_mtime_without_dispatch(
                self.home, window_seconds=3600,
            )
        self.assertEqual(signals, [])

    def test_recent_mtime_without_dispatch_yields_info(self) -> None:
        """Mindspace mtime あり / dispatch 無し → W1 info"""
        _mk_mind(self.home, "alice")
        # dispatch 無しで mtime のみ最近 (mk_mind が write したばかり)
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_w1_mtime_without_dispatch(
                self.home, window_seconds=3600,
            )
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s.code, "W1")
        self.assertEqual(s.level, "info")  # issue 文面: 誤検知多いので info 降格
        self.assertEqual(s.mind, "alice")


class TestDetectI2InboxBuildup(_HomeFixture):

    def test_under_threshold_no_signal(self) -> None:
        _mk_mind(self.home, "alice")
        for i in range(3):
            _write_dispatch(
                self.home, "bob", "alice",
                dispatched_at="2026-05-26T10:00:00Z", msg_id=f"m{i}",
            )
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_i2_inbox_buildup(
                self.home, threshold=5,
            )
        self.assertEqual(signals, [])

    def test_over_threshold_yields_info(self) -> None:
        _mk_mind(self.home, "alice")
        for i in range(7):
            _write_dispatch(
                self.home, "bob", "alice",
                dispatched_at="2026-05-26T10:00:00Z", msg_id=f"m{i}",
            )
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_i2_inbox_buildup(
                self.home, threshold=5,
            )
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s.code, "I2")
        self.assertEqual(s.level, "info")
        self.assertEqual(s.mind, "alice")
        self.assertIn("7", s.message)
        self.assertIn("5", s.message)


class TestDetectI1NewStale(unittest.TestCase):

    def test_no_stale_transition_no_signal(self) -> None:
        prev = {"minds": [{"mind_name": "alice", "category": "active"}]}
        curr = {"minds": [{"mind_name": "alice", "category": "active"}]}
        self.assertEqual(anomaly.detect_i1_new_stale(prev, curr), [])

    def test_active_to_stale_yields_signal(self) -> None:
        prev = {"minds": [{"mind_name": "alice", "category": "active"}]}
        curr = {"minds": [{"mind_name": "alice", "category": "stale"}]}
        signals = anomaly.detect_i1_new_stale(prev, curr)
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s.code, "I1")
        self.assertEqual(s.level, "info")
        self.assertEqual(s.mind, "alice")
        self.assertIn("active", s.message)

    def test_stale_to_stale_no_signal(self) -> None:
        """既に stale だった Mind は新規発生分でないので報告しない。"""
        prev = {"minds": [{"mind_name": "alice", "category": "stale"}]}
        curr = {"minds": [{"mind_name": "alice", "category": "stale"}]}
        self.assertEqual(anomaly.detect_i1_new_stale(prev, curr), [])

    def test_new_mind_not_reported(self) -> None:
        """curr にだけ居る (= 新規 spawn) Mind は I1 対象外。"""
        prev = {"minds": []}
        curr = {"minds": [{"mind_name": "alice", "category": "stale"}]}
        self.assertEqual(anomaly.detect_i1_new_stale(prev, curr), [])


class TestDiffSnapshots(unittest.TestCase):

    def test_added_removed_changed_keys(self) -> None:
        prev = {"minds": [
            {"mind_name": "alice", "category": "active", "status": "active",
             "unread_inbox_count": 0, "archive_count": 1},
            {"mind_name": "bob", "category": "active", "status": "active",
             "unread_inbox_count": 0, "archive_count": 0},
        ]}
        curr = {"minds": [
            {"mind_name": "alice", "category": "stale", "status": "idle",
             "unread_inbox_count": 5, "archive_count": 1},
            {"mind_name": "carol", "category": "active", "status": "active",
             "unread_inbox_count": 0, "archive_count": 0},
        ]}
        result = anomaly.diff_snapshots(prev, curr)
        # carol が added
        self.assertEqual([m["mind_name"] for m in result["added"]], ["carol"])
        # bob が removed
        self.assertEqual([m["mind_name"] for m in result["removed"]], ["bob"])
        # alice が changed (category / status / unread_inbox_count)
        self.assertEqual(len(result["changed"]), 1)
        ch = result["changed"][0]
        self.assertEqual(ch["mind_name"], "alice")
        self.assertIn("category", ch["fields"])
        self.assertIn("status", ch["fields"])
        self.assertIn("unread_inbox_count", ch["fields"])

    def test_no_change_empty_diff(self) -> None:
        same = {"minds": [{"mind_name": "alice", "category": "active",
                           "status": "active", "unread_inbox_count": 0,
                           "archive_count": 0}]}
        result = anomaly.diff_snapshots(same, same)
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertEqual(result["changed"], [])


class TestDetectAllOrchestration(_HomeFixture):

    def test_empty_realm_no_signals(self) -> None:
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_all(self.home)
        self.assertEqual(signals, [])

    def test_warnings_sorted_before_info(self) -> None:
        """warning が先、info が後 になる sort 順を検証。"""
        # W3 (orphan kind, warning) + W1 (info) を 1 Realm に同居させる
        _mk_mind(self.home, "alice", kind="weird-kind")
        with redirect_stderr(io.StringIO()):
            signals = anomaly.detect_all(
                self.home,
                w1_window_seconds=3600,  # 直前作った Mindspace なので mtime ヒット
            )
        codes = [s.code for s in signals]
        levels = [s.level for s in signals]
        self.assertIn("W3", codes)
        self.assertIn("W1", codes)
        # warning が先
        self.assertEqual(levels[0], "warning")
        # info が同じ並びの後
        last_warning_idx = max(
            i for i, lv in enumerate(levels) if lv == "warning"
        )
        first_info_idx = min(
            (i for i, lv in enumerate(levels) if lv == "info"), default=-1,
        )
        if first_info_idx != -1:
            self.assertLess(last_warning_idx, first_info_idx)


class TestFormatAndJson(unittest.TestCase):

    def test_format_empty(self) -> None:
        self.assertEqual(anomaly.format_signals_table([]), "(no anomalies)")

    def test_format_with_signals(self) -> None:
        signals = [
            anomaly.AnomalySignal("W3", "warning", "alice", "orphan"),
            anomaly.AnomalySignal("I2", "info", "bob", "inbox full"),
        ]
        text = anomaly.format_signals_table(signals)
        self.assertIn("warnings (1)", text)
        self.assertIn("info (1)", text)
        self.assertIn("alice", text)
        self.assertIn("bob", text)

    def test_signals_to_json(self) -> None:
        signals = [anomaly.AnomalySignal("W2", "warning", "x", "y")]
        self.assertEqual(anomaly.signals_to_json(signals), [
            {"code": "W2", "level": "warning", "mind": "x", "message": "y"},
        ])


if __name__ == "__main__":
    unittest.main()
