from __future__ import annotations

import unittest

import pandas as pd

from src.backtest.equity_curve import build_equity_curve
from src.backtest.metrics import compute_backtest_metrics


class BacktestMetricsTests(unittest.TestCase):
    def test_compute_backtest_metrics_uses_closed_and_open_flags(self) -> None:
        trades = pd.DataFrame(
            [
                {
                    "pnl_net_usdt": 100.0,
                    "trade_closed": True,
                    "exit_reason": "TP2",
                },
                {
                    "pnl_net_usdt": -50.0,
                    "trade_closed": True,
                    "exit_reason": "STOP_LOSS",
                },
                {
                    "pnl_net_usdt": 0.0,
                    "trade_closed": False,
                    "exit_reason": "NO_EXIT",
                },
            ]
        )

        metrics = compute_backtest_metrics(trades)

        self.assertEqual(metrics["total_trades"], 3)
        self.assertEqual(metrics["closed_trades"], 2)
        self.assertEqual(metrics["open_trades"], 1)
        self.assertAlmostEqual(metrics["net_pnl_usdt"], 50.0, places=6)
        self.assertAlmostEqual(metrics["gross_profit_usdt"], 100.0, places=6)
        self.assertAlmostEqual(metrics["gross_loss_usdt"], 50.0, places=6)
        self.assertAlmostEqual(metrics["profit_factor"], 2.0, places=6)
        self.assertAlmostEqual(metrics["win_rate"], 1 / 3, places=6)
        self.assertAlmostEqual(metrics["stop_loss_rate"], 1 / 3, places=6)
        self.assertAlmostEqual(metrics["tp2_rate"], 1 / 3, places=6)

    def test_build_equity_curve_accumulates_from_initial_capital(self) -> None:
        trades = pd.DataFrame(
            [
                {"exit_time": "2026-01-01T00:15:00Z", "pnl_net_usdt": 100.0},
                {"exit_time": "2026-01-01T00:30:00Z", "pnl_net_usdt": -25.0},
            ]
        )

        curve = build_equity_curve(trades, initial_capital=1000.0)

        self.assertEqual(list(curve["equity"]), [1100.0, 1075.0])


if __name__ == "__main__":
    unittest.main()
