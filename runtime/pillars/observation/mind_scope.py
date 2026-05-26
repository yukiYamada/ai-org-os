#!/usr/bin/env python3
"""
Mind-scope Observation API (Observation Pillar v1.0 / #68)。

Conduit Pillar の MCP tool 経由で Mind が **自分自身の範囲だけ** を観察する
ための純粋関数群。Mind 向けの開放窓口だが、観察できるのは:

- `observe_self`: 呼び出し元 Mind 自身 (mind_name で指定された 1 件)
- `observe_dispatches_for`: 自分が from / to のいずれかに登場する dispatch
- `observe_guild_for`: 自分が所属する Guild のロールアップ

ADR-0017 (Warden vs Mind 監視) 層分離の系として、Warden 内部観測
(observe.py / anomaly.py / dispatch_flow.py / resource_usage.py) と
**同じデータ源** を Mind が安全な切り口で読めるようにする。観察結果に
他 Mind / 他 Guild の情報は含めない (= identity binding と claim-only-own-guild
の思想を Observation 側にも拡張)。

設計の境界:
- 入力 mind_name は呼び出し元 (= Conduit Pillar 側で identity binding 済) を
  そのまま受け取る前提
- 他 Mind / 他 Guild の情報を返さないことは、本モジュールの関数の **戻り値**
  で物理的に保証する (call site で axiom チェックを忘れても情報漏れしない)
- Mindspace 不可侵 (ADR-0014) は ここでも維持: stat / frontmatter / 件数のみ
  参照、本文は読まない

依存: 標準ライブラリのみ + 既存の同 Pillar / 隣接 Pillar (registry / inbox)。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 同 dir の module を import
sys.path.insert(0, str(Path(__file__).parent))

import dispatch_flow as _df  # noqa: E402
import observe as _obs  # noqa: E402
import resource_usage as _ru  # noqa: E402


# ---- observe_self ---------------------------------------------------------


def observe_self(
    mind_name: str,
    *,
    home_dir: Path | None = None,
    now_epoch: float | None = None,
) -> dict:
    """`mind_name` 自身の観察結果のみ返す。

    返り値: ok=True なら以下の dict、見つからなければ ok=False, code=not_found。
    ```
    {
      "ok": True,
      "mind_name": "alice",
      "kind": "generic",
      "persona": "designer",
      "guild": "default",
      "spawned_at_epoch": ...,
      "last_activity_epoch": ...,
      "unread_inbox_count": 3,
      "archive_count": 12,
      "status": "active",
      "category": "running",
      "mindspace_files": 7,
      "mindspace_bytes": 5432,
    }
    ```

    他 Mind の情報は **含まない** (1 件のみ返す)。本文は読まない (stat と
    frontmatter のみ)。
    """
    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    # gather_observations は env を見るので一時的に向ける (anomaly.py と同じ流儀)
    old_home = os.environ.get("AI_ORG_OS_HOME")
    os.environ["AI_ORG_OS_HOME"] = str(home)
    try:
        observations = _obs.gather_observations(
            now_epoch if now_epoch is not None else time.time()
        )
    finally:
        if old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = old_home

    for obs, status, category in observations:
        if obs.mind_name != mind_name:
            continue
        mind_dir = home / "minds" / mind_name
        files, byte_count = _ru._scan_dir_size(mind_dir)
        # Mind の所属 Guild も含めて返す (Persona 側で参考にできるよう)
        sys.path.insert(
            0,
            str(Path(__file__).resolve().parent.parent / "registry"),
        )
        try:
            from guild import get_mind_guild  # noqa: PLC0415

            guild = get_mind_guild(mind_name) or ""
        except Exception:  # noqa: BLE001
            guild = ""
        return {
            "ok": True,
            "mind_name": obs.mind_name,
            "kind": obs.kind,
            "persona": obs.persona,
            "guild": guild,
            "spawned_at_epoch": obs.spawned_at_epoch,
            "last_activity_epoch": obs.last_activity_epoch,
            "unread_inbox_count": obs.unread_inbox_count,
            "archive_count": obs.archive_count,
            "status": status,
            "category": category,
            "mindspace_files": files,
            "mindspace_bytes": byte_count,
        }
    return {
        "ok": False,
        "code": "not_found",
        "error": f"mind '{mind_name}' not found (no .mind-meta.md)",
    }


# ---- observe_dispatches_for ----------------------------------------------


def observe_dispatches_for(
    mind_name: str,
    *,
    home_dir: Path | None = None,
    window_seconds: int | None = None,
    now_epoch: float | None = None,
) -> dict:
    """`mind_name` が **from または to** に登場する dispatch のみ返す。

    返り値:
    ```
    {
      "ok": True,
      "mind_name": "alice",
      "window_seconds": 3600,
      "outbound": [{to, count, first_at, last_at}, ...],   # alice -> *
      "inbound":  [{from, count, first_at, last_at}, ...], # * -> alice
    }
    ```

    `window_seconds` を渡すと現在時刻からその秒数以内に絞る。None なら全件。
    他 Mind 同士の dispatch (例: bob -> carol) は **含まない** (caller が
    forget しても情報が漏れない物理保証)。本文は読まない (frontmatter のみ)。
    """
    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    storage_dir = home / "conduit-storage"
    cutoff: float | None = None
    if window_seconds is not None:
        now = now_epoch if now_epoch is not None else time.time()
        cutoff = now - window_seconds

    # from/to per direction の集計用バケット
    outbound: dict[str, dict[str, str | int]] = {}  # to -> bucket
    inbound: dict[str, dict[str, str | int]] = {}   # from -> bucket
    for meta in _df.iter_dispatches(storage_dir):
        if cutoff is not None:
            epoch = _obs._epoch_from_iso(meta.get("dispatched_at", ""))
            if epoch < cutoff:
                continue
        sender = meta.get("from", "")
        recipient = meta.get("to", "")
        if sender == mind_name and recipient != mind_name:
            _accumulate(outbound, recipient, meta["dispatched_at"])
        elif recipient == mind_name and sender != mind_name:
            _accumulate(inbound, sender, meta["dispatched_at"])
        elif sender == mind_name and recipient == mind_name:
            # 自己宛 dispatch は outbound にも inbound にも入れる
            # (運用上ありえる: メモ的な自分宛 Dispatch)
            _accumulate(outbound, recipient, meta["dispatched_at"])
            _accumulate(inbound, sender, meta["dispatched_at"])
        # それ以外 (= 他 Mind 同士) は無視
    return {
        "ok": True,
        "mind_name": mind_name,
        "window_seconds": window_seconds,
        "outbound": _bucket_to_list(outbound, key="to"),
        "inbound": _bucket_to_list(inbound, key="from"),
    }


def _accumulate(
    buckets: dict[str, dict[str, str | int]],
    counterpart: str,
    dispatched_at: str,
) -> None:
    """from→to の片側集計用 helper。aggregate_flow と同じロジック。"""
    cur = buckets.get(counterpart)
    if cur is None:
        buckets[counterpart] = {
            "count": 1,
            "first_at": dispatched_at,
            "last_at": dispatched_at,
        }
        return
    cur["count"] = int(cur["count"]) + 1
    if dispatched_at < str(cur["first_at"]):
        cur["first_at"] = dispatched_at
    if dispatched_at > str(cur["last_at"]):
        cur["last_at"] = dispatched_at


def _bucket_to_list(
    buckets: dict[str, dict[str, str | int]],
    *,
    key: str,
) -> list[dict]:
    """`key` は "from" / "to" のラベル。辞書順で安定 sort。"""
    out: list[dict] = []
    for name, b in sorted(buckets.items()):
        out.append({
            key: name,
            "count": int(b["count"]),
            "first_at": str(b["first_at"]),
            "last_at": str(b["last_at"]),
        })
    return out


# ---- observe_guild_for ----------------------------------------------------


def observe_guild_for(
    mind_name: str,
    *,
    home_dir: Path | None = None,
) -> dict:
    """`mind_name` が所属する Guild のロールアップを返す。

    返り値:
    ```
    {
      "ok": True,
      "mind_name": "alice",
      "guild": "default",
      "members": ["alice", "bob"],
      "guildmasters": ["gm-default"],
      "pending_issues": 3,
    }
    ```

    他 Guild の情報は含めない。registry エントリ無で guild 不明なら
    ok=False, code=forbidden。
    """
    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    # registry / inbox を home に向けるため env を一時的に向ける
    old_home = os.environ.get("AI_ORG_OS_HOME")
    os.environ["AI_ORG_OS_HOME"] = str(home)
    try:
        sys.path.insert(
            0,
            str(Path(__file__).resolve().parent.parent / "registry"),
        )
        sys.path.insert(
            0,
            str(Path(__file__).resolve().parent.parent / "inbox"),
        )
        try:
            from guild import (  # noqa: PLC0415
                get_mind_guild,
                enumerate_members,
                enumerate_guildmasters,
            )
            from inbox import list_pending_issues  # noqa: PLC0415
        except ImportError as exc:  # 異常環境
            return {
                "ok": False,
                "code": "internal_error",
                "error": f"observation Pillar dependency missing: {exc}",
            }
        guild = get_mind_guild(mind_name)
        if not guild:
            return {
                "ok": False,
                "code": "forbidden",
                "error": (
                    f"mind '{mind_name}' has no registry entry, "
                    f"observe_my_guild requires a registered mind"
                ),
            }
        members = enumerate_members(guild)
        guildmasters = enumerate_guildmasters(guild)
        try:
            pending = list_pending_issues()
        except Exception:  # noqa: BLE001
            pending = []
        # Phase 5c-1 / ADR-0019: issue の guild フィールドで filter
        pending_count = sum(1 for r in pending if (r.guild or "default") == guild)
        return {
            "ok": True,
            "mind_name": mind_name,
            "guild": guild,
            "members": members,
            "guildmasters": guildmasters,
            "pending_issues": pending_count,
        }
    finally:
        if old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = old_home


# ---- --for-warden 用統合 payload (observe.py から呼ばれる) -----------------


REPORT_SCHEMA_VERSION = "1.0"


def build_realm_report(
    *,
    home_dir: Path | None = None,
    inbox_threshold: int | None = None,
    w1_window_seconds: int | None = None,
    now_epoch: float | None = None,
) -> dict:
    """Realm 全体の統合観察 payload (observe.py --for-warden 用)。

    Mind 向け API ではない (Warden / 人間運用者向けの **無制約観察**)。
    schema_version 付き JSON で、外部運用ツールから安定して読めるようにする。
    """
    import anomaly as _an  # noqa: PLC0415

    home = Path(home_dir) if home_dir is not None else _obs._runtime_home()
    now = now_epoch if now_epoch is not None else time.time()
    # observations
    old_home = os.environ.get("AI_ORG_OS_HOME")
    os.environ["AI_ORG_OS_HOME"] = str(home)
    try:
        observations = _obs.gather_observations(now)
    finally:
        if old_home is None:
            os.environ.pop("AI_ORG_OS_HOME", None)
        else:
            os.environ["AI_ORG_OS_HOME"] = old_home
    minds_payload = [
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
    ]
    # flow
    edges = _df.aggregate_flow(home / "conduit-storage")
    # resource (gather_observations と同じ Mind 集合)
    buckets: list[_ru.UsageBucket] = []
    for o, _, _ in observations:
        mind_dir = home / "minds" / o.mind_name
        files, byte_count = _ru._scan_dir_size(mind_dir)
        buckets.append(
            _ru.UsageBucket(
                name=o.mind_name,
                category="mindspace",
                file_count=files,
                byte_count=byte_count,
            )
        )
    buckets.append(_ru.conduit_storage_usage(home))
    # anomaly
    detect_kwargs: dict = {"home_dir": home, "now_epoch": now}
    if inbox_threshold is not None:
        detect_kwargs["inbox_threshold"] = inbox_threshold
    if w1_window_seconds is not None:
        detect_kwargs["w1_window_seconds"] = w1_window_seconds
    signals = _an.detect_all(**detect_kwargs)
    import datetime as _dt  # noqa: PLC0415

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "minds": minds_payload,
        "flow": _df.flow_to_json(edges),
        "resource": _ru.usage_to_json(buckets),
        "anomaly": _an.signals_to_json(signals),
    }
