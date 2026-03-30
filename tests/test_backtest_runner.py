from __future__ import annotations

import unittest

import pandas as pd

from src.backtest.backtest_runner import BacktestRunner


class BacktestRunnerTests(unittest.TestCase):
    def test_runner_returns_empty_outputs_when_no_signals(self) -> None:
        market_df = pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                },
                {
                    "timestamp": "2026-01-01T00:15:00Z",
                    "open": 100.5,
                    "high": 102.0,
                    "low": 100.0,
                    "close": 101.0,
                },
            ]
        )

        runner = BacktestRunner(
            symbol="BTCUSDT",
            market_df=market_df,
            signal_fn=lambda _df, _i: None,
            initial_capital=1000.0,
            save_outputs=False,
            print_progress=False,
        )

        trades_df, metrics, equity_curve_df = runner.run()

        self.assertTrue(trades_df.empty)
        self.assertTrue(equity_curve_df.empty)
        self.assertEqual(metrics["total_trades"], 0)
        self.assertEqual(metrics["net_pnl_usdt"], 0.0)


if __name__ == "__main__":
    unittest.main()
