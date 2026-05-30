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
import os
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
        # Issue #116: Phase 5e Step A 以降、run_one_cycle は build_realm_report
        # を module-top で呼ぶ。build_realm_report は _runtime_home() →
        # $AI_ORG_OS_HOME (デフォルト ~/.ai-org-os) を見るため、テストが
        # 走るホストに実 Mind が居ると report が現実の minds を巻き込み
        # judgment が fallback-error に倒れる。setUp で AI_ORG_OS_HOME を
        # tempdir に向けて isolation を取り直す。
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = str(self.workspace)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
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


class TestActuateDispatches(unittest.TestCase):
    """Phase 5e Step B: action=dispatch-prompt の actuator 経路。

    Conduit Pillar の send_dispatch を patch して呼び出しが正しく行われる
    ことを検証。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.snapshots_dir = Path(self.tmp.name) / "snapshots"
        self.snapshots_dir.mkdir()
        self.issues_dir = Path(self.tmp.name) / "issues"
        self.issues_dir.mkdir()
        # Issue #116: build_realm_report が実 $AI_ORG_OS_HOME を読みに行く
        # 漏れを塞ぐ (TestRunOneCycle と同じ理由)。
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = self.tmp.name
        # Issue #113: actuator が registry check するので、判定対象 Mind を
        # registry に登録扱いにしておく。テストごとに必要な Mind を _register
        # で追加。
        self.registry_minds = Path(self.tmp.name) / "registry" / "minds"
        self.registry_minds.mkdir(parents=True)

    def _register(self, mind_name: str) -> None:
        """Test helper: registry/minds/<name>.md を作って Mind 登録扱いにする。
        kill-mind.sh / spawn-mind.sh の registry layout に揃える。"""
        (self.registry_minds / f"{mind_name}.md").write_text(
            f"---\nmind_name: {mind_name}\n---\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        self.tmp.cleanup()

    def test_dispatch_prompt_invokes_conduit_send_dispatch(self) -> None:
        self._register("alice")
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_message(
            '[{"mind_name":"alice","action":"dispatch-prompt","reason":"silent",'
            '"dispatch_topic":"status?","dispatch_body":"What are you doing?"}]'
        )

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor._send_dispatch_via_conduit") as mock_send:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["to_mind"], "alice")
        self.assertEqual(kwargs["topic"], "status?")
        self.assertEqual(kwargs["body"], "What are you doing?")
        self.assertEqual(result.dispatches_sent, 1)
        self.assertEqual(
            result.judgments_action_breakdown, {"dispatch-prompt": 1}
        )

    def test_dispatch_failure_does_not_abort_cycle(self) -> None:
        """send_dispatch が 1 件失敗しても、他 Mind の dispatch は試みられ
        cycle は完走する (ADR-0013 §1 F3)。"""
        self._register("alice")
        self._register("bob")
        snapshot_payload = {
            "minds": [
                {"mind_name": "alice"},
                {"mind_name": "bob"},
            ]
        }
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_message(
            '[{"mind_name":"alice","action":"dispatch-prompt","reason":"r",'
            '"dispatch_topic":"t","dispatch_body":"b1"},'
            '{"mind_name":"bob","action":"dispatch-prompt","reason":"r",'
            '"dispatch_topic":"t","dispatch_body":"b2"}]'
        )

        # alice には storage 異常、bob は成功する想定
        def fake_send(*, to_mind: str, topic: str, body: str) -> None:
            if to_mind == "alice":
                raise RuntimeError("storage write failed")

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor._send_dispatch_via_conduit", side_effect=fake_send):
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        # bob だけが成功カウントされる
        self.assertEqual(result.dispatches_sent, 1)
        self.assertEqual(result.judgment_status, "ok")

    def test_no_dispatch_when_no_dispatch_prompt_action(self) -> None:
        """通常の ok / monitor 判定では send_dispatch は呼ばれない (= 後方互換)。"""
        self._register("alice")
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_message(
            '[{"mind_name":"alice","action":"ok","reason":"healthy"}]'
        )

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor._send_dispatch_via_conduit") as mock_send:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        mock_send.assert_not_called()
        self.assertEqual(result.dispatches_sent, 0)

    def test_warden_sender_name_locked(self) -> None:
        """sender 名は "warden" 固定 (judgment.py 側の system prompt と
        Mind 側 inbox 観測が一致する必要があるため)。"""
        from conductor import WARDEN_SENDER_NAME
        self.assertEqual(WARDEN_SENDER_NAME, "warden")

    def test_skip_dispatch_when_mind_not_registered(self) -> None:
        """Issue #113: judgment 時点で snapshot に居ても registry 不在なら
        skip。kill-mind が registry → conduit-storage の順なので、registry
        不在 = kill 進行中。dispatch を送ると空 inbox dir が再生成され
        kill 後にゴミが残る (ADR-0023 違反)。"""
        # alice は意図的に _register しない (= 不在)
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_message(
            '[{"mind_name":"alice","action":"dispatch-prompt","reason":"r",'
            '"dispatch_topic":"t","dispatch_body":"b"}]'
        )

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor._send_dispatch_via_conduit") as mock_send:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        # send_dispatch は呼ばれない、dispatches_sent=0、cycle は完走
        mock_send.assert_not_called()
        self.assertEqual(result.dispatches_sent, 0)
        self.assertEqual(result.judgment_status, "ok")

    def test_partial_skip_when_some_minds_unregistered(self) -> None:
        """alice (登録あり) と carol (登録なし) が両方 dispatch-prompt 対象
        の場合、alice には送り、carol は skip する (= partial actuation)。"""
        self._register("alice")
        # carol は意図的に _register しない
        snapshot_payload = {
            "minds": [{"mind_name": "alice"}, {"mind_name": "carol"}]
        }
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_message(
            '[{"mind_name":"alice","action":"dispatch-prompt","reason":"r",'
            '"dispatch_topic":"t","dispatch_body":"ba"},'
            '{"mind_name":"carol","action":"dispatch-prompt","reason":"r",'
            '"dispatch_topic":"t","dispatch_body":"bc"}]'
        )

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor._send_dispatch_via_conduit") as mock_send:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1,
                client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        # alice にだけ送られる
        self.assertEqual(mock_send.call_count, 1)
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["to_mind"], "alice")
        self.assertEqual(result.dispatches_sent, 1)


class TestWardenInboxFeedback(unittest.TestCase):
    """Phase 5e Step D / ADR-0025: Mind から warden への返信を Conductor が
    Judgment 入力に含め、Judgment 成功後に ack する経路の検証。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.snapshots_dir = Path(self.tmp.name) / "snapshots"
        self.snapshots_dir.mkdir()
        self.issues_dir = Path(self.tmp.name) / "issues"
        self.issues_dir.mkdir()
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = self.tmp.name
        (Path(self.tmp.name) / "registry" / "minds").mkdir(parents=True)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        self.tmp.cleanup()

    def test_parse_dispatch_frontmatter_typical_message(self) -> None:
        from conductor import _parse_dispatch_frontmatter
        content = (
            "---\n"
            "from: alice\n"
            "to: warden\n"
            "topic: re: status check\n"
            "dispatched_at: 2026-05-30T01:58:03Z\n"
            "msg_id: abc-123\n"
            "---\n"
            "\n"
            "Reply body here, multi line\n"
            "with content.\n"
        )
        parsed = _parse_dispatch_frontmatter(content)
        self.assertEqual(parsed["from"], "alice")
        self.assertEqual(parsed["to"], "warden")
        self.assertEqual(parsed["topic"], "re: status check")
        self.assertIn("Reply body here", parsed["body"])
        self.assertIn("with content.", parsed["body"])

    def test_parse_dispatch_frontmatter_malformed_returns_raw(self) -> None:
        from conductor import _parse_dispatch_frontmatter
        # frontmatter なし
        parsed = _parse_dispatch_frontmatter("just a body, no frontmatter\n")
        self.assertIn("raw", parsed)
        self.assertNotIn("from", parsed)

    def test_warden_replies_passed_to_judgment_when_ok(self) -> None:
        """warden inbox が non-empty なら judgment_input に warden_inbox 追加、
        judgment 成功時に全件 ack される。"""
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_message(
            '[{"mind_name":"alice","action":"ok","reason":"r"}]'
        )

        fake_replies = [
            {"msg_id": "id-1", "from": "alice", "topic": "t",
             "body": "b1", "to": "warden"},
            {"msg_id": "id-2", "from": "bob", "topic": "t",
             "body": "b2", "to": "warden"},
        ]

        captured_input: dict = {}

        def spy_judge(report, client=None):  # noqa: ARG001
            captured_input.update(report)
            from judgment import MindJudgment
            return [MindJudgment("alice", "ok", "r")]

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor.judge_snapshot", side_effect=spy_judge), \
             patch("conductor._read_warden_inbox", return_value=fake_replies), \
             patch("conductor._ack_warden_inbox", return_value=2) as mock_ack:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1, client=client,
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        # Judgment 入力に warden_inbox が含まれていたこと
        self.assertIn("warden_inbox", captured_input)
        self.assertEqual(len(captured_input["warden_inbox"]), 2)
        # 成功時に ack 全件
        mock_ack.assert_called_once()
        acked_ids = mock_ack.call_args.args[0]
        self.assertEqual(set(acked_ids), {"id-1", "id-2"})
        self.assertEqual(result.warden_replies_read, 2)
        self.assertEqual(result.warden_replies_acked, 2)

    def test_warden_replies_not_acked_on_fallback(self) -> None:
        """Judgment 失敗時は ack しない (at-least-once 配送: 次 cycle で再読込)。"""
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        fake_replies = [
            {"msg_id": "id-1", "from": "alice", "topic": "t", "body": "b"},
        ]

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor.judge_snapshot",
                   side_effect=RuntimeError("api down")), \
             patch("conductor._read_warden_inbox", return_value=fake_replies), \
             patch("conductor._ack_warden_inbox") as mock_ack:
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1, client=MagicMock(),
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        # fallback-error 経路: 読みはしたが ack はしない
        self.assertEqual(result.judgment_status, "fallback-error")
        self.assertEqual(result.warden_replies_read, 1)
        self.assertEqual(result.warden_replies_acked, 0)
        mock_ack.assert_not_called()

    def test_empty_warden_inbox_no_section_in_input(self) -> None:
        """warden inbox 空なら judgment_input に warden_inbox key を追加しない
        (= 既存挙動完全互換)。"""
        snapshot_payload = {"minds": [{"mind_name": "alice"}]}
        captured_input: dict = {}

        def spy_judge(report, client=None):  # noqa: ARG001
            captured_input.update(report)
            from judgment import MindJudgment
            return [MindJudgment("alice", "ok", "r")]

        with patch("conductor.write_snapshot") as mock_write, \
             patch("conductor.load_snapshot") as mock_load, \
             patch("conductor.judge_snapshot", side_effect=spy_judge), \
             patch("conductor._read_warden_inbox", return_value=[]):
            mock_write.return_value = self.snapshots_dir / "fake.json"
            mock_load.return_value = snapshot_payload

            result = run_one_cycle(
                1, client=MagicMock(),
                issues_dir=self.issues_dir,
                snapshots_dir=self.snapshots_dir,
            )

        self.assertNotIn("warden_inbox", captured_input)
        self.assertEqual(result.warden_replies_read, 0)
        self.assertEqual(result.warden_replies_acked, 0)

    def test_max_replies_per_cycle_truncates(self) -> None:
        """MAX_WARDEN_REPLIES_PER_CYCLE を超える reply は truncate される。
        実際の truncation は _read_warden_inbox 内で行われる。"""
        from conductor import MAX_WARDEN_REPLIES_PER_CYCLE
        # ロックテスト: 上限定数の値を固定 (config drift 防止)
        self.assertEqual(MAX_WARDEN_REPLIES_PER_CYCLE, 20)

    def test_read_warden_inbox_truncates_actually(self) -> None:
        """Self-review fix: 単なる定数 assert ではなく、25 件 mock を流して
        実際に 20 件しか parse されないことを確認する。
        slice 式 messages[:MAX_WARDEN_REPLIES_PER_CYCLE] のリファクタ事故を
        catch する。"""
        from conductor import _read_warden_inbox

        # 25 件の fake message を返す Nexus mock
        fake_messages = [
            {
                "msg_id": f"id-{i:02d}",
                "content": (
                    "---\n"
                    f"from: alice\nto: warden\ntopic: t{i}\n"
                    f"dispatched_at: 2026-05-30T00:00:00Z\nmsg_id: id-{i:02d}\n"
                    "---\n\nbody\n"
                ),
            }
            for i in range(25)
        ]

        nexus_mock = MagicMock()
        nexus_mock.read_inbox.return_value = {"messages": fake_messages}

        # storage.Nexus の遅延 import をスタブで差し替え
        with patch.dict("sys.modules"):
            fake_module = MagicMock()
            fake_module.Nexus = MagicMock(return_value=nexus_mock)
            sys.modules["storage"] = fake_module
            result = _read_warden_inbox()

        # 20 件で truncate されている (25 件全部入っていない)
        self.assertEqual(len(result), 20)
        # 先頭 20 件 = id-00..id-19 が来ている (slice の先頭優先)
        self.assertEqual(result[0]["msg_id"], "id-00")
        self.assertEqual(result[-1]["msg_id"], "id-19")


class TestWriteStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "conductor-status.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _sample_result(self, dispatches_sent: int = 0) -> CycleResult:
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
            dispatches_sent=dispatches_sent,
        )

    def test_writes_json_with_schema(self) -> None:
        write_status(self._sample_result(), target=self.path, total_cycles=10)
        self.assertTrue(self.path.exists())
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "conductor-status/v1")
        self.assertEqual(payload["total_cycles"], 10)

    def test_status_payload_includes_dispatches_sent(self) -> None:
        """Phase 5e Step B hotfix: actuator 活動量を status JSON で公開する。
        observe.py --realm が「Warden が dispatch を何件送ったか」を表示
        するために必要 (Step B 本体で CycleResult には足したが payload
        に反映漏れだった)。"""
        write_status(self._sample_result(dispatches_sent=2), target=self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("dispatches_sent", payload["last_cycle"])
        self.assertEqual(payload["last_cycle"]["dispatches_sent"], 2)

    def test_status_payload_zero_dispatches_default(self) -> None:
        """dispatch を出さない cycle (fallback / 全 ok 等) では 0 が出る。"""
        write_status(self._sample_result(), target=self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["last_cycle"]["dispatches_sent"], 0)

    def test_status_payload_includes_warden_replies(self) -> None:
        """Phase 5e Step D / ADR-0025: warden_replies_read / acked が
        status JSON で公開される (observe.py から見える)。"""
        r = CycleResult(
            cycle=4,
            started_at="2026-05-30T01:00:00Z",
            ended_at="2026-05-30T01:00:01Z",
            pending_issues=0,
            snapshot_path="/tmp/snap.json",
            judgments_count=1,
            judgments_action_breakdown={"ok": 1},
            judgment_status="ok",
            judgment_error=None,
            dispatches_sent=0,
            warden_replies_read=3,
            warden_replies_acked=3,
        )
        write_status(r, target=self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["last_cycle"]["warden_replies_read"], 3)
        self.assertEqual(payload["last_cycle"]["warden_replies_acked"], 3)
        self.assertEqual(payload["last_cycle"]["cycle"], 4)

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
