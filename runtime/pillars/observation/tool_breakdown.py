"""Phase 5g.B #193: Per-cycle work breakdown from mind_loop.cycle_summary events.

Usage:
    python observe.py --tool-breakdown <mind> [--slow-only]

Reads mind_loop.cycle_summary events from $AI_ORG_OS_HOME/logs/minds/<mind>/mind-loop.jsonl
and displays cycle duration / num_turns / tokens breakdown.

--slow-only: Only show cycles with duration >= 300s (slow cycle threshold).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _runtime_home() -> Path:
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os"


def _parse_duration(duration_api_ms: int) -> str:
    """Convert ms to human-readable format."""
    if duration_api_ms < 1000:
        return f"{duration_api_ms}ms"
    s = duration_api_ms / 1000
    if s < 60:
        return f"{s:.1f}s"
    m = int(s // 60)
    s_rem = int(s % 60)
    return f"{m}m{s_rem:02d}s"


def cmd_tool_breakdown(mind: str | None, slow_only: bool) -> int:
    """Show per-cycle work breakdown for a Mind.

    Args:
        mind: Mind name (required)
        slow_only: If True, only show cycles >= 300s

    Returns:
        0 on success, 1 on error
    """
    if mind is None:
        print("ERROR: --tool-breakdown requires <mind> argument", file=sys.stderr)
        print("Usage: observe.py --tool-breakdown <mind> [--slow-only]", file=sys.stderr)
        return 1

    event_log = _runtime_home() / "logs" / "minds" / mind / "mind-loop.jsonl"
    if not event_log.exists():
        print(f"ERROR: No event log found for mind '{mind}'", file=sys.stderr)
        print(f"  Looked for: {event_log}", file=sys.stderr)
        return 1

    # Collect cycle_summary events
    summaries: list[dict] = []
    slow_threshold_s = 300

    try:
        with event_log.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("event") == "mind_loop.cycle_summary":
                        duration_s = event.get("duration_api_ms", 0) / 1000
                        if slow_only and duration_s < slow_threshold_s:
                            continue
                        summaries.append(event)
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        print(f"ERROR: Failed to read event log: {exc}", file=sys.stderr)
        return 1

    if not summaries:
        if slow_only:
            print(f"No slow cycles (>={slow_threshold_s}s) found for mind '{mind}'")
        else:
            print(f"No cycle summary events found for mind '{mind}'")
        return 0

    # Display table
    print(f"=== Cycle Work Breakdown: {mind} ===")
    if slow_only:
        print(f"  (showing only cycles >= {slow_threshold_s}s)")
    print()
    print(f"{'Cycle':<8} {'Duration':<12} {'Turns':<8} {'In Tokens':<12} {'Out Tokens':<12}")
    print("-" * 60)

    total_duration_ms = 0
    total_turns = 0
    total_in = 0
    total_out = 0

    for summary in summaries:
        cycle = summary.get("cycle", "?")
        duration_ms = summary.get("duration_api_ms", 0)
        num_turns = summary.get("num_turns", 0)
        tokens = summary.get("tokens", {})
        in_tokens = tokens.get("input", 0)
        out_tokens = tokens.get("output", 0)

        total_duration_ms += duration_ms
        total_turns += num_turns
        total_in += in_tokens
        total_out += out_tokens

        duration_str = _parse_duration(duration_ms)
        print(f"{cycle:<8} {duration_str:<12} {num_turns:<8} {in_tokens:<12,} {out_tokens:<12,}")

    print("-" * 60)
    print(f"{'TOTAL':<8} {_parse_duration(total_duration_ms):<12} {total_turns:<8} {total_in:<12,} {total_out:<12,}")
    print()
    print(f"Cycles shown: {len(summaries)}")
    if len(summaries) > 0:
        avg_duration_ms = total_duration_ms / len(summaries)
        avg_turns = total_turns / len(summaries)
        print(f"Average duration: {_parse_duration(int(avg_duration_ms))}")
        print(f"Average turns: {avg_turns:.1f}")

    return 0
