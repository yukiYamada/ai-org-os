#!/usr/bin/env python3
"""
test_judgment.py — Judgment Pillar のユニットテスト。

API key 不要、anthropic SDK 未インストール環境でも動く（client を mock するため）。

テスト対象:
- _parse_response: 各種フォーマット (正常 / fence 付き / 不正 / 不足) のパース
- judge_snapshot: client を mock して入出力ペアの整合性
- make_client: 環境変数 / API key 引数 / 不在時の例外
- VALID_ACTIONS の語彙
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from judgment import (  # noqa: E402
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    VALID_ACTIONS,
    AnthropicNotConfigured,
    JudgmentParseError,
    MindJudgment,
    _build_system_prompt,
    _build_user_prompt,
    _parse_response,
    judge_snapshot,
    make_client,
)


def _mock_message(text: str) -> MagicMock:
    """Anthropic SDK の Message オブジェクトを模擬する。

    content は list[block]、block.type == 'text' で block.text を持つ。
    """
    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


SAMPLE_SNAPSHOT = {
    "generated_at": "2026-05-24T00:00:00Z",
    "snapshot_id": "20260524T000000Z-000000",
    "minds": [
        {
            "mind_name": "alice",
            "kind": "generic",
            "persona": "designer",
            "spawned_at_epoch": 1700000000.0,
            "last_activity_epoch": 1700000100.0,
            "unread_inbox_count": 0,
            "archive_count": 0,
            "status": "active",
            "category": "running",
        },
        {
            "mind_name": "bob",
            "kind": "generic",
            "persona": "reviewer",
            "spawned_at_epoch": 1700000000.0,
            "last_activity_epoch": 1700000000.0,
            "unread_inbox_count": 5,
            "archive_count": 2,
            "status": "idle",
            "category": "unread",
        },
    ],
}


class TestVocabulary(unittest.TestCase):
    def test_valid_actions_locked(self) -> None:
        """VALID_ACTIONS は 5 種類で固定 (Phase 5e Step B で dispatch-prompt 追加)。
        語彙拡張時はテストも更新する。"""
        self.assertEqual(
            VALID_ACTIONS,
            frozenset({
                "ok", "monitor", "investigate",
                "dispatch-prompt",  # Phase 5e Step B
                "notify-human",
            }),
        )


class TestPrompts(unittest.TestCase):
    def test_system_prompt_mentions_actions(self) -> None:
        prompt = _build_system_prompt()
        # 全 action 語彙が system prompt に含まれる（Claude が知らない語彙を出さないように）
        for action in VALID_ACTIONS:
            self.assertIn(action, prompt)

    def test_user_prompt_includes_snapshot(self) -> None:
        prompt = _build_user_prompt(SAMPLE_SNAPSHOT)
        self.assertIn("alice", prompt)
        self.assertIn("bob", prompt)
        self.assertIn("2 total", prompt)

    def test_user_prompt_marks_v01_schema_only_minds_section(self) -> None:
        """Phase 5e: v0.1 snapshot 入力では header に 'sections: minds' のみ。"""
        prompt = _build_user_prompt(SAMPLE_SNAPSHOT)
        self.assertIn("schema=0.1", prompt)
        self.assertIn("sections: minds", prompt)
        # flow / resource / anomaly は v0.1 では sections に出ない
        self.assertNotIn("sections: minds, flow", prompt)

    def test_user_prompt_advertises_all_v10_sections(self) -> None:
        """Phase 5e: --for-warden の v1.0 統合 report は全 section を header で
        告知する (= Claude が「これを見るぞ」と即座に判別できる)。"""
        report = {
            "schema_version": "1.0",
            "generated_at": "2026-05-29T00:00:00Z",
            "minds": [
                {"mind_name": "alice", "kind": "generic", "persona": "designer",
                 "status": "active", "category": "running",
                 "unread_inbox_count": 0, "archive_count": 0,
                 "spawned_at_epoch": 0.0, "last_activity_epoch": 0.0},
            ],
            "flow": [{"from_mind": "alice", "to_mind": "bob", "count": 1,
                      "first_at": "2026-05-29T00:00:00Z",
                      "last_at": "2026-05-29T00:00:00Z"}],
            "resource": [{"name": "alice", "category": "mindspace",
                          "file_count": 3, "byte_count": 1024}],
            "anomaly": [{"code": "W3", "level": "warning",
                         "mind": "alice", "message": "orphan kind"}],
        }
        prompt = _build_user_prompt(report)
        self.assertIn("schema=1.0", prompt)
        self.assertIn("sections: minds, flow, resource, anomaly", prompt)
        # 内容も含まれる
        self.assertIn("W3", prompt)
        self.assertIn("orphan kind", prompt)

    def test_system_prompt_mentions_v10_signals(self) -> None:
        """Phase 5e: system prompt が flow/resource/anomaly を判断材料として
        言及している (= Claude が判断材料を活用できる)。"""
        prompt = _build_system_prompt()
        for keyword in ("flow", "resource", "anomaly", "W2", "W3", "I1", "I2"):
            self.assertIn(keyword, prompt)


class TestParseResponse(unittest.TestCase):
    def test_parses_valid_array(self) -> None:
        text = (
            '[{"mind_name":"alice","action":"ok","reason":"healthy"},'
            '{"mind_name":"bob","action":"investigate","reason":"unread idle"}]'
        )
        result = _parse_response(text, ["alice", "bob"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], MindJudgment("alice", "ok", "healthy"))
        self.assertEqual(result[1].action, "investigate")

    def test_handles_markdown_fences(self) -> None:
        """Claude が ```json ... ``` で囲んできた場合の defensive parsing。"""
        text = '```json\n[{"mind_name":"alice","action":"ok","reason":"ok"}]\n```'
        result = _parse_response(text, ["alice"])
        self.assertEqual(len(result), 1)

    def test_handles_plain_fences(self) -> None:
        text = '```\n[{"mind_name":"alice","action":"ok","reason":"ok"}]\n```'
        result = _parse_response(text, ["alice"])
        self.assertEqual(len(result), 1)

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(JudgmentParseError):
            _parse_response("not json at all", ["alice"])

    def test_non_array_raises(self) -> None:
        with self.assertRaises(JudgmentParseError):
            _parse_response('{"mind_name":"alice","action":"ok","reason":"r"}', ["alice"])

    def test_missing_key_raises(self) -> None:
        # reason 欠落
        text = '[{"mind_name":"alice","action":"ok"}]'
        with self.assertRaises(JudgmentParseError):
            _parse_response(text, ["alice"])

    def test_invalid_action_raises(self) -> None:
        text = '[{"mind_name":"alice","action":"destroy","reason":"too harsh"}]'
        with self.assertRaises(JudgmentParseError):
            _parse_response(text, ["alice"])

    def test_missing_mind_raises(self) -> None:
        """期待された Mind 名が出力に無い場合は fail（呼び出し側で fallback）。"""
        text = '[{"mind_name":"alice","action":"ok","reason":"r"}]'
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response(text, ["alice", "bob"])
        self.assertIn("bob", str(ctx.exception))

    def test_unknown_mind_raises(self) -> None:
        """Codex P1 PR #65: Claude が hallucinated Mind を返したら fail。

        旧実装は missing (expected - seen) しか見てなかったので、expected を全て
        含みつつ extra な mind_name が混ざっていても通過した。今は seen - expected
        も検証して unknown を弾く。
        """
        text = (
            '[{"mind_name":"alice","action":"ok","reason":"r"},'
            '{"mind_name":"ghost","action":"investigate","reason":"hallucinated"}]'
        )
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response(text, ["alice"])
        self.assertIn("ghost", str(ctx.exception))
        self.assertIn("unknown", str(ctx.exception).lower())

    def test_missing_and_unknown_both_reported(self) -> None:
        """missing と unknown が同時にあれば両方 message に含まれる。"""
        text = '[{"mind_name":"ghost","action":"ok","reason":"r"}]'
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response(text, ["alice"])
        msg = str(ctx.exception)
        self.assertIn("alice", msg)  # missing
        self.assertIn("ghost", msg)  # unknown

    def test_reason_truncated_at_200(self) -> None:
        long = "x" * 500
        text = f'[{{"mind_name":"alice","action":"ok","reason":"{long}"}}]'
        result = _parse_response(text, ["alice"])
        self.assertEqual(len(result[0].reason), 200)

    def test_empty_array_with_no_expected(self) -> None:
        result = _parse_response("[]", [])
        self.assertEqual(result, [])

    def test_fence_does_not_corrupt_backtick_in_reason(self) -> None:
        """self-review fix (#65): JSON 本文中の backtick が fence 剥がしで壊されない。

        旧実装の `raw.strip("\\`")` は文字単位で全 backtick を消すので、reason 内に
        backtick が含まれる場合に JSON が壊れた。新実装は行単位で剥がす。
        """
        # reason に backtick を含む。fence で囲まれた典型応答
        text = (
            '```json\n'
            '[{"mind_name":"alice","action":"ok","reason":"use `grep` here"}]\n'
            '```'
        )
        result = _parse_response(text, ["alice"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].reason, "use `grep` here")

    def test_empty_mind_name_raises(self) -> None:
        """self-review fix (#65): 空文字 mind_name は不正。"""
        text = '[{"mind_name":"","action":"ok","reason":"r"}]'
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response(text, ["alice"])
        self.assertIn("empty mind_name", str(ctx.exception))

    def test_duplicate_mind_name_raises(self) -> None:
        """self-review fix (#65): 同じ mind_name を 2 回返したら fail。"""
        text = (
            '[{"mind_name":"alice","action":"ok","reason":"r1"},'
            '{"mind_name":"alice","action":"investigate","reason":"r2"}]'
        )
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response(text, ["alice"])
        self.assertIn("duplicate mind_name", str(ctx.exception))

    def test_parse_error_includes_raw_snippet(self) -> None:
        """self-review fix (#65): 例外メッセージに raw response 抜粋を含めて debug 性を上げる。"""
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response("not json at all", ["alice"])
        # 例外メッセージに raw 内容のヒントが含まれる
        self.assertIn("not json", str(ctx.exception))


class TestJudgeSnapshot(unittest.TestCase):
    def test_empty_minds_short_circuits(self) -> None:
        """Mind が 0 件なら SDK を呼ばずに空リスト即返。"""
        client = MagicMock()
        result = judge_snapshot({"minds": []}, client=client)
        self.assertEqual(result, [])
        client.messages.create.assert_not_called()

    def test_happy_path_with_mocked_client(self) -> None:
        client = MagicMock()
        client.messages.create.return_value = _mock_message(
            '[{"mind_name":"alice","action":"ok","reason":"healthy"},'
            '{"mind_name":"bob","action":"investigate","reason":"unread idle"}]'
        )
        result = judge_snapshot(SAMPLE_SNAPSHOT, client=client)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].mind_name, "alice")
        # SDK 呼び出しのパラメータも検証
        client.messages.create.assert_called_once()
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], DEFAULT_MODEL)
        self.assertEqual(kwargs["max_tokens"], DEFAULT_MAX_TOKENS)
        self.assertEqual(kwargs["temperature"], DEFAULT_TEMPERATURE)

    def test_no_text_block_raises(self) -> None:
        """応答に text block が無いと JudgmentParseError。"""
        client = MagicMock()
        empty_message = MagicMock()
        empty_message.content = []
        client.messages.create.return_value = empty_message
        with self.assertRaises(JudgmentParseError):
            judge_snapshot(SAMPLE_SNAPSHOT, client=client)

    def test_passes_snapshot_to_user_prompt(self) -> None:
        client = MagicMock()
        client.messages.create.return_value = _mock_message(
            '[{"mind_name":"alice","action":"ok","reason":"r"},'
            '{"mind_name":"bob","action":"ok","reason":"r"}]'
        )
        judge_snapshot(SAMPLE_SNAPSHOT, client=client)
        user_message = client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("alice", user_message)
        self.assertIn("bob", user_message)


