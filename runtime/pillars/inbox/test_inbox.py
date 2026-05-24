#!/usr/bin/env python3
"""
test_inbox.py — Inbox Pillar (inbox.py) のユニットテスト。

Phase 5a-5 / Issue #40。テスト要件:
- submit_issue: 正常系 / 不正 title / 不正 submitter / 不正 priority / 不正 body
- list_pending_issues: 空 / 複数 / frontmatter 不正のスキップ / ソート順
- claim_issue: 正常系 / 存在しない id / 二重 claim / 不正 issue_id
- atomic write の tmp 残骸チェック
- path traversal 防御（issue_id は外部から渡されない）

標準ライブラリのみ。mcp 等は不要。
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

# Make `import inbox` work no matter where unittest is invoked from.
sys.path.insert(0, str(Path(__file__).parent))

from inbox import (  # noqa: E402
    ALLOWED_PRIORITIES,
    ISSUE_ID_RE,
    IssueNotFoundError,
    IssueRecord,
    IssueValidationError,
    SUBMITTER_RE,
    TITLE_MAX_LEN,
    _gen_issue_id,
    claim_issue,
    list_pending_issues,
    main,
    submit_issue,
)


FIXED_NOW = dt.datetime(2026, 5, 24, 12, 0, 0, tzinfo=dt.timezone.utc)


class TestGenIssueId(unittest.TestCase):
    def test_format(self) -> None:
        iid = _gen_issue_id(FIXED_NOW)
        # `YYYYMMDDTHHMMSSZ-<8 hex>`
        self.assertRegex(iid, ISSUE_ID_RE.pattern)
        self.assertTrue(iid.startswith("20260524T120000Z-"))

    def test_random_part_is_8_hex(self) -> None:
        iid = _gen_issue_id(FIXED_NOW)
        random_part = iid.split("-")[-1]
        self.assertEqual(len(random_part), 8)
        int(random_part, 16)  # hex として parse できる

    def test_uniqueness_in_same_second(self) -> None:
        """同一秒に大量生成しても 8 hex の衝突は実用上発生しない。"""
        ids = {_gen_issue_id(FIXED_NOW) for _ in range(1000)}
        self.assertEqual(len(ids), 1000)


class TestSubmitIssueValidation(unittest.TestCase):
    """submit_issue の入力検証。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.issues_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_reject_empty_title(self) -> None:
        with self.assertRaises(IssueValidationError):
            submit_issue("", "body", issues_dir=self.issues_dir)

    def test_reject_too_long_title(self) -> None:
        title = "a" * (TITLE_MAX_LEN + 1)
        with self.assertRaises(IssueValidationError):
            submit_issue(title, "body", issues_dir=self.issues_dir)

    def test_accept_max_length_title(self) -> None:
        """境界値: ちょうど TITLE_MAX_LEN は accept。"""
        title = "a" * TITLE_MAX_LEN
        path = submit_issue(title, "body", issues_dir=self.issues_dir)
        self.assertTrue(path.exists())

    def test_reject_newline_in_title(self) -> None:
        with self.assertRaises(IssueValidationError):
            submit_issue("title\nwith newline", "body", issues_dir=self.issues_dir)
        with self.assertRaises(IssueValidationError):
            submit_issue("title\rwith CR", "body", issues_dir=self.issues_dir)

    def test_reject_invalid_submitter(self) -> None:
        cases = ["", "has space", "has/slash", "../escape", "x" * 65, "日本語"]
        for bad in cases:
            with self.subTest(submitter=bad):
                with self.assertRaises(IssueValidationError):
                    submit_issue(
                        "ok title",
                        "body",
                        submitter=bad,
                        issues_dir=self.issues_dir,
                    )

    def test_accept_valid_submitter(self) -> None:
        cases = ["human", "alice", "user.bot_2", "A-Z_0-9.123"]
        for good in cases:
            with self.subTest(submitter=good):
                path = submit_issue(
                    "ok title",
                    "body",
                    submitter=good,
                    issues_dir=self.issues_dir,
                )
                self.assertTrue(path.exists())

    def test_reject_invalid_priority(self) -> None:
        for bad in ["", "p4", "P1", "high", "p1 "]:
            with self.subTest(priority=bad):
                with self.assertRaises(IssueValidationError):
                    submit_issue(
                        "ok",
                        "body",
                        priority=bad,
                        issues_dir=self.issues_dir,
                    )

    def test_accept_all_allowed_priorities(self) -> None:
        for p in ALLOWED_PRIORITIES:
            with self.subTest(priority=p):
                path = submit_issue(
                    "ok",
                    "body",
                    priority=p,
                    issues_dir=self.issues_dir,
                )
                self.assertTrue(path.exists())

    def test_reject_non_string_body(self) -> None:
        with self.assertRaises(IssueValidationError):
            submit_issue("ok", None, issues_dir=self.issues_dir)  # type: ignore[arg-type]


