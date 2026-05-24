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
import os
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

    並行性 / 衝突耐性:
        - 同一プロセス内では microsecond 粒度の ID が単調増加するため衝突しない。
        - **異なるプロセスから同時刻に呼んだ場合** の衝突に対しては、tmp ファイルを
          PID + counter で区別したうえで `os.link` (hardlink) を使って最終ファイル名を
          atomic に予約する。`os.link` は既存ファイルがあると `FileExistsError` で
          失敗するため、衝突したら counter を増やしてリトライする。
        - 書き込みは tmp ファイルに完了してから link するので、途中で失敗しても
          壊れた JSON は最終位置に残らない（tmp 残骸は次回 prune が掃除する）。
    """
    if target_dir is None:
        target_dir = DEFAULT_SNAPSHOT_DIR
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    target_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_payload(now)
    sid = payload["snapshot_id"]
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)

    # tmp 名は PID と nanosecond で他プロセスと衝突しないようにする。
    # （同一プロセスで write_snapshot を高速連打しても被らないよう time_ns も加える）
    tmp_path = target_dir / f"{sid}.json.tmp.{os.getpid()}.{dt.datetime.now().strftime('%f')}"
    tmp_path.write_text(serialized, encoding="utf-8")

    try:
        # 最終ファイル名を atomic に予約する。`os.link` は既存ファイルがあると
        # FileExistsError で失敗する（POSIX 上 atomic）。Windows でも同一 device
        # 内ならハードリンクとして動作する。
        counter = 1
        chosen: Path | None = None
        while chosen is None:
            candidate = (
                target_dir / f"{sid}.json"
                if counter == 1
                else target_dir / f"{sid}-{counter}.json"
            )
            try:
                os.link(str(tmp_path), str(candidate))
                chosen = candidate
            except FileExistsError:
                counter += 1
                if counter > 1000:
                    # 防衛的: 1000 回連続で衝突する状況は実用上無い。安全のため abort。
                    raise RuntimeError(
                        f"could not allocate snapshot name after 1000 attempts at {target_dir}"
                    )
    finally:
        # tmp を掃除（hardlink 後は安全に消せる、本体は chosen に残る）。
        try:
            tmp_path.unlink()
        except OSError:
            pass

    return chosen


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
        - .json 以外のファイル / サブディレクトリは触らない（*.tmp* 残骸は別扱い）。
        - 削除中の OSError は無視（ファイル系の競合は無視して続行）。
        - 境界条件: mtime <= cutoff を「古い」と判定する（Codex P2 PR #62 指摘。
          旧 `<` だと粒度の荒い FS で `ttl_days=0` でも残ることがあった）。
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
        if not entry.is_file():
            continue
        # *.json 本体は TTL 判定。
        # *.json.tmp.* / *.tmp は write_snapshot の crash 残骸候補。
        # tmp は古さに関係なく削除対象（最新 write_snapshot が成功すれば即時 unlink される）。
        name = entry.name
        is_snapshot = entry.suffix == ".json"
        is_tmp_residue = ".tmp" in name
        if not (is_snapshot or is_tmp_residue):
            continue
        try:
            if is_tmp_residue:
                # tmp 残骸は 5 秒以上経過したもののみ削除（進行中の write を巻き込まない）。
                if entry.stat().st_mtime <= now.timestamp() - 5:
                    entry.unlink()
                    deleted.append(entry)
            elif entry.stat().st_mtime <= cutoff:
                # Codex P2 PR #62: `<` だと mtime == cutoff のファイルが残った。
                # `ttl_days=0` を「全削除」と扱う README/CLI 契約に合わせて `<=` に変更。
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
