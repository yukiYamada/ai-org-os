"""
observe.py --status の実装層 (Phase 5g.B #174)。

「いまの Realm」を 1 view で示す health overview。後追い observation (= trace /
cost) と違い、「現時点の生死 / 進行状況 / 滞留 / 累計 cost」を集約する。

入力源 (read-only、書き込みなし):
- $AI_ORG_OS_HOME/conductor-status.json   — 最終 cycle 情報
- $AI_ORG_OS_HOME/registry/minds/         — spawn 履歴
- $AI_ORG_OS_HOME/minds/<mind>/           — Mindspace (pid file 等)
- $AI_ORG_OS_HOME/logs/minds/<mind>/mind-loop.jsonl — per-Mind event
- $AI_ORG_OS_HOME/logs/notify.jsonl       — critical 通知履歴
- $AI_ORG_OS_HOME/issues/inbox/           — 未 claim issue 数

ADR-0014 物理境界: host 側 (B 穴あき) から container の dir を読む観察専用。
stdlib only。cost.py の aggregate を再利用する。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any


def _ai_org_os_home() -> Path:
    """`$AI_ORG_OS_HOME` 解決 (trace.py / cost.py と同じ規約)。"""
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os"


def _parse_iso_ts(ts: str | None) -> dt.datetime | None:
    """ISO ts を datetime に。失敗 / None は None。"""
    if not isinstance(ts, str) or not ts:
        return None
    s = ts.rstrip("Z")
    if "+" not in s and "-" not in s[10:]:
        s = s + "+00:00"
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def _age_seconds(ts: str | None, now: dt.datetime) -> int | None:
    """ISO ts から現在までの経過秒。"""
    d = _parse_iso_ts(ts)
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    delta = now - d
    return int(delta.total_seconds())


def _read_json(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _iter_jsonl(path: Path):
    """JSONL を 1 行ずつ dict で yield。malformed は silent skip。"""
    if not path.is_file():
        return
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _list_dir(path: Path) -> list[Path]:
    """sorted children or []."""
    if not path.is_dir():
        return []
    try:
        return sorted(path.iterdir())
    except OSError:
        return []


def _mind_alive(mind_dir: Path) -> bool:
    """Mindspace に有効 pid file があれば alive と判定。
    pid 自体の OS-level 生存確認まではしない (= cross-platform 困難)。"""
    pid_file = mind_dir / ".mind-loop.pid"
    if not pid_file.is_file():
        return False
    try:
        pid_text = pid_file.read_text(encoding="utf-8").strip()
        return bool(pid_text and pid_text.isdigit())
    except OSError:
        return False


def _gather_mind_info(
    home: Path,
    mind_name: str,
    now: dt.datetime,
) -> dict:
    """1 Mind の状態を集約。

    返す dict:
      mind, alive, spawned_at, age_s, last_event_ts, last_event_age_s,
      last_cycle, last_event, error_streak, timeout_streak,
      total_cost_usd, cost_cycles
    """
    info: dict[str, Any] = {
        "mind": mind_name,
        "alive": False,
        "spawned_at": None,
        "age_s": None,
        "last_event_ts": None,
        "last_event_age_s": None,
        "last_cycle": None,
        "last_event": None,
        "error_streak": 0,
        "timeout_streak": 0,
        "total_cost_usd": 0.0,
        "cost_cycles": 0,
    }

    mind_dir = home / "minds" / mind_name
    info["alive"] = _mind_alive(mind_dir)

    # spawn 情報 (registry)
    spawn_meta = _read_json(home / "registry" / "minds" / mind_name / "spawn.json")
    if spawn_meta is None:
        # fallback: 古い形式は spawned-at という single-line file かもしれない
        spawned_at_file = home / "registry" / "minds" / mind_name / "spawned-at"
        if spawned_at_file.is_file():
            try:
                info["spawned_at"] = spawned_at_file.read_text(encoding="utf-8").strip()
            except OSError:
                pass
    else:
        info["spawned_at"] = spawn_meta.get("spawned_at") or spawn_meta.get("ts")
    info["age_s"] = _age_seconds(info["spawned_at"], now)

    # per-Mind event log を 1 pass で 走査
    event_log = home / "logs" / "minds" / mind_name / "mind-loop.jsonl"
    last_ts: str | None = None
    last_cycle: int | None = None
    last_event_name: str | None = None
    err_streak = 0
    to_streak = 0
    cost_total = 0.0
    cost_cycles = 0
    for ev in _iter_jsonl(event_log):
        ev_name = ev.get("event")
        ts = ev.get("ts")
        if isinstance(ts, str) and (last_ts is None or ts > last_ts):
            last_ts = ts
            last_event_name = ev_name
            cyc = ev.get("cycle")
            if isinstance(cyc, int):
                last_cycle = cyc
        if ev_name == "mind_loop.error":
            err_streak = int(ev.get("streak", err_streak) or err_streak)
        elif ev_name == "mind_loop.timeout":
            to_streak = int(ev.get("streak", to_streak) or to_streak)
        elif ev_name in ("mind_loop.start", "mind_loop.end"):
            # 正常 cycle で streak は reset される (= per-cycle 上書きで OK)
            if ev_name == "mind_loop.end" and ev.get("exit_code") == 0:
                err_streak = 0
                to_streak = 0
        elif ev_name == "mind_loop.cost":
            try:
                cost_total += float(ev.get("cost_usd") or 0)
                cost_cycles += 1
            except (TypeError, ValueError):
                pass

    info["last_event_ts"] = last_ts
    info["last_event_age_s"] = _age_seconds(last_ts, now)
    info["last_cycle"] = last_cycle
    info["last_event"] = last_event_name
    info["error_streak"] = err_streak
    info["timeout_streak"] = to_streak
    info["total_cost_usd"] = cost_total
    info["cost_cycles"] = cost_cycles
    return info


def gather_status(home: Path, now: dt.datetime | None = None) -> dict:
    """Realm 全体の health 集約を返す。

    返す dict:
      summary: {now_ts, conductor_cycle, conductor_cycle_age_s, total_minds,
                alive_minds, open_issues, total_cost_usd, notify_recent_count}
      minds:   [per-mind info, alphabetical]
      issues:  {pending_count}
      notifications: {recent_critical_count, recent_warning_count}
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    minds_root = home / "minds"
    mind_names = sorted(p.name for p in _list_dir(minds_root) if p.is_dir())
    minds_info = [_gather_mind_info(home, m, now) for m in mind_names]
    alive_count = sum(1 for m in minds_info if m["alive"])

    # Conductor 最終 cycle
    cond_status = _read_json(home / "conductor-status.json") or {}
    last = cond_status.get("last_cycle") or {}
    cond_cycle = cond_status.get("total_cycles")
    cond_cycle_age = _age_seconds(last.get("ended_at"), now)

    # 未 claim issue (= inbox)。subdir 数 or *.json 数で数える
    issues_inbox = home / "issues" / "inbox"
    pending_issues = 0
    if issues_inbox.is_dir():
        try:
            pending_issues = sum(
                1 for p in issues_inbox.iterdir() if p.is_file() or p.is_dir()
            )
        except OSError:
            pending_issues = 0

    # notify 集計
    crit_count = 0
    warn_count = 0
    for ev in _iter_jsonl(home / "logs" / "notify.jsonl"):
        sev = ev.get("severity")
        if sev == "critical":
            crit_count += 1
        elif sev == "warning":
            warn_count += 1

    total_cost = sum(m["total_cost_usd"] for m in minds_info)

    return {
        "summary": {
            "now_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ai_org_os_home": str(home),
            "conductor_cycle": cond_cycle,
            "conductor_cycle_age_s": cond_cycle_age,
            "conductor_judgment_status": last.get("judgment_status"),
            "total_minds": len(minds_info),
            "alive_minds": alive_count,
            "open_issues": pending_issues,
            "total_cost_usd": total_cost,
            "notify_critical_count": crit_count,
            "notify_warning_count": warn_count,
        },
        "minds": minds_info,
        "issues": {"pending_count": pending_issues},
        "notifications": {
            "critical_count": crit_count,
            "warning_count": warn_count,
        },
    }


