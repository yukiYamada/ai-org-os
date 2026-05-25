"""
test_observe.py — observe.py の Realm view 集約ロジックを検証する。

Codex P2 (#88): Inbox 読み込み失敗時に Guild summary が「pending=0」を
全 Guild に表示する不整合の回帰防止。pending_list が None のとき
"pending=?" + 説明行が出ることを確認する。

標準ライブラリのみ。`list_pending_issues` を unittest.mock で例外を
raise するように差し替える。
"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
