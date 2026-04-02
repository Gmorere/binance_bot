from __future__ import annotations

import unittest

import pandas as pd

from src.backtest.signal_builder import build_breakout_signal_for_index
from src.features.indicators import add_basic_indicators
from src.strategy.scoring_policy import CandidateRiskResolution


class SignalBuilderTests(unittest.TestCase):
    def _build_market_df(self) -> pd.DataFrame:
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

        return add_basic_indicators(pd.DataFrame(rows))

    def test_build_breakout_signal_for_index_uses_trade_candidate_path(self) -> None:
        market_df = self._build_market_df()

        signal = build_breakout_signal_for_index(
            symbol="BTCUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.01,
            risk_bucket="normal",
            max_notional_pct=0.60,
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
        self.assertGreater(signal.notional_value_usdt, 0)
        self.assertLessEqual(signal.notional_value_usdt, 10000.0 * 0.60 + 1e-9)
        self.assertEqual(signal.risk_bucket, "normal")
        self.assertEqual(signal.execution_result.entry_price, signal.order_plan.entry_price)

    def test_build_breakout_signal_for_index_caps_notional_with_sizing_engine(self) -> None:
        market_df = self._build_market_df()

        signal = build_breakout_signal_for_index(
            symbol="BTCUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.011,
            risk_bucket="exceptional",
            max_notional_pct=0.10,
            leverage=8.0,
            max_forward_bars=10,
            fee_rate_entry=0.0004,
            fee_rate_exit=0.0004,
            force_close_on_last_candle=True,
            max_bars_in_trade=5,
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        expected_max_notional = 10000.0 * 0.10
        self.assertAlmostEqual(signal.notional_value_usdt, expected_max_notional, places=6)
        self.assertAlmostEqual(
            signal.position_size_units * signal.order_plan.entry_price,
            expected_max_notional,
            places=6,
        )

    def test_build_breakout_signal_for_index_applies_slippage_to_execution_fill(self) -> None:
        market_df = self._build_market_df()

        signal = build_breakout_signal_for_index(
            symbol="BTCUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.01,
            risk_bucket="normal",
            max_notional_pct=0.60,
            leverage=8.0,
            max_forward_bars=10,
            fee_rate_entry=0.0004,
            fee_rate_exit=0.0004,
            slippage_pct=0.01,
            force_close_on_last_candle=True,
            max_bars_in_trade=5,
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertGreater(signal.execution_result.entry_price, signal.order_plan.entry_price)

    def test_build_breakout_signal_for_index_respects_candidate_filter(self) -> None:
        market_df = self._build_market_df()

        signal = build_breakout_signal_for_index(
            symbol="BTCUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.01,
            risk_bucket="normal",
            max_notional_pct=0.60,
            leverage=8.0,
            max_forward_bars=10,
            fee_rate_entry=0.0004,
            fee_rate_exit=0.0004,
            force_close_on_last_candle=True,
            max_bars_in_trade=5,
            candidate_filter=lambda _candidate: (False, ["Trade bloqueado por test."]),
        )

        self.assertIsNone(signal)

    def test_build_breakout_signal_for_index_can_override_risk_from_resolver(self) -> None:
        market_df = self._build_market_df()

        signal = build_breakout_signal_for_index(
            symbol="BTCUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.006,
            risk_bucket="normal",
            max_notional_pct=0.60,
            leverage=8.0,
            max_forward_bars=10,
            fee_rate_entry=0.0004,
            fee_rate_exit=0.0004,
            force_close_on_last_candle=True,
            max_bars_in_trade=5,
            candidate_risk_resolver=lambda _candidate, _default_pct, _default_bucket: CandidateRiskResolution(
                trade_allowed=True,
                risk_pct=0.011,
                risk_bucket="exceptional",
                score_total=96.0,
                notes=["Score setup=96.00"],
            ),
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.risk_bucket, "exceptional")
        self.assertAlmostEqual(signal.risk_pct, 0.011, places=6)
        self.assertTrue(any("Score setup=96.00" in note for note in signal.order_plan.notes))

    def _build_pullback_market_df(self) -> pd.DataFrame:
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

        return add_basic_indicators(pd.DataFrame(rows))

    def test_build_breakout_signal_for_index_can_use_pullback_setup(self) -> None:
        market_df = self._build_pullback_market_df()

        signal = build_breakout_signal_for_index(
            symbol="ETHUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.01,
            risk_bucket="manual_0.0100",
            max_notional_pct=0.90,
            leverage=8.0,
            max_forward_bars=10,
            fee_rate_entry=0.0004,
            fee_rate_exit=0.0004,
            force_close_on_last_candle=True,
            max_bars_in_trade=5,
            allowed_setups=["PULLBACK"],
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.order_plan.symbol, "ETHUSDT")
        self.assertEqual(signal.order_plan.setup_type, "PULLBACK")
        self.assertEqual(signal.order_plan.side, "SHORT")
        self.assertGreater(signal.position_size_units, 0)

    def test_build_breakout_signal_for_index_blocks_pullback_when_body_is_too_extended(self) -> None:
        market_df = self._build_pullback_market_df().copy()
        market_df.loc[34, "open"] = 98.2
        market_df.loc[34, "high"] = 98.3
        market_df.loc[34, "low"] = 95.6

        signal = build_breakout_signal_for_index(
            symbol="ETHUSDT",
            market_df=market_df,
            trigger_index=34,
            capital_usdt=10000.0,
            risk_pct=0.01,
            risk_bucket="manual_0.0100",
            max_notional_pct=0.90,
            leverage=8.0,
            max_forward_bars=10,
            fee_rate_entry=0.0004,
            fee_rate_exit=0.0004,
            force_close_on_last_candle=True,
            max_bars_in_trade=5,
            allowed_setups=["PULLBACK"],
            max_trigger_body_atr_multiple=1.0,
        )

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
