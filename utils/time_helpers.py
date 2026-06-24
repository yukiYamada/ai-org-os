"""Timestamp formatting utilities for ai-org-os."""

from datetime import datetime


def format_cycle_timestamp(iso_str: str) -> str:
    """Convert ISO8601 timestamp to human-readable format.

    Args:
        iso_str: ISO8601 timestamp string (e.g., "2026-06-24T11:29:38Z")

    Returns:
        Formatted string in "YYYY-MM-DD HH:MM:SS" format

    Raises:
        ValueError: If iso_str is not a valid ISO8601 timestamp
    """
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid ISO8601 timestamp: {iso_str}") from e
