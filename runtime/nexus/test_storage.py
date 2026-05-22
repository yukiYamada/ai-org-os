"""
Unit tests for Nexus storage layer.

Standard library only (unittest, tempfile, pathlib). No MCP dependency.

Run:
  python -m unittest runtime.nexus.test_storage
or:
  cd runtime/nexus && python -m unittest test_storage
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from storage import Nexus


class NexusTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.nexus = Nexus(storage_dir=self.tmp_dir)

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
        # inbox から消える
        result = self.nexus.read_inbox(mind_name="b")
        self.assertEqual(result["count"], 0)
        # archive に存在する
        archive_path = self.tmp_dir / "archive" / "b" / f"{msg_id}.md"
        self.assertTrue(archive_path.exists())

    def test_unknown_msg_returns_not_ok(self) -> None:
        result = self.nexus.ack_dispatch(mind_name="b", msg_id="20260522T000000Z-a-deadbeef")
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])

    def test_invalid_msg_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.nexus.ack_dispatch(mind_name="b", msg_id="../../escape")


class TestSecurityConstraints(NexusTestBase):
    def test_mind_name_cannot_traverse_path(self) -> None:
        # 万一 validation を抜けても storage_dir 内に閉じることを担保
        # validation はここで raise されるはず
        with self.assertRaises(ValueError):
            self.nexus.read_inbox(mind_name="../outside")

    def test_long_mind_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.nexus.read_inbox(mind_name="a" * 65)


if __name__ == "__main__":
    unittest.main()
