"""
test_nexus_tool.py — Nexus MCP tool 層 (nexus.py の call_tool) のユニットテスト。

Phase 5c-1 / ADR-0019: claim_issue の Guild axiom 強制を検証する。

設計の注意:
- nexus.py は `mcp` パッケージに依存する。ホスト Python に mcp が無い環境
  (test-nexus-unit.sh のデフォルト構成) では本ファイル全体を skip する。
  既存 test_storage.py は std lib のみで動くため、guild axiom は本ファイルで
  独立に検証する。
- _nexus はモジュールロード時に AI_ORG_OS_MIND_NAME 環境変数で identity を
  バインドするため、本テストは「unbound」 (env 未設定) の前提で動かす。
- inbox / minds の物理パスは AI_ORG_OS_HOME 環境変数で tmp dir に向ける
  (inbox.py / guild.py が呼び出し時に env を再評価する設計に依存)。
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

try:  # mcp が無ければスキップ
    import mcp  # noqa: F401
    _MCP_AVAILABLE = True
except Exception:  # noqa: BLE001
    _MCP_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).parent))


def _write_mind_meta(
    home: Path,
    mind_name: str,
    guild: str,
    persona: str = "designer",
) -> None:
    d = home / "minds" / mind_name
    d.mkdir(parents=True, exist_ok=True)
    (d / ".mind-meta.md").write_text(
        f"---\nmind_name: {mind_name}\nkind: generic\npersona: {persona}\n"
        f"guild: {guild}\n---\n",
        encoding="utf-8",
    )


def _submit_issue(home: Path, title: str, guild: str) -> str:
    """tmp $AI_ORG_OS_HOME 配下の inbox に直接 Issue を作って issue_id を返す。"""
    # inbox は env を再評価するので、子モジュール import 後でも tmp に向く
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "inbox"))
    import inbox as _inbox  # noqa: PLC0415
    path = _inbox.submit_issue(title, "body", guild=guild)
    return path.stem


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package not installed; skip nexus tool tests")
class TestClaimIssueGuildAxiom(unittest.TestCase):
    """ADR-0019 §3: mind の guild と issue の guild が一致しない場合
    `code: forbidden` で reject されることを検証する。
    """

    def setUp(self) -> None:
        # tmp HOME を AI_ORG_OS_HOME に設定 → inbox / minds がここを向く
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = str(self.home)
        # identity binding は外す (multi-mind を 1 つの Nexus で扱うため)
        self._old_bound = os.environ.pop("AI_ORG_OS_MIND_NAME", None)

        # 既にロード済みなら fresh import (env が遅延評価でも _nexus は
        # モジュールロード時に作られるため、識別バインドを反映するには再ロード)
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)
        # Note: nexus.py が import 時に Server() / _nexus を初期化するので
        # 環境変数を確定させてから import すること。
        self.nexus = importlib.import_module("nexus")

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        if self._old_bound is not None:
            os.environ["AI_ORG_OS_MIND_NAME"] = self._old_bound
        self.tmp.cleanup()
        # 副作用を残さないため、テスト後にもう一度クリア
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)

    def _call(self, name: str, args: dict) -> dict:
        result = asyncio.run(self.nexus.call_tool(name, args))
        # call_tool は [TextContent(...)] を返す。 .text に JSON 文字列。
        self.assertEqual(len(result), 1)
        return json.loads(result[0].text)

    def test_claim_succeeds_when_guilds_match(self) -> None:
        _write_mind_meta(self.home, "alice", guild="default")
        iid = _submit_issue(self.home, "ok", guild="default")
        out = self._call("claim_issue", {"mind_name": "alice", "issue_id": iid})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("claimed_by"), "alice")
        self.assertEqual(out.get("guild"), "default")

    def test_claim_rejected_when_mind_guild_mismatches_issue_guild(self) -> None:
        _write_mind_meta(self.home, "alice", guild="default")
        iid = _submit_issue(self.home, "wrong-guild", guild="backend")
        out = self._call("claim_issue", {"mind_name": "alice", "issue_id": iid})
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("mind_guild"), "default")
        self.assertEqual(out.get("issue_guild"), "backend")
        self.assertIn("claim-only-own-guild", out.get("error", ""))

    def test_claim_rejected_preserves_issue_in_inbox(self) -> None:
        """forbidden で reject された Issue は inbox に残り、後で正しい Mind が claim できる。"""
        _write_mind_meta(self.home, "alice", guild="default")
        _write_mind_meta(self.home, "bob", guild="backend")
        iid = _submit_issue(self.home, "for-bob", guild="backend")

        # alice (default) は claim 失敗
        out = self._call("claim_issue", {"mind_name": "alice", "issue_id": iid})
        self.assertEqual(out.get("code"), "forbidden")

        # inbox に残っている
        inbox_path = self.home / "issues" / "inbox" / f"{iid}.md"
        self.assertTrue(inbox_path.exists())

        # bob (backend) なら claim 成功
        out2 = self._call("claim_issue", {"mind_name": "bob", "issue_id": iid})
        self.assertTrue(out2.get("ok"), out2)
        self.assertEqual(out2.get("claimed_by"), "bob")

    def test_legacy_mind_without_guild_field_treated_as_default(self) -> None:
        """guild フィールド無し (Phase 5c-1 以前の Mind) は default 扱い。"""
        d = self.home / "minds" / "legacy"
        d.mkdir(parents=True, exist_ok=True)
        (d / ".mind-meta.md").write_text(
            "---\nmind_name: legacy\nkind: generic\npersona: designer\n---\n",
            encoding="utf-8",
        )
        iid = _submit_issue(self.home, "default-issue", guild="default")
        out = self._call("claim_issue", {"mind_name": "legacy", "issue_id": iid})
        self.assertTrue(out.get("ok"), out)

    def test_unknown_issue_returns_not_found(self) -> None:
        _write_mind_meta(self.home, "alice", guild="default")
        out = self._call(
            "claim_issue",
            {"mind_name": "alice", "issue_id": "20260524T120000Z-000000-deadbeef"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "not_found")

    def test_path_traversal_in_mind_name_rejected(self) -> None:
        """Codex P2 (#88): unbound Nexus (assert_identity が no-op の状況) でも
        crafted mind_name ('../...' 等) は guild lookup に到達する前に format
        検証で reject される。これにより minds/ 外の .mind-meta.md を読みに
        いく path traversal の窓を塞ぐ。
        """
        _submit_issue(self.home, "for-anyone", guild="default")
        # 不正な mind_name (path traversal を試みる)。
        # 既存の inbox を peek すらせず、validation 段階で fail するはず。
        for bad in ["../escape", "has space", "x" * 65, "a/b", ""]:
            out = self._call(
                "claim_issue",
                {"mind_name": bad, "issue_id": "20260524T120000Z-000000-deadbeef"},
            )
            self.assertFalse(out.get("ok"), f"mind_name={bad!r} should be rejected, got {out}")
            # storage._validate_mind_name の ValueError は call_tool の
            # `except ValueError` で {"ok": False, "error": ...} になる。
            # code は invalid_input / forbidden のいずれかではなく無印 (string).
            self.assertIn("mind_name", out.get("error", ""))


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package not installed; skip nexus tool tests")
class TestReadPendingIssues(unittest.TestCase):
    """read_pending_issues が guild フィールドを含めて返すことを検証 (ADR-0019)。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = str(self.home)
        self._old_bound = os.environ.pop("AI_ORG_OS_MIND_NAME", None)
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)
        self.nexus = importlib.import_module("nexus")

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        if self._old_bound is not None:
            os.environ["AI_ORG_OS_MIND_NAME"] = self._old_bound
        self.tmp.cleanup()
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)

    def test_read_pending_includes_guild(self) -> None:
        _submit_issue(self.home, "default-issue", guild="default")
        _submit_issue(self.home, "backend-issue", guild="backend")
        out = asyncio.run(self.nexus.call_tool("read_pending_issues", {}))
        data = json.loads(out[0].text)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("count"), 2)
        guilds = sorted(item["guild"] for item in data["issues"])
        self.assertEqual(guilds, ["backend", "default"])


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package not installed; skip nexus tool tests")
class TestReadInboxGuildmasterAxiom(unittest.TestCase):
    """Phase 5c-2 / ADR-0021: target_mind を別 Mind に指定する場合、
    発令者の persona が guildmaster でなければ code: forbidden で reject。
    自分の inbox を読むときは従来通り誰でも可。
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = str(self.home)
        self._old_bound = os.environ.pop("AI_ORG_OS_MIND_NAME", None)
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)
        self.nexus = importlib.import_module("nexus")

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        if self._old_bound is not None:
            os.environ["AI_ORG_OS_MIND_NAME"] = self._old_bound
        self.tmp.cleanup()
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)

    def _call(self, name: str, args: dict) -> dict:
        result = asyncio.run(self.nexus.call_tool(name, args))
        return json.loads(result[0].text)

    def _send_to(self, sender: str, recipient: str, topic: str = "hi") -> None:
        # tmp Nexus を直接呼んで Dispatch を 1 件 inbox に置く。
        from storage import Nexus as _NexusCls  # noqa: PLC0415
        storage_dir = self.home / "conduit-storage"
        unbound = _NexusCls(storage_dir=storage_dir, identity=None)
        unbound.send_dispatch(
            from_mind=sender, to_mind=recipient, topic=topic, body="x",
        )

    def test_self_inbox_works_for_any_persona(self) -> None:
        _write_mind_meta(self.home, "alice", guild="default", persona="designer")
        self._send_to("bob", "alice")
        out = self._call("read_inbox", {"mind_name": "alice"})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("count"), 1)

    def test_others_inbox_forbidden_for_designer(self) -> None:
        _write_mind_meta(self.home, "alice", guild="default", persona="designer")
        _write_mind_meta(self.home, "bob", guild="default", persona="implementer")
        self._send_to("carol", "bob")
        out = self._call(
            "read_inbox",
            {"mind_name": "alice", "target_mind": "bob"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_persona"), "designer")
        self.assertIn("read-others-inbox-only-by-guildmaster", out.get("error", ""))

    def test_others_inbox_allowed_for_guildmaster(self) -> None:
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        _write_mind_meta(self.home, "bob", guild="default", persona="implementer")
        self._send_to("carol", "bob")
        out = self._call(
            "read_inbox",
            {"mind_name": "gm", "target_mind": "bob"},
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("mind"), "bob")
        self.assertEqual(out.get("count"), 1)
        self.assertEqual(out.get("observed_by"), "gm")

    def test_target_mind_format_validation(self) -> None:
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        # 形式違反 target_mind は ValueError (storage._validate_mind_name 経由)
        out = self._call(
            "read_inbox",
            {"mind_name": "gm", "target_mind": "../escape"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertIn("target_mind", out.get("error", ""))


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package not installed; skip nexus tool tests")
class TestSpawnMindGuildmasterAxiom(unittest.TestCase):
    """Phase 5c-2 / ADR-0021: spawn_mind は persona=guildmaster の Mind のみ可。
    spawn-mind.sh を subprocess で呼ぶため、host venv の python + Guild
    template が利用可能な統合環境前提のテストは別途 e2e で確認する。
    本ファイルでは axiom 強制部分 (= forbidden の判定) のみを単体テスト。
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = str(self.home)
        self._old_bound = os.environ.pop("AI_ORG_OS_MIND_NAME", None)
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)
        self.nexus = importlib.import_module("nexus")

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        if self._old_bound is not None:
            os.environ["AI_ORG_OS_MIND_NAME"] = self._old_bound
        self.tmp.cleanup()
        for mod in ("nexus", "inbox", "guild", "storage"):
            sys.modules.pop(mod, None)

    def _call(self, name: str, args: dict) -> dict:
        result = asyncio.run(self.nexus.call_tool(name, args))
        return json.loads(result[0].text)

    def test_spawn_forbidden_for_designer(self) -> None:
        _write_mind_meta(self.home, "alice", guild="default", persona="designer")
        out = self._call(
            "spawn_mind",
            {
                "mind_name": "alice", "new_mind_name": "newbie",
                "kind": "generic", "persona": "designer",
            },
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_persona"), "designer")
        self.assertIn("guildmaster-only-spawn", out.get("error", ""))

    def test_spawn_forbidden_for_unknown_mind(self) -> None:
        # .mind-meta.md が存在しない (= persona = None) → forbidden
        out = self._call(
            "spawn_mind",
            {
                "mind_name": "ghost", "new_mind_name": "newbie",
                "kind": "generic", "persona": "designer",
            },
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_persona"), "<unknown>")

    def test_spawn_format_validation_for_new_mind_name(self) -> None:
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        # 不正な new_mind_name は ValueError で reject (path traversal 防御)
        out = self._call(
            "spawn_mind",
            {
                "mind_name": "gm", "new_mind_name": "../escape",
                "kind": "generic", "persona": "designer",
            },
        )
        self.assertFalse(out.get("ok"), out)
        self.assertIn("new_mind_name", out.get("error", ""))


if __name__ == "__main__":
    unittest.main()
