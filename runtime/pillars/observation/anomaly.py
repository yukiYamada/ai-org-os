#!/usr/bin/env python3
"""
Anomaly Observer (Observation Pillar v0.3 / #67)。

Realm 内の異常候補シグナルを生成する。Warden は axiom に縛られない
(ADR-0010 §5) ので無制約に判定できるが、本モジュールは **意図的に**
Mindspace 不可侵 (ADR-0014) の精神を保つ:

- W2/W3 はファイル名と `.mind-meta.md` frontmatter のみ参照
- W1 は dispatch_flow (= frontmatter のみ) と Mindspace mtime のみ
- I1 は v0.1 snapshot JSON のみ
- I2 は inbox の **件数** (内容は読まない)

シグナル一覧 (issue #67 §「スコープ」):
  W1 (info, 降格): Mindspace mtime 更新があるが Conduit に対応 dispatch 無し
  W2 (warning):    Mindspace 配下に他 Mind 名のディレクトリ片
  W3 (warning):    .mind-meta.md の kind が registered kinds に存在しない (孤児)
  I1 (info):       直前 snapshot と比較した stale 遷移の新規発生分
  I2 (info):       inbox に unread が一定閾値を超えて蓄積

「Mind には公開しない」(#67 §5) — 本モジュールの出力先は Warden 内部 /
人間運用者のみ。Mind 通知は Judgment Pillar (#38) が個別判断で行う想定。

依存: 標準ライブラリのみ (ADR-0005 / ADR-0009)。dispatch_flow / observe
モジュールは同 dir なので sys.path 経由で import。
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# 同一ディレクトリ内 module を import (パッケージ化していないため)
sys.path.insert(0, str(Path(__file__).parent))

import dispatch_flow as _df  # noqa: E402
import observe as _obs  # noqa: E402

# Mind 名検証 (storage._VALID_NAME_RE と同じ文字集合)
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# I2 のデフォルト閾値 (issue 文面に「一定閾値超」と書かれているので
# 設定可能にしておく。最初は 10 件超を info で出す)
DEFAULT_INBOX_BUILDUP_THRESHOLD = 10

# W1 のデフォルト「直近 N 秒」ウィンドウ。Mind が静かにしていれば 0、
# 最近 Mindspace に file 変更があれば該当 Mind として候補に上げる。
# v0.1 では 1 時間に設定 (issue の判断ポイント: 誤検知が多いので info)。
DEFAULT_W1_WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class AnomalySignal:
    """1 件の異常候補。

    `code` は "W1" / "W2" / "W3" / "I1" / "I2" のいずれか。
    `level` は "warning" or "info"。
    `mind` は対象 Mind 名 (集計対象が無いシグナルなら空文字)。
    `message` は人間可読な短い説明 (運用者がログで読む)。
    """

    code: str
    level: str
    mind: str
    message: str


# ---- W2: Mindspace 配下に他 Mind 名のディレクトリ片 -----------------------

def detect_w2_foreign_mind_dir(
    home_dir: Path | None = None,
) -> list[AnomalySignal]:
    """各 Mindspace を走査し、他 Mind 名と一致する dir / file 名を探す。

    例: Mind 'alice' の Mindspace に `bob/` という dir があれば、それは
    Mindspace 不可侵 (ADR-0014) 違反の物理痕跡。**Mindspace の中身は
    読まない**、entry 名だけ比較する。

    走査の対象は **直下 entry のみ** (再帰しない)。Mindspace 配下深くに
    紛れた偶然一致 (例: `.cache/bob/` 等) は誤検知になりやすいので除外。
    将来 (v1.0) で深さを設定可能にする。
    """
    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    minds_root = home / "minds"
    if not minds_root.is_dir():
        return []
    # spawned mind set (.mind-meta.md 持ち)
    spawned: set[str] = set()
    for entry in minds_root.iterdir():
        if not entry.is_dir():
            continue
        if not _VALID_NAME_RE.match(entry.name):
            continue
        if (entry / ".mind-meta.md").is_file():
            spawned.add(entry.name)
    signals: list[AnomalySignal] = []
    for mind_name in sorted(spawned):
        mind_dir = minds_root / mind_name
        try:
            entries = list(os.scandir(mind_dir))
        except OSError:
            continue
        for sub in entries:
            if sub.name == mind_name:
                continue  # 自分自身の名前と一致する dir 名は禁止しない
            if sub.name in spawned:
                kind = "dir" if sub.is_dir() else "file"
                signals.append(
                    AnomalySignal(
                        code="W2",
                        level="warning",
                        mind=mind_name,
                        message=(
                            f"foreign mind name '{sub.name}' as {kind} inside "
                            f"mindspace of '{mind_name}' (axiom: mindspace "
                            f"inviolability)"
                        ),
                    )
                )
    return signals


# ---- W3: .mind-meta.md の kind が registered kinds に存在しない ------------

def detect_w3_orphan_kind(
    home_dir: Path | None = None,
) -> list[AnomalySignal]:
    """各 Mind の `.mind-meta.md` から kind を読み、registered でなければ報告。

    registered の判定は Registry Pillar の `list_kinds()` を使う。
    overlay (`$AI_ORG_OS_HOME/kinds/`) + templates の両方を見るので、利用者が
    定義した kind は登録扱いになる。

    Mindspace 不可侵: `.mind-meta.md` の frontmatter から `kind:` フィールド
    のみ読む。本文 / 他フィールドは触らない。
    """
    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    minds_root = home / "minds"
    if not minds_root.is_dir():
        return []
    # Registry Pillar の list_kinds を import (cross-pillar dependency)。
    # observe.py / spawn-mind.sh と同じ流儀。
    runtime_dir = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(runtime_dir / "pillars" / "registry"))
    try:
        from registry import list_kinds  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        # registry.py が無い環境 (= 異常) → 検知をスキップ
        return []
    # Codex P2 (#94): list_kinds の overlay 解決は $AI_ORG_OS_HOME を見るので、
    # caller が home_dir を渡して別 Realm を観察する場合、その home の
    # `kinds/` overlay を含めるために環境変数を一時的に向ける。同じ流儀で
    # detect_i2_inbox_buildup でも gather_observations を呼ぶ前に env を
    # 設定している。これにより `home_dir/kinds/<x>.md` に置いた kind が
    # 「未登録」扱いされる false-positive W3 を防ぐ。
    old_home = os.environ.get("AI_ORG_OS_HOME")
    os.environ["AI_ORG_OS_HOME"] = str(home)
    try:
        registered = {ki.name for ki in list_kinds()}
    except Exception:  # noqa: BLE001
        return []
    finally:
        if old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = old_home
    signals: list[AnomalySignal] = []
    for entry in sorted(minds_root.iterdir()):
        if not entry.is_dir():
            continue
        meta = entry / ".mind-meta.md"
        if not meta.is_file():
            continue
        kind = _obs._read_meta(meta, "kind", default="")
        if not kind:
            continue
        if kind not in registered:
            signals.append(
                AnomalySignal(
                    code="W3",
                    level="warning",
                    mind=entry.name,
                    message=(
                        f"mind '{entry.name}' declares kind='{kind}' which is "
                        f"not in registered kinds {sorted(registered)} (orphan)"
                    ),
                )
            )
    return signals


# ---- W1: Mindspace mtime と Conduit dispatch 履歴の不整合 ------------------

def detect_w1_mtime_without_dispatch(
    home_dir: Path | None = None,
    *,
    window_seconds: int = DEFAULT_W1_WINDOW_SECONDS,
    now_epoch: float | None = None,
) -> list[AnomalySignal]:
    """直近 `window_seconds` 内に Mindspace mtime 更新があるのに、対応する
    dispatch (送受信ともに) が conduit-storage に見当たらない Mind を info で
    報告する。

    Issue #67 の判断ポイント: 誤検知が出やすい (Mind 自身が CLAUDE.md や
    note を書くだけでも mtime を更新する) → **info に降格**。運用ログを
    蓄積してから warning へ昇格を検討する。

    Mindspace 不可侵: stat() のみ (内容は読まない)。dispatch_flow も
    frontmatter のみ。
    """
    import time as _time  # noqa: PLC0415

    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    minds_root = home / "minds"
    if not minds_root.is_dir():
        return []
    now = now_epoch if now_epoch is not None else _time.time()
    window_start = now - window_seconds

    # 各 Mind の mtime
    recent_minds: dict[str, float] = {}
    for entry in sorted(minds_root.iterdir()):
        if not entry.is_dir() or not (entry / ".mind-meta.md").is_file():
            continue
        latest = _obs._latest_mtime(entry)
        if latest >= window_start:
            recent_minds[entry.name] = latest

    if not recent_minds:
        return []

    # window 内に from/to に登場する Mind の set を作る
    storage_dir = home / "conduit-storage"
    seen_in_dispatch: set[str] = set()
    for meta in _df.iter_dispatches(storage_dir):
        ts = meta.get("dispatched_at", "")
        epoch = _obs._epoch_from_iso(ts)
        if epoch < window_start:
            continue
        seen_in_dispatch.add(meta["from"])
        seen_in_dispatch.add(meta["to"])

    signals: list[AnomalySignal] = []
    for mind_name in sorted(recent_minds):
        if mind_name in seen_in_dispatch:
            continue
        signals.append(
            AnomalySignal(
                code="W1",
                level="info",
                mind=mind_name,
                message=(
                    f"mindspace of '{mind_name}' was touched within last "
                    f"{window_seconds}s but no inbound/outbound dispatch was "
                    f"seen — possible non-Nexus write (or quiet self-update)"
                ),
            )
        )
    return signals


# ---- I2: inbox に unread が一定閾値を超えて蓄積 -----------------------------

def detect_i2_inbox_buildup(
    home_dir: Path | None = None,
    *,
    threshold: int = DEFAULT_INBOX_BUILDUP_THRESHOLD,
    now_epoch: float | None = None,
) -> list[AnomalySignal]:
    """各 Mind の unread inbox 件数が `threshold` を超えていれば info を出す。

    inbox **件数** だけ見る (内容は読まない)。
    `gather_observations()` の `unread_inbox_count` を流用。
    """
    import time as _time  # noqa: PLC0415

    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    old_home = os.environ.get("AI_ORG_OS_HOME")
    os.environ["AI_ORG_OS_HOME"] = str(home)
    try:
        observations = _obs.gather_observations(
            now_epoch if now_epoch is not None else _time.time()
        )
    finally:
        if old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = old_home
    signals: list[AnomalySignal] = []
    for obs, _status, _category in observations:
        if obs.unread_inbox_count > threshold:
            signals.append(
                AnomalySignal(
                    code="I2",
                    level="info",
                    mind=obs.mind_name,
                    message=(
                        f"mind '{obs.mind_name}' has {obs.unread_inbox_count} "
                        f"unread messages (threshold={threshold})"
                    ),
                )
            )
    return signals


# ---- I1: 直前 snapshot と比較した stale 遷移の新規発生 -----------------------

def detect_i1_new_stale(
    prev_snapshot: dict,
    curr_snapshot: dict,
) -> list[AnomalySignal]:
    """v0.1 snapshot 形式の 2 つを比較し、category が「`stale` でない」→
    「`stale` である」に遷移した Mind を info で報告する。

    snapshot は `snapshot.load_snapshot` で読んだ dict (= `_build_payload`
    形式)。各 Mind は `mind_name` / `category` を持つ。

    両 snapshot に居ない Mind / 片方にしか居ない Mind は無視 (新規 spawn /
    kill は anomaly ではない)。
    """
    prev_cat = {m["mind_name"]: m.get("category", "") for m in prev_snapshot.get("minds", [])}
    curr_cat = {m["mind_name"]: m.get("category", "") for m in curr_snapshot.get("minds", [])}
    signals: list[AnomalySignal] = []
    for mind, cur_c in sorted(curr_cat.items()):
        prev_c = prev_cat.get(mind)
        if prev_c is None:
            continue  # new mind
        if cur_c == "stale" and prev_c != "stale":
            signals.append(
                AnomalySignal(
                    code="I1",
                    level="info",
                    mind=mind,
                    message=(
                        f"mind '{mind}' transitioned to stale "
                        f"(was '{prev_c}')"
                    ),
                )
            )
    return signals


# ---- snapshot diff (--diff <a> <b> の汎用版) -------------------------------


def diff_snapshots(
    prev_snapshot: dict,
    curr_snapshot: dict,
) -> dict[str, list[dict]]:
    """2 snapshot の Mind 単位差分。category / status / unread_inbox_count の
    変化と、prev のみ / curr のみに居る Mind を返す。

    観察用 (--diff フラグから呼ばれる)。anomaly に紐づかない一般的な差分。

    戻り値:
        {
          "added":   [{mind_name, category, status, unread_inbox_count}, ...],
          "removed": [...],
          "changed": [{mind_name, fields: {key: [before, after]}}, ...],
        }
    """
    def _by_name(payload: dict) -> dict[str, dict]:
        return {m["mind_name"]: m for m in payload.get("minds", [])}

    prev = _by_name(prev_snapshot)
    curr = _by_name(curr_snapshot)
    added: list[dict] = []
    removed: list[dict] = []
    changed: list[dict] = []
    for mind, c in sorted(curr.items()):
        if mind not in prev:
            added.append({
                "mind_name": mind,
                "category": c.get("category"),
                "status": c.get("status"),
                "unread_inbox_count": c.get("unread_inbox_count"),
            })
            continue
        p = prev[mind]
        fields: dict[str, list] = {}
        for key in ("category", "status", "unread_inbox_count", "archive_count"):
            if p.get(key) != c.get(key):
                fields[key] = [p.get(key), c.get(key)]
        if fields:
            changed.append({"mind_name": mind, "fields": fields})
    for mind, p in sorted(prev.items()):
        if mind not in curr:
            removed.append({
                "mind_name": mind,
                "category": p.get("category"),
                "status": p.get("status"),
                "unread_inbox_count": p.get("unread_inbox_count"),
            })
    return {"added": added, "removed": removed, "changed": changed}


# ---- detect_all (orchestrator) -------------------------------------------


def detect_all(
    home_dir: Path | None = None,
    *,
    prev_snapshot: dict | None = None,
    curr_snapshot: dict | None = None,
    inbox_threshold: int = DEFAULT_INBOX_BUILDUP_THRESHOLD,
    w1_window_seconds: int = DEFAULT_W1_WINDOW_SECONDS,
    now_epoch: float | None = None,
) -> list[AnomalySignal]:
    """全シグナル (W1/W2/W3/I1/I2) を一括検知して返す。

    snapshot 比較 (I1) は prev/curr の両方が与えられたときのみ実行する。
    片方が None なら I1 は skip (空 list 同等)。

    結果は `(level desc, code asc, mind asc)` でソート: warning が先、
    同 level 内は code → mind 名のアルファベット順。
    """
    signals: list[AnomalySignal] = []
    signals.extend(detect_w2_foreign_mind_dir(home_dir))
    signals.extend(detect_w3_orphan_kind(home_dir))
    signals.extend(
        detect_w1_mtime_without_dispatch(
            home_dir,
            window_seconds=w1_window_seconds,
            now_epoch=now_epoch,
        )
    )
    signals.extend(
        detect_i2_inbox_buildup(
            home_dir, threshold=inbox_threshold, now_epoch=now_epoch
        )
    )
    if prev_snapshot is not None and curr_snapshot is not None:
        signals.extend(detect_i1_new_stale(prev_snapshot, curr_snapshot))

    # warning → info の順、同一 level 内は code → mind
    level_order = {"warning": 0, "info": 1}
    signals.sort(
        key=lambda s: (level_order.get(s.level, 99), s.code, s.mind)
    )
    return signals


# ---- 表示 ----


def format_signals_table(signals: list[AnomalySignal]) -> str:
    """human-readable な ASCII 表示。warning と info を別セクションに分ける。"""
    if not signals:
        return "(no anomalies)"
    warnings = [s for s in signals if s.level == "warning"]
    infos = [s for s in signals if s.level == "info"]
    lines: list[str] = []
    if warnings:
        lines.append(f"=== Anomalies / warnings ({len(warnings)}) ===")
        for s in warnings:
            lines.append(f"  [{s.code}] {s.mind}: {s.message}")
    if infos:
        if lines:
            lines.append("")
        lines.append(f"=== Anomalies / info ({len(infos)}) ===")
        for s in infos:
            lines.append(f"  [{s.code}] {s.mind}: {s.message}")
    return "\n".join(lines)


def signals_to_json(signals: list[AnomalySignal]) -> list[dict]:
    return [asdict(s) for s in signals]


# ---- CLI ----


def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="anomaly.py",
        description="Anomaly observer (Observation v0.3 / #67)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit JSON instead of an ASCII table",
    )
    parser.add_argument(
        "--inbox-threshold", type=int,
        default=DEFAULT_INBOX_BUILDUP_THRESHOLD,
        help=f"I2 threshold for unread inbox buildup (default: {DEFAULT_INBOX_BUILDUP_THRESHOLD})",
    )
    parser.add_argument(
        "--w1-window", type=int, default=DEFAULT_W1_WINDOW_SECONDS,
        help=f"W1 window in seconds (default: {DEFAULT_W1_WINDOW_SECONDS})",
    )
    parser.add_argument(
        "--prev-snapshot", type=Path, default=None,
        help="path to previous snapshot JSON for I1 detection",
    )
    parser.add_argument(
        "--curr-snapshot", type=Path, default=None,
        help="path to current snapshot JSON for I1 detection",
    )
    ns = parser.parse_args(argv)

    prev = None
    curr = None
    if ns.prev_snapshot and ns.curr_snapshot:
        from snapshot import load_snapshot  # noqa: PLC0415

        prev = load_snapshot(ns.prev_snapshot)
        curr = load_snapshot(ns.curr_snapshot)

    signals = detect_all(
        prev_snapshot=prev,
        curr_snapshot=curr,
        inbox_threshold=ns.inbox_threshold,
        w1_window_seconds=ns.w1_window,
    )
    if ns.json:
        print(json.dumps(signals_to_json(signals), ensure_ascii=False, indent=2))
    else:
        print(format_signals_table(signals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
