from __future__ import annotations

import unittest

import pandas as pd

from src.backtest.signal_builder import build_breakout_signal_for_index
from src.features.indicators import add_basic_indicators


class SignalBuilderTests(unittest.TestCase):
    def test_build_breakout_signal_for_index_uses_trade_candidate_path(self) -> None:
        rows: list[dict[str, object]] = []
        start = pd.Timestamp("2026-01-01T00:00:00Z")

        for i in range(36):
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
            elif i == 34:
                open_price = 106.5
                close_price = 107.0
                high_price = 107.2
                low_price = 106.2
                volume = 2200
            else:
                open_price = 107.3
                close_price = 108.0
                high_price = 111.0
                low_price = 107.0
                volume = 1800

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

        signal = build_breakout_signal_for_index(
            symbol="BTCUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.01,
            leverage=8.0,
            max_forward_bars=10,
            fee_rate_entry=0.0004,
            fee_rate_exit=0.0004,
            force_close_on_last_candle=True,
            max_bars_in_trade=5,
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.order_plan.symbol, "BTCUSDT")
        self.assertGreater(signal.position_size_units, 0)
        self.assertEqual(signal.execution_result.entry_price, signal.order_plan.entry_price)


if __name__ == "__main__":
    unittest.main()