class TestSubmitIssue(unittest.TestCase):
    """submit_issue 正常系・ファイル構造。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.issues_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_writes_to_inbox(self) -> None:
        path = submit_issue(
            "テストタイトル",
            "詳細な依頼内容",
            issues_dir=self.issues_dir,
        )
        self.assertTrue(path.exists())
        self.assertEqual(path.parent.name, "inbox")
        self.assertTrue(path.name.endswith(".md"))
        # issue_id 形式
        self.assertRegex(path.stem, ISSUE_ID_RE.pattern)

    def test_frontmatter_contains_all_fields(self) -> None:
        path = submit_issue(
            "タイトル",
            "本文",
            priority="p1",
            submitter="alice",
            issues_dir=self.issues_dir,
            now=FIXED_NOW,
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("issue_id: ", text)
        self.assertIn("title: タイトル", text)
        self.assertIn("submitted_at: 2026-05-24T12:00:00Z", text)
        self.assertIn("submitter: alice", text)
        self.assertIn("priority: p1", text)
        self.assertIn("本文", text)

    def test_creates_directories_if_missing(self) -> None:
        nested = self.issues_dir / "nested" / "issues"
        path = submit_issue("t", "b", issues_dir=nested)
        self.assertTrue(path.exists())
        self.assertTrue((nested / "inbox").is_dir())
        self.assertTrue((nested / "archive").is_dir())

    def test_no_tmp_residue_after_write(self) -> None:
        """atomic write の tmp ファイルが残らない。"""
        submit_issue("t", "b", issues_dir=self.issues_dir)
        inbox = self.issues_dir / "inbox"
        residues = list(inbox.glob("*.tmp*"))
        self.assertEqual(residues, [], f"unexpected tmp residue: {residues}")

    def test_multiple_submissions_have_unique_ids(self) -> None:
        paths = [
            submit_issue(f"t{i}", "b", issues_dir=self.issues_dir) for i in range(10)
        ]
        ids = {p.stem for p in paths}
        self.assertEqual(len(ids), 10)

    def test_concurrent_submissions_do_not_collide(self) -> None:
        """並行 submit で互いを上書きしない（atomic os.link）。"""
        n = 20
        errors: list[BaseException] = []

        def worker(i: int) -> None:
            try:
                submit_issue(f"t{i}", "b", issues_dir=self.issues_dir)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        inbox = self.issues_dir / "inbox"
        files = list(inbox.glob("*.md"))
        self.assertEqual(len(files), n, "all submissions should produce unique files")


class TestListPendingIssues(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.issues_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_when_no_issues(self) -> None:
        self.assertEqual(list_pending_issues(issues_dir=self.issues_dir), [])

    def test_empty_when_dir_missing(self) -> None:
        nonexistent = self.issues_dir / "no_such"
        self.assertEqual(list_pending_issues(issues_dir=nonexistent), [])

    def test_lists_multiple_in_order(self) -> None:
        # 投入順 = issue_id 昇順
        t0 = FIXED_NOW
        t1 = FIXED_NOW + dt.timedelta(seconds=1)
        t2 = FIXED_NOW + dt.timedelta(seconds=2)
        p_a = submit_issue("A", "a", issues_dir=self.issues_dir, now=t0)
        p_b = submit_issue("B", "b", issues_dir=self.issues_dir, now=t1)
        p_c = submit_issue("C", "c", issues_dir=self.issues_dir, now=t2)

        records = list_pending_issues(issues_dir=self.issues_dir)
        self.assertEqual(len(records), 3)
        # issue_id の昇順 = 投入時刻昇順
        self.assertLess(records[0].issue_id, records[1].issue_id)
        self.assertLess(records[1].issue_id, records[2].issue_id)
        # 中身の検証
        titles = [r.title for r in records]
        self.assertEqual(titles, ["A", "B", "C"])
        paths = [r.path for r in records]
        self.assertEqual(paths, [p_a, p_b, p_c])

    def test_fifo_order_within_same_second(self) -> None:
        """Codex P2 PR #70 fix: 同一秒内でも microsecond 解像度で FIFO 保証。

        旧実装は random 8 hex だけで sort していたため、同一秒の投入は arrival
        と無関係な順序になっていた。microsecond を ID に含めることで
        lexicographic = FIFO を担保する。
        """
        base = FIXED_NOW  # microsecond = 0
        # 同じ秒内、microsecond 違いで 3 件投入
        ts = [
            base.replace(microsecond=100_000),
            base.replace(microsecond=500_000),
            base.replace(microsecond=900_000),
        ]
        submit_issue("first",  "1", issues_dir=self.issues_dir, now=ts[0])
        submit_issue("second", "2", issues_dir=self.issues_dir, now=ts[1])
        submit_issue("third",  "3", issues_dir=self.issues_dir, now=ts[2])

        records = list_pending_issues(issues_dir=self.issues_dir)
        self.assertEqual(len(records), 3)
        self.assertEqual([r.title for r in records], ["first", "second", "third"])

    def test_skips_invalid_frontmatter(self) -> None:
        """frontmatter が壊れているファイルはスキップされる（全停止しない）。"""
        inbox = self.issues_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        # 正常な Issue
        good = submit_issue("ok", "body", issues_dir=self.issues_dir, now=FIXED_NOW)
        # frontmatter 無し（issue_id 形式のファイル名でも内容が空なら skip）
        bad_id = "20260524T120001Z-deadbeef"
        (inbox / f"{bad_id}.md").write_text("no frontmatter here", encoding="utf-8")
        # frontmatter 閉じてない
        bad_id2 = "20260524T120002Z-cafef00d"
        (inbox / f"{bad_id2}.md").write_text("---\nissue_id: x\n", encoding="utf-8")
        # ファイル名と issue_id が一致しない（手書き偽装）
        bad_id3 = "20260524T120003Z-12345678"
        forged = (
            "---\n"
            "issue_id: 20260524T120099Z-99999999\n"
            "title: forged\n"
            "submitted_at: 2026-05-24T12:00:03Z\n"
            "submitter: human\n"
            "priority: p2\n"
            "---\n\nbody\n"
        )
        (inbox / f"{bad_id3}.md").write_text(forged, encoding="utf-8")

        records = list_pending_issues(issues_dir=self.issues_dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].path, good)

    def test_ignores_non_md_files(self) -> None:
        inbox = self.issues_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "README.txt").write_text("hello", encoding="utf-8")
        (inbox / ".gitkeep").write_text("", encoding="utf-8")
        submit_issue("ok", "b", issues_dir=self.issues_dir)
        records = list_pending_issues(issues_dir=self.issues_dir)
        self.assertEqual(len(records), 1)

    def test_record_body_excludes_frontmatter(self) -> None:
        body_text = "line 1\nline 2\n\nline 4"
        submit_issue("t", body_text, issues_dir=self.issues_dir, now=FIXED_NOW)
        records = list_pending_issues(issues_dir=self.issues_dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].body, body_text)


class TestClaimIssue(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.issues_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_moves_to_archive(self) -> None:
        path = submit_issue("t", "b", issues_dir=self.issues_dir)
        issue_id = path.stem
        rec = claim_issue(issue_id, issues_dir=self.issues_dir)
        self.assertEqual(rec.issue_id, issue_id)
        # inbox からは消えた
        self.assertFalse(path.exists())
        # archive に移った（Windows の短いファイル名 KOKORO~1 と
        # 通常の kokoro068 の表記揺れに耐えるため resolve() で正規化して比較）。
        archived = (self.issues_dir / "archive" / f"{issue_id}.md").resolve()
        self.assertTrue(archived.exists())
        self.assertEqual(rec.path.resolve(), archived)

    def test_not_found_for_unknown_id(self) -> None:
        # New format (Codex P2 PR #70 fix): YYYYMMDDTHHMMSSZ-NNNNNN-<8 hex>
        unknown = "20260524T120000Z-000000-00000000"
        with self.assertRaises(IssueNotFoundError):
            claim_issue(unknown, issues_dir=self.issues_dir)

    def test_double_claim_raises(self) -> None:
        path = submit_issue("t", "b", issues_dir=self.issues_dir)
        issue_id = path.stem
        claim_issue(issue_id, issues_dir=self.issues_dir)
        with self.assertRaises(IssueNotFoundError):
            claim_issue(issue_id, issues_dir=self.issues_dir)

    def test_claim_with_claimer_records_metadata(self) -> None:
        """Phase 5b-2 (#75): claimer 指定で frontmatter に claimed_by/claimed_at が追記される。"""
        path = submit_issue("t", "body content", issues_dir=self.issues_dir)
        issue_id = path.stem
        fixed_now = dt.datetime(2026, 5, 24, 3, 0, 0, tzinfo=dt.timezone.utc)

        rec = claim_issue(
            issue_id,
            issues_dir=self.issues_dir,
            claimer="alice",
            now=fixed_now,
        )

        # 戻り値は archive 側のパス
        archived = (self.issues_dir / "archive" / f"{issue_id}.md").resolve()
        self.assertEqual(rec.path.resolve(), archived)
        # inbox からは消えた
        self.assertFalse(path.exists())

        # archive ファイルに claimed_by / claimed_at が追記されている
        content = archived.read_text(encoding="utf-8")
        self.assertIn("claimed_by: alice", content)
        self.assertIn("claimed_at: 2026-05-24T03:00:00Z", content)
        # 元の body は残っている
        self.assertIn("body content", content)
        # 元の他フィールドも残っている
        self.assertIn(f"issue_id: {issue_id}", content)
        self.assertIn("title: t", content)
        self.assertIn("submitter: human", content)

    def test_claim_with_invalid_claimer_raises(self) -> None:
        """claimer も submitter と同じ文字集合検証。"""
        path = submit_issue("t", "b", issues_dir=self.issues_dir)
        issue_id = path.stem
        bad_claimers = ["", "has space", "../escape", "x" * 65, "日本語"]
        for bad in bad_claimers:
            with self.subTest(claimer=bad):
                with self.assertRaises(IssueValidationError):
                    claim_issue(issue_id, issues_dir=self.issues_dir, claimer=bad)

    def test_double_claim_with_claimer_raises(self) -> None:
        """claimer 付き claim も二重 claim 拒否する (atomic 維持)。"""
        path = submit_issue("t", "b", issues_dir=self.issues_dir)
        issue_id = path.stem
        claim_issue(issue_id, issues_dir=self.issues_dir, claimer="alice")
        with self.assertRaises(IssueNotFoundError):
            claim_issue(issue_id, issues_dir=self.issues_dir, claimer="bob")

    def test_claim_with_claimer_leaves_no_tmp_residue(self) -> None:
        """claim 完了後 *.tmp.claim.* 残骸が残らない。"""
        path = submit_issue("t", "b", issues_dir=self.issues_dir)
        claim_issue(path.stem, issues_dir=self.issues_dir, claimer="alice")
        residues = list((self.issues_dir / "archive").glob("*.tmp.*"))
        self.assertEqual(residues, [])

    def test_rejects_invalid_issue_id_format(self) -> None:
        """path traversal / 危険文字を含む issue_id は形式チェックで弾く。"""
        bad_ids = [
            "../etc/passwd",
            "20260524T120000Z-../escape",
            "20260524T120000Z-XXXXXXXX",  # 非 hex
            "20260524T120000Z-deadbee",   # 7 hex
            "20260524T120000Z-deadbeef0", # 9 hex
            "not-an-id",
            "",
            "20260524T120000Z\x00",
            "/abs/path",
        ]
        for bad in bad_ids:
            with self.subTest(issue_id=bad):
                with self.assertRaises(IssueValidationError):
                    claim_issue(bad, issues_dir=self.issues_dir)

    def test_concurrent_claim_only_one_wins(self) -> None:
        """同じ Issue を 2 並行 claim → 1 つだけ成功、もう 1 つは NotFound。"""
        path = submit_issue("t", "b", issues_dir=self.issues_dir)
        issue_id = path.stem

        results: list[str] = []
        errors: list[BaseException] = []
        barrier = threading.Barrier(2)

        def worker() -> None:
            barrier.wait()
            try:
                rec = claim_issue(issue_id, issues_dir=self.issues_dir)
                results.append(rec.issue_id)
            except IssueNotFoundError as exc:
                errors.append(exc)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 1, f"exactly one claim must win, got {results}")
        self.assertEqual(len(errors), 1, f"the loser must see NotFound, got {errors}")
        self.assertIsInstance(errors[0], IssueNotFoundError)


