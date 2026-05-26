"""
test_mind_scope.py — mind_scope.py の Mind-scope 観察 API のテスト
(Observation Pillar v1.0 / #68)。

検証する性質:
- observe_self: 自分の row のみ返す、他 Mind の情報無し
- observe_self: 存在しない Mind は not_found
- observe_dispatches_for: 自分が from/to の dispatch のみ、他 Mind 間は除外
- observe_dispatches_for: window_seconds で時間絞り込み
- observe_guild_for: 自 Guild の members / guildmasters / pending を返す
- observe_guild_for: registry エントリ無は forbidden
- build_realm_report: schema_version + 4 セクション (minds / flow / resource / anomaly)

標準ライブラリのみ。
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import mind_scope  # noqa: E402


def _mk_mind(
    home: Path,
    name: str,
    *,
    kind: str = "generic",
    persona: str = "designer",
    guild: str = "default",
) -> None:
    """tmp $AI_ORG_OS_HOME に Mindspace + registry entry を作る。"""
    d = home / "minds" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / ".mind-meta.md").write_text(
        f"---\nmind_name: {name}\nkind: {kind}\npersona: {persona}\n"
        f"guild: {guild}\nspawned_at: 2026-05-26T00:00:00Z\n---\n",
        encoding="utf-8",
    )
    reg = home / "registry" / "minds"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{name}.md").write_text(
        f"---\nmind_name: {name}\nkind: {kind}\npersona: {persona}\n"
        f"guild: {guild}\nspawned_at: 2026-05-26T00:00:00Z\n---\n",
        encoding="utf-8",
    )


def _write_dispatch(
    home: Path,
    sender: str,
    recipient: str,
    *,
    dispatched_at: str,
    msg_id: str,
    state: str = "inbox",
) -> None:
    rec_dir = home / "conduit-storage" / state / recipient
    rec_dir.mkdir(parents=True, exist_ok=True)
    p = rec_dir / f"{msg_id}.md"
    p.write_text(
        f"---\nfrom: {sender}\nto: {recipient}\ntopic: t\n"
        f"dispatched_at: {dispatched_at}\nmsg_id: {msg_id}\n---\nbody\n",
        encoding="utf-8",
    )


class _HomeFixture(unittest.TestCase):
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


class TestObserveSelf(_HomeFixture):

    def test_returns_self_only(self) -> None:
        _mk_mind(self.home, "alice")
        _mk_mind(self.home, "bob")
        with redirect_stderr(io.StringIO()):
            out = mind_scope.observe_self("alice")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out["mind_name"], "alice")
        # bob の情報は出てこない (1 件のみ)
        self.assertNotIn("bob", str(out))

    def test_includes_guild_and_size(self) -> None:
        _mk_mind(self.home, "alice", guild="research")
        # filler 追加で size != 0 に
        (self.home / "minds" / "alice" / "note.md").write_text(
            "hello", encoding="utf-8",
        )
        with redirect_stderr(io.StringIO()):
            out = mind_scope.observe_self("alice")
        self.assertEqual(out["guild"], "research")
        self.assertGreater(out["mindspace_files"], 0)
        self.assertGreater(out["mindspace_bytes"], 0)

    def test_not_found(self) -> None:
        with redirect_stderr(io.StringIO()):
            out = mind_scope.observe_self("ghost")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("code"), "not_found")


class TestObserveDispatchesFor(_HomeFixture):

    def test_filters_to_only_caller_dispatches(self) -> None:
        _mk_mind(self.home, "alice")
        _mk_mind(self.home, "bob")
        _mk_mind(self.home, "carol")
        # alice -> bob
        _write_dispatch(
            self.home, "alice", "bob",
            dispatched_at="2026-05-26T10:00:00Z", msg_id="m1",
        )
        # bob -> alice
        _write_dispatch(
            self.home, "bob", "alice",
            dispatched_at="2026-05-26T11:00:00Z", msg_id="m2",
        )
        # bob -> carol (他 Mind 同士、alice には見えてはならない)
        _write_dispatch(
            self.home, "bob", "carol",
            dispatched_at="2026-05-26T12:00:00Z", msg_id="m3",
        )
        with redirect_stderr(io.StringIO()):
            out = mind_scope.observe_dispatches_for("alice")
        self.assertTrue(out.get("ok"))
        # outbound: alice -> bob
        self.assertEqual([e["to"] for e in out["outbound"]], ["bob"])
        # inbound: bob -> alice
        self.assertEqual([e["from"] for e in out["inbound"]], ["bob"])
        # bob -> carol は **どこにも出ない**
        flat = str(out)
        self.assertNotIn("carol", flat)

    def test_window_seconds_filters_by_time(self) -> None:
        _mk_mind(self.home, "alice")
        _mk_mind(self.home, "bob")
        # 古い dispatch (24h 前)
        _write_dispatch(
            self.home, "alice", "bob",
            dispatched_at="2026-05-25T10:00:00Z", msg_id="m1",
        )
        # 新しい dispatch (1h 前 = window 内)
        _write_dispatch(
            self.home, "alice", "bob",
            dispatched_at="2026-05-26T10:00:00Z", msg_id="m2",
        )
        # now_epoch を固定 (2026-05-26T10:30:00Z 相当)
        import calendar  # noqa: PLC0415
        import datetime as dt  # noqa: PLC0415
        now = calendar.timegm(
            dt.datetime(2026, 5, 26, 10, 30, 0).timetuple()
        )
        with redirect_stderr(io.StringIO()):
            out = mind_scope.observe_dispatches_for(
                "alice", window_seconds=3600, now_epoch=now,
            )
        # 1h window だと 新しい dispatch のみ
        self.assertEqual(len(out["outbound"]), 1)
        self.assertEqual(out["outbound"][0]["count"], 1)
        self.assertEqual(out["outbound"][0]["first_at"], "2026-05-26T10:00:00Z")


class TestObserveGuildFor(_HomeFixture):

    def test_returns_own_guild_rollup(self) -> None:
        _mk_mind(self.home, "alice", guild="default")
        _mk_mind(self.home, "gm", persona="guildmaster", guild="default")
        _mk_mind(self.home, "carol", guild="research")
        with redirect_stderr(io.StringIO()):
            out = mind_scope.observe_guild_for("alice")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out["guild"], "default")
        self.assertIn("alice", out["members"])
        self.assertIn("gm", out["members"])
        self.assertIn("gm", out["guildmasters"])
        # 他 Guild の Mind 'carol' は出ない
        self.assertNotIn("carol", out["members"])

    def test_no_registry_entry_is_forbidden(self) -> None:
        # registry 無で .mind-meta.md だけある "legacy" Mind は forbidden
        d = self.home / "minds" / "legacy"
        d.mkdir(parents=True, exist_ok=True)
        (d / ".mind-meta.md").write_text(
            "---\nmind_name: legacy\nkind: generic\npersona: designer\n"
            "guild: default\n---\n",
            encoding="utf-8",
        )
        with redirect_stderr(io.StringIO()):
            out = mind_scope.observe_guild_for("legacy")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("code"), "forbidden")


class TestBuildRealmReport(_HomeFixture):

    def test_schema_and_sections(self) -> None:
        _mk_mind(self.home, "alice")
        with redirect_stderr(io.StringIO()):
            report = mind_scope.build_realm_report()
        self.assertEqual(report["schema_version"], "1.0")
        self.assertIn("generated_at", report)
        # 4 セクション
        self.assertIn("minds", report)
        self.assertIn("flow", report)
        self.assertIn("resource", report)
        self.assertIn("anomaly", report)
        # minds は 1 件 (alice)
        self.assertEqual(len(report["minds"]), 1)
        self.assertEqual(report["minds"][0]["mind_name"], "alice")
        # resource は mindspace + storage の 2 バケット
        self.assertEqual(
            [b["category"] for b in report["resource"]],
            ["mindspace", "conduit-storage"],
        )


if __name__ == "__main__":
    unittest.main()
