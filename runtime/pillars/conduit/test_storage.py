"""
Unit tests for Nexus storage layer.

Standard library only (unittest, tempfile, pathlib). No MCP dependency.

Run (any of these works from the repo root or from runtime/pillars/conduit):
  python -m unittest discover runtime/pillars/conduit -p 'test_*.py'
  cd runtime/pillars/conduit && python -m unittest test_storage
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Make `import storage` work no matter where unittest is invoked from.
sys.path.insert(0, str(Path(__file__).parent))

from storage import AuthorizationError, Nexus  # noqa: E402  — sys.path tweak must run first


class NexusTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        # ADR-0026: logs_dir を tmp 配下に固定して、本物の ~/.ai-org-os/logs/
        # を test が汚さないようにする。
        self.logs_dir = self.tmp_dir / "logs"
        # Fix #136: minds_dir も tmp 配下に固定 (nudge file を実 Mindspace に
        # touch しないため)。
        self.minds_dir = self.tmp_dir / "minds"
        self.nexus = Nexus(
            storage_dir=self.tmp_dir,
            logs_dir=self.logs_dir,
            minds_dir=self.minds_dir,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestSendDispatch(NexusTestBase):
    def test_happy_path_creates_inbox_file(self) -> None:
        result = self.nexus.send_dispatch(
            from_mind="mind-a",
            to_mind="mind-b",
            topic="hello",
            body="本文です",
        )
        self.assertTrue(result["ok"])
        self.assertIn("msg_id", result)
        msg_path = Path(result["stored_at"])
        self.assertTrue(msg_path.exists())
        content = msg_path.read_text(encoding="utf-8")
        self.assertIn("from: mind-a", content)
        self.assertIn("to: mind-b", content)
        self.assertIn("topic: hello", content)
        self.assertIn("本文です", content)

    def test_invalid_from_mind_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.nexus.send_dispatch(from_mind="../evil", to_mind="b", topic="t", body="x")

    def test_invalid_to_mind_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.nexus.send_dispatch(from_mind="a", to_mind="bad name with space", topic="t", body="x")

    def test_empty_topic_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.nexus.send_dispatch(from_mind="a", to_mind="b", topic="   ", body="x")

    def test_newline_in_topic_rejected(self) -> None:
        """axiom: topic 改行は frontmatter 破壊 → identity 偽装可。
        Phase 5e Step B Codex P1 fix。\n / \r 両方を reject。"""
        for bad in ("foo\nfrom: evil", "foo\rbar", "foo\r\nbar"):
            with self.subTest(topic=bad):
                with self.assertRaises(ValueError) as ctx:
                    self.nexus.send_dispatch(
                        from_mind="a", to_mind="b", topic=bad, body="x"
                    )
                self.assertIn("newline", str(ctx.exception).lower())

    def test_msg_id_format(self) -> None:
        result = self.nexus.send_dispatch(from_mind="m1", to_mind="m2", topic="t", body="x")
        # YYYYMMDDTHHMMSSZ-<sender>-<8 hex>
        self.assertRegex(result["msg_id"], r"^\d{8}T\d{6}Z-m1-[0-9a-f]{8}$")


class TestReadInbox(NexusTestBase):
    def test_empty_inbox(self) -> None:
        result = self.nexus.read_inbox(mind_name="nobody")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["messages"], [])

    def test_returns_sent_messages(self) -> None:
        self.nexus.send_dispatch(from_mind="a", to_mind="b", topic="t1", body="body1")
        self.nexus.send_dispatch(from_mind="a", to_mind="b", topic="t2", body="body2")
        result = self.nexus.read_inbox(mind_name="b")
        self.assertEqual(result["count"], 2)
        bodies = "\n".join(m["content"] for m in result["messages"])
        self.assertIn("body1", bodies)
        self.assertIn("body2", bodies)

    def test_other_mind_inbox_not_leaked(self) -> None:
        self.nexus.send_dispatch(from_mind="a", to_mind="b", topic="t", body="secret-for-b")
        result = self.nexus.read_inbox(mind_name="c")
        self.assertEqual(result["count"], 0)


class TestAckDispatch(NexusTestBase):
    def test_moves_to_archive(self) -> None:
        sent = self.nexus.send_dispatch(from_mind="a", to_mind="b", topic="t", body="x")
        msg_id = sent["msg_id"]
        ack = self.nexus.ack_dispatch(mind_name="b", msg_id=msg_id)
        self.assertTrue(ack["ok"])
        self.assertFalse(ack.get("already_acked"))
        # inbox から消える
        result = self.nexus.read_inbox(mind_name="b")
        self.assertEqual(result["count"], 0)
        # archive に存在する
        archive_path = self.tmp_dir / "archive" / "b" / f"{msg_id}.md"
        self.assertTrue(archive_path.exists())

    def test_unknown_msg_returns_not_ok(self) -> None:
        # Never existed in either inbox or archive.
        result = self.nexus.ack_dispatch(mind_name="b", msg_id="20260522T000000Z-a-deadbeef")
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])

    def test_invalid_msg_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.nexus.ack_dispatch(mind_name="b", msg_id="../../escape")

    def test_double_ack_is_idempotent(self) -> None:
        # Regression test for Codex P1 (PR #23): ack_dispatch must be safe to retry.
        # MCP transport timeouts / client restarts may cause the same ack to be issued twice.
        sent = self.nexus.send_dispatch(from_mind="a", to_mind="b", topic="t", body="x")
        msg_id = sent["msg_id"]

        # First ack: normal path.
        first = self.nexus.ack_dispatch(mind_name="b", msg_id=msg_id)
        self.assertTrue(first["ok"])
        self.assertFalse(first.get("already_acked"))

        # Second ack: must succeed as a no-op, not return ok=False.
        second = self.nexus.ack_dispatch(mind_name="b", msg_id=msg_id)
        self.assertTrue(second["ok"], f"second ack should be idempotent, got: {second}")
        self.assertTrue(second.get("already_acked"))
        self.assertEqual(first["archived_at"], second["archived_at"])


class TestSecurityConstraints(NexusTestBase):
    def test_mind_name_cannot_traverse_path(self) -> None:
        # 万一 validation を抜けても storage_dir 内に閉じることを担保
        # validation はここで raise されるはず
        with self.assertRaises(ValueError):
            self.nexus.read_inbox(mind_name="../outside")

    def test_long_mind_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.nexus.read_inbox(mind_name="a" * 65)


class TestIdentityBinding(unittest.TestCase):
    """Issue #19 / ADR-0008: identity binding prevents Mind impersonation.

    Each Nexus session can be bound to a single Mind name (typically via the
    AI_ORG_OS_MIND_NAME env var). All operations whose mind_name / from_mind
    does not match the bound identity are rejected with PermissionError.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        # ADR-0026: 全 Nexus に渡す logs_dir を統一して、本物の
        # ~/.ai-org-os/logs/ を test が汚さないようにする。
        self.logs_dir = self.tmp_dir / "logs"
        # Fix #136: minds_dir も tmp 配下 (nudge file の test 隔離)。
        self.minds_dir = self.tmp_dir / "minds"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _nx(self, **kwargs: object) -> Nexus:
        """各テストの Nexus 生成で logs_dir / minds_dir / storage_dir を統一注入する。"""
        defaults = {
            "storage_dir": self.tmp_dir,
            "logs_dir": self.logs_dir,
            "minds_dir": self.minds_dir,
        }
        defaults.update(kwargs)
        return Nexus(**defaults)  # type: ignore[arg-type]

    def test_invalid_identity_rejected_at_init(self) -> None:
        with self.assertRaises(ValueError):
            Nexus(storage_dir=self.tmp_dir, identity="../escape", logs_dir=self.logs_dir, minds_dir=self.minds_dir)

    def test_reserved_identity_warden_rejected_at_init(self) -> None:
        """Issue #112 / ADR-0024 §3: Mind が 'warden' として MCP server を
        立ち上げられない (Warden 偽装防止)。"""
        with self.assertRaises(ValueError) as ctx:
            self._nx(identity="warden")
        self.assertIn("reserved", str(ctx.exception).lower())
        self.assertIn("warden", str(ctx.exception))

    def test_unbound_nexus_accepts_warden_sender(self) -> None:
        """identity=None (= Conductor/Warden 経路) は warden を from_mind に
        使えなければ Step B actuator が壊れる。予約語チェックは Mind 名
        (identity) にのみ適用、from_mind には適用しない。"""
        nx = self._nx()  # identity=None
        result = nx.send_dispatch(
            from_mind="warden", to_mind="bob", topic="t", body="x"
        )
        self.assertTrue(result["ok"])

    def test_unbound_nexus_accepts_any_mind(self) -> None:
        # 既存挙動の維持（identity=None で誰の名前でも OK）。
        nx = self._nx()
        result = nx.send_dispatch(from_mind="anyone", to_mind="other", topic="t", body="x")
        self.assertTrue(result["ok"])

    def test_bound_nexus_accepts_matching_from_mind(self) -> None:
        nx = self._nx(identity="alice")
        result = nx.send_dispatch(from_mind="alice", to_mind="bob", topic="t", body="x")
        self.assertTrue(result["ok"])

    def test_bound_nexus_rejects_impersonation_in_send(self) -> None:
        nx = self._nx(identity="alice")
        with self.assertRaises(AuthorizationError) as ctx:
            nx.send_dispatch(from_mind="bob", to_mind="carol", topic="t", body="x")
        self.assertIn("alice", str(ctx.exception))
        self.assertIn("bob", str(ctx.exception))
        # AuthorizationError must NOT be the built-in PermissionError, so that
        # callers can distinguish identity denials from fs-level permission errors
        # (Codex P2 PR #27 follow-up).
        self.assertNotIsInstance(ctx.exception, PermissionError)

    def test_bound_nexus_rejects_reading_other_inbox(self) -> None:
        nx = self._nx(identity="alice")
        with self.assertRaises(AuthorizationError):
            nx.read_inbox(mind_name="bob")

    def test_bound_nexus_accepts_reading_own_inbox(self) -> None:
        nx = self._nx(identity="alice")
        result = nx.read_inbox(mind_name="alice")
        self.assertTrue(result["ok"])

    def test_bound_nexus_rejects_acking_other_message(self) -> None:
        # alice's session cannot ack messages addressed to bob.
        nx = self._nx(identity="alice")
        with self.assertRaises(AuthorizationError):
            nx.ack_dispatch(mind_name="bob", msg_id="20260523T000000Z-x-deadbeef")

    def test_bound_nexus_can_ack_own_message_end_to_end(self) -> None:
        # alice sends to bob; bob's session acks it. Two distinct bound sessions.
        nx_alice = self._nx(identity="alice")
        nx_bob = self._nx(identity="bob")

        sent = nx_alice.send_dispatch(from_mind="alice", to_mind="bob", topic="t", body="hi")
        msg_id = sent["msg_id"]

        # bob can read his own inbox.
        inbox = nx_bob.read_inbox(mind_name="bob")
        self.assertEqual(inbox["count"], 1)

        # bob can ack his own message.
        ack = nx_bob.ack_dispatch(mind_name="bob", msg_id=msg_id)
        self.assertTrue(ack["ok"])

        # alice CANNOT ack bob's message (impersonation guard).
        with self.assertRaises(AuthorizationError):
            nx_alice.ack_dispatch(mind_name="bob", msg_id=msg_id)

    def test_auth_error_is_distinct_from_builtin_permission_error(self) -> None:
        # Codex P2 (PR #27 follow-up): AuthorizationError must NOT be a subclass
        # of built-in PermissionError, so callers and `except` clauses can
        # distinguish identity denials from OS-level fs permission errors.
        self.assertFalse(issubclass(AuthorizationError, PermissionError))
        self.assertTrue(issubclass(AuthorizationError, Exception))


