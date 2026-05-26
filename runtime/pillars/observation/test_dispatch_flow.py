"""
test_dispatch_flow.py — dispatch_flow.py のユニットテスト (Observation v0.2 / #66)。

検証する性質:
- happy path: 単一 / 複数 / 双方向 dispatch の集計
- ill-formed frontmatter (no `---` / unterminated / 必須欠落 / 形式違反) の skip
- recipient dir 名と `to` フィールドの食い違いを skip
- inbox + archive の合算
- symlink の無視 (path traversal 防御 / 二重カウント防御)
- OSError 系の skip 動作 (個別 file 失敗で集計全体を止めない)
- 本文に立ち入らない: 本文側に `---` を含むファイルでも frontmatter のみ抽出

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

import dispatch_flow as df  # noqa: E402


def _write_dispatch(
    storage_dir: Path,
    state: str,
    to: str,
    msg_id: str,
    *,
    sender: str = "alice",
    recipient: str | None = None,
    dispatched_at: str = "2026-05-26T10:00:00Z",
    topic: str = "hi",
    body: str = "hello",
    extra_lines: list[str] | None = None,
) -> Path:
    """tmp storage に dispatch file を 1 つ書く。"""
    rec_dir = storage_dir / state / to
    rec_dir.mkdir(parents=True, exist_ok=True)
    msg_path = rec_dir / f"{msg_id}.md"
    fm = [
        "---",
        f"from: {sender}",
        f"to: {recipient if recipient is not None else to}",
        f"topic: {topic}",
        f"dispatched_at: {dispatched_at}",
        f"msg_id: {msg_id}",
    ]
    if extra_lines:
        fm.extend(extra_lines)
    fm.append("---")
    content = "\n".join(fm) + "\n\n" + body + "\n"
    msg_path.write_text(content, encoding="utf-8")
    return msg_path


class TestParseDispatchFrontmatter(unittest.TestCase):
    """parse_dispatch_frontmatter の境界ケース。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _silent(self, fn, *a, **kw):
        with redirect_stderr(io.StringIO()):
            return fn(*a, **kw)

    def test_happy_path(self) -> None:
        path = _write_dispatch(self.dir, "inbox", "bob", "m1", sender="alice")
        meta = df.parse_dispatch_frontmatter(path)
        self.assertIsNotNone(meta)
        assert meta is not None  # type narrow
        self.assertEqual(meta["from"], "alice")
        self.assertEqual(meta["to"], "bob")
        self.assertEqual(meta["dispatched_at"], "2026-05-26T10:00:00Z")
        self.assertEqual(meta["msg_id"], "m1")

    def test_no_frontmatter_returns_none(self) -> None:
        path = self.dir / "noframe.md"
        path.write_text("just body, no frontmatter\n", encoding="utf-8")
        self.assertIsNone(self._silent(df.parse_dispatch_frontmatter, path))

    def test_unterminated_frontmatter_returns_none(self) -> None:
        path = self.dir / "unterm.md"
        path.write_text(
            "---\nfrom: alice\nto: bob\ndispatched_at: 2026-05-26T10:00:00Z\n",
            encoding="utf-8",
        )
        self.assertIsNone(self._silent(df.parse_dispatch_frontmatter, path))

    def test_missing_required_field(self) -> None:
        path = self.dir / "missing.md"
        path.write_text(
            "---\nfrom: alice\nto: bob\n---\nbody\n",
            encoding="utf-8",
        )
        # dispatched_at が無い → None
        self.assertIsNone(self._silent(df.parse_dispatch_frontmatter, path))

    def test_invalid_from(self) -> None:
        path = self.dir / "badfrom.md"
        path.write_text(
            "---\nfrom: ../escape\nto: bob\n"
            "dispatched_at: 2026-05-26T10:00:00Z\n---\nbody\n",
            encoding="utf-8",
        )
        self.assertIsNone(self._silent(df.parse_dispatch_frontmatter, path))

    def test_invalid_dispatched_at_format(self) -> None:
        path = self.dir / "badtime.md"
        path.write_text(
            "---\nfrom: alice\nto: bob\n"
            "dispatched_at: yesterday\n---\nbody\n",
            encoding="utf-8",
        )
        self.assertIsNone(self._silent(df.parse_dispatch_frontmatter, path))

    def test_body_contains_triple_dash_is_ignored(self) -> None:
        """本文に `---` が含まれていても frontmatter は冒頭ブロックで確定する。
        本文を read してしまっていると、ここで余計な処理が走って失敗する。
        """
        path = _write_dispatch(
            self.dir,
            "inbox",
            "bob",
            "m2",
            body="line1\n---\nline2 (this is body, not frontmatter)\n",
        )
        meta = df.parse_dispatch_frontmatter(path)
        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(meta["from"], "alice")
        self.assertEqual(meta["to"], "bob")

    def test_open_failure_returns_none(self) -> None:
        # 存在しないパス。`open` が失敗して None。
        missing = self.dir / "does-not-exist.md"
        self.assertIsNone(self._silent(df.parse_dispatch_frontmatter, missing))


