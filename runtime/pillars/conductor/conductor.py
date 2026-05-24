#!/usr/bin/env python3
"""
Conductor Pillar: Warden の心拍 (Phase 5b-1, Issue #71)。

各 Pillar (Observation / Inbox / Judgment / Lifecycle / Conduit / Registry) は
「呼ばれれば動く関数」として揃っているが、それを呼ぶ常駐エンジンが居なかった。
Conductor が **1 cycle = 観測 + 判断 + 行動** を周期的に回す。

ADR 整合:
- ADR-0010 §5: Warden は機能の集合体。Judgment はループなし呼び出し駆動 → これを
  「呼ぶ側」が Conductor。
- ADR-0011: Pillar として `runtime/pillars/conductor/` 配下に配置、編集不可。
- ADR-0013 §1 F3: Pillar 異常 (例: Judgment が API 不在で失敗) は Realm 停止を
  意味しない → Conductor は各 step を try/except で囲み、fallback で続行。

1 cycle の流れ:
  1. Inbox を poll → 未処理 Issue を list_pending_issues で取得
  2. (Phase 5b-1 ではここで一旦記録のみ、claim/spawn は次フェーズ)
  3. Observation snapshot 取得 (`write_snapshot`)
  4. Judgment Claude 呼び出し (snapshot → MindJudgment list)
     - API key 不在 / API 失敗 → rule-based fallback (全 Mind を "monitor")
  5. cycle status を `runtime/realm/conductor-status.json` に書き出す
  6. sleep して次 cycle へ

呼び出し駆動 / 常駐の境界:
- Conductor は **唯一の常駐プロセス** (Warden 本体の身体)
- 他 Pillar (Judgment / Observation / Inbox / etc) はすべて関数呼び出し
- Mind は Mind 側ループ (mind-loop.sh) で独立に動く

停止:
- SIGTERM / SIGINT で進行中 cycle を完走してから抜ける (mind-loop.sh と同じ)
- docker compose down で Realm 全体停止 = Conductor も止まる
"""

from __future__ import annotations

import datetime as dt
import json
import os
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Pillar 群への import パス整備。同プロセス内 import (ADR-0010 §6) を許可。
RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RUNTIME_DIR / "pillars" / "observation"))
sys.path.insert(0, str(RUNTIME_DIR / "pillars" / "inbox"))
sys.path.insert(0, str(RUNTIME_DIR / "pillars" / "judgment"))

# 他 Pillar の API を import。失敗したら起動できないのでこれは fatal。
from snapshot import load_snapshot, write_snapshot  # noqa: E402
from inbox import list_pending_issues  # noqa: E402
from judgment import (  # noqa: E402
    AnthropicNotConfigured,
    JudgmentParseError,
    MindJudgment,
    judge_snapshot,
    make_client,
)

DEFAULT_PERIOD_S = 30


def _runtime_home() -> Path:
    """$AI_ORG_OS_HOME or ~/.ai-org-os/ (Phase 5b-4 / ADR-0018)。"""
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os"


def _default_status_file() -> Path:
    return _runtime_home() / "conductor-status.json"


# 関数で解決するが、互換のため module-level エイリアスは残す。
DEFAULT_STATUS_FILE = _default_status_file()


@dataclass(frozen=True)
class CycleResult:
    """1 cycle の結果サマリ。status JSON に書く / log に出すための情報源。"""

    cycle: int
    started_at: str
    ended_at: str
    pending_issues: int
    snapshot_path: str | None
    judgments_count: int
    judgments_action_breakdown: dict[str, int]
    judgment_status: str  # "ok" / "fallback-no-key" / "fallback-error" / "skipped"
    judgment_error: str | None


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fallback_judgments(snapshot: dict, reason: str) -> tuple[list[MindJudgment], str]:
    """rule-based fallback: 全 Mind を "monitor" 扱いにする。

    Judgment が動かない時の安全側挙動 (ADR-0013 §1 F3 整合)。
    Conductor 自体は動き続け、人間は status JSON を見て介入できる。
    """
    minds = snapshot.get("minds", []) if isinstance(snapshot, dict) else []
    fallback = [
        MindJudgment(
            mind_name=str(m.get("mind_name", "")),
            action="monitor",
            reason=f"fallback ({reason})",
        )
        for m in minds
        if m.get("mind_name")
    ]
    return fallback, reason


