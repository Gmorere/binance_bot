from __future__ import annotations

import json
from pathlib import Path
import shutil
import unittest
import uuid

import pandas as pd

from src.backtest.baseline_artifacts import (
    build_portfolio_proxy_summary,
    build_run_baseline_payload,
    build_symbol_baseline_record,
    save_run_baseline_artifacts,
)


class BacktestBaselineArtifactsTests(unittest.TestCase):
    def test_build_symbol_baseline_record_includes_market_window_and_metrics(self) -> None:
        market_df = pd.DataFrame(
            [
                {"timestamp": "2026-01-01T00:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100.5},
                {"timestamp": "2026-01-01T00:15:00Z", "open": 100.5, "high": 102, "low": 100, "close": 101},
            ]
        )
        trades_df = pd.DataFrame([{"pnl_net_usdt": 10.0}])
        metrics = {
            "total_trades": 1,
            "closed_trades": 1,
            "open_trades": 0,
            "win_rate": 1.0,
            "profit_factor": 999999.0,
            "expectancy": 10.0,
            "max_drawdown": 0.0,
            "net_pnl_usdt": 10.0,
            "gross_profit_usdt": 10.0,
            "gross_loss_usdt": 0.0,
            "avg_win": 10.0,
            "avg_loss": 0.0,
            "stop_loss_rate": 0.0,
            "tp2_rate": 1.0,
            "timeout_rate": 0.0,
            "end_of_data_rate": 0.0,
        }

        record = build_symbol_baseline_record(
            symbol="BTCUSDT",
            market_df=market_df,
            trades_df=trades_df,
            metrics=metrics,
            initial_capital=10000.0,
        )

        self.assertEqual(record["symbol"], "BTCUSDT")
        self.assertEqual(record["rows"], 2)
        self.assertEqual(record["total_trades"], 1)
        self.assertEqual(record["trade_rows_exported"], 1)
        self.assertIn("time_weighted_margin_usage_pct", record)
        self.assertTrue(record["start"].startswith("2026-01-01"))
        self.assertTrue(record["end"].startswith("2026-01-01"))

    def test_build_portfolio_proxy_summary_aggregates_symbols(self) -> None:
        summary = build_portfolio_proxy_summary(
            symbol_records=[
                {"symbol": "BTCUSDT", "total_trades": 3, "closed_trades": 3, "open_trades": 0, "net_pnl_usdt": 15.0, "gross_profit_usdt": 30.0, "gross_loss_usdt": 15.0, "win_rate": 0.5},
                {
                    "symbol": "ETHUSDT",
                    "total_trades": 2,
                    "closed_trades": 2,
                    "open_trades": 0,
                    "net_pnl_usdt": -5.0,
                    "gross_profit_usdt": 5.0,
                    "gross_loss_usdt": 10.0,
                    "win_rate": 0.25,
                    "time_in_market_share": 0.10,
                    "time_weighted_notional_usage_pct": 0.20,
                    "time_weighted_margin_usage_pct": 0.05,
                },
            ]
        )

        self.assertEqual(summary["symbol_count"], 2)
        self.assertEqual(summary["total_trades"], 5)
        self.assertEqual(summary["total_net_pnl_usdt"], 10.0)
        self.assertEqual(summary["best_symbol_by_net_pnl"], "BTCUSDT")
        self.assertEqual(summary["worst_symbol_by_net_pnl"], "ETHUSDT")
        self.assertIn("aggregate_time_weighted_margin_usage_pct_proxy", summary)

    def test_save_run_baseline_artifacts_writes_snapshot_and_summary(self) -> None:
        config = {
            "project": {"name": "binance_futures_bot", "version": "0.1.0"},
            "runtime": {"mode": "backtest"},
            "timeframes": {"entry": "15m"},
            "symbols": {"enabled": ["BTCUSDT", "ETHUSDT"]},
            "capital": {"initial_capital": 10000.0, "quote_asset": "USDT"},
            "_meta": {"config_path": "ignored", "base_dir": "ignored"},
        }
        run_payload = build_run_baseline_payload(
            config=config,
            symbol_records=[
                {"symbol": "BTCUSDT", "total_trades": 3, "closed_trades": 3, "open_trades": 0, "net_pnl_usdt": 15.0, "gross_profit_usdt": 30.0, "gross_loss_usdt": 15.0, "win_rate": 0.5},
                {
                    "symbol": "ETHUSDT",
                    "total_trades": 2,
                    "closed_trades": 2,
                    "open_trades": 0,
                    "net_pnl_usdt": -5.0,
                    "gross_profit_usdt": 5.0,
                    "gross_loss_usdt": 10.0,
                    "win_rate": 0.25,
                    "time_in_market_share": 0.10,
                    "time_weighted_notional_usage_pct": 0.20,
                    "time_weighted_margin_usage_pct": 0.05,
                },
            ],
            backtest_risk_bucket="normal",
            backtest_risk_pct=0.006,
        )

        tmp_dir = Path("outputs") / f"test_baseline_artifacts_{uuid.uuid4().hex}"
        tmp_dir.mkdir(parents=True, exist_ok=False)
        try:
            paths = save_run_baseline_artifacts(
                output_dir=str(tmp_dir),
                config=config,
                run_payload=run_payload,
            )

            for path in paths.values():
                self.assertTrue(Path(path).exists())

            config_snapshot = json.loads(Path(paths["config_snapshot_path"]).read_text(encoding="utf-8"))
            baseline_summary = json.loads(Path(paths["baseline_summary_path"]).read_text(encoding="utf-8"))

            self.assertNotIn("_meta", config_snapshot)
            self.assertEqual(baseline_summary["backtest_risk_bucket"], "normal")
            self.assertEqual(len(baseline_summary["symbols"]), 2)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
