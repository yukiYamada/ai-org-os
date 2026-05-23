"""
Mind status / category computation.

Pure functions. No I/O, no global state, no external deps.
Adapted from local-multi-window-bash-editor's lib/pure.js (calcStatus / calcCategory)
for the ai-org-os Realm Observatory.

The mapping:
  bash-editor "session"   ≒ ai-org-os "Mind"
  bash-editor "no output" ≒ ai-org-os "no Mindspace activity"
  bash-editor "waiting_confirmation pattern" ≒ ai-org-os "unread inbox count > 0"

See ADR-0009 (relationship-with-bash-editor-and-claude-team) for the rationale
of porting just the pure logic instead of importing the whole tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["active", "waiting", "idle"]
Category = Literal["attention", "running", "unread", "stale", "read"]

# Thresholds in seconds. Tuned for Mind-scale (slow async messaging) rather than
# bash-editor's PTY scale (sub-second prompt cadence).
ACTIVE_THRESHOLD_SEC = 5 * 60        # < 5 min since last activity -> active
IDLE_THRESHOLD_SEC = 60 * 60         # < 1 h -> waiting, >= 1 h -> idle
STALE_THRESHOLD_SEC = 6 * 60 * 60    # >= 6 h with no unread -> stale


@dataclass(frozen=True)
class MindObservation:
    """A snapshot of one Mind's externally observable state.

    Only metadata that can be gathered without violating Axiom (Mindspace
    inviolability): we look at file mtimes and Nexus storage counts, never at
    Mindspace file contents.
    """

    mind_name: str
    kind: str
    persona: str
    spawned_at_epoch: float
    last_activity_epoch: float
    unread_inbox_count: int
    archive_count: int


def _silence_seconds(observation: MindObservation, now_epoch: float) -> float:
    """How long since the Mind last did anything observable. Clamped to >= 0."""
    return max(0.0, now_epoch - observation.last_activity_epoch)


def calc_status(observation: MindObservation, now_epoch: float) -> Status:
    """How recent the Mind's observable activity is."""
    silence = _silence_seconds(observation, now_epoch)
    if silence < ACTIVE_THRESHOLD_SEC:
        return "active"
    if silence < IDLE_THRESHOLD_SEC:
        return "waiting"
    return "idle"


def calc_category(observation: MindObservation, now_epoch: float) -> Category:
    """Operational priority for the Realm Dashboard.

    Priority order (highest first):
      - attention: active AND has unread (Guildmaster / external should look)
      - unread:    not-active AND has unread (will be picked up next poll)
      - running:   active, nothing to attend to
      - stale:     idle for a long time, no unread (likely forgotten)
      - read:      everything else (caught up, recently idle)
    """
    status = calc_status(observation, now_epoch)
    has_unread = observation.unread_inbox_count > 0
    silence = _silence_seconds(observation, now_epoch)

    if has_unread and status == "active":
        return "attention"
    if has_unread:
        return "unread"
    if status == "active":
        return "running"
    if silence >= STALE_THRESHOLD_SEC:
        return "stale"
    return "read"