def _action_breakdown(judgments: list[MindJudgment]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for j in judgments:
        breakdown[j.action] = breakdown.get(j.action, 0) + 1
    return breakdown


def run_one_cycle(
    cycle_number: int,
    *,
    client: Any | None = None,
    issues_dir: Path | None = None,
    snapshots_dir: Path | None = None,
) -> CycleResult:
    """1 cycle 実行。例外はすべて吸収して CycleResult を返す。

    引数:
        cycle_number: 識別子 (log / status JSON に書く)
        client: テスト用に Judgment client を差し替えるための DI。None なら
                make_client() を試み、失敗したら fallback ルートを取る
        issues_dir / snapshots_dir: テスト用に保管先を差し替え可

    各 step の失敗は **cycle 全体を止めない**:
    - Inbox 読み失敗 → 0 件として続行
    - snapshot 失敗 → judgment skip
    - Judgment 失敗 → fallback "monitor"
    """
    started_at = _utcnow()

    # ---- step 1: Inbox poll
    try:
        pending = list_pending_issues(issues_dir=issues_dir)
        pending_count = len(pending)
    except Exception as exc:  # noqa: BLE001 — Pillar 異常を Realm 停止に繋げない
        print(f"[conductor][cycle {cycle_number}] inbox poll failed: {exc}", file=sys.stderr)
        # debug 性のためフルトレースを出す (self-review fix)
        traceback.print_exc(file=sys.stderr)
        pending_count = -1  # marker: 取得失敗 (observe.py --realm では "?" 表示にする)

    # ---- step 2-3: Observation snapshot
    snapshot_path: Path | None = None
    snapshot_payload: dict = {"minds": []}
    try:
        snapshot_path = write_snapshot(target_dir=snapshots_dir)
        snapshot_payload = load_snapshot(snapshot_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[conductor][cycle {cycle_number}] snapshot failed: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    # ---- step 4: Judgment
    judgments: list[MindJudgment] = []
    judgment_status = "ok"
    judgment_error: str | None = None

    if not snapshot_payload.get("minds"):
        judgment_status = "skipped"
    else:
        # client が無ければ make_client を試す。AnthropicNotConfigured は fallback。
        local_client = client
        if local_client is None:
            try:
                local_client = make_client()
            except AnthropicNotConfigured as exc:
                judgments, _ = _fallback_judgments(snapshot_payload, "no-api-key")
                judgment_status = "fallback-no-key"
                judgment_error = str(exc)

        if judgment_status == "ok":
            try:
                judgments = judge_snapshot(snapshot_payload, client=local_client)
            except (JudgmentParseError, AnthropicNotConfigured) as exc:
                judgments, _ = _fallback_judgments(
                    snapshot_payload, f"judgment-error: {type(exc).__name__}"
                )
                judgment_status = "fallback-error"
                judgment_error = str(exc)
            except Exception as exc:  # noqa: BLE001 — SDK 内部 / network error
                judgments, _ = _fallback_judgments(
                    snapshot_payload, f"unexpected: {type(exc).__name__}"
                )
                judgment_status = "fallback-error"
                judgment_error = str(exc)

    ended_at = _utcnow()
    result = CycleResult(
        cycle=cycle_number,
        started_at=_iso(started_at),
        ended_at=_iso(ended_at),
        pending_issues=pending_count,
        snapshot_path=str(snapshot_path) if snapshot_path else None,
        judgments_count=len(judgments),
        judgments_action_breakdown=_action_breakdown(judgments),
        judgment_status=judgment_status,
        judgment_error=judgment_error,
    )
    return result


def write_status(
    result: CycleResult,
    target: Path | None = None,
    *,
    total_cycles: int | None = None,
) -> Path:
    """conductor-status.json に最新 cycle の情報を atomic に書く。

    Realm 統合ビュー (observe.py --realm) がこのファイルを読んで cycle 状態を出す。
    """
    target_path = target if target is not None else _default_status_file()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "conductor-status/v1",
        "last_cycle": {
            "cycle": result.cycle,
            "started_at": result.started_at,
            "ended_at": result.ended_at,
            "pending_issues": result.pending_issues,
            "snapshot_path": result.snapshot_path,
            "judgments_count": result.judgments_count,
            "judgments_action_breakdown": result.judgments_action_breakdown,
            "judgment_status": result.judgment_status,
            "judgment_error": result.judgment_error,
        },
        "total_cycles": total_cycles if total_cycles is not None else result.cycle,
        "updated_at": _iso(_utcnow()),
    }

    # atomic write (snapshot.py / inbox.py と同じパターン)。
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(target_path)
    return target_path


def run_loop(
    *,
    period_s: int = DEFAULT_PERIOD_S,
    max_cycles: int = 0,
    status_path: Path | None = None,
    issues_dir: Path | None = None,
    snapshots_dir: Path | None = None,
    client: Any | None = None,
) -> int:
    """常駐ループ。SIGTERM / SIGINT で graceful 停止 (進行中 cycle 完走)。

    引数:
        period_s: cycle 間隔 (秒、0 で sleep なし)
        max_cycles: 上限。0 = 無限 (本番)、テストでは 1〜3 程度に
        status_path: status JSON 書き込み先
        issues_dir / snapshots_dir / client: テスト用 DI

    戻り値: 実行した cycle 総数
    """
    received_stop = {"flag": False}

    def _on_signal(signum: int, frame: Any) -> None:
        received_stop["flag"] = True
        print(
            f"[conductor] received signal {signum}, exiting after current cycle...",
            file=sys.stderr,
        )

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    print(
        f"[conductor] starting loop (period={period_s}s, max_cycles={max_cycles})",
        file=sys.stderr,
    )

    cycle = 0
    while True:
        cycle += 1
        result = run_one_cycle(
            cycle,
            client=client,
            issues_dir=issues_dir,
            snapshots_dir=snapshots_dir,
        )
        try:
            write_status(result, target=status_path, total_cycles=cycle)
        except OSError as exc:
            print(f"[conductor][cycle {cycle}] write_status failed: {exc}", file=sys.stderr)

        # 進捗を 1 行で出す (docker logs で見やすく)
        print(
            f"[conductor][cycle {cycle}] pending={result.pending_issues} "
            f"snapshot={'ok' if result.snapshot_path else 'fail'} "
            f"judgment={result.judgment_status} "
            f"actions={result.judgments_action_breakdown}",
            flush=True,
        )

        if received_stop["flag"]:
            break
        if max_cycles > 0 and cycle >= max_cycles:
            break

        # sleep を細切れにして signal 受信時に即抜ける
        if period_s > 0:
            slept = 0
            while slept < period_s:
                time.sleep(1)
                slept += 1
                if received_stop["flag"]:
                    break
            if received_stop["flag"]:
                break

    print(f"[conductor] loop ended after {cycle} cycle(s)", file=sys.stderr)
    return cycle


def _parse_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(
            f"[conductor] env {name} is not an integer (got '{raw}'), using {default}",
            file=sys.stderr,
        )
        return default


def _path_from_env(name: str) -> Path | None:
    """環境変数からパスを読む。空文字 / 未設定なら None。

    E2E テスト等で snapshots / issues / status のパスを差し替えるために使う。
    """
    raw = os.environ.get(name, "")
    return Path(raw) if raw else None


if __name__ == "__main__":
    period = _parse_int_env("AI_ORG_OS_CONDUCTOR_PERIOD", DEFAULT_PERIOD_S)
    max_cycles = _parse_int_env("AI_ORG_OS_CONDUCTOR_MAX_CYCLES", 0)

    # E2E テスト向け: env で path を差し替え可能。None なら conductor.py のデフォルト
    # (= 本物の runtime/issues, runtime/pillars/observation/snapshots, runtime/realm/)。
    issues_override = _path_from_env("AI_ORG_OS_CONDUCTOR_ISSUES_DIR")
    snapshots_override = _path_from_env("AI_ORG_OS_CONDUCTOR_SNAPSHOTS_DIR")
    status_override = _path_from_env("AI_ORG_OS_CONDUCTOR_STATUS_PATH")

    sys.exit(
        0
        if run_loop(
            period_s=period,
            max_cycles=max_cycles,
            status_path=status_override,
            issues_dir=issues_override,
            snapshots_dir=snapshots_override,
        )
        else 1
    )
