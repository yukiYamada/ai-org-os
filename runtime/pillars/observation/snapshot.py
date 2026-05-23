#!/usr/bin/env python3
"""
Observation Pillar v0.1: スナップショット履歴記録。

`observe.gather_observations()` の結果を JSON ファイルとして
`runtime/pillars/observation/snapshots/` に保存する。観測の時系列を
ホストローカルで蓄積し、後で diff / 異常検知の入力にする
（ROADMAP.md v0.1 → v0.3 の系譜）。

責務:
- write_snapshot(target_dir, now=None) -> Path: 1 件保存
- prune_snapshots(target_dir, ttl_days, now=None) -> list[Path]: TTL 経過分を削除
- load_snapshot(path) -> dict: 保存済み JSON を読み戻す（diff / test 用）

依存:
- 標準ライブラリのみ（ADR-0005 / ADR-0009 の依存ゼロ方針）
- observe.gather_observations を import で再利用

Axiom 整合（ROADMAP v0.1 §「Axiom 整合チェック」）:
- Mindspace 中身に触れない（gather_observations の制約をそのまま継承）
- 観測痕跡は Pillar 領域に書く（snapshots/ は Pillar の所有物）
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

# Make `import observe` work without a package setup. observe.py が居る
# ディレクトリは本ファイルと同じ。
sys.path.insert(0, str(Path(__file__).parent))

from observe import gather_observations  # noqa: E402

DEFAULT_TTL_DAYS = 7
# snapshots ディレクトリのデフォルト。テストでは tmp に差し替えて使う。
DEFAULT_SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def _snapshot_id(now: dt.datetime) -> str:
    """Snapshot ファイル名用のソート可能な文字列を返す。

    フォーマット: YYYYMMDDTHHMMSSZ-NNNNNN (microsecond suffix で同秒衝突を回避)。
    """
    return now.strftime("%Y%m%dT%H%M%SZ") + f"-{now.microsecond:06d}"


def _build_payload(now: dt.datetime) -> dict:
    """gather_observations の結果を JSON 化用 dict に組み立てる。

    フォーマットは observe.py の --json と互換。snapshot_id を追加する。
    """
    observations = gather_observations(now.timestamp())
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_id": _snapshot_id(now),
        "minds": [
            {
                "mind_name": o.mind_name,
                "kind": o.kind,
                "persona": o.persona,
                "spawned_at_epoch": o.spawned_at_epoch,
                "last_activity_epoch": o.last_activity_epoch,
                "unread_inbox_count": o.unread_inbox_count,
                "archive_count": o.archive_count,
                "status": s,
                "category": c,
            }
            for o, s, c in observations
        ],
    }


def write_snapshot(
    target_dir: Path | None = None,
    now: dt.datetime | None = None,
) -> Path:
    """現在の観測スナップショットを JSON ファイルとして保存する。

    引数:
        target_dir: 保存先ディレクトリ。None なら DEFAULT_SNAPSHOT_DIR を使う。
                    存在しなければ親ごと作る。
        now: 現在時刻 (UTC, aware)。None なら datetime.now(UTC) を使う。
             テスト時に固定するために引数化。

    戻り値:
        書き込んだファイルの絶対パス。

    重複防止:
        microsecond 粒度の ID で衝突はほぼ起きないが、起きた場合は
        -2, -3, ... の suffix を付けて衝突回避する。
    """
    if target_dir is None:
        target_dir = DEFAULT_SNAPSHOT_DIR
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    target_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_payload(now)
    sid = payload["snapshot_id"]

    path = target_dir / f"{sid}.json"
    counter = 1
    while path.exists():
        counter += 1
        path = target_dir / f"{sid}-{counter}.json"

    # 原子性のため、tmp に書いて rename する（壊れた JSON を残さない）。
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
    return path


def prune_snapshots(
    target_dir: Path | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    now: dt.datetime | None = None,
) -> list[Path]:
    """target_dir 内で ttl_days より古い *.json を削除する。

    引数:
        target_dir: 対象ディレクトリ。None なら DEFAULT_SNAPSHOT_DIR。
        ttl_days: 保持日数。0 なら全削除、負数は ValueError。
        now: 比較基準時刻。None なら datetime.now(UTC)。

    戻り値:
        削除したパスの list（テスト / 監査用）。

    注意:
        - mtime 基準で判定する。手動コピー等で mtime が新しくなっている
          ファイルは保持される（意図された挙動）。
        - .json 以外のファイル / サブディレクトリは触らない。
        - 削除中の OSError は無視（ファイル系の競合は無視して続行）。
    """
    if target_dir is None:
        target_dir = DEFAULT_SNAPSHOT_DIR
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    if ttl_days < 0:
        raise ValueError(f"ttl_days must be non-negative (got {ttl_days})")
    if not target_dir.is_dir():
        return []

    cutoff = now.timestamp() - (ttl_days * 86400)
    deleted: list[Path] = []
    for entry in target_dir.iterdir():
        if not entry.is_file() or entry.suffix != ".json":
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                deleted.append(entry)
        except OSError:
            # ファイルが消えた / アクセス拒否 etc。先勝ち / 競合は無視。
            continue
    return deleted


def load_snapshot(path: Path) -> dict:
    """保存済みスナップショット JSON を dict として読み戻す。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    # 単体実行: snapshot を 1 件取って path を stdout に出すだけ。
    # 通常は observe.py --snapshot 経由で呼ぶ。
    p = write_snapshot()
    print(p)
