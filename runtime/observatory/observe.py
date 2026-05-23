#!/usr/bin/env python3
"""
Realm Observatory CLI.

Walks runtime/minds/ and runtime/nexus/storage/ to produce a current snapshot
of all spawned Minds with status / category. Standard library only.

Usage:
  python3 runtime/observatory/observe.py
  python3 runtime/observatory/observe.py --json   # machine-readable

See ADR-0009 for the design rationale (port pure logic only, no Web UI yet).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

# Locate runtime root from this file's path: runtime/observatory/observe.py
RUNTIME_DIR = Path(__file__).resolve().parent.parent
MINDS_DIR = RUNTIME_DIR / "minds"
NEXUS_STORAGE = RUNTIME_DIR / "nexus" / "storage"
INBOX_DIR = NEXUS_STORAGE / "inbox"
ARCHIVE_DIR = NEXUS_STORAGE / "archive"

# Make `import mind_status` work without needing a package setup.
sys.path.insert(0, str(Path(__file__).parent))

from mind_status import MindObservation, calc_category, calc_status  # noqa: E402


def _read_meta(meta_path: Path, key: str, default: str = "?") -> str:
    if not meta_path.is_file():
        return default
    try:
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return default


def _epoch_from_iso(iso_str: str) -> float:
    """Parse YYYY-MM-DDTHH:MM:SSZ into a UTC epoch. Returns 0.0 on failure."""
    try:
        parsed = dt.datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ")
        return parsed.replace(tzinfo=dt.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _count_messages(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for _ in directory.glob("*.md"))


def _latest_mtime(mind_dir: Path) -> float:
    """Find latest mtime anywhere in the Mindspace. Returns 0.0 if empty."""
    if not mind_dir.is_dir():
        return 0.0
    latest = 0.0
    for entry in mind_dir.rglob("*"):
        if entry.is_file():
            try:
                latest = max(latest, entry.stat().st_mtime)
            except OSError:
                continue
    return latest


def gather_observations(now_epoch: float) -> list[tuple[MindObservation, str, str]]:
    """Walk runtime/minds/ and return (observation, status, category) per Mind.

    Only directories with .mind-meta.md count as real spawned Minds (the
    convention from spawn-mind.sh). Bare dirs are ignored.
    """
    result: list[tuple[MindObservation, str, str]] = []
    if not MINDS_DIR.is_dir():
        return result

    for mind_dir in sorted(MINDS_DIR.iterdir()):
        if not mind_dir.is_dir():
            continue
        meta = mind_dir / ".mind-meta.md"
        if not meta.is_file():
            continue
        name = mind_dir.name
        observation = MindObservation(
            mind_name=name,
            kind=_read_meta(meta, "kind"),
            persona=_read_meta(meta, "persona"),
            spawned_at_epoch=_epoch_from_iso(_read_meta(meta, "spawned_at")),
            last_activity_epoch=_latest_mtime(mind_dir),
            unread_inbox_count=_count_messages(INBOX_DIR / name),
            archive_count=_count_messages(ARCHIVE_DIR / name),
        )
        result.append(
            (observation, calc_status(observation, now_epoch), calc_category(observation, now_epoch))
        )
    return result


def _format_table(observations: list[tuple[MindObservation, str, str]]) -> str:
    if not observations:
        return "No minds spawned."

    status_counts = {"active": 0, "waiting": 0, "idle": 0}
    category_counts = {"attention": 0, "running": 0, "unread": 0, "stale": 0, "read": 0}
    for _, status, category in observations:
        status_counts[status] += 1
        category_counts[category] += 1

    lines: list[str] = []
    lines.append("=== Realm Observatory ===")
    lines.append(f"  total: {len(observations)}")
    lines.append(
        "  status:   "
        f"active={status_counts['active']}  "
        f"waiting={status_counts['waiting']}  "
        f"idle={status_counts['idle']}"
    )
    lines.append(
        "  category: "
        f"attention={category_counts['attention']}  "
        f"running={category_counts['running']}  "
        f"unread={category_counts['unread']}  "
        f"stale={category_counts['stale']}  "
        f"read={category_counts['read']}"
    )
    lines.append("")
    lines.append(
        f"{'NAME':<20} {'KIND':<10} {'PERSONA':<14} {'STATUS':<8} {'CATEGORY':<10} {'INBOX/ARCHIVE'}"
    )
    for observation, status, category in observations:
        ia = f"{observation.unread_inbox_count}/{observation.archive_count}"
        lines.append(
            f"{observation.mind_name:<20} {observation.kind:<10} "
            f"{observation.persona:<14} {status:<8} {category:<10} {ia}"
        )
    return "\n".join(lines)


def _format_json(observations: list[tuple[MindObservation, str, str]]) -> str:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv

    now_epoch = time.time()
    observations = gather_observations(now_epoch)

    if as_json:
        print(_format_json(observations))
    else:
        print(_format_table(observations))
    return 0


if __name__ == "__main__":
    sys.exit(main())
