"""
test_observe.py — observe.py の Realm view 集約ロジックを検証する。

Codex P2 (#88): Inbox 読み込み失敗時に Guild summary が「pending=0」を
全 Guild に表示する不整合の回帰防止。pending_list が None のとき
"pending=?" + 説明行が出ることを確認する。

標準ライブラリのみ。`list_pending_issues` を unittest.mock で例外を
raise するように差し替える。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import observe  # noqa: E402


class TestFormatRealmViewInboxFailure(unittest.TestCase):
    """Codex P2 (#88): list_pending_issues が失敗した場合の Guild section の振る舞い。"""

    def setUp(self) -> None:
        # observe.py の guild lookup は templates/guilds/default を見るので
        # AI_ORG_OS_HOME を tmp に向けて副作用を出さない (home overlay は空)。
        self.tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("AI_ORG_OS_HOME")
        os.environ["AI_ORG_OS_HOME"] = self.tmp.name

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        self.tmp.cleanup()

    def test_guild_section_shows_unknown_when_inbox_fails(self) -> None:
        # Inbox 読み込みが例外で失敗するシナリオ。
        # observe.py 内部の `from inbox import list_pending_issues` は
        # `sys.modules` に依存するので、先に inbox を import → モジュールの
        # 関数を差し替える方法を取る。
        sys.path.insert(
            0,
            str(Path(observe.RUNTIME_DIR) / "pillars" / "inbox"),
        )
        import inbox  # noqa: PLC0415

        # _format_realm_view は引数に MindObservation 群を取り、内部で
        # 各種 lookup を行う。空 list で OK。
        with mock.patch.object(
            inbox,
            "list_pending_issues",
            side_effect=RuntimeError("simulated read failure"),
        ):
            out = observe._format_realm_view([])

        # Inbox section が unavailable を示すこと
        self.assertIn("Inbox Queue (unavailable:", out)
        # Guild section が "pending=?" を 1 つ以上含むこと (default Guild)
        self.assertIn("pending=?", out)
        # pending=0 が並ぶ誤情報が出ないこと
        self.assertNotIn(
            "pending=0", out,
            "Inbox unavailable のときに pending=0 を見せてはいけない "
            "(Codex P2 #88)",
        )
        # 「なぜ ? が並んでいるか」の説明行があること
        self.assertIn("pending counts unknown", out)

    def test_guild_section_shows_zero_when_inbox_empty(self) -> None:
        """Inbox 読み込みが成功 (空 list) のときは従来通り pending=0 を表示。

        Codex P2 修正で「失敗時 vs 空 list」を区別したことの保証。
        """
        sys.path.insert(
            0,
            str(Path(observe.RUNTIME_DIR) / "pillars" / "inbox"),
        )
        import inbox  # noqa: PLC0415

        with mock.patch.object(inbox, "list_pending_issues", return_value=[]):
            out = observe._format_realm_view([])

        # Inbox は success
        self.assertIn("Inbox Queue (0 pending)", out)
        # Guild section は pending=0 を表示 (現状の挙動)
        self.assertIn("pending=0", out)
        self.assertNotIn("pending=?", out)
        self.assertNotIn("pending counts unknown", out)


class TestResourceMindSetConsistency(unittest.TestCase):
    """Codex P2 (#93): `--resource` (table) と `--resource --json` が同じ
    Mind 集合を返すことを検証する。

    旧実装は JSON 側が `all_usage()` (= `minds/` 配下の **valid 名前** dir
    すべて) を駆動軸にしていたため、`.mind-meta.md` が無い「中途状態」
    dir も JSON にだけ現れる不整合があった。修正後は両者とも
    `gather_observations()` 由来の Mind だけを報告する。
    """

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

    def _mk_mind(self, name: str, *, with_meta: bool) -> None:
        d = self.home / "minds" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "filler.txt").write_text("x" * 10, encoding="utf-8")
        if with_meta:
            (d / ".mind-meta.md").write_text(
                f"---\nmind_name: {name}\nkind: generic\n"
                f"persona: designer\nguild: default\n"
                f"spawned_at: 2026-05-26T00:00:00Z\n---\n",
                encoding="utf-8",
            )

    def test_json_and_table_report_same_mind_set(self) -> None:
        """spawned Mind (alice) と「dir だけある」half-baked dir (stray) を
        両方置く。--resource と --resource --json の Mind 集合は一致するべき。
        """
        self._mk_mind("alice", with_meta=True)
        self._mk_mind("stray", with_meta=False)  # 中途半端 dir

        from io import StringIO  # noqa: PLC0415
        from contextlib import redirect_stdout, redirect_stderr  # noqa: PLC0415

        # --resource (table)
        buf_table = StringIO()
        with redirect_stdout(buf_table), redirect_stderr(StringIO()):
            observe.main(["--resource"])
        table_out = buf_table.getvalue()
        self.assertIn("alice", table_out)
        # half-baked dir は table に出ない (gather_observations が
        # .mind-meta.md 必須としているため)
        # NOTE: "stray" は category 行などに混入しない厳しめ検査だが、
        # 文字列マッチで十分 (テーブルの NAME 列に出現しないこと)。
        self.assertNotIn("stray", table_out)

        # --resource --json
        buf_json = StringIO()
        with redirect_stdout(buf_json), redirect_stderr(StringIO()):
            observe.main(["--resource", "--json"])
        json_payload = json.loads(buf_json.getvalue())
        json_mindspaces = sorted(
            b["name"] for b in json_payload if b["category"] == "mindspace"
        )
        # spawned mind だけ。stray は JSON にも出ないこと。
        self.assertEqual(json_mindspaces, ["alice"])
        # 末尾の conduit-storage バケットは別 category で 1 件揃う
        categories = [b["category"] for b in json_payload]
        self.assertEqual(categories.count("conduit-storage"), 1)


if __name__ == "__main__":
    unittest.main()