class TestMakeClient(unittest.TestCase):
    def test_missing_key_raises(self) -> None:
        # 環境変数を一時的に消す
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AnthropicNotConfigured) as ctx:
                make_client()
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_explicit_key_overrides_env(self) -> None:
        """api_key 引数で明示渡しすれば env 不要。

        anthropic SDK が installed されていなければ AnthropicNotConfigured。
        installed なら Anthropic オブジェクトが返る（インスタンス検証は省略、
        environment dependent）。
        """
        try:
            import anthropic  # noqa: F401
        except ImportError:
            with self.assertRaises(AnthropicNotConfigured):
                make_client(api_key="sk-test-dummy")
            return
        # SDK が居る場合
        client = make_client(api_key="sk-test-dummy")
        self.assertIsNotNone(client)


class TestDispatchPromptAction(unittest.TestCase):
    """Phase 5e Step B: action=dispatch-prompt のパース挙動。
    body/topic 必須、他 action では存在しても無視。"""

    def test_dispatch_prompt_with_topic_and_body_parsed(self) -> None:
        text = (
            '[{"mind_name":"alice","action":"dispatch-prompt",'
            '"reason":"silent",'
            '"dispatch_topic":"are you stuck?",'
            '"dispatch_body":"You have been silent for a while. What is your status?"}]'
        )
        result = _parse_response(text, ["alice"])
        self.assertEqual(len(result), 1)
        j = result[0]
        self.assertEqual(j.action, "dispatch-prompt")
        self.assertEqual(j.dispatch_topic, "are you stuck?")
        self.assertIn("silent for a while", j.dispatch_body or "")

    def test_dispatch_prompt_missing_topic_raises(self) -> None:
        text = (
            '[{"mind_name":"alice","action":"dispatch-prompt",'
            '"reason":"r","dispatch_body":"hi"}]'
        )
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response(text, ["alice"])
        self.assertIn("dispatch_topic", str(ctx.exception))

    def test_dispatch_prompt_missing_body_raises(self) -> None:
        text = (
            '[{"mind_name":"alice","action":"dispatch-prompt",'
            '"reason":"r","dispatch_topic":"t"}]'
        )
        with self.assertRaises(JudgmentParseError) as ctx:
            _parse_response(text, ["alice"])
        self.assertIn("dispatch_body", str(ctx.exception))

    def test_dispatch_prompt_empty_body_raises(self) -> None:
        text = (
            '[{"mind_name":"alice","action":"dispatch-prompt",'
            '"reason":"r","dispatch_topic":"t","dispatch_body":""}]'
        )
        with self.assertRaises(JudgmentParseError):
            _parse_response(text, ["alice"])

    def test_dispatch_prompt_body_truncated(self) -> None:
        """1000 chars 上限で truncate される (LLM 暴走防御)。"""
        long_body = "x" * 5000
        text = (
            '[{"mind_name":"alice","action":"dispatch-prompt","reason":"r",'
            '"dispatch_topic":"t","dispatch_body":"' + long_body + '"}]'
        )
        result = _parse_response(text, ["alice"])
        self.assertEqual(len(result[0].dispatch_body or ""), 1000)

    def test_other_actions_have_no_dispatch_fields(self) -> None:
        """他 action では dispatch_body 等が None になる (= 副作用なし、後方互換)。"""
        text = '[{"mind_name":"alice","action":"ok","reason":"healthy"}]'
        result = _parse_response(text, ["alice"])
        self.assertIsNone(result[0].dispatch_topic)
        self.assertIsNone(result[0].dispatch_body)

    def test_system_prompt_mentions_dispatch_prompt(self) -> None:
        prompt = _build_system_prompt()
        self.assertIn("dispatch-prompt", prompt)
        self.assertIn("dispatch_topic", prompt)
        self.assertIn("dispatch_body", prompt)
        # "from warden" のような表現で sender 名を含む
        self.assertIn("warden", prompt.lower())


if __name__ == "__main__":
    unittest.main()