class TestDispatchJsonlLogging(NexusTestBase):
    """ADR-0026 §4.1: send_dispatch / ack_dispatch が dispatch.jsonl に記録する。"""

    def _read_log_lines(self) -> list[dict]:
        import json

        log_path = self.logs_dir / "dispatch.jsonl"
        if not log_path.exists():
            return []
        return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]

    def test_send_writes_dispatch_sent_event(self) -> None:
        result = self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="hello", body="hi"
        )
        rows = self._read_log_lines()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["event"], "dispatch.sent")
        self.assertEqual(row["actor"], "conduit")
        self.assertEqual(row["from"], "alice")
        self.assertEqual(row["to"], "bob")
        self.assertEqual(row["topic"], "hello")
        self.assertEqual(row["msg_id"], result["msg_id"])

    def test_ack_writes_dispatch_acked_event(self) -> None:
        sent = self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t", body="x"
        )
        self.nexus.ack_dispatch(mind_name="bob", msg_id=sent["msg_id"])
        rows = self._read_log_lines()
        # send + ack で 2 行
        self.assertEqual(len(rows), 2)
        ack_row = rows[1]
        self.assertEqual(ack_row["event"], "dispatch.acked")
        self.assertEqual(ack_row["actor"], "conduit")
        self.assertEqual(ack_row["by"], "bob")
        self.assertEqual(ack_row["msg_id"], sent["msg_id"])

    def test_already_acked_does_not_emit_duplicate_event(self) -> None:
        """2 回目の ack (= already_acked) は log line を増やさない。"""
        sent = self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t", body="x"
        )
        self.nexus.ack_dispatch(mind_name="bob", msg_id=sent["msg_id"])
        before = len(self._read_log_lines())
        # 2 回目: already_acked になる
        result = self.nexus.ack_dispatch(mind_name="bob", msg_id=sent["msg_id"])
        self.assertTrue(result["already_acked"])
        after = len(self._read_log_lines())
        self.assertEqual(before, after, "already_acked should NOT emit dispatch.acked")

    def test_not_found_ack_does_not_emit_event(self) -> None:
        """存在しない msg_id への ack は ok=False で、log line も増やさない。"""
        result = self.nexus.ack_dispatch(
            mind_name="bob", msg_id="20260522T000000Z-x-deadbeef"
        )
        self.assertFalse(result["ok"])
        self.assertEqual(self._read_log_lines(), [])

    def test_log_file_not_created_on_invalid_send(self) -> None:
        """validation で raise する経路では log を書かない (= write 後に到達不能)。"""
        with self.assertRaises(ValueError):
            self.nexus.send_dispatch(
                from_mind="../evil", to_mind="bob", topic="t", body="x"
            )
        self.assertEqual(self._read_log_lines(), [])


