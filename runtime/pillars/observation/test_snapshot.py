#!/usr/bin/env python3
"""
test_snapshot.py — Observation Pillar v0.1 (snapshot.py) のユニットテスト。

ROADMAP v0.1 のテスト要件:
- 保存 / 読み戻し
- ID 重複（microsecond 同一時 → suffix で回避）
- TTL prune の安全性（負数 / 非存在ディレクトリ / 非 json ファイル混在）

mcp 等の外部依存なし。標準ライブラリのみで完結。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Make `import snapshot` work no matter where unittest is invoked from.
sys.path.insert(0, str(Path(__file__).parent))

from snapshot import (  # noqa: E402
    DEFAULT_TTL_DAYS,
    _build_payload,
    _snapshot_id,
    load_snapshot,
    prune_snapshots,
    write_snapshot,
)


FIXED_NOW = dt.datetime(2026, 5, 24, 12, 0, 0, 123456, tzinfo=dt.timezone.utc)


class TestSnapshotId(unittest.TestCase):
    def test_id_format(self) -> None:
        sid = _snapshot_id(FIXED_NOW)
        self.assertEqual(sid, "20260524T120000Z-123456")

    def test_id_sortable(self) -> None:
        a = _snapshot_id(FIXED_NOW)
        b = _snapshot_id(FIXED_NOW + dt.timedelta(microseconds=1))
        self.assertLess(a, b)


class TestBuildPayload(unittest.TestCase):
    def test_payload_keys(self) -> None:
        payload = _build_payload(FIXED_NOW)
        self.assertIn("generated_at", payload)
        self.assertIn("snapshot_id", payload)
        self.assertIn("minds", payload)
        self.assertEqual(payload["generated_at"], "2026-05-24T12:00:00Z")
        self.assertIsInstance(payload["minds"], list)


class TestWriteSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_writes_json_file(self) -> None:
        path = write_snapshot(target_dir=self.target, now=FIXED_NOW)
        self.assertTrue(path.exists())
        self.assertTrue(path.name.endswith(".json"))
        # JSON parseable
        loaded = load_snapshot(path)
        self.assertEqual(loaded["snapshot_id"], "20260524T120000Z-123456")
        self.assertIn("minds", loaded)

    def test_creates_target_dir_if_missing(self) -> None:
        nested = self.target / "doesnt_exist_yet" / "snapshots"
        path = write_snapshot(target_dir=nested, now=FIXED_NOW)
        self.assertTrue(path.exists())
        self.assertTrue(nested.is_dir())

    def test_same_microsecond_does_not_overwrite(self) -> None:
        """Microsecond 衝突時に -2, -3 が付くこと。"""
        p1 = write_snapshot(target_dir=self.target, now=FIXED_NOW)
        p2 = write_snapshot(target_dir=self.target, now=FIXED_NOW)
        self.assertNotEqual(p1, p2)
        self.assertTrue(p1.exists())
        self.assertTrue(p2.exists())
        # 中身は同じ snapshot_id だが、ファイル名が違う
        d1 = load_snapshot(p1)
        d2 = load_snapshot(p2)
        self.assertEqual(d1["snapshot_id"], d2["snapshot_id"])

    def test_payload_is_valid_json(self) -> None:
        path = write_snapshot(target_dir=self.target, now=FIXED_NOW)
        # json.loads が例外なく通る = valid JSON
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["generated_at"], "2026-05-24T12:00:00Z")

    def test_no_tmp_residue_after_write(self) -> None:
        """書き込み完了後 tmp ファイルが残らない。"""
        write_snapshot(target_dir=self.target, now=FIXED_NOW)
        residues = list(self.target.glob("*.tmp*"))
        self.assertEqual(residues, [])

    def test_collision_uses_link_and_increments_counter(self) -> None:
        """衝突時に os.link が FileExistsError → counter で別名。

        self-review fix: tmp + rename だと race window で snapshot が失われうるが、
        os.link は atomic に予約するので並行衝突しても両方残る。
        ここでは事前に sid.json を作っておくことで衝突状況を再現する。
        """
        sid = "20260524T120000Z-123456"
        # 事前に「先客」を置く
        pre_existing = self.target / f"{sid}.json"
        pre_existing.write_text("{}", encoding="utf-8")

        # write_snapshot は sid と衝突するので -2 サフィックスを使うはず
        path = write_snapshot(target_dir=self.target, now=FIXED_NOW)
        self.assertEqual(path.name, f"{sid}-2.json")
        # 元のファイルは消えていない
        self.assertTrue(pre_existing.exists())
        # 新しいファイルは valid JSON で snapshot_id を持つ
        loaded = load_snapshot(path)
        self.assertEqual(loaded["snapshot_id"], sid)


class TestPruneSnapshots(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_at_mtime(self, name: str, mtime_epoch: float) -> Path:
        path = self.target / name
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (mtime_epoch, mtime_epoch))
        return path

    def test_deletes_files_older_than_ttl(self) -> None:
        now = FIXED_NOW
        # 10 日前の古いファイルを 2 つ、1 日前の新しいファイルを 1 つ
        old1 = self._write_at_mtime("old1.json", now.timestamp() - 10 * 86400)
        old2 = self._write_at_mtime("old2.json", now.timestamp() - 10 * 86400)
        new1 = self._write_at_mtime("new.json", now.timestamp() - 86400)

        deleted = prune_snapshots(target_dir=self.target, ttl_days=7, now=now)
        deleted_names = {p.name for p in deleted}
        self.assertEqual(deleted_names, {"old1.json", "old2.json"})
        self.assertFalse(old1.exists())
        self.assertFalse(old2.exists())
        self.assertTrue(new1.exists())

    def test_skips_non_json_files(self) -> None:
        now = FIXED_NOW
        self._write_at_mtime("old.json", now.timestamp() - 10 * 86400)
        bystander = self._write_at_mtime("README.txt", now.timestamp() - 10 * 86400)
        deleted = prune_snapshots(target_dir=self.target, ttl_days=7, now=now)
        self.assertEqual({p.name for p in deleted}, {"old.json"})
        self.assertTrue(bystander.exists(), "non-json must not be deleted")

    def test_negative_ttl_raises(self) -> None:
        with self.assertRaises(ValueError):
            prune_snapshots(target_dir=self.target, ttl_days=-1, now=FIXED_NOW)

    def test_ttl_zero_deletes_all_json(self) -> None:
        now = FIXED_NOW
        # 全部 1 秒前 = 0 日 TTL なら全削除
        self._write_at_mtime("a.json", now.timestamp() - 1)
        self._write_at_mtime("b.json", now.timestamp() - 1)
        deleted = prune_snapshots(target_dir=self.target, ttl_days=0, now=now)
        self.assertEqual(len(deleted), 2)

    def test_ttl_zero_deletes_mtime_equal_to_now(self) -> None:
        """Codex P2 PR #62: mtime == cutoff のファイルも削除される (`<=` 境界)。

        旧実装の `<` だと、mtime が now と等しいファイル (粒度が荒い FS でよく起きる) が
        ttl_days=0 でも残ってしまう。README/CLI は ttl_days=0 を「全削除」と謳う。
        """
        now = FIXED_NOW
        self._write_at_mtime("equal.json", now.timestamp())
        deleted = prune_snapshots(target_dir=self.target, ttl_days=0, now=now)
        self.assertEqual({p.name for p in deleted}, {"equal.json"})

    def test_ttl_boundary_inclusive_for_ttl_days(self) -> None:
        """ちょうど ttl_days 秒前のファイルも削除される（`<=` 境界）。"""
        now = FIXED_NOW
        # ちょうど 7 日前 = 7 * 86400 秒前
        boundary = self._write_at_mtime("boundary.json", now.timestamp() - 7 * 86400)
        deleted = prune_snapshots(target_dir=self.target, ttl_days=7, now=now)
        self.assertEqual({p.name for p in deleted}, {"boundary.json"})
        self.assertFalse(boundary.exists())

    def test_cleans_old_tmp_residue(self) -> None:
        """self-review fix: prune は 5 秒以上経過した *.tmp* 残骸を掃除する。

        write_snapshot が途中で crash した場合に tmp ファイルが残るが、これを
        次回 prune で掃除する。進行中の write を巻き込まないよう 5 秒の余白を取る。
        """
        now = FIXED_NOW
        # 古い tmp 残骸（5 秒前以前）
        old_tmp = self._write_at_mtime("snap.json.tmp.12345.999999", now.timestamp() - 60)
        # 新しい tmp（進行中の write 想定、5 秒以内なので消さない）
        new_tmp = self._write_at_mtime("snap2.json.tmp.67890.111111", now.timestamp() - 2)
        # 通常の json
        keep = self._write_at_mtime("keep.json", now.timestamp() - 1)

        deleted = prune_snapshots(target_dir=self.target, ttl_days=7, now=now)
        deleted_names = {p.name for p in deleted}
        # 古い tmp だけ消える
        self.assertEqual(deleted_names, {"snap.json.tmp.12345.999999"})
        self.assertFalse(old_tmp.exists())
        self.assertTrue(new_tmp.exists(), "fresh tmp must not be deleted")
        self.assertTrue(keep.exists())

    def test_missing_dir_returns_empty(self) -> None:
        nonexistent = self.target / "no_such_subdir"
        deleted = prune_snapshots(target_dir=nonexistent, ttl_days=7, now=FIXED_NOW)
        self.assertEqual(deleted, [])

    def test_does_not_recurse_into_subdirs(self) -> None:
        now = FIXED_NOW
        sub = self.target / "subdir"
        sub.mkdir()
        nested = sub / "old.json"
        nested.write_text("{}", encoding="utf-8")
        os.utime(nested, (now.timestamp() - 10 * 86400,) * 2)

        deleted = prune_snapshots(target_dir=self.target, ttl_days=7, now=now)
        self.assertEqual(deleted, [])
        self.assertTrue(nested.exists(), "prune must not recurse into subdirs")


class TestRoundTrip(unittest.TestCase):
    """書き込み → 読み戻しの一貫性。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_load_after_write_matches_payload(self) -> None:
        path = write_snapshot(target_dir=self.target, now=FIXED_NOW)
        loaded = load_snapshot(path)
        # スキーマ整合
        self.assertEqual(loaded["snapshot_id"], "20260524T120000Z-123456")
        self.assertEqual(loaded["generated_at"], "2026-05-24T12:00:00Z")
        self.assertIsInstance(loaded["minds"], list)
        # 各 Mind エントリのフィールド存在チェック（Mind が居ない時はスキップ可）
        for entry in loaded["minds"]:
            for key in (
                "mind_name",
                "kind",
                "persona",
                "spawned_at_epoch",
                "last_activity_epoch",
                "unread_inbox_count",
                "archive_count",
                "status",
                "category",
            ):
                self.assertIn(key, entry, f"missing key {key}")


if __name__ == "__main__":
    unittest.main()
