from __future__ import annotations

import unittest

import pandas as pd

from src.features.indicators import add_basic_indicators
from src.strategy.signal_service import detect_breakout_trade_candidate


class SignalServiceTests(unittest.TestCase):
    def test_detect_breakout_trade_candidate_returns_order_plan(self) -> None:
        rows: list[dict[str, object]] = []
        start = pd.Timestamp("2026-01-01T00:00:00Z")

        for i in range(35):
            timestamp = start + pd.Timedelta(minutes=15 * i)

            if i < 22:
                open_price = 100 + (i * 0.3)
                close_price = open_price + 0.1
                high_price = close_price + 0.2
                low_price = open_price - 0.2
                volume = 1000
            elif 22 <= i <= 33:
                open_price = 105.0
                close_price = 105.1
                high_price = 105.4
                low_price = 104.8
                volume = 1000
            else:
                open_price = 106.5
                close_price = 107.0
                high_price = 107.2
                low_price = 106.2
                volume = 2200

            rows.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        market_df = add_basic_indicators(pd.DataFrame(rows))

        candidate = detect_breakout_trade_candidate(
            symbol="BTCUSDT",
            market_df=market_df,
            trigger_index=len(market_df) - 1,
            entry_reference_price=107.3,
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.order_plan.symbol, "BTCUSDT")
        self.assertEqual(candidate.order_plan.side, "LONG")
        self.assertAlmostEqual(candidate.order_plan.entry_price, 107.3, places=6)
        self.assertTrue(any("Breakout LONG detectado." in note for note in candidate.setup_notes))


if __name__ == "__main__":
    unittest.main()