def _fmt_age(sec: int | None) -> str:
    if sec is None:
        return "-"
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        return f"{sec // 3600}h"
    return f"{sec // 86400}d"


def _fmt_usd(v: float) -> str:
    return f"${v:.4f}"


def format_text(agg: dict) -> str:
    s = agg["summary"]
    out: list[str] = []
    out.append("[Realm Health]")
    out.append(f"  Time: {s['now_ts']}  Home: {s['ai_org_os_home']}")
    cond_cyc = s.get("conductor_cycle")
    cond_age = _fmt_age(s.get("conductor_cycle_age_s"))
    cond_status = s.get("conductor_judgment_status") or "-"
    out.append(
        f"  Conductor: cycle={cond_cyc or '-'} age={cond_age} status={cond_status}"
    )
    out.append(
        f"  Minds: {s['alive_minds']}/{s['total_minds']} alive   "
        f"Issues pending: {s['open_issues']}   "
        f"Cost: {_fmt_usd(s['total_cost_usd'])}"
    )
    if s["notify_critical_count"] or s["notify_warning_count"]:
        out.append(
            f"  Notifications: critical={s['notify_critical_count']}  "
            f"warning={s['notify_warning_count']}  "
            f"(see logs/notify.jsonl)"
        )
    out.append("")

    if agg["minds"]:
        out.append("[Per-Mind]")
        out.append(
            f"  {'Mind':<16} {'Alive':>5} {'Age':>6} {'LastEvt':>16} "
            f"{'LastAge':>8} {'Cyc':>5} {'ErrStrk':>7} {'ToStrk':>7} {'Cost':>10}"
        )
        for m in agg["minds"]:
            alive_str = "yes" if m["alive"] else "no"
            last_evt = (m["last_event"] or "-")[:16]
            out.append(
                f"  {m['mind']:<16} {alive_str:>5} {_fmt_age(m['age_s']):>6} "
                f"{last_evt:>16} {_fmt_age(m['last_event_age_s']):>8} "
                f"{m['last_cycle'] if m['last_cycle'] is not None else '-':>5} "
                f"{m['error_streak']:>7} {m['timeout_streak']:>7} "
                f"{_fmt_usd(m['total_cost_usd']):>10}"
            )
    else:
        out.append("[Per-Mind]  (no Minds spawned)")
    return "\n".join(out) + "\n"


def format_json(agg: dict) -> str:
    return json.dumps(agg, ensure_ascii=False, indent=2)


def cmd_status(
    *,
    as_json: bool = False,
    home: Path | None = None,
    now: dt.datetime | None = None,
) -> int:
    """observe.py から呼ばれる entry。home / now は test 注入用。"""
    h = home if home is not None else _ai_org_os_home()
    agg = gather_status(h, now=now)
    if as_json:
        print(format_json(agg))
    else:
        print(format_text(agg), end="")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Realm health overview")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args()
    sys.exit(cmd_status(as_json=args.json))
