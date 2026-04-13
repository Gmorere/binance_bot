from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import pandas as pd

from src.data.binance_kline_updater import BinanceKlineUpdaterError, RefreshResult
from src.live.market_data_runtime import (
    MarketDataPollResult,
    build_market_data_service,
    refresh_entry_market_data,
)


class MarketDataRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        base = Path("tests") / "_tmp_market_data_runtime" / uuid.uuid4().hex
        base.mkdir(parents=True, exist_ok=True)
        self.temp_dir = base
        self.raw_data_path = base / "data" / "raw"
        self.raw_data_path.mkdir(parents=True, exist_ok=True)
        self.config = {
            "project": {"mode": "paper"},
            "runtime": {
                "mode": "paper",
                "exchange": "binance_usdm",
                "poll_interval_seconds": 15,
                "paper_risk_bucket": "normal",
            },
            "symbols": {"enabled": ["BTCUSDT"]},
            "timeframes": {"entry": "15m"},
            "capital": {"initial_capital": 10000.0},
            "strategy": {"name": "continuation_breakout_momentum_v1"},
            "score_thresholds": {"min_trade": 70, "aggressive": 85, "exceptional": 93},
            "risk": {
                "risk_by_score": {
                    "small": 0.004,
                    "normal": 0.006,
                    "strong": 0.0085,
                    "exceptional": 0.011,
                },
                "max_open_positions": 3,
                "max_open_risk": {"normal": 0.0225, "offensive": 0.03, "absolute": 0.035},
                "loss_limits": {"daily": 0.02, "weekly": 0.05},
            },
            "leverage": {"BTCUSDT": 8},
            "position_limits": {"max_notional_pct": {"BTCUSDT": 0.6}},
            "execution": {
                "fee_rate_entry": 0.0004,
                "fee_rate_exit": 0.0004,
                "slippage": {"BTCUSDT": 0.0002},
            },
            "filters": {
                "min_rr_net": 1.8,
                "min_breakout_volume_multiple": 1.0,
                "max_consolidation_range_atr_multiple": 1.2,
                "max_trigger_candle_atr_multiple": 1.8,
            },
            "data": {
                "raw_data_path": str(self.raw_data_path),
                "processed_data_path": str(base / "data" / "processed"),
                "outputs_path": str(base / "outputs"),
                "refresh_from_binance_rest": False,
                "candle_close_grace_seconds": 3,
            },
            "reporting": {
                "save_trades_csv": True,
                "save_metrics_json": True,
                "save_equity_chart": False,
            },
            "binance": {
                "use_testnet": True,
                "recv_window_ms": 5000,
                "timeout_seconds": 30,
                "market_data_limit": 500,
            },
        }
        self._write_csv(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000.0,
                },
                {
                    "timestamp": "2026-01-01T00:15:00Z",
                    "open": 100.5,
                    "high": 101.5,
                    "low": 100.0,
                    "close": 101.0,
                    "volume": 1100.0,
                },
            ]
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_csv(self, rows: list[dict[str, object]]) -> None:
        pd.DataFrame(rows).to_csv(self.raw_data_path / "BTCUSDT_15m.csv", index=False)

    def test_refresh_entry_market_data_skips_when_disabled(self) -> None:
        results = refresh_entry_market_data(self.config, output_fn=lambda _line: None)
        self.assertEqual(results, [])

    def test_refresh_uses_prod_market_data_url_by_default_even_if_orders_use_testnet(self) -> None:
        self.config["data"]["refresh_from_binance_rest"] = True  # type: ignore[index]
        captured_calls: list[dict[str, object]] = []

        def fake_refresh(**kwargs: object) -> RefreshResult:
            captured_calls.append(kwargs)
            return RefreshResult(
                symbol="BTCUSDT",
                timeframe=str(kwargs["timeframe"]),
                rows_before=2,
                rows_after=2,
                new_rows=0,
                latest_timestamp="2026-01-01 00:15:00+00:00",
            )

        refresh_entry_market_data(
            self.config,
            output_fn=lambda _line: None,
            refresh_symbol_timeframe_csv_fn=fake_refresh,
        )

        self.assertEqual(len(captured_calls), 1)
        self.assertEqual(captured_calls[0]["base_url"], "https://fapi.binance.com")
        self.assertEqual(captured_calls[0]["max_retries"], 2)
        self.assertEqual(captured_calls[0]["retry_backoff_ms"], 1000)

    def test_refresh_entry_market_data_logs_and_continues_on_refresh_error(self) -> None:
        self.config["data"]["refresh_from_binance_rest"] = True  # type: ignore[index]
        outputs: list[str] = []

        def failing_refresh(**_kwargs: object) -> RefreshResult:
            raise BinanceKlineUpdaterError("418 teapot")

        results = refresh_entry_market_data(
            self.config,
            output_fn=outputs.append,
            refresh_symbol_timeframe_csv_fn=failing_refresh,
        )

        self.assertEqual(results, [])
        self.assertTrue(any("data_refresh_error" in line for line in outputs))

    def test_polling_service_applies_error_backoff_after_refresh_error(self) -> None:
        self.config["data"]["refresh_from_binance_rest"] = True  # type: ignore[index]
        outputs: list[str] = []

        def failing_refresh(**_kwargs: object) -> RefreshResult:
            raise BinanceKlineUpdaterError("418 teapot")

        service = build_market_data_service(
            self.config,
            output_fn=outputs.append,
            refresh_symbol_timeframe_csv_fn=failing_refresh,
        )

        now_ms = int(pd.Timestamp("2026-01-01T01:30:00Z").timestamp() * 1000)
        poll_result = service.poll(now_ms=now_ms)

        self.assertIsInstance(poll_result, MarketDataPollResult)
        self.assertEqual(poll_result.refresh_results, [])
        self.assertEqual(poll_result.next_poll_after_ms, now_ms + 120000)
        self.assertTrue(any("data_refresh_error_backoff" in line for line in outputs))

    def test_polling_service_respects_next_candle_close_before_refreshing_again(self) -> None:
        self.config["data"]["refresh_from_binance_rest"] = True  # type: ignore[index]
        refresh_calls: list[dict[str, object]] = []
        outputs: list[str] = []

        def fake_refresh(**kwargs: object) -> RefreshResult:
            refresh_calls.append(kwargs)
            self._write_csv(
                [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 100.5,
                        "volume": 1000.0,
                    },
                    {
                        "timestamp": "2026-01-01T00:15:00Z",
                        "open": 100.5,
                        "high": 101.5,
                        "low": 100.0,
                        "close": 101.0,
                        "volume": 1100.0,
                    },
                    {
                        "timestamp": "2026-01-01T00:30:00Z",
                        "open": 101.0,
                        "high": 102.0,
                        "low": 100.8,
                        "close": 101.8,
                        "volume": 1200.0,
                    },
                ]
            )
            return RefreshResult(
                symbol="BTCUSDT",
                timeframe="15m",
                rows_before=2,
                rows_after=3,
                new_rows=1 if len(refresh_calls) == 1 else 0,
                latest_timestamp="2026-01-01 00:30:00+00:00",
            )

        service = build_market_data_service(
            self.config,
            output_fn=outputs.append,
            refresh_symbol_timeframe_csv_fn=fake_refresh,
        )

        first_result = service.poll(
            now_ms=int(pd.Timestamp("2026-01-01T00:35:00Z").timestamp() * 1000)
        )
        second_result = service.poll(
            now_ms=int(pd.Timestamp("2026-01-01T00:40:00Z").timestamp() * 1000)
        )
        third_result = service.poll(
            now_ms=int(pd.Timestamp("2026-01-01T01:00:05Z").timestamp() * 1000)
        )

        self.assertIsInstance(first_result, MarketDataPollResult)
        self.assertEqual(len(refresh_calls), 2)
        self.assertEqual(first_result.snapshot.latest_timestamps["BTCUSDT"], "2026-01-01 00:30:00+00:00")
        self.assertEqual(second_result.snapshot.latest_timestamps["BTCUSDT"], "2026-01-01 00:30:00+00:00")
        self.assertEqual(third_result.snapshot.latest_timestamps["BTCUSDT"], "2026-01-01 00:30:00+00:00")
        self.assertEqual(first_result.refresh_results[0].new_rows, 1)
        self.assertEqual(second_result.refresh_results, [])
        self.assertEqual(third_result.refresh_results[0].new_rows, 0)
        self.assertEqual(first_result.next_poll_after_ms, 1767229203000)
        self.assertEqual(second_result.next_poll_after_ms, 1767229203000)
        self.assertEqual(third_result.next_poll_after_ms, 1767229220000)
        self.assertTrue(any("data_refresh_skip" in line for line in outputs))
        self.assertTrue(any("data_refresh_schedule" in line for line in outputs))

    def test_snapshot_loads_bias_and_context_timeframes_when_configured(self) -> None:
        self.config["timeframes"] = {"entry": "15m", "bias": "1h", "context": "4h"}  # type: ignore[index]

        pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000.0,
                },
                {
                    "timestamp": "2026-01-01T01:00:00Z",
                    "open": 100.5,
                    "high": 101.5,
                    "low": 100.0,
                    "close": 101.0,
                    "volume": 1100.0,
                },
            ]
        ).to_csv(self.raw_data_path / "BTCUSDT_1h.csv", index=False)
        pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000.0,
                },
                {
                    "timestamp": "2026-01-01T04:00:00Z",
                    "open": 100.5,
                    "high": 101.5,
                    "low": 100.0,
                    "close": 101.0,
                    "volume": 1100.0,
                },
            ]
        ).to_csv(self.raw_data_path / "BTCUSDT_4h.csv", index=False)

        snapshot = build_market_data_service(
            self.config,
            output_fn=lambda _line: None,
        ).load_entry_market_snapshot()

        self.assertIn("BTCUSDT", snapshot.market_data_by_symbol)
        self.assertIn("BTCUSDT", snapshot.bias_market_data_by_symbol)
        self.assertIn("BTCUSDT", snapshot.context_market_data_by_symbol)
        self.assertFalse(snapshot.bias_market_data_by_symbol["BTCUSDT"].empty)
        self.assertFalse(snapshot.context_market_data_by_symbol["BTCUSDT"].empty)


if __name__ == "__main__":
    unittest.main()
