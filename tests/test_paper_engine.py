from __future__ import annotations

import unittest

import pandas as pd

from src.features.indicators import add_basic_indicators
from src.live.paper_engine import create_initial_paper_state, run_paper_cycle


def _build_market_df(latest_rows: list[dict[str, object]]) -> pd.DataFrame:
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

    rows.extend(latest_rows)
    return add_basic_indicators(pd.DataFrame(rows))


class PaperEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "project": {"mode": "paper"},
            "runtime": {
                "mode": "paper",
                "exchange": "binance_usdm",
                "poll_interval_seconds": 15,
                "paper_risk_bucket": "normal",
            },
            "capital": {"initial_capital": 10000.0},
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
            "execution": {"fee_rate_entry": 0.0004, "fee_rate_exit": 0.0004},
            "leverage": {"BTCUSDT": 8},
            "position_limits": {"max_notional_pct": {"BTCUSDT": 0.60}},
            "binance": {"use_testnet": True, "recv_window_ms": 5000, "timeout_seconds": 30},
        }

    def test_paper_cycle_opens_position_from_candidate(self) -> None:
        market_df = _build_market_df(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-01T08:30:00Z"),
                    "open": 106.5,
                    "high": 107.2,
                    "low": 106.2,
                    "close": 107.0,
                    "volume": 2200,
                }
            ]
        )
        state = create_initial_paper_state(10000.0)

        result = run_paper_cycle(
            config=self.config,
            market_data_by_symbol={"BTCUSDT": market_df},
            state=state,
        )

        self.assertEqual(result.opened_symbols, ["BTCUSDT"])
        self.assertIn("BTCUSDT", result.state.open_positions)
        self.assertLess(result.state.equity, 10000.0)
        self.assertGreater(result.state.open_risk_pct, 0.0)

    def test_paper_cycle_manages_tp1_then_tp2(self) -> None:
        open_df = _build_market_df(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-01T08:30:00Z"),
                    "open": 106.5,
                    "high": 107.2,
                    "low": 106.2,
                    "close": 107.0,
                    "volume": 2200,
                }
            ]
        )
        state = create_initial_paper_state(10000.0)
        first = run_paper_cycle(
            config=self.config,
            market_data_by_symbol={"BTCUSDT": open_df},
            state=state,
        )
        position = first.state.open_positions["BTCUSDT"]

        tp1_df = pd.concat(
            [
                open_df,
                add_basic_indicators(
                    pd.DataFrame(
                        [
                            {
                                "timestamp": pd.Timestamp("2026-01-01T08:45:00Z"),
                                "open": position.entry_price,
                                "high": position.tp1_price + 0.5,
                                "low": position.entry_price - 0.2,
                                "close": position.tp1_price,
                                "volume": 1500,
                            }
                        ]
                    )
                ),
            ],
            ignore_index=True,
        )
        tp1_df = add_basic_indicators(tp1_df[["timestamp", "open", "high", "low", "close", "volume"]])

        second = run_paper_cycle(
            config=self.config,
            market_data_by_symbol={"BTCUSDT": tp1_df},
            state=first.state,
        )

        self.assertEqual(second.closed_symbols, [])
        self.assertIn("BTCUSDT", second.state.open_positions)
        self.assertTrue(second.state.open_positions["BTCUSDT"].tp1_hit)

        position_after_tp1 = second.state.open_positions["BTCUSDT"]
        tp2_df = pd.concat(
            [
                tp1_df,
                add_basic_indicators(
                    pd.DataFrame(
                        [
                            {
                                "timestamp": pd.Timestamp("2026-01-01T09:00:00Z"),
                                "open": position_after_tp1.tp1_price,
                                "high": position_after_tp1.tp2_price + 0.5,
                                "low": position_after_tp1.tp1_price - 0.2,
                                "close": position_after_tp1.tp2_price,
                                "volume": 1600,
                            }
                        ]
                    )
                ),
            ],
            ignore_index=True,
        )
        tp2_df = add_basic_indicators(tp2_df[["timestamp", "open", "high", "low", "close", "volume"]])

        third = run_paper_cycle(
            config=self.config,
            market_data_by_symbol={"BTCUSDT": tp2_df},
            state=second.state,
        )

        self.assertEqual(third.closed_symbols, ["BTCUSDT"])
        self.assertNotIn("BTCUSDT", third.state.open_positions)
        self.assertEqual(third.state.total_trades, 1)


if __name__ == "__main__":
    unittest.main()
