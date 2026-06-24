"""Tests for time_helpers module."""

import pytest
from utils.time_helpers import format_cycle_timestamp


def test_format_cycle_timestamp_valid():
    """Test formatting of valid ISO8601 timestamp."""
    result = format_cycle_timestamp("2026-06-24T11:29:38Z")
    assert result == "2026-06-24 11:29:38"


def test_format_cycle_timestamp_invalid():
    """Test error handling for invalid timestamp."""
    with pytest.raises(ValueError, match="Invalid ISO8601 timestamp"):
        format_cycle_timestamp("not-a-timestamp")


def test_format_cycle_timestamp_edge_case():
    """Test formatting of edge case (midnight, first day of year)."""
    result = format_cycle_timestamp("2026-01-01T00:00:00Z")
    assert result == "2026-01-01 00:00:00"
