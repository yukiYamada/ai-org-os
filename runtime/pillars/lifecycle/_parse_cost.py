#!/usr/bin/env python3
"""Phase 5g.B (#172) chunk 1: claude `--output-format json` を読んで mind_loop.cost
event を emit、result text を stdout に出力するヘルパ。

mind-loop.sh から呼ばれる:
    python _parse_cost.py <json_input_file> <mind_name> <cycle> <event_log_path>

挙動:
  - json_input_file が読めない / parse 失敗 → exit 0 (= silent fail、cost event なし)
  - parse 成功 → event_log_path に mind_loop.cost を append、result text を stdout
  - cost event 書き込み失敗時も silent (Realm を止めない、ADR-0013 F3)
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_cost_event(data: dict, mind: str, cycle: int) -> dict:
    """claude JSON から mind_loop.cost event payload を構築する。

    欠損 field は default 0 / None で埋める。claude は基本的に必ず usage を
    出すが、is_error 時等の例外ケースで欠ける可能性を考慮。
    """
    usage = data.get("usage") or {}
    model_usage = data.get("modelUsage") or {}
    return {
        "ts": _now_iso(),
        "event": "mind_loop.cost",
        "mind": mind,
        "cycle": cycle,
        "cost_usd": data.get("total_cost_usd", 0),
        "duration_api_ms": data.get("duration_api_ms", 0),
        "num_turns": data.get("num_turns", 0),
        "tokens": {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
            "cache_creation": usage.get("cache_creation_input_tokens", 0),
            "cache_read": usage.get("cache_read_input_tokens", 0),
        },
        "models": {
            name: u.get("costUSD", 0) for name, u in model_usage.items()
        },
        "session_id": data.get("session_id"),
        "is_error": bool(data.get("is_error")),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 5:
        # 想定外の呼び出し方 → silent skip
        return 0

    json_path = Path(argv[1])
    mind = argv[2]
    try:
        cycle = int(argv[3])
    except (TypeError, ValueError):
        return 0
    event_log = Path(argv[4])

    if not json_path.exists() or json_path.stat().st_size == 0:
        return 0

    try:
        # MSYS / Windows で CP932 にならないよう UTF-8 を明示
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # 不正 JSON (= claude crashed / timeout で truncate 等) は silent fail。
        # mind_loop.error / mind_loop.timeout 経路で別途記録されている。
        return 0

    if not isinstance(data, dict):
        return 0

    # result text を stdout (= mind-loop.sh が LOG_FILE に追記する)
    result_text = data.get("result")
    if isinstance(result_text, str) and result_text:
        try:
            # encoding 明示 (CP932 等で fail しないよう)
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        print(result_text)

    # cost event を event_log に append
    event = _build_cost_event(data, mind, cycle)
    try:
        event_log.parent.mkdir(parents=True, exist_ok=True)
        with event_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        # event 書き込み失敗時も Realm を止めない (ADR-0013 §1 F3)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
