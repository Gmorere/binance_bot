from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import pandas as pd

from src.features.indicators import add_basic_indicators
from src.live.market_data_runtime import (
    MarketDataPollResult,
    MarketDataSnapshot,
    detect_symbols_with_new_candles,
)
from src.live.paper_runtime import (
    PaperRuntimeLoopError,
    _resolve_sleep_seconds,
    run_paper_runtime_loop,
)


def _build_breakout_market_df() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    start = pd.Timestamp("2026-01-01T00:00:00Z")

    for i in range(22):
        timestamp = start + pd.Timedelta(minutes=15 * i)
        open_price = 100 + (i * 0.3)
        close_price = open_price + 0.1
        high_price = close_price + 0.2
        low_price = open_price - 0.2
        rows.append(
            {
                "timestamp": timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 1000,
            }
        )

    for i in range(12):
        timestamp = start + pd.Timedelta(minutes=15 * (22 + i))
        rows.append(
            {
                "timestamp": timestamp,
                "open": 105.0,
                "high": 105.4,
                "low": 104.8,
                "close": 105.1,
                "volume": 1000,
            }
        )

    rows.append(
        {
            "timestamp": pd.Timestamp("2026-01-01T08:30:00Z"),
            "open": 106.5,
            "high": 107.2,
            "low": 106.2,
            "close": 107.0,
            "volume": 2200,
        }
    )

    return add_basic_indicators(pd.DataFrame(rows))


class FakeMarketDataService:
    def __init__(self, poll_results: list[MarketDataPollResult]) -> None:
        self.poll_results = poll_results
        self.poll_calls = 0

    def poll(self, *, now_ms: int | None = None) -> MarketDataPollResult:
        _ = now_ms
        self.poll_calls += 1
        return self.poll_results.pop(0)


class PaperRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        base = Path("tests") / "_tmp_paper_runtime" / uuid.uuid4().hex
        base.mkdir(parents=True, exist_ok=True)
        self.temp_dir = base
        self.config = {
            "project": {"mode": "paper"},
            "runtime": {
                "mode": "paper",
                "exchange": "binance_usdm",
                "poll_interval_seconds": 1,
                "paper_risk_bucket": "normal",
            },
            "capital": {"initial_capital": 10000.0},
            "symbols": {"enabled": ["BTCUSDT"]},
            "timeframes": {"entry": "15m"},
            "risk": {
                "risk_by_score": {
                    "small": 0.004,
                    "normal": 0.006,
                    "strong": 0.0085,
                    "exceptional": 0.011,
                },
                "max_open_positions": 3,
                "max_open_risk": {
                    "normal": 0.0225,
                    "offensive": 0.03,
                    "absolute": 0.035,
                },
                "loss_limits": {"daily": 0.02, "weekly": 0.05},
            },
            "execution": {
                "fee_rate_entry": 0.0004,
                "fee_rate_exit": 0.0004,
                "slippage": {"BTCUSDT": 0.0002},
            },
            "leverage": {"BTCUSDT": 8},
            "position_limits": {"max_notional_pct": {"BTCUSDT": 0.60}},
            "data": {
                "raw_data_path": str(base / "data" / "raw"),
                "processed_data_path": str(base / "data" / "processed"),
                "outputs_path": str(base / "outputs"),
                "refresh_from_binance_rest": False,
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

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_symbols_with_new_candles(self) -> None:
        latest = {"ETHUSDT": "t2", "BTCUSDT": "t1"}
        processed = {"BTCUSDT": "t0", "ETHUSDT": "t2"}
        self.assertEqual(detect_symbols_with_new_candles(latest, processed), ["BTCUSDT"])

    def test_resolve_sleep_seconds_uses_next_poll_when_available(self) -> None:
        sleep_seconds = _resolve_sleep_seconds(
            2500,
            now_ms=1000,
            fallback_seconds=15.0,
        )
        self.assertEqual(sleep_seconds, 1.5)

    def test_resolve_sleep_seconds_falls_back_when_service_has_no_schedule(self) -> None:
        sleep_seconds = _resolve_sleep_seconds(
            None,
            now_ms=1000,
            fallback_seconds=15.0,
        )
        self.assertEqual(sleep_seconds, 15.0)

    def test_runtime_loop_processes_new_candle_once_and_uses_service_schedule(self) -> None:
        market_df = _build_breakout_market_df()
        latest_timestamp = str(pd.to_datetime(market_df.iloc[-1]["timestamp"], utc=True))
        snapshot = MarketDataSnapshot(
            entry_timeframe="15m",
            market_data_by_symbol={"BTCUSDT": market_df},
            latest_timestamps={"BTCUSDT": latest_timestamp},
        )

        poll_results = [
            MarketDataPollResult(snapshot=snapshot, refresh_results=[], next_poll_after_ms=3500),
            MarketDataPollResult(snapshot=snapshot, refresh_results=[], next_poll_after_ms=4500),
        ]
        service = FakeMarketDataService(poll_results)
        outputs: list[str] = []
        sleep_calls: list[float] = []

        summary = run_paper_runtime_loop(
            config=self.config,
            max_cycles=2,
            output_fn=outputs.append,
            sleep_fn=sleep_calls.append,
            time_fn=lambda: 2.0,
            market_data_service=service,
        )

        self.assertEqual(service.poll_calls, 2)
        self.assertEqual(summary.cycles_executed, 2)
        self.assertEqual(summary.cycles_with_new_candles, 1)
        self.assertEqual(summary.cycle_errors, 0)
        self.assertTrue(summary.last_state_path.exists())
        self.assertEqual(sleep_calls, [1.5])
        self.assertTrue(any("decisions=" in line for line in outputs))
        self.assertTrue(any("runtime_status cycles=1" in line for line in outputs))
        self.assertTrue(any("sleep_seconds=1.500" in line for line in outputs))
        self.assertTrue(any("no_new_candles" in line for line in outputs))

    def test_runtime_loop_continues_with_backoff_on_cycle_error(self) -> None:
        market_df = _build_breakout_market_df()
        latest_timestamp = str(pd.to_datetime(market_df.iloc[-1]["timestamp"], utc=True))
        snapshot = MarketDataSnapshot(
            entry_timeframe="15m",
            market_data_by_symbol={"BTCUSDT": market_df},
            latest_timestamps={"BTCUSDT": latest_timestamp},
        )

        poll_results = [
            MarketDataPollResult(snapshot=snapshot, refresh_results=[], next_poll_after_ms=3500),
            MarketDataPollResult(snapshot=snapshot, refresh_results=[], next_poll_after_ms=4500),
        ]
        service = FakeMarketDataService(poll_results)
        outputs: list[str] = []
        sleep_calls: list[float] = []

        config_with_error = dict(self.config)
        config_with_error["leverage"] = {}

        summary = run_paper_runtime_loop(
            config=config_with_error,
            max_cycles=2,
            output_fn=outputs.append,
            sleep_fn=sleep_calls.append,
            time_fn=lambda: 2.0,
            market_data_service=service,
        )

        self.assertEqual(summary.cycles_executed, 2)
        self.assertEqual(summary.cycles_with_new_candles, 0)
        self.assertEqual(summary.cycle_errors, 1)
        self.assertEqual(sleep_calls, [120.0])
        self.assertTrue(any("runtime_cycle_error cycle=1" in line for line in outputs))
        self.assertTrue(any("runtime_status cycles=1" in line for line in outputs))
        self.assertTrue(
            any(
                "sleep_seconds=120.000 reason=runtime_cycle_error" in line
                for line in outputs
            )
        )

    def test_runtime_loop_fail_fast_in_once_mode_on_cycle_error(self) -> None:
        market_df = _build_breakout_market_df()
        latest_timestamp = str(pd.to_datetime(market_df.iloc[-1]["timestamp"], utc=True))
        snapshot = MarketDataSnapshot(
            entry_timeframe="15m",
            market_data_by_symbol={"BTCUSDT": market_df},
            latest_timestamps={"BTCUSDT": latest_timestamp},
        )
        service = FakeMarketDataService(
            [MarketDataPollResult(snapshot=snapshot, refresh_results=[], next_poll_after_ms=3500)]
        )
        config_with_error = dict(self.config)
        config_with_error["leverage"] = {}

        with self.assertRaises(PaperRuntimeLoopError):
            run_paper_runtime_loop(
                config=config_with_error,
                once=True,
                output_fn=lambda _line: None,
                sleep_fn=lambda _seconds: None,
                market_data_service=service,
            )


if __name__ == "__main__":
    unittest.main()
