"""
Unit tests for the pure status / category logic.

Standard library only (unittest). No filesystem access.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mind_status import (  # noqa: E402
    ACTIVE_THRESHOLD_SEC,
    IDLE_THRESHOLD_SEC,
    STALE_THRESHOLD_SEC,
    MindObservation,
    calc_category,
    calc_status,
)


def _obs(
    *,
    mind_name: str = "m",
    spawned: float = 0.0,
    last: float = 0.0,
    unread: int = 0,
    archive: int = 0,
) -> MindObservation:
    return MindObservation(
        mind_name=mind_name,
        kind="generic",
        persona="designer",
        spawned_at_epoch=spawned,
        last_activity_epoch=last,
        unread_inbox_count=unread,
        archive_count=archive,
    )


class TestCalcStatus(unittest.TestCase):
    def test_active_when_recent(self) -> None:
        now = 10_000
        self.assertEqual(calc_status(_obs(last=now - 60), now), "active")

    def test_active_at_threshold_boundary_below(self) -> None:
        now = 10_000
        self.assertEqual(
            calc_status(_obs(last=now - (ACTIVE_THRESHOLD_SEC - 1)), now), "active"
        )

    def test_waiting_just_above_active_threshold(self) -> None:
        now = 10_000
        self.assertEqual(
            calc_status(_obs(last=now - ACTIVE_THRESHOLD_SEC), now), "waiting"
        )

    def test_waiting_below_idle_threshold(self) -> None:
        now = 100_000
        self.assertEqual(
            calc_status(_obs(last=now - (IDLE_THRESHOLD_SEC - 1)), now), "waiting"
        )

    def test_idle_at_or_after_idle_threshold(self) -> None:
        now = 100_000
        self.assertEqual(
            calc_status(_obs(last=now - IDLE_THRESHOLD_SEC), now), "idle"
        )
        self.assertEqual(
            calc_status(_obs(last=now - 2 * IDLE_THRESHOLD_SEC), now), "idle"
        )

    def test_future_activity_clamped_to_zero_silence(self) -> None:
        # mtime in the future (clock skew) should not flip status into idle.
        now = 100
        self.assertEqual(calc_status(_obs(last=now + 50), now), "active")


class TestCalcCategory(unittest.TestCase):
    def test_attention_when_active_with_unread(self) -> None:
        now = 100
        self.assertEqual(calc_category(_obs(last=now - 60, unread=3), now), "attention")

    def test_running_when_active_no_unread(self) -> None:
        now = 100
        self.assertEqual(calc_category(_obs(last=now - 60, unread=0), now), "running")

    def test_unread_when_waiting_with_unread(self) -> None:
        now = 10_000
        # past active threshold but not yet idle
        silence = ACTIVE_THRESHOLD_SEC + 60
        self.assertEqual(calc_category(_obs(last=now - silence, unread=2), now), "unread")

    def test_unread_when_idle_with_unread(self) -> None:
        now = 100_000
        silence = IDLE_THRESHOLD_SEC + 60
        self.assertEqual(calc_category(_obs(last=now - silence, unread=1), now), "unread")

    def test_stale_after_threshold_without_unread(self) -> None:
        now = 1_000_000
        self.assertEqual(
            calc_category(_obs(last=now - STALE_THRESHOLD_SEC, unread=0), now), "stale"
        )

    def test_read_when_idle_not_yet_stale_without_unread(self) -> None:
        now = 1_000_000
        silence = IDLE_THRESHOLD_SEC + 60  # idle but well under stale
        self.assertEqual(calc_category(_obs(last=now - silence, unread=0), now), "read")

    def test_unread_takes_priority_over_stale(self) -> None:
        # Even if silence > stale threshold, unread categorizes as 'unread', not 'stale'.
        now = 1_000_000
        self.assertEqual(
            calc_category(_obs(last=now - 2 * STALE_THRESHOLD_SEC, unread=1), now),
            "unread",
        )


class TestSilenceClamping(unittest.TestCase):
    def test_negative_silence_does_not_break_category(self) -> None:
        now = 100
        # last activity is in the future
        self.assertEqual(calc_category(_obs(last=now + 50, unread=0), now), "running")


if __name__ == "__main__":
    unittest.main()
