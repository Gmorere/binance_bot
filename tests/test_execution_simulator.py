from __future__ import annotations

import unittest

import pandas as pd

from src.execution.execution_simulator import simulate_trade_v1
from src.strategy.entry_rules import OrderPlan


class ExecutionSimulatorTests(unittest.TestCase):
    def test_long_trade_hits_tp1_then_tp2(self) -> None:
        future_df = pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                },
                {
                    "timestamp": "2026-01-01T00:15:00Z",
                    "open": 104.0,
                    "high": 111.0,
                    "low": 103.0,
                    "close": 110.0,
                },
                {
                    "timestamp": "2026-01-01T00:30:00Z",
                    "open": 110.0,
                    "high": 121.0,
                    "low": 109.0,
                    "close": 120.0,
                },
            ]
        )

        order_plan = OrderPlan(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=100.0,
            stop_price=90.0,
            tp1_price=110.0,
            tp2_price=120.0,
            rr_1=1.0,
            rr_2=2.0,
            breakout_level=99.0,
            setup_type="BREAKOUT",
            notes=[],
        )

        result = simulate_trade_v1(
            symbol="BTCUSDT",
            future_df=future_df,
            order_plan=order_plan,
            position_size_units=10.0,
            fee_rate_entry=0.001,
            fee_rate_exit=0.001,
        )

        self.assertTrue(result.trade_closed)
        self.assertEqual(result.exit_reason, "TP2")
        self.assertAlmostEqual(result.exit_price or 0.0, 116.0, places=6)
        self.assertAlmostEqual(result.pnl_gross_usdt, 160.0, places=6)
        self.assertAlmostEqual(result.fee_entry_usdt, 1.0, places=6)
        self.assertAlmostEqual(result.fee_exit_usdt, 1.16, places=6)
        self.assertAlmostEqual(result.pnl_net_usdt, 157.84, places=6)

    def test_long_stop_gap_exits_at_open(self) -> None:
        future_df = pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 85.0,
                    "high": 101.0,
                    "low": 84.0,
                    "close": 86.0,
                }
            ]
        )

        order_plan = OrderPlan(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=100.0,
            stop_price=90.0,
            tp1_price=110.0,
            tp2_price=120.0,
            rr_1=1.0,
            rr_2=2.0,
            breakout_level=99.0,
            setup_type="BREAKOUT",
            notes=[],
        )

        result = simulate_trade_v1(
            symbol="BTCUSDT",
            future_df=future_df,
            order_plan=order_plan,
            position_size_units=10.0,
            fee_rate_entry=0.0,
            fee_rate_exit=0.0,
        )

        self.assertTrue(result.trade_closed)
        self.assertEqual(result.exit_reason, "STOP_LOSS")
        self.assertEqual(result.exit_price, 85.0)
        self.assertAlmostEqual(result.pnl_gross_usdt, -150.0, places=6)
        self.assertAlmostEqual(result.pnl_net_usdt, -150.0, places=6)

    def test_stop_has_priority_on_ambiguous_candle(self) -> None:
        future_df = pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 100.0,
                    "high": 121.0,
                    "low": 89.0,
                    "close": 118.0,
                }
            ]
        )

        order_plan = OrderPlan(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=100.0,
            stop_price=90.0,
            tp1_price=110.0,
            tp2_price=120.0,
            rr_1=1.0,
            rr_2=2.0,
            breakout_level=99.0,
            setup_type="BREAKOUT",
            notes=[],
        )

        result = simulate_trade_v1(
            symbol="BTCUSDT",
            future_df=future_df,
            order_plan=order_plan,
            position_size_units=10.0,
            fee_rate_entry=0.0,
            fee_rate_exit=0.0,
        )

        self.assertEqual(result.exit_reason, "STOP_LOSS")
        self.assertEqual(result.exit_price, 90.0)
        self.assertAlmostEqual(result.pnl_net_usdt, -100.0, places=6)

    def test_slippage_reduces_long_trade_pnl_on_entry_and_exit(self) -> None:
        future_df = pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                },
                {
                    "timestamp": "2026-01-01T00:15:00Z",
                    "open": 104.0,
                    "high": 111.0,
                    "low": 103.0,
                    "close": 110.0,
                },
                {
                    "timestamp": "2026-01-01T00:30:00Z",
                    "open": 110.0,
                    "high": 121.0,
                    "low": 109.0,
                    "close": 120.0,
                },
            ]
        )

        order_plan = OrderPlan(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=100.0,
            stop_price=90.0,
            tp1_price=110.0,
            tp2_price=120.0,
            rr_1=1.0,
            rr_2=2.0,
            breakout_level=99.0,
            setup_type="BREAKOUT",
            notes=[],
        )

        no_slippage = simulate_trade_v1(
            symbol="BTCUSDT",
            future_df=future_df,
            order_plan=order_plan,
            position_size_units=10.0,
            fee_rate_entry=0.0,
            fee_rate_exit=0.0,
            slippage_pct=0.0,
        )
        with_slippage = simulate_trade_v1(
            symbol="BTCUSDT",
            future_df=future_df,
            order_plan=order_plan,
            position_size_units=10.0,
            fee_rate_entry=0.0,
            fee_rate_exit=0.0,
            slippage_pct=0.01,
        )

        self.assertGreater(with_slippage.entry_price, no_slippage.entry_price)
        self.assertLess(with_slippage.exit_price or 0.0, no_slippage.exit_price or 0.0)
        self.assertLess(with_slippage.pnl_gross_usdt, no_slippage.pnl_gross_usdt)
        self.assertAlmostEqual(with_slippage.entry_price, 101.0, places=6)
        self.assertAlmostEqual(with_slippage.exit_price or 0.0, 114.84, places=6)

    def test_stop_gap_does_not_double_apply_slippage(self) -> None:
        future_df = pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 85.0,
                    "high": 101.0,
                    "low": 84.0,
                    "close": 86.0,
                }
            ]
        )

        order_plan = OrderPlan(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=100.0,
            stop_price=90.0,
            tp1_price=110.0,
            tp2_price=120.0,
            rr_1=1.0,
            rr_2=2.0,
            breakout_level=99.0,
            setup_type="BREAKOUT",
            notes=[],
        )

        result = simulate_trade_v1(
            symbol="BTCUSDT",
            future_df=future_df,
            order_plan=order_plan,
            position_size_units=10.0,
            fee_rate_entry=0.0,
            fee_rate_exit=0.0,
            slippage_pct=0.01,
        )

        self.assertEqual(result.exit_reason, "STOP_LOSS")
        self.assertEqual(result.exit_price, 85.0)
        self.assertAlmostEqual(result.pnl_gross_usdt, -160.0, places=6)


if __name__ == "__main__":
    unittest.main()