class TestAggregateFlow(unittest.TestCase):
    """aggregate_flow の集計挙動。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _silent_agg(self) -> list[df.FlowEdge]:
        with redirect_stderr(io.StringIO()):
            return df.aggregate_flow(self.storage)

    def test_empty_storage_yields_empty_list(self) -> None:
        edges = self._silent_agg()
        self.assertEqual(edges, [])

    def test_single_dispatch_inbox(self) -> None:
        _write_dispatch(
            self.storage, "inbox", "bob", "m1",
            sender="alice", dispatched_at="2026-05-26T10:00:00Z",
        )
        edges = self._silent_agg()
        self.assertEqual(len(edges), 1)
        e = edges[0]
        self.assertEqual(e.from_mind, "alice")
        self.assertEqual(e.to_mind, "bob")
        self.assertEqual(e.count, 1)
        self.assertEqual(e.first_at, "2026-05-26T10:00:00Z")
        self.assertEqual(e.last_at, "2026-05-26T10:00:00Z")

    def test_combines_inbox_and_archive(self) -> None:
        _write_dispatch(
            self.storage, "inbox", "bob", "m1",
            sender="alice", dispatched_at="2026-05-26T10:00:00Z",
        )
        _write_dispatch(
            self.storage, "archive", "bob", "m2",
            sender="alice", dispatched_at="2026-05-26T11:00:00Z",
        )
        edges = self._silent_agg()
        self.assertEqual(len(edges), 1)
        e = edges[0]
        self.assertEqual(e.count, 2)
        self.assertEqual(e.first_at, "2026-05-26T10:00:00Z")
        self.assertEqual(e.last_at, "2026-05-26T11:00:00Z")

    def test_separate_edges_for_different_senders(self) -> None:
        _write_dispatch(self.storage, "inbox", "bob", "m1", sender="alice")
        _write_dispatch(self.storage, "inbox", "bob", "m2", sender="carol")
        edges = self._silent_agg()
        # (alice, bob) と (carol, bob) で別 edge、辞書順ソート
        self.assertEqual([(e.from_mind, e.to_mind) for e in edges],
                         [("alice", "bob"), ("carol", "bob")])

    def test_bidirectional_dispatches(self) -> None:
        _write_dispatch(self.storage, "inbox", "bob", "m1", sender="alice")
        _write_dispatch(self.storage, "inbox", "alice", "m2", sender="bob")
        edges = self._silent_agg()
        self.assertEqual(len(edges), 2)
        keys = sorted((e.from_mind, e.to_mind) for e in edges)
        self.assertEqual(keys, [("alice", "bob"), ("bob", "alice")])

    def test_recipient_dir_mismatch_is_skipped(self) -> None:
        # recipient dir 名 = 'bob' なのに frontmatter で `to: carol`
        # → 契約違反として skip
        _write_dispatch(
            self.storage, "inbox", "bob", "m1",
            sender="alice", recipient="carol",
        )
        self.assertEqual(self._silent_agg(), [])

    def test_malformed_recipient_dir_name_is_skipped(self) -> None:
        # 不正なディレクトリ名 (path traversal を試みる類)
        bad = self.storage / "inbox" / ".."
        # .. は OS によって作れないので別 invalid name で試す
        weird = self.storage / "inbox" / "has space"
        weird.mkdir(parents=True, exist_ok=True)
        (weird / "m1.md").write_text(
            "---\nfrom: alice\nto: has space\n"
            "dispatched_at: 2026-05-26T10:00:00Z\n---\nbody\n",
            encoding="utf-8",
        )
        # 'has space' は _VALID_NAME_RE 違反 → skip
        self.assertEqual(self._silent_agg(), [])

    def test_ill_formed_file_skipped(self) -> None:
        # 正常な 1 件
        _write_dispatch(self.storage, "inbox", "bob", "m1", sender="alice")
        # ill-formed (frontmatter 無し)
        rec = self.storage / "inbox" / "bob"
        (rec / "broken.md").write_text("just body\n", encoding="utf-8")
        edges = self._silent_agg()
        # broken は skip、正常 1 件のみ集計される
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].count, 1)

    def test_symlink_recipient_dir_skipped(self) -> None:
        """symlink な recipient dir は path traversal の窓 → 無視。"""
        # 正常な dir
        _write_dispatch(self.storage, "inbox", "bob", "m1", sender="alice")
        # symlink (alice → bob)。OS によっては symlink を作れないので、その場合は skip
        link_path = self.storage / "inbox" / "alice"
        try:
            os.symlink(self.storage / "inbox" / "bob", link_path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not supported on this filesystem")
        edges = self._silent_agg()
        # bob 経由は 1 件、alice symlink は無視
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].to_mind, "bob")

    def test_with_pre_built_metas(self) -> None:
        """metas 引数 (injection 点) のスモークテスト。"""
        metas = [
            {"from": "x", "to": "y", "dispatched_at": "2026-05-26T09:00:00Z"},
            {"from": "x", "to": "y", "dispatched_at": "2026-05-26T11:00:00Z"},
        ]
        edges = df.aggregate_flow(metas=metas)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].count, 2)
        self.assertEqual(edges[0].first_at, "2026-05-26T09:00:00Z")
        self.assertEqual(edges[0].last_at, "2026-05-26T11:00:00Z")


class TestFormat(unittest.TestCase):
    def test_empty_table(self) -> None:
        self.assertEqual(df.format_flow_table([]), "(no dispatches)")

    def test_table_has_header_and_row(self) -> None:
        edges = [df.FlowEdge("alice", "bob", 3,
                             "2026-05-26T10:00:00Z", "2026-05-26T12:00:00Z")]
        text = df.format_flow_table(edges)
        self.assertIn("from", text)
        self.assertIn("alice", text)
        self.assertIn("bob", text)
        self.assertIn("3", text)

    def test_json_roundtrip(self) -> None:
        edges = [df.FlowEdge("a", "b", 1, "t1", "t1")]
        out = df.flow_to_json(edges)
        self.assertEqual(out, [{
            "from_mind": "a", "to_mind": "b", "count": 1,
            "first_at": "t1", "last_at": "t1",
        }])


if __name__ == "__main__":
    unittest.main()