class TestPathTraversalDefense(unittest.TestCase):
    """issue_id が外部から渡される箇所では path traversal を拒否する。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.issues_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_submit_does_not_accept_issue_id_from_outside(self) -> None:
        """submit_issue のシグネチャに issue_id を渡す API は存在しない。

        Pillar の public API は title/body/priority/submitter のみを引数に取り、
        issue_id は内部生成。これは構造的な path traversal 防御。
        """
        import inspect

        sig = inspect.signature(submit_issue)
        self.assertNotIn("issue_id", sig.parameters)

    def test_claim_validates_issue_id_pattern(self) -> None:
        """claim は外部から issue_id を受けるので、形式を必ず検証する。"""
        with self.assertRaises(IssueValidationError):
            claim_issue("../../../etc/passwd", issues_dir=self.issues_dir)


class TestPatterns(unittest.TestCase):
    """正規表現が他 Pillar と整合していることの確認（regression）。"""

    def test_submitter_pattern_matches_mind_name_pattern(self) -> None:
        # conduit/storage.py / spawn-mind.sh と同じ pattern。
        self.assertEqual(SUBMITTER_RE.pattern, r"^[A-Za-z0-9._-]{1,64}$")

    def test_priorities_include_p0_through_p3(self) -> None:
        self.assertEqual(set(ALLOWED_PRIORITIES), {"p0", "p1", "p2", "p3"})


class TestCli(unittest.TestCase):
    """CLI 経由の動作確認。end-to-end ではなく、各サブコマンドの単体動作。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.issues_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> int:
        return main(argv)

    def test_submit_then_list_then_claim(self) -> None:
        # submit
        rc = self._run(
            [
                "--issues-dir",
                str(self.issues_dir),
                "submit",
                "test cli",
                "--body",
                "body",
                "--priority",
                "p1",
            ]
        )
        self.assertEqual(rc, 0)

        # list
        records = list_pending_issues(issues_dir=self.issues_dir)
        self.assertEqual(len(records), 1)
        issue_id = records[0].issue_id

        # claim
        rc = self._run(
            ["--issues-dir", str(self.issues_dir), "claim", issue_id]
        )
        self.assertEqual(rc, 0)
        # claim 後は inbox から消える
        self.assertEqual(list_pending_issues(issues_dir=self.issues_dir), [])

    def test_submit_invalid_title_returns_nonzero(self) -> None:
        rc = self._run(
            [
                "--issues-dir",
                str(self.issues_dir),
                "submit",
                "title\nwith newline",
            ]
        )
        self.assertNotEqual(rc, 0)

    def test_claim_unknown_returns_nonzero(self) -> None:
        rc = self._run(
            [
                "--issues-dir",
                str(self.issues_dir),
                "claim",
                # New format (Codex P2 PR #70 fix): YYYYMMDDTHHMMSSZ-NNNNNN-<8 hex>
                "20260524T120000Z-000000-00000000",
            ]
        )
        self.assertNotEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
