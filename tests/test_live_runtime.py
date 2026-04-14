from __future__ import annotations

import unittest

from src.live.live_runtime import LiveRuntimeLoopError, run_live_runtime_loop


class FakeBinanceClient:
    def __init__(self, payload: dict[str, object] | None = None, *, fail: bool = False) -> None:
        self.payload = payload or {
            "totalWalletBalance": "10000.00",
            "availableBalance": "9500.00",
            "positions": [],
        }
        self.fail = fail
        self.account_calls = 0

    def get_account_info(self) -> dict[str, object]:
        self.account_calls += 1
        if self.fail:
            raise RuntimeError("simulated account failure")
        return self.payload


class LiveRuntimeTests(unittest.TestCase):
    def _base_config(self, *, mode: str = "live") -> dict[str, object]:
        return {
            "project": {"mode": mode},
            "runtime": {
                "mode": mode,
                "exchange": "binance_usdm",
                "poll_interval_seconds": 15,
                "backtest_risk_bucket": "normal",
                "paper_risk_bucket": "normal",
            },
            "binance": {
                "use_testnet": True,
                "use_testnet_market_data": False,
                "recv_window_ms": 5000,
                "timeout_seconds": 30,
                "market_data_limit": 500,
                "rest_max_retries": 2,
                "rest_retry_backoff_ms": 1000,
            },
            "data": {
                "refresh_from_binance_rest": True,
                "candle_close_grace_seconds": 3,
                "refresh_error_backoff_seconds": 120,
            },
        }

    def test_live_runtime_requires_live_mode(self) -> None:
        with self.assertRaises(LiveRuntimeLoopError):
            run_live_runtime_loop(
                config=self._base_config(mode="paper"),
                once=True,
                output_fn=lambda _line: None,
            )

    def test_live_runtime_blocks_execution_by_default(self) -> None:
        fake_client = FakeBinanceClient()
        outputs: list[str] = []
        summary = run_live_runtime_loop(
            config=self._base_config(),
            once=True,
            output_fn=outputs.append,
            client=fake_client,
            env={},
        )

        self.assertEqual(summary.cycles_executed, 1)
        self.assertEqual(summary.account_checks, 1)
        self.assertEqual(summary.reconciliations_ok, 1)
        self.assertEqual(summary.orders_submitted, 0)
        self.assertEqual(summary.orders_blocked, 1)
        self.assertFalse(summary.live_execution_enabled)
        self.assertTrue(any("live_guard execution_disabled" in line for line in outputs))

    def test_live_runtime_requires_credentials_if_live_enabled(self) -> None:
        with self.assertRaises(LiveRuntimeLoopError):
            run_live_runtime_loop(
                config=self._base_config(),
                once=True,
                output_fn=lambda _line: None,
                env={"LIVE_ENABLED": "true"},
                client=None,
            )

    def test_live_runtime_runs_without_client_in_safe_mode(self) -> None:
        outputs: list[str] = []
        summary = run_live_runtime_loop(
            config=self._base_config(),
            once=True,
            output_fn=outputs.append,
            env={},
            client=None,
        )

        self.assertEqual(summary.cycles_executed, 1)
        self.assertEqual(summary.account_checks, 0)
        self.assertEqual(summary.reconciliations_ok, 0)
        self.assertEqual(summary.orders_blocked, 1)
        self.assertTrue(any("safe_mode_no_client=true" in line for line in outputs))

    def test_live_runtime_continues_when_account_check_fails(self) -> None:
        fake_client = FakeBinanceClient(fail=True)
        outputs: list[str] = []
        sleep_calls: list[float] = []
        summary = run_live_runtime_loop(
            config=self._base_config(),
            max_cycles=2,
            output_fn=outputs.append,
            sleep_fn=sleep_calls.append,
            client=fake_client,
            env={},
        )

        self.assertEqual(summary.cycles_executed, 2)
        self.assertEqual(summary.account_checks, 2)
        self.assertEqual(summary.reconciliations_ok, 0)
        self.assertEqual(summary.cycle_errors, 2)
        self.assertEqual(sleep_calls, [15.0])
        self.assertTrue(any("live_cycle_error" in line for line in outputs))


if __name__ == "__main__":
    unittest.main()
