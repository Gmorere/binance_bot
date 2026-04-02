from __future__ import annotations

import unittest

import pandas as pd

from src.features.indicators import add_basic_indicators
from src.strategy.signal_service import detect_breakout_trade_candidate, detect_trade_candidate


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

    def test_detect_trade_candidate_returns_pullback_short_order_plan(self) -> None:
        rows: list[dict[str, object]] = []
        start = pd.Timestamp("2026-01-01T00:00:00Z")

        closes = [
            110.0, 109.8, 109.6, 109.4, 109.2, 109.0, 108.8, 108.6, 108.4, 108.2,
            108.0, 107.8, 107.6, 107.4, 107.2, 107.0, 106.8, 106.6, 106.4, 106.2,
            106.0, 105.8, 105.6, 105.4, 105.2, 103.6, 102.0, 100.4, 98.8, 97.2,
            96.0, 96.8, 97.6, 98.4, 95.7, 95.2,
        ]

        for i, close_price in enumerate(closes):
            timestamp = start + pd.Timedelta(minutes=15 * i)
            open_price = closes[i - 1] if i > 0 else close_price + 0.2

            if i <= 24:
                high_price = max(open_price, close_price) + 0.3
                low_price = min(open_price, close_price) - 0.3
                volume = 1000
            elif 25 <= i <= 30:
                high_price = max(open_price, close_price) + 0.5
                low_price = min(open_price, close_price) - 0.5
                volume = 1300
            elif 31 <= i <= 33:
                high_price = max(open_price, close_price) + 0.4
                low_price = min(open_price, close_price) - 0.2
                volume = 1100
            elif i == 34:
                open_price = 96.8
                high_price = 97.0
                low_price = 95.6
                volume = 1900
            else:
                open_price = 95.5
                high_price = 95.7
                low_price = 94.8
                volume = 1500

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

        candidate = detect_trade_candidate(
            symbol="ETHUSDT",
            market_df=market_df,
            trigger_index=34,
            entry_reference_price=95.5,
            allowed_setups=["PULLBACK"],
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.order_plan.symbol, "ETHUSDT")
        self.assertEqual(candidate.order_plan.side, "SHORT")
        self.assertEqual(candidate.order_plan.setup_type, "PULLBACK")
        self.assertAlmostEqual(candidate.order_plan.entry_price, 95.5, places=6)
        self.assertTrue(
            any("Pullback continuation SHORT detectado." in note for note in candidate.setup_notes)
        )

    def test_detect_trade_candidate_rejects_pullback_with_overextended_body(self) -> None:
        rows: list[dict[str, object]] = []
        start = pd.Timestamp("2026-01-01T00:00:00Z")

        closes = [
            110.0, 109.8, 109.6, 109.4, 109.2, 109.0, 108.8, 108.6, 108.4, 108.2,
            108.0, 107.8, 107.6, 107.4, 107.2, 107.0, 106.8, 106.6, 106.4, 106.2,
            106.0, 105.8, 105.6, 105.4, 105.2, 103.6, 102.0, 100.4, 98.8, 97.2,
            96.0, 96.8, 97.6, 98.4, 95.7, 95.2,
        ]

        for i, close_price in enumerate(closes):
            timestamp = start + pd.Timedelta(minutes=15 * i)
            open_price = closes[i - 1] if i > 0 else close_price + 0.2

            if i <= 24:
                high_price = max(open_price, close_price) + 0.3
                low_price = min(open_price, close_price) - 0.3
                volume = 1000
            elif 25 <= i <= 30:
                high_price = max(open_price, close_price) + 0.5
                low_price = min(open_price, close_price) - 0.5
                volume = 1300
            elif 31 <= i <= 33:
                high_price = max(open_price, close_price) + 0.4
                low_price = min(open_price, close_price) - 0.2
                volume = 1100
            elif i == 34:
                open_price = 98.2
                high_price = 98.3
                low_price = 95.6
                volume = 1900
            else:
                open_price = 95.5
                high_price = 95.7
                low_price = 94.8
                volume = 1500

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

        candidate = detect_trade_candidate(
            symbol="ETHUSDT",
            market_df=market_df,
            trigger_index=34,
            entry_reference_price=95.5,
            allowed_setups=["PULLBACK"],
            max_trigger_body_atr_multiple=1.0,
        )

        self.assertIsNone(candidate)


if __name__ == "__main__":
    unittest.main()
