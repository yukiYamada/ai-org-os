#!/usr/bin/env python3
"""
test_conductor.py — Conductor Pillar のユニットテスト。

ポイント:
- Anthropic SDK 未インストール環境 / API key 不在環境でも動く
- 他 Pillar (Observation / Inbox / Judgment) を実体として呼び出す統合的テストと、
  client を mock してロジック単体を確認する両建て
- 1 cycle 完走 / signal 停止 / fallback ルートをそれぞれ検証
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from conductor import (  # noqa: E402
    CycleResult,
    _action_breakdown,
    _fallback_judgments,
    run_loop,
    run_one_cycle,
    write_status,
)
from judgment import MindJudgment  # noqa: E402


def _mock_anthropic_message(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


class TestActionBreakdown(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(_action_breakdown([]), {})

    def test_count_by_action(self) -> None:
        js = [
            MindJudgment("a", "ok", "r"),
            MindJudgment("b", "ok", "r"),
            MindJudgment("c", "monitor", "r"),
        ]
        self.assertEqual(_action_breakdown(js), {"ok": 2, "monitor": 1})


class TestFallbackJudgments(unittest.TestCase):
    def test_all_minds_get_monitor(self) -> None:
        snapshot = {"minds": [{"mind_name": "alice"}, {"mind_name": "bob"}]}
        result, reason = _fallback_judgments(snapshot, "test-reason")
        self.assertEqual(reason, "test-reason")
        self.assertEqual(len(result), 2)
        for j in result:
            self.assertEqual(j.action, "monitor")
            self.assertIn("test-reason", j.reason)

    def test_skips_empty_mind_name(self) -> None:
        snapshot = {"minds": [{"mind_name": ""}, {"mind_name": "ok"}]}
        result, _ = _fallback_judgments(snapshot, "r")
        self.assertEqual([j.mind_name for j in result], ["ok"])

    def test_handles_non_dict_snapshot(self) -> None:
        result, _ = _fallback_judgments(None, "r")  # type: ignore[arg-type]
        self.assertEqual(result, [])


class TestRunOneCycle(unittest.TestCase):
    def setUp(self) -> None:
        # tmp 環境を 1 つの workspace dir にまとめる:
        #   tmp/issues/{inbox,archive}/
        #   tmp/snapshots/
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.issues_dir = self.workspace / "issues"
        self.snapshots_dir = self.workspace / "snapshots"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cycle_with_no_minds_skips_judgment(self) -> None:
        """Mind が居ない (snapshot 空) なら judgment は skipped で OK。

        注: gather_observations は module-level MINDS_DIR (本物の runtime/minds) を
        読むため、テスト隔離のため load_snapshot を patch して空 snapshot を返す。
        """
        client = MagicMock()
        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = {"minds": []}

            result = run_one_cycle(
                1,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )
        self.assertEqual(result.cycle, 1)
        self.assertEqual(result.judgment_status, "skipped")
        self.assertEqual(result.judgments_count, 0)
        # snapshot は試みている (mock とはいえ path が返る)
        self.assertIsNotNone(result.snapshot_path)
        # client は呼ばれない (Mind 居ないなら判定要らない)
        client.messages.create.assert_not_called()

    def test_cycle_fallback_when_client_raises(self) -> None:
        """judge_snapshot 内で client が例外を投げると fallback-error 経路。

        Mind が居ない場合 judgment は skipped になるので、Mind を 1 つ仕込む。
        最も手っ取り早く: runtime/minds/<name>/.mind-meta.md を本物の場所に作る…
        は副作用が大きいので、Conductor の judge_snapshot を mock する。
        """
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}

        # write_snapshot / load_snapshot / judge_snapshot をモジュール経由で patch
        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor.judge_snapshot") as mock_judge:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload
            mock_judge.side_effect = RuntimeError("boom")

            client = MagicMock()
            result = run_one_cycle(
                42,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        self.assertEqual(result.cycle, 42)
        self.assertEqual(result.judgment_status, "fallback-error")
        self.assertIn("boom", result.judgment_error or "")
        # fallback で 1 件は出る (Mind 数 = 1)
        self.assertEqual(result.judgments_count, 1)
        self.assertEqual(result.judgments_action_breakdown, {"monitor": 1})

    def test_cycle_fallback_when_no_api_key(self) -> None:
        """client=None で make_client が AnthropicNotConfigured を投げたら fallback。"""
        snapshot_payload = {"minds": [{"mind_name": "bob"}]}

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor.make_client") as mock_make:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload
            from judgment import AnthropicNotConfigured
            mock_make.side_effect = AnthropicNotConfigured("no key")

            result = run_one_cycle(
                7,
                client=None,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        self.assertEqual(result.judgment_status, "fallback-no-key")
        self.assertEqual(result.judgments_count, 1)

    def test_cycle_happy_path_with_mocked_client(self) -> None:
        """mocked client が valid 応答 → judgment_status='ok'。"""
        snapshot_payload = {
            "minds": [
                {"mind_name": "alice"},
                {"mind_name": "bob"},
            ]
        }

        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_message(
            '[{"mind_name":"alice","action":"ok","reason":"r"},'
            '{"mind_name":"bob","action":"investigate","reason":"r"}]'
        )

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        self.assertEqual(result.judgment_status, "ok")
        self.assertEqual(result.judgments_count, 2)
        self.assertEqual(result.judgments_action_breakdown, {"ok": 1, "investigate": 1})

    def test_cycle_uses_realm_report_when_available(self) -> None:
        """Phase 5e: build_realm_report が成功すると judgment_input は
        v1.0 統合 report (= flow / anomaly 含む) になる。
        judge_snapshot に渡される dict を spy して anomaly が含まれることを assertion。
        """
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        realm_report = {
            "schema_version": "1.0",
            "generated_at": "2026-05-29T00:00:00Z",
            "minds": [{"mind_name": "alice"}],
            "flow": [],
            "resource": [],
            "anomaly": [{"code": "W3", "level": "warning",
                         "mind": "alice", "message": "orphan kind"}],
        }
        captured: dict = {}

        def spy_judge(report, **kwargs):
            captured["report"] = report
            from judgment import MindJudgment
            return [MindJudgment("alice", "investigate", "W3 cited")]

        client = MagicMock()
        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor.build_realm_report") as mock_report, \
             patch("conductor.judge_snapshot") as mock_judge:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload
            mock_report.return_value = realm_report
            mock_judge.side_effect = spy_judge

            result = run_one_cycle(
                99, client=client,
                issues_dir=self.issues_dir, snapshots_dir=self.snapshots_dir,
            )

        # build_realm_report が呼ばれた
        mock_report.assert_called_once()
        # judge_snapshot に渡された dict が v1.0 report (= anomaly 含む)
        self.assertEqual(captured["report"].get("schema_version"), "1.0")
        self.assertEqual(len(captured["report"].get("anomaly", [])), 1)
        # 判定結果は正常に処理される
        self.assertEqual(result.judgment_status, "ok")
        self.assertEqual(result.judgments_action_breakdown, {"investigate": 1})

    def test_cycle_falls_back_to_snapshot_when_report_empty(self) -> None:
        """Phase 5e 防御: build_realm_report が空 minds を返すなら snapshot を
        使う (= 観測漏れで judgment が 0 件入力 skipped になるのを防ぐ)。
        """
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        empty_report = {
            "schema_version": "1.0",
            "minds": [],  # 観測漏れを模倣
            "flow": [], "resource": [], "anomaly": [],
        }
        captured: dict = {}

        def spy_judge(report, **kwargs):
            captured["report"] = report
            from judgment import MindJudgment
            return [MindJudgment("alice", "ok", "healthy")]

        client = MagicMock()
        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor.build_realm_report") as mock_report, \
             patch("conductor.judge_snapshot") as mock_judge:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload
            mock_report.return_value = empty_report
            mock_judge.side_effect = spy_judge

            result = run_one_cycle(
                100, client=client,
                issues_dir=self.issues_dir, snapshots_dir=self.snapshots_dir,
            )

        # snapshot にフォールバック (schema_version 無し、v0.1 形式)
        self.assertNotIn("schema_version", captured["report"])
        self.assertEqual(len(captured["report"]["minds"]), 1)
        # judgement_status は ok (skipped にならない)
        self.assertEqual(result.judgment_status, "ok")

    def test_cycle_handles_inbox_failure(self) -> None:
        """inbox poll が例外でも cycle は完走する。"""
        with patch("conductor.list_pending_issues") as mock_inbox, \
             patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load:
            mock_inbox.side_effect = RuntimeError("fs error")
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = {"minds": []}

            result = run_one_cycle(
                1,
                client=MagicMock(),
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        # pending=-1 は「取得失敗」マーカー
        self.assertEqual(result.pending_issues, -1)
        # それでも snapshot は試みている。Mind 0 件なので skipped。
        self.assertEqual(result.judgment_status, "skipped")


class TestWriteStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "conductor-status.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _sample_result(self) -> CycleResult:
        return CycleResult(
            cycle=3,
            started_at="2026-05-24T01:00:00Z",
            ended_at="2026-05-24T01:00:01Z",
            pending_issues=2,
            snapshot_path="/tmp/snap.json",
            judgments_count=5,
            judgments_action_breakdown={"ok": 3, "monitor": 2},
            judgment_status="ok",
            judgment_error=None,
        )

    def test_writes_json_with_schema(self) -> None:
        write_status(self._sample_result(), target=self.path, total_cycles=10)
        self.assertTrue(self.path.exists())
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "conductor-status/v1")
        self.assertEqual(payload["total_cycles"], 10)
        self.assertEqual(payload["last_cycle"]["cycle"], 3)

    def test_atomic_write_no_tmp_residue(self) -> None:
        write_status(self._sample_result(), target=self.path)
        # tmp 残骸が無い
        residues = list(self.path.parent.glob("*.tmp"))
        self.assertEqual(residues, [])

    def test_creates_parent_dir(self) -> None:
        nested = self.path.parent / "nested" / "status.json"
        write_status(self._sample_result(), target=nested)
        self.assertTrue(nested.exists())


class TestRunLoop(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.status = self.workspace / "status.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_max_cycles_stops_after_limit(self) -> None:
        # client は使われないが、念のため mock 渡し
        cycles = run_loop(
            period_s=0,
            max_cycles=3,
            status_path=self.status,
            issues_dir=self.workspace / "issues",
            snapshots_dir=self.workspace / "snapshots",
            client=MagicMock(),
        )
        self.assertEqual(cycles, 3)
        # status JSON が書かれた
        self.assertTrue(self.status.exists())
        payload = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertEqual(payload["total_cycles"], 3)
        self.assertEqual(payload["last_cycle"]["cycle"], 3)


if __name__ == "__main__":
    unittest.main()
