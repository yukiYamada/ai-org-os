"""
Unit tests for conduit.utils (Phase 5f Step 3)。

Standard library only (unittest, datetime)。

Run:
  python -m unittest discover runtime/pillars/conduit -p 'test_*.py'
  cd runtime/pillars/conduit && python -m unittest test_utils
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import parse_msg_id, utc_iso_compact  # noqa: E402  — sys.path tweak must run first


class UtcIsoCompactTest(unittest.TestCase):
    def test_injected_now_is_formatted_exactly(self) -> None:
        fixed = datetime(2026, 6, 3, 7, 34, 0, tzinfo=timezone.utc)
        self.assertEqual(utc_iso_compact(fixed), "20260603T073400Z")

    def test_default_now_has_compact_shape(self) -> None:
        out = utc_iso_compact()
        self.assertEqual(len(out), 16)
        self.assertTrue(out.endswith("Z"))
        self.assertEqual(out[8], "T")

    def test_naive_datetime_is_formatted_as_given(self) -> None:
        # tz 情報なしの datetime を渡しても strftime は値をそのまま整形する。
        # 呼び出し側が UTC を保証する責任を持つ契約 (docstring 参照)。
        naive = datetime(2026, 1, 2, 3, 4, 5)
        self.assertEqual(utc_iso_compact(naive), "20260102T030405Z")


class ParseMsgIdTest(unittest.TestCase):
    def test_round_trip_simple_sender(self) -> None:
        result = parse_msg_id("20260604T110218Z-alice-2dcbeea2")
        self.assertEqual(result.timestamp, "20260604T110218Z")
        self.assertEqual(result.sender, "alice")
        self.assertEqual(result.suffix, "2dcbeea2")

    def test_sender_with_hyphen_is_preserved(self) -> None:
        # `gm-default` のように mind_name にハイフンを含むケース。
        result = parse_msg_id("20260604T110218Z-gm-default-2dcbeea2")
        self.assertEqual(result.sender, "gm-default")
        self.assertEqual(result.timestamp, "20260604T110218Z")
        self.assertEqual(result.suffix, "2dcbeea2")

    def test_malformed_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_msg_id("not-a-msgid")


if __name__ == "__main__":
    unittest.main()
