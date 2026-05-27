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
    """Test fixture: Mind を spawn したことにする。

    Phase 5c-2 P1 fix (#91 Codex): authoritative メタは Mind registry
    (`<home>/registry/minds/<name>.md`)。Mindspace 内 `.mind-meta.md` も
    informational copy として書く (observe.py が走査するため)。
    """
    # Mindspace (informational copy + observe.py が走査する目印)
    d = home / "minds" / mind_name
    d.mkdir(parents=True, exist_ok=True)
    (d / ".mind-meta.md").write_text(
        f"---\nmind_name: {mind_name}\nkind: generic\npersona: {persona}\n"
        f"guild: {guild}\n---\n",
        encoding="utf-8",
    )
    # Mind registry (authoritative for axiom enforcement)
    reg = home / "registry" / "minds"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{mind_name}.md").write_text(
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

    def test_legacy_mind_without_registry_entry_is_forbidden(self) -> None:
        """Codex P1 (#91 2 回目) で仕様変更: Phase 5c-2 以前に spawn された
        Mind (registry エントリ無) は axiom-controlled な操作 (claim_issue 等)
        で forbidden。default fallback すると default Guildmaster が registry
        無 Mind を観察できる cross-guild bypass の窓になるため、明示的に
        unknown 扱い。利用者は対象 Mind を kill して再 spawn する。
        """
        # Mindspace 内 .mind-meta.md だけある古い Mind (registry 無)
        d = self.home / "minds" / "legacy"
        d.mkdir(parents=True, exist_ok=True)
        (d / ".mind-meta.md").write_text(
            "---\nmind_name: legacy\nkind: generic\npersona: designer\n"
            "guild: default\n---\n",
            encoding="utf-8",
        )
        iid = _submit_issue(self.home, "default-issue", guild="default")
        out = self._call("claim_issue", {"mind_name": "legacy", "issue_id": iid})
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertIn("registry", out.get("error", "").lower())

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

    def test_cross_guild_observation_forbidden_even_for_guildmaster(self) -> None:
        """Codex P1 (#91): Guildmaster であっても異 Guild の Mind は監視不可。

        claim-only-own-guild と同じ Guild 隔離の思想。Guildmaster は自 Guild の
        運営層であって、ai-org-os 全 Realm を覗ける存在ではない。
        """
        _write_mind_meta(
            self.home, "gm-research", guild="research", persona="guildmaster",
        )
        _write_mind_meta(
            self.home, "bob-backend", guild="backend", persona="implementer",
        )
        self._send_to("carol", "bob-backend")
        out = self._call(
            "read_inbox",
            {"mind_name": "gm-research", "target_mind": "bob-backend"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_guild"), "research")
        self.assertEqual(out.get("target_guild"), "backend")
        self.assertIn("cross-guild", out.get("error", "").lower())


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

    def test_spawn_subprocess_uses_utf8_encoding(self) -> None:
        """Dogfooding bug 2026-05-26: Windows JP locale (cp932) で
        subprocess output に日本語が混じると UnicodeDecodeError で reader
        thread が死亡し、proc.stdout が None → `[-500:]` で TypeError、
        実 spawn が成功しても MCP は ok=false を返す不整合があった。

        修正: subprocess.run に encoding="utf-8" / errors="replace" を渡す。
        本テストは subprocess.run の呼び出し引数を mock で intercept して
        encoding が明示されていることを直接検証する (= 回帰防止)。
        """
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        # subprocess.run を mock 化、引数を捕捉、proc.returncode=0 を返す
        from unittest import mock  # noqa: PLC0415
        captured = {}

        def fake_run(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            # 成功を装う最小限の proc-like オブジェクト
            class _Proc:
                returncode = 0
                stdout = "ok\n"
                stderr = ""
            return _Proc()

        # subprocess.run 自体は nexus module 内で import されるので
        # 'nexus.subprocess' を patch する (関数内 import 経由)。
        import subprocess as _sp  # noqa: PLC0415

        with mock.patch.object(_sp, "run", side_effect=fake_run):
            out = self._call(
                "spawn_mind",
                {
                    "mind_name": "gm", "new_mind_name": "newbie",
                    "kind": "generic", "persona": "designer",
                },
            )
        # 呼び出しが行われたこと
        self.assertIn("kwargs", captured, out)
        self.assertEqual(captured["kwargs"].get("encoding"), "utf-8")
        self.assertEqual(captured["kwargs"].get("errors"), "replace")
        # 成功扱いになっていること (= 回帰時はここで {ok: false, error: TypeError} になる)
        self.assertTrue(out.get("ok"), out)


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package not installed; skip nexus tool tests")
class TestKillMindGuildmasterAxiom(unittest.TestCase):
    """Phase 5c-3 / ADR-0021: kill_mind は同 Guild 所属の persona=guildmaster の
    Mind のみ可、かつ self-kill 不可。
    spawn_mind と同じく subprocess (kill-mind.sh) を呼ぶ成功パスは host venv 環境
    依存なので e2e に回し、本クラスでは axiom 強制部分 (forbidden 判定の 3 段階)
    のみを単体テストする。
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

    def test_kill_forbidden_for_designer(self) -> None:
        """非 guildmaster Persona (= designer) の Mind は他 Mind を kill できない。"""
        _write_mind_meta(self.home, "alice", guild="default", persona="designer")
        _write_mind_meta(self.home, "bob", guild="default", persona="implementer")
        out = self._call(
            "kill_mind",
            {"mind_name": "alice", "target_mind": "bob"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_persona"), "designer")
        self.assertIn("guildmaster-only-kill", out.get("error", ""))

    def test_kill_forbidden_for_unknown_mind(self) -> None:
        """registry エントリ無の Mind は persona=None → forbidden。
        default fallback による越権を許さない (Codex P1 #91 2 回目と同じ思想)。
        """
        _write_mind_meta(self.home, "bob", guild="default", persona="implementer")
        out = self._call(
            "kill_mind",
            {"mind_name": "ghost", "target_mind": "bob"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_persona"), "<unknown>")

    def test_self_kill_forbidden_even_for_guildmaster(self) -> None:
        """Guildmaster であっても自分自身を kill することは禁止。
        最後の Guildmaster や自身の撤収は人間 (ADR-0012) が kill-mind.sh で行う。
        """
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        out = self._call(
            "kill_mind",
            {"mind_name": "gm", "target_mind": "gm"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertIn("self-kill", out.get("error", "").lower())
        self.assertIn("guildmaster-only-kill", out.get("error", ""))

    def test_cross_guild_kill_forbidden(self) -> None:
        """Guildmaster であっても異 Guild の Mind は kill できない。
        claim-only-own-guild / read-others-inbox-only-by-guildmaster と同じ
        Guild 隔離思想 (Guildmaster は自 Guild の運営層であって Realm 全体の
        撤収権を持つ存在ではない)。
        """
        _write_mind_meta(
            self.home, "gm-research", guild="research", persona="guildmaster",
        )
        _write_mind_meta(
            self.home, "bob-backend", guild="backend", persona="implementer",
        )
        out = self._call(
            "kill_mind",
            {"mind_name": "gm-research", "target_mind": "bob-backend"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_guild"), "research")
        self.assertEqual(out.get("target_guild"), "backend")
        self.assertIn("cross-guild", out.get("error", "").lower())

    def test_target_mind_format_validation(self) -> None:
        """形式違反 target_mind (path traversal) は registry lookup より前に
        format 検証で reject される。"""
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        out = self._call(
            "kill_mind",
            {"mind_name": "gm", "target_mind": "../escape"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertIn("target_mind", out.get("error", ""))

    def test_kill_forbidden_when_target_has_no_registry(self) -> None:
        """target_mind の registry エントリ無は target_guild=None → forbidden。
        default fallback すると default Guildmaster が registry 無 target を
        kill できる cross-guild bypass の窓になるため、明示的に unknown 扱い。
        """
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        # target は Mindspace のみで registry エントリ無
        d = self.home / "minds" / "stray"
        d.mkdir(parents=True, exist_ok=True)
        (d / ".mind-meta.md").write_text(
            "---\nmind_name: stray\nkind: generic\npersona: implementer\n"
            "guild: default\n---\n",
            encoding="utf-8",
        )
        out = self._call(
            "kill_mind",
            {"mind_name": "gm", "target_mind": "stray"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertIsNone(out.get("target_guild"))
        self.assertIn("registry", out.get("error", "").lower())

    def test_kill_subprocess_uses_utf8_encoding(self) -> None:
        """spawn_mind と対称の予防的回帰テスト。kill-mind.sh が将来日本語
        メッセージを返したときに Windows JP locale (cp932) で死なないよう、
        subprocess.run に encoding="utf-8" / errors="replace" が渡されている
        ことを検証する (2026-05-26 dogfooding bug の予防)。
        """
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        _write_mind_meta(self.home, "victim", guild="default", persona="implementer")
        from unittest import mock  # noqa: PLC0415
        captured = {}

        def fake_run(*args, **kwargs):
            captured["kwargs"] = kwargs
            class _Proc:
                returncode = 0
                stdout = "killed\n"
                stderr = ""
            return _Proc()

        import subprocess as _sp  # noqa: PLC0415

        with mock.patch.object(_sp, "run", side_effect=fake_run):
            out = self._call(
                "kill_mind",
                {"mind_name": "gm", "target_mind": "victim"},
            )
        self.assertIn("kwargs", captured, out)
        self.assertEqual(captured["kwargs"].get("encoding"), "utf-8")
        self.assertEqual(captured["kwargs"].get("errors"), "replace")
        self.assertTrue(out.get("ok"), out)


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package not installed; skip nexus tool tests")
class TestRegistryAuthoritativeNotMindspace(unittest.TestCase):
    """Codex P1 (#91) 回帰防止: Mindspace 内 `.mind-meta.md` を改ざんしても
    axiom 強制を bypass できないことを検証する。authoritative source は
    Mind registry (`$AI_ORG_OS_HOME/registry/minds/<name>.md`) のみ。
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

    def _spawn_designer_with_forged_mindspace(self, mind: str, guild: str) -> None:
        """designer の Mind を Mindspace に作るが、`.mind-meta.md` を
        `persona: guildmaster` で **改ざん**する。registry は本来の designer
        のまま。Mind が「caller-controlled flag」で昇格を試みる攻撃の模倣。
        """
        # 正しい registry エントリ (= 真の persona は designer)
        reg = self.home / "registry" / "minds"
        reg.mkdir(parents=True, exist_ok=True)
        (reg / f"{mind}.md").write_text(
            f"---\nmind_name: {mind}\nkind: generic\npersona: designer\n"
            f"guild: {guild}\n---\n",
            encoding="utf-8",
        )
        # Mindspace 内の改ざん .mind-meta.md (= Mind が自分で書き換えたつもり)
        ms = self.home / "minds" / mind
        ms.mkdir(parents=True, exist_ok=True)
        (ms / ".mind-meta.md").write_text(
            f"---\nmind_name: {mind}\nkind: generic\npersona: guildmaster\n"
            f"guild: {guild}\n---\n",
            encoding="utf-8",
        )

    def test_forged_mindspace_persona_cannot_bypass_spawn_axiom(self) -> None:
        """designer Mind が Mindspace 内 `.mind-meta.md` で `persona:
        guildmaster` を僭称しても、`spawn_mind` は registry 側の真値 (=
        designer) を見るので forbidden で reject される。
        """
        self._spawn_designer_with_forged_mindspace("attacker", "default")
        out = self._call(
            "spawn_mind",
            {
                "mind_name": "attacker", "new_mind_name": "victim",
                "kind": "generic", "persona": "designer",
            },
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        # registry を見ているので persona は designer のまま見える
        self.assertEqual(out.get("requester_persona"), "designer")

    def test_missing_registry_entry_blocks_claim_issue(self) -> None:
        """Codex P1 (#91 2 回目): registry エントリ無の Mind は claim_issue で
        forbidden。default fallback すると Guild 隔離が破れるので、明示的に
        unknown 扱い。"""
        ms = self.home / "minds" / "old-mind"
        ms.mkdir(parents=True, exist_ok=True)
        (ms / ".mind-meta.md").write_text(
            "---\nmind_name: old-mind\nkind: generic\npersona: designer\n"
            "guild: default\n---\n",
            encoding="utf-8",
        )
        iid = _submit_issue(self.home, "for-anyone", guild="default")
        out = self._call(
            "claim_issue", {"mind_name": "old-mind", "issue_id": iid},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertIsNone(out.get("mind_guild"))
        self.assertIn("registry", out.get("error", "").lower())

    def test_missing_registry_entry_blocks_cross_inbox_read(self) -> None:
        """default guildmaster が registry 無 target を観察してしまう穴 (Codex
        P1 #91 2 回目) を塞ぐ: target_guild が None なら forbidden。"""
        _write_mind_meta(self.home, "gm", guild="default", persona="guildmaster")
        ms = self.home / "minds" / "ghost-backend"
        ms.mkdir(parents=True, exist_ok=True)
        (ms / ".mind-meta.md").write_text(
            "---\nmind_name: ghost-backend\nkind: generic\n"
            "persona: implementer\nguild: backend\n---\n",
            encoding="utf-8",
        )
        out = self._call(
            "read_inbox",
            {"mind_name": "gm", "target_mind": "ghost-backend"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertIsNone(out.get("target_guild"))
        self.assertIn("registry", out.get("error", "").lower())

    def test_forged_mindspace_persona_cannot_bypass_read_inbox_axiom(self) -> None:
        """同上を read_inbox 経路でも検証 (target_mind 指定して他者観察)。"""
        self._spawn_designer_with_forged_mindspace("attacker", "default")
        # 観察対象 (bob) は別途用意
        _write_mind_meta(self.home, "bob", guild="default", persona="implementer")
        out = self._call(
            "read_inbox",
            {"mind_name": "attacker", "target_mind": "bob"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_persona"), "designer")

    def test_forged_mindspace_persona_cannot_bypass_kill_mind_axiom(self) -> None:
        """Phase 5c-3: 同上を kill_mind 経路でも検証。Mindspace 内
        `.mind-meta.md` で persona=guildmaster を僭称しても、registry 側の真値
        (= designer) を見るので kill_mind は forbidden で reject される。"""
        self._spawn_designer_with_forged_mindspace("attacker", "default")
        _write_mind_meta(self.home, "victim", guild="default", persona="implementer")
        out = self._call(
            "kill_mind",
            {"mind_name": "attacker", "target_mind": "victim"},
        )
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")
        self.assertEqual(out.get("requester_persona"), "designer")
        self.assertIn("guildmaster-only-kill", out.get("error", ""))


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package not installed; skip nexus tool tests")
class TestMindScopeObservationTools(unittest.TestCase):
    """Phase 5d-3 (#68 / ADR-0017): Mind 向け Observation MCP tool 3 個の
    identity binding + scope filter を検証する。

    本 class は AI_ORG_OS_MIND_NAME を **bound** にして、identity binding が
    効いた状態でテストする (他クラスは unbound で multi-mind を扱うため
    対比的に bound)。
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = str(self.home)
        # identity を alice に bind
        self._old_bound = os.environ.get("AI_ORG_OS_MIND_NAME")
        os.environ["AI_ORG_OS_MIND_NAME"] = "alice"
        for mod in (
            "nexus", "inbox", "guild", "storage",
            "mind_scope", "dispatch_flow", "observe", "resource_usage",
            "anomaly",
        ):
            sys.modules.pop(mod, None)
        self.nexus = importlib.import_module("nexus")

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        if self._old_bound is None:
            os.environ.pop("AI_ORG_OS_MIND_NAME", None)
        else:
            os.environ["AI_ORG_OS_MIND_NAME"] = self._old_bound
        self.tmp.cleanup()
        for mod in (
            "nexus", "inbox", "guild", "storage",
            "mind_scope", "dispatch_flow", "observe", "resource_usage",
            "anomaly",
        ):
            sys.modules.pop(mod, None)

    def _call(self, name: str, args: dict) -> dict:
        result = asyncio.run(self.nexus.call_tool(name, args))
        return json.loads(result[0].text)

    def _mk_two_minds(self) -> None:
        _write_mind_meta(self.home, "alice", guild="default")
        _write_mind_meta(self.home, "bob", guild="default")

    def test_observe_self_returns_caller_only(self) -> None:
        self._mk_two_minds()
        out = self._call("observe_self", {"mind_name": "alice"})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("mind_name"), "alice")
        self.assertNotIn("bob", json.dumps(out))

    def test_observe_self_identity_binding_rejects_impersonation(self) -> None:
        """bound 状態で他 Mind を名乗ろうとすると forbidden (ADR-0008)。"""
        self._mk_two_minds()
        out = self._call("observe_self", {"mind_name": "bob"})
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")

    def test_observe_my_dispatches_filters_other_minds(self) -> None:
        self._mk_two_minds()
        _write_mind_meta(self.home, "carol", guild="default")
        # alice -> bob
        from storage import Nexus as _NexusCls  # noqa: PLC0415
        storage_dir = self.home / "conduit-storage"
        unbound = _NexusCls(storage_dir=storage_dir, identity=None)
        unbound.send_dispatch(
            from_mind="alice", to_mind="bob", topic="hi", body="x",
        )
        # bob -> carol (alice には見えてはいけない)
        unbound.send_dispatch(
            from_mind="bob", to_mind="carol", topic="hi", body="x",
        )
        out = self._call("observe_my_dispatches", {"mind_name": "alice"})
        self.assertTrue(out.get("ok"), out)
        # outbound: alice -> bob のみ
        self.assertEqual(len(out["outbound"]), 1)
        self.assertEqual(out["outbound"][0]["to"], "bob")
        # carol は **どこにも出ない**
        self.assertNotIn("carol", json.dumps(out))

    def test_observe_my_dispatches_identity_binding(self) -> None:
        self._mk_two_minds()
        out = self._call("observe_my_dispatches", {"mind_name": "bob"})
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")

    def test_observe_my_guild_returns_own_guild_rollup(self) -> None:
        self._mk_two_minds()
        _write_mind_meta(self.home, "carol", guild="research")  # 他 Guild
        out = self._call("observe_my_guild", {"mind_name": "alice"})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("guild"), "default")
        self.assertIn("alice", out["members"])
        self.assertIn("bob", out["members"])
        # 他 Guild の carol は含まれない
        self.assertNotIn("carol", out["members"])
        self.assertNotIn("carol", json.dumps(out))

    def test_observe_my_guild_identity_binding(self) -> None:
        self._mk_two_minds()
        out = self._call("observe_my_guild", {"mind_name": "bob"})
        self.assertFalse(out.get("ok"), out)
        self.assertEqual(out.get("code"), "forbidden")


if __name__ == "__main__":
    unittest.main()
