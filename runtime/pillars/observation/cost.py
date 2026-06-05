"""
observe.py --cost の実装層 (Phase 5g.B #172 chunk 2)。

`logs/minds/<mind>/mind-loop.jsonl` から `mind_loop.cost` event を抽出して
per-Mind / per-day / per-model の集計を返す。

責務:
- iter_cost_events:  全 mind-loop.jsonl から mind_loop.cost 行を抽出
- aggregate:         Mind / 日 / model 別の集計を返す
- format_text:       人間可読 1 view
- format_json:       JSON 出力 (= 機械処理 / dashboard 連携用)
- cmd_cost:          observe.py から呼ばれる subcommand entry

ADR-0014 物理境界: host 側 (B 穴あき) から container の logs/ を読む読み手専用。
stdlib only。trace.py の parse_since / _default_logs_dir を再利用する。
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def _default_logs_dir() -> Path:
    """`$AI_ORG_OS_HOME/logs/` 解決。trace.py と同じ規約。"""
    import os

    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env) / "logs"
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os" / "logs"


def iter_cost_events(
    logs_dir: Path,
    *,
    mind: str | None = None,
    since_ts: str | None = None,
    stderr: Any = None,
) -> Iterable[dict]:
    """`logs_dir/minds/*/mind-loop.jsonl` を読み、mind_loop.cost event を yield。

    - mind が指定されたら、その Mind の log のみ走査 (= I/O 節約)
    - since_ts は trace.parse_since が返す ISO 文字列。string 比較で >= を見る
    - 壊れた行 / 非 dict / ts 欠落 / 非 cost event は skip (= 静音、cost 集計の
      主目的を妨げない)。trace と違い WARN は出さない (= 集計時のノイズ削減)
    - stderr は test 注入用 (現状未使用、将来 verbose mode 用に予約)
    """
    if stderr is None:
        stderr = sys.stderr
    minds_dir = logs_dir / "minds"
    if not minds_dir.is_dir():
        return
    candidates = (
        [minds_dir / mind] if mind else sorted(minds_dir.iterdir())
    )
    for mind_dir in candidates:
        log_path = mind_dir / "mind-loop.jsonl"
        if not log_path.is_file():
            continue
        try:
            raw = log_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("event") != "mind_loop.cost":
                continue
            ts = obj.get("ts")
            if not isinstance(ts, str):
                continue
            if since_ts is not None and ts < since_ts:
                continue
            yield obj


def _date_part(ts: str) -> str:
    """ISO ts から YYYY-MM-DD を抽出 (= per-day 集計 key)。

    ISO-8601 で `T` 区切りを前提 (= 我々が emit する形式)。`T` が無ければ
    そのまま返す (= 集計が日単位崩れるが落ちない、最低限の robustness)。
    """
    return ts.split("T", 1)[0]


def aggregate(events: Iterable[dict]) -> dict:
    """cost event の列から per-Mind / per-day / per-model 集計を返す。

    返す dict:
      {
        "summary": {"total_cost_usd": ..., "total_cycles": N, "minds": M,
                    "first_ts": "...", "last_ts": "..."},
        "per_mind": {mind: {"cost_usd": ..., "cycles": N,
                            "tokens": {"input":..., "output":...,
                                       "cache_creation":..., "cache_read":...},
                            "max_cycle_cost": float, "errors": int}},
        "per_day": {"YYYY-MM-DD": {"cost_usd": ..., "cycles": N, "minds": [...]}},
        "per_model": {model: {"cost_usd": ..., "share": float}},
      }
    """
    per_mind: dict[str, dict] = {}
    per_day: dict[str, dict] = {}
    per_model: dict[str, float] = defaultdict(float)
    total = 0.0
    total_cycles = 0
    first_ts: str | None = None
    last_ts: str | None = None

    for ev in events:
        mind = ev.get("mind") or "?"
        ts = ev.get("ts") or ""
        cost = float(ev.get("cost_usd") or 0)
        tokens = ev.get("tokens") or {}
        models = ev.get("models") or {}
        is_error = bool(ev.get("is_error"))

        # per-Mind 集計
        m = per_mind.setdefault(
            mind,
            {
                "cost_usd": 0.0,
                "cycles": 0,
                "tokens": {
                    "input": 0,
                    "output": 0,
                    "cache_creation": 0,
                    "cache_read": 0,
                },
                "max_cycle_cost": 0.0,
                "errors": 0,
            },
        )
        m["cost_usd"] += cost
        m["cycles"] += 1
        if cost > m["max_cycle_cost"]:
            m["max_cycle_cost"] = cost
        for k in ("input", "output", "cache_creation", "cache_read"):
            m["tokens"][k] += int(tokens.get(k, 0) or 0)
        if is_error:
            m["errors"] += 1

        # per-day 集計
        day = _date_part(ts)
        d = per_day.setdefault(day, {"cost_usd": 0.0, "cycles": 0, "minds": set()})
        d["cost_usd"] += cost
        d["cycles"] += 1
        d["minds"].add(mind)

        # per-model 集計
        if isinstance(models, dict):
            for model_name, model_cost in models.items():
                try:
                    per_model[model_name] += float(model_cost)
                except (TypeError, ValueError):
                    continue

        # 全体
        total += cost
        total_cycles += 1
        if first_ts is None or ts < first_ts:
            first_ts = ts
        if last_ts is None or ts > last_ts:
            last_ts = ts

    # per-day の minds: set → sorted list (JSON serializable)
    for d in per_day.values():
        d["minds"] = sorted(d["minds"])

    # per-model に share% を付与
    per_model_with_share: dict[str, dict] = {}
    for name, cost in per_model.items():
        share = (cost / total) if total > 0 else 0.0
        per_model_with_share[name] = {"cost_usd": cost, "share": share}

    return {
        "summary": {
            "total_cost_usd": total,
            "total_cycles": total_cycles,
            "minds": len(per_mind),
            "first_ts": first_ts,
            "last_ts": last_ts,
        },
        "per_mind": per_mind,
        "per_day": per_day,
        "per_model": per_model_with_share,
    }


def _fmt_usd(v: float) -> str:
    """USD を短く表示 ($0.0123)。"""
    return f"${v:.4f}"


def _fmt_tokens(n: int) -> str:
    """token 数を 5.2k 形式に。1000 未満はそのまま。"""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1_000_000:.1f}M"


def format_text(agg: dict) -> str:
    """human-readable 1 view を返す。"""
    s = agg["summary"]
    if s["total_cycles"] == 0:
        return "[Cost Summary]\n  No mind_loop.cost events found (logs/ empty or pre-#172).\n"

    out: list[str] = []
    out.append("[Cost Summary]")
    out.append(
        f"  Period: {s['first_ts']} .. {s['last_ts']}"
    )
    out.append(
        f"  Total: {_fmt_usd(s['total_cost_usd'])} over "
        f"{s['total_cycles']} cycle(s) across {s['minds']} Mind(s)"
    )
    out.append("")

    # per-Mind
    out.append("[Per-Mind]")
    out.append(
        f"  {'Mind':<16} {'Cycles':>6} {'Total':>10} {'Avg':>10} {'Max':>10} "
        f"{'in':>7} {'out':>7} {'cache_r':>8} {'err':>4}"
    )
    for mind, m in sorted(agg["per_mind"].items(), key=lambda kv: -kv[1]["cost_usd"]):
        avg = (m["cost_usd"] / m["cycles"]) if m["cycles"] else 0.0
        out.append(
            f"  {mind:<16} {m['cycles']:>6} {_fmt_usd(m['cost_usd']):>10} "
            f"{_fmt_usd(avg):>10} {_fmt_usd(m['max_cycle_cost']):>10} "
            f"{_fmt_tokens(m['tokens']['input']):>7} "
            f"{_fmt_tokens(m['tokens']['output']):>7} "
            f"{_fmt_tokens(m['tokens']['cache_read']):>8} "
            f"{m['errors']:>4}"
        )
    out.append("")

    # per-day (= 期間が複数日に渡る時のみ意味あり、1 日でも表示する)
    out.append("[Per-Day]")
    out.append(f"  {'Date':<12} {'Cost':>10} {'Cycles':>6}  Minds")
    for day, d in sorted(agg["per_day"].items()):
        minds_str = ",".join(d["minds"])
        out.append(
            f"  {day:<12} {_fmt_usd(d['cost_usd']):>10} {d['cycles']:>6}  {minds_str}"
        )
    out.append("")

    # per-model
    out.append("[Per-Model]")
    out.append(f"  {'Model':<40} {'Cost':>10}  Share")
    for name, info in sorted(
        agg["per_model"].items(), key=lambda kv: -kv[1]["cost_usd"]
    ):
        pct = info["share"] * 100
        out.append(
            f"  {name:<40} {_fmt_usd(info['cost_usd']):>10}  {pct:5.1f}%"
        )
    return "\n".join(out) + "\n"


def format_json(agg: dict) -> str:
    return json.dumps(agg, ensure_ascii=False, indent=2)


def cmd_cost(
    *,
    mind: str | None = None,
    since: str | None = None,
    as_json: bool = False,
    logs_dir: Path | None = None,
) -> int:
    """observe.py から呼ばれる entry。

    logs_dir は test 注入用。本番は None → `_default_logs_dir()`。
    """
    # trace.py から parse_since を再利用
    sys.path.insert(0, str(Path(__file__).parent))
    from trace import parse_since  # noqa: PLC0415

    try:
        since_ts = parse_since(since)
    except ValueError as exc:
        print(f"[cost] ERROR: {exc}", file=sys.stderr)
        return 2

    logs = logs_dir if logs_dir is not None else _default_logs_dir()
    events = list(iter_cost_events(logs, mind=mind, since_ts=since_ts))
    agg = aggregate(events)
    if as_json:
        print(format_json(agg))
    else:
        print(format_text(agg), end="")
    return 0


if __name__ == "__main__":
    # standalone CLI (= observe.py 経由でなく直接呼べる)
    import argparse

    parser = argparse.ArgumentParser(description="mind_loop.cost event aggregator")
    parser.add_argument("--mind", help="filter to one Mind")
    parser.add_argument("--since", help="filter by time (1h / 30m / 5d / ISO ts)")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args()
    sys.exit(cmd_cost(mind=args.mind, since=args.since, as_json=args.json))
