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
        """VALID_ACTIONS は 4 種類で固定。語彙拡張時はテストも更新する。"""
        self.assertEqual(VALID_ACTIONS, frozenset({"ok", "monitor", "investigate", "notify-human"}))


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

    def test_reason_truncated_at_200(self) -> None:
        long = "x" * 500
        text = f'[{{"mind_name":"alice","action":"ok","reason":"{long}"}}]'
        result = _parse_response(text, ["alice"])
        self.assertEqual(len(result[0].reason), 200)

    def test_empty_array_with_no_expected(self) -> None:
        result = _parse_response("[]", [])
        self.assertEqual(result, [])


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


if __name__ == "__main__":
    unittest.main()
