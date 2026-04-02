from __future__ import annotations

import json
from pathlib import Path
import shutil
import unittest
import uuid

import pandas as pd

from src.backtest.baseline_diagnostics import (
    build_portfolio_diagnostic,
    build_symbol_diagnostic,
    render_markdown_report,
    save_diagnostic_artifacts,
)


class BacktestBaselineDiagnosticsTests(unittest.TestCase):
    def test_build_symbol_diagnostic_summarizes_exit_reasons_and_cap_share(self) -> None:
        trades_df = pd.DataFrame(
            [
                {
                    "side": "LONG",
                    "pnl_net_usdt": -10.0,
                    "exit_reason": "STOP_LOSS",
                    "notes": "Backtest notional_usdt: 6000.0000 | El notional calculado supera el maximo permitido",
                },
                {
                    "side": "LONG",
                    "pnl_net_usdt": 20.0,
                    "exit_reason": "TP2",
                    "notes": "Sizing valido calculado correctamente.",
                },
                {
                    "side": "SHORT",
                    "pnl_net_usdt": -5.0,
                    "exit_reason": "TIMEOUT",
                    "notes": "El notional calculado supera el maximo permitido",
                },
            ]
        )

        diagnostic = build_symbol_diagnostic(
            "BTCUSDT",
            trades_df,
            baseline_record={
                "avg_notional_pct_of_capital": 0.40,
                "avg_margin_pct_of_capital": 0.08,
                "time_in_market_share": 0.12,
                "time_weighted_notional_usage_pct": 0.05,
                "time_weighted_margin_usage_pct": 0.01,
                "capital_idle_share_proxy": 0.99,
            },
        )

        self.assertEqual(diagnostic["trade_count"], 3)
        self.assertAlmostEqual(diagnostic["notional_capped_share"], 2 / 3, places=6)
        self.assertAlmostEqual(diagnostic["avg_margin_pct_of_capital"], 0.08, places=6)
        self.assertEqual(len(diagnostic["by_exit_reason"]), 3)
        self.assertEqual(len(diagnostic["by_side"]), 2)

    def test_render_markdown_report_contains_symbol_sections(self) -> None:
        markdown = render_markdown_report(
            baseline_summary={
                "portfolio_proxy": {
                    "symbol_count": 1,
                    "total_trades": 3,
                    "total_net_pnl_usdt": -5.0,
                    "average_win_rate": 0.33,
                    "best_symbol_by_net_pnl": "BTCUSDT",
                    "worst_symbol_by_net_pnl": "BTCUSDT",
                    "aggregate_time_in_market_share_proxy": 0.12,
                    "aggregate_time_weighted_margin_usage_pct_proxy": 0.04,
                    "aggregate_capital_idle_share_proxy": 0.96,
                }
            },
            symbol_diagnostics=[
                {
                    "symbol": "BTCUSDT",
                    "trade_count": 3,
                    "net_pnl_usdt": -5.0,
                    "expectancy": -1.0,
                    "win_rate": 0.33,
                    "profit_factor": 0.8,
                    "stop_loss_share": 0.33,
                    "timeout_share": 0.33,
                    "tp2_share": 0.33,
                    "notional_capped_share": 0.66,
                    "avg_notional_pct_of_capital": 0.40,
                    "avg_margin_pct_of_capital": 0.08,
                    "time_in_market_share": 0.12,
                    "time_weighted_notional_usage_pct": 0.05,
                    "time_weighted_margin_usage_pct": 0.01,
                    "capital_idle_share_proxy": 0.99,
                    "by_exit_reason": [],
                    "by_side": [],
                }
            ],
            portfolio_diagnostic={
                "worst_expectancy_symbol": "BTCUSDT",
                "highest_timeout_share_symbol": "BTCUSDT",
                "highest_notional_capped_share_symbol": "BTCUSDT",
            },
        )

        self.assertIn("# Backtest Baseline Diagnostic", markdown)
        self.assertIn("## BTCUSDT", markdown)
        self.assertIn("notional_capped_share", markdown)
        self.assertIn("aggregate_capital_idle_share_proxy", markdown)

    def test_save_diagnostic_artifacts_writes_json_and_markdown(self) -> None:
        tmp_dir = Path("outputs") / f"test_baseline_diagnostic_{uuid.uuid4().hex}"
        tmp_dir.mkdir(parents=True, exist_ok=False)
        try:
            paths = save_diagnostic_artifacts(
                output_dir=tmp_dir,
                baseline_summary={
                    "generated_at_utc": "2026-04-01T00:00:00+00:00",
                    "backtest_risk_bucket": "normal",
                    "backtest_risk_pct": 0.006,
                    "portfolio_proxy": {
                        "symbol_count": 1,
                        "total_trades": 3,
                        "total_net_pnl_usdt": -5.0,
                        "average_win_rate": 0.33,
                        "best_symbol_by_net_pnl": "BTCUSDT",
                        "worst_symbol_by_net_pnl": "BTCUSDT",
                        "aggregate_time_in_market_share_proxy": 0.12,
                        "aggregate_time_weighted_margin_usage_pct_proxy": 0.04,
                        "aggregate_capital_idle_share_proxy": 0.96,
                    },
                },
                symbol_diagnostics=[
                    {
                        "symbol": "BTCUSDT",
                        "trade_count": 3,
                        "net_pnl_usdt": -5.0,
                        "expectancy": -1.0,
                        "win_rate": 0.33,
                        "profit_factor": 0.8,
                        "stop_loss_share": 0.33,
                        "timeout_share": 0.33,
                        "tp2_share": 0.33,
                        "notional_capped_share": 0.66,
                        "avg_notional_pct_of_capital": 0.40,
                        "avg_margin_pct_of_capital": 0.08,
                        "time_in_market_share": 0.12,
                        "time_weighted_notional_usage_pct": 0.05,
                        "time_weighted_margin_usage_pct": 0.01,
                        "capital_idle_share_proxy": 0.99,
                        "by_exit_reason": [],
                        "by_side": [],
                    }
                ],
                portfolio_diagnostic={"worst_expectancy_symbol": "BTCUSDT"},
            )

            self.assertTrue(Path(paths["json_path"]).exists())
            self.assertTrue(Path(paths["md_path"]).exists())

            payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["portfolio_diagnostic"]["worst_expectancy_symbol"], "BTCUSDT")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_build_portfolio_diagnostic_returns_symbols_for_extremes(self) -> None:
        diagnostic = build_portfolio_diagnostic(
            [
                {
                    "symbol": "BTCUSDT",
                    "expectancy": -3.0,
                    "timeout_share": 0.20,
                    "stop_loss_share": 0.50,
                    "notional_capped_share": 0.90,
                },
                {
                    "symbol": "ETHUSDT",
                    "expectancy": -1.0,
                    "timeout_share": 0.30,
                    "stop_loss_share": 0.40,
                    "notional_capped_share": 0.20,
                },
            ]
        )

        self.assertEqual(diagnostic["worst_expectancy_symbol"], "BTCUSDT")
        self.assertEqual(diagnostic["highest_timeout_share_symbol"], "ETHUSDT")
        self.assertEqual(diagnostic["highest_notional_capped_share_symbol"], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
