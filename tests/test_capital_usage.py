from __future__ import annotations

import unittest

import pandas as pd

from src.backtest.capital_usage import build_capital_usage_metrics


class CapitalUsageTests(unittest.TestCase):
    def test_build_capital_usage_metrics_computes_margin_and_time_weighted_usage(self) -> None:
        trades_df = pd.DataFrame(
            [
                {
                    "entry_price": 100.0,
                    "size_qty": 10.0,
                    "leverage": 5.0,
                    "exit_index": 3,
                    "notes": "Sizing valido calculado correctamente.",
                },
                {
                    "entry_price": 50.0,
                    "size_qty": 20.0,
                    "leverage": 10.0,
                    "exit_index": 1,
                    "notes": "El notional calculado supera el maximo permitido",
                },
            ]
        )

        metrics = build_capital_usage_metrics(
            trades_df=trades_df,
            initial_capital=10000.0,
            market_rows=100,
        )

        self.assertAlmostEqual(metrics["avg_notional_per_trade_usdt"], 1000.0, places=6)
        self.assertAlmostEqual(metrics["avg_margin_required_usdt"], 150.0, places=6)
        self.assertAlmostEqual(metrics["time_in_market_share"], 0.06, places=6)
        self.assertAlmostEqual(metrics["time_weighted_margin_usage_pct"], 0.001, places=6)
        self.assertAlmostEqual(metrics["capital_idle_share_proxy"], 0.999, places=6)
        self.assertAlmostEqual(metrics["notional_capped_share"], 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