class TestDispatchNudge(NexusTestBase):
    """Fix #136: send_dispatch が recipient Mindspace の .mind-loop.nudge を
    touch して mind-loop の sleep を即時抜けさせる。

    nudge は **recipient Mindspace が存在するときだけ** 作る (= Mind 未 spawn /
    Warden への dispatch / kill 直後 race では silent skip)。失敗系は dispatch
    本体を覆さない (= F3-like)。
    """

    def _nudge_path(self, mind: str) -> Path:
        return self.minds_dir / mind / ".mind-loop.nudge"

    def _make_mindspace(self, mind: str) -> None:
        (self.minds_dir / mind).mkdir(parents=True, exist_ok=True)

    def test_nudge_created_when_recipient_mindspace_exists(self) -> None:
        """recipient の Mindspace が存在すれば nudge file が touch される。"""
        self._make_mindspace("bob")
        self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t", body="x"
        )
        self.assertTrue(
            self._nudge_path("bob").is_file(),
            "expected .mind-loop.nudge to exist for recipient bob",
        )

    def test_nudge_skipped_when_recipient_mindspace_missing(self) -> None:
        """recipient の Mindspace が無ければ nudge は作らず、dispatch 本体は成功。"""
        # bob's Mindspace は意図的に作らない
        result = self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t", body="x"
        )
        self.assertTrue(result["ok"])
        # nudge 親 dir は無い
        self.assertFalse(self._nudge_path("bob").exists())

    def test_nudge_does_not_touch_sender_mindspace(self) -> None:
        """nudge は recipient 側にしか作らない (= self-nudge 不要)。"""
        self._make_mindspace("alice")
        self._make_mindspace("bob")
        self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t", body="x"
        )
        self.assertFalse(self._nudge_path("alice").exists())
        self.assertTrue(self._nudge_path("bob").is_file())

    def test_nudge_failure_does_not_break_dispatch(self) -> None:
        """nudge 書き込みが失敗しても send_dispatch は成功を返す (F3-like)。

        recipient Mindspace を **file** にしておく (dir ではない) → nudge の
        touch は OSError になるが、dispatch 本体は既に永続化されている。
        """
        # bob を file として作る (= mkdir 不可、nudge path は無効)
        (self.minds_dir).mkdir(parents=True, exist_ok=True)
        bogus = self.minds_dir / "bob"
        bogus.write_text("not a dir", encoding="utf-8")
        result = self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t", body="x"
        )
        self.assertTrue(result["ok"])
        # dispatch 自体は archive 側に置かれている (= storage_dir/inbox/bob/...)
        # は recipient_inbox の mkdir で fail するはずなので、本ケースは
        # send_dispatch の earlier step で OSError になる可能性が高い。
        # 重要なのは "is_dir() == False" の場合に nudge skip すること。
        # bob は file なので is_dir() == False → nudge code は noop。
        # よって少なくとも send_dispatch が完走 (= ok=True) すれば nudge 起因の
        # exception は無いことが保証される。

    def test_warden_recipient_does_not_create_nudge(self) -> None:
        """warden 宛 dispatch (Mind 返信、ADR-0025) は warden Mindspace が無い
        ので nudge は silent skip。"""
        result = self.nexus.send_dispatch(
            from_mind="alice", to_mind="warden", topic="reply", body="x"
        )
        self.assertTrue(result["ok"])
        self.assertFalse(self._nudge_path("warden").exists())

    def test_nudge_overwrites_existing(self) -> None:
        """同 recipient に短時間で複数 dispatch が来ても nudge は冪等 (touch)。"""
        self._make_mindspace("bob")
        self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t1", body="x"
        )
        self.assertTrue(self._nudge_path("bob").is_file())
        # 2 回目: 既に nudge があっても touch は冪等
        self.nexus.send_dispatch(
            from_mind="alice", to_mind="bob", topic="t2", body="x"
        )
        self.assertTrue(self._nudge_path("bob").is_file())


if __name__ == "__main__":
    unittest.main()
