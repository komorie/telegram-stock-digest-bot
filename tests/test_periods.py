from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tg_portfolio_bot.cli import _split_cursor_periods
from tg_portfolio_bot.periods import latest_completed_daily_end, make_cursor_period, make_daily_period, period_label


KST = timezone(timedelta(hours=9), name="Asia/Seoul")


class PeriodTests(unittest.TestCase):
    def test_daily_period_uses_previous_11_to_current_11(self) -> None:
        period = make_daily_period("Asia/Seoul", datetime(2026, 5, 26).date(), 11)

        self.assertEqual(period.start_local, datetime(2026, 5, 25, 11, tzinfo=KST))
        self.assertEqual(period.end_local, datetime(2026, 5, 26, 11, tzinfo=KST))
        self.assertEqual(period_label(period), "2026년 5월 25일 11:00 ~ 2026년 5월 26일 10:59")

    def test_cursor_period_label_keeps_non_boundary_end_time(self) -> None:
        period = make_cursor_period(
            datetime(2026, 5, 25, 11, tzinfo=KST),
            datetime(2026, 5, 26, 23, 20, tzinfo=KST),
        )

        self.assertEqual(period_label(period), "2026년 5월 25일 11:00 ~ 2026년 5월 26일 23:20")

    def test_cursor_does_not_send_before_next_cutoff(self) -> None:
        periods = _split_cursor_periods(
            datetime(2026, 5, 26, 23, 20, tzinfo=KST),
            datetime(2026, 5, 27, 10, 59, tzinfo=KST),
            11,
        )

        self.assertEqual(periods, [])

    def test_cursor_sends_one_late_period_after_one_cutoff(self) -> None:
        periods = _split_cursor_periods(
            datetime(2026, 5, 26, 23, 20, tzinfo=KST),
            datetime(2026, 5, 27, 14, 0, tzinfo=KST),
            11,
        )

        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].start_local, datetime(2026, 5, 26, 23, 20, tzinfo=KST))
        self.assertEqual(periods[0].end_local, datetime(2026, 5, 27, 14, 0, tzinfo=KST))

    def test_cursor_splits_when_two_cutoffs_passed(self) -> None:
        periods = _split_cursor_periods(
            datetime(2026, 5, 26, 23, 20, tzinfo=KST),
            datetime(2026, 5, 28, 14, 0, tzinfo=KST),
            11,
        )

        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0].start_local, datetime(2026, 5, 26, 23, 20, tzinfo=KST))
        self.assertEqual(periods[0].end_local, datetime(2026, 5, 27, 11, 0, tzinfo=KST))
        self.assertEqual(periods[1].start_local, datetime(2026, 5, 27, 11, 0, tzinfo=KST))
        self.assertEqual(periods[1].end_local, datetime(2026, 5, 28, 14, 0, tzinfo=KST))

    def test_latest_completed_daily_end_before_cutoff(self) -> None:
        result = latest_completed_daily_end(
            "Asia/Seoul",
            11,
            now=datetime(2026, 5, 26, 10, 30, tzinfo=KST),
        )

        self.assertEqual(result, datetime(2026, 5, 25, 11, tzinfo=KST))

    def test_latest_completed_daily_end_after_cutoff(self) -> None:
        result = latest_completed_daily_end(
            "Asia/Seoul",
            11,
            now=datetime(2026, 5, 26, 11, 1, tzinfo=KST),
        )

        self.assertEqual(result, datetime(2026, 5, 26, 11, tzinfo=KST))


if __name__ == "__main__":
    unittest.main()
