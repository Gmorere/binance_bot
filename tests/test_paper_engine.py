from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import pandas as pd
from unittest.mock import patch

from src.features.indicators import add_basic_indicators
from src.live.candidate_scanner import SymbolCandidate
from src.strategy.entry_rules import OrderPlan
from src.strategy.signal_service import TradeCandidate
from src.live.paper_engine import (
    create_initial_paper_state,
    load_paper_state,
    run_paper_cycle,
    save_paper_state,
)


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


def _build_short_context_df(timeframe: str) -> pd.DataFrame:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    rows: list[dict[str, object]] = []

    for i in range(12):
        timestamp = start + pd.Timedelta(hours=i if timeframe == "1h" else i * 4)
        close_price = 100.0 - (i * 1.5)
        rows.append(
            {
                "timestamp": timestamp,
                "close": close_price,
                "ema_20": close_price + 0.8,
                "ema_50": close_price + 1.2,
                "ema_200": close_price + 3.0,
            }
        )

    return pd.DataFrame(rows)


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
            "timeframes": {"entry": "15m", "bias": "1h", "context": "4h"},
            "strategy": {
                "backtest_policy": {
                    "enabled": False,
                    "enforce_context_alignment": False,
                    "allowed_sides": {"BTCUSDT": ["SHORT"]},
                }
            },
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
                "slippage": {"BTCUSDT": 0.0},
            },
            "leverage": {"BTCUSDT": 8},
            "position_limits": {"max_notional_pct": {"BTCUSDT": 0.60}},
            "filters": {
                "min_breakout_volume_multiple": 1.0,
                "max_consolidation_range_atr_multiple": 1.2,
                "max_trigger_candle_atr_multiple": 1.8,
            },
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

    def test_paper_cycle_applies_entry_slippage_to_open_fill(self) -> None:
        self.config["execution"]["slippage"] = {"BTCUSDT": 0.01}  # type: ignore[index]
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

        position = result.state.open_positions["BTCUSDT"]
        self.assertAlmostEqual(position.entry_price, 107.0 * 1.01, places=6)
        self.assertTrue(any("OPEN BTCUSDT" in event for event in result.events))

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

    def test_paper_cycle_replays_missed_candles_for_open_position(self) -> None:
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

        replay_df = pd.concat(
            [
                open_df,
                pd.DataFrame(
                    [
                        {
                            "timestamp": pd.Timestamp("2026-01-01T08:45:00Z"),
                            "open": position.entry_price,
                            "high": position.tp1_price + 0.5,
                            "low": position.entry_price - 0.2,
                            "close": position.tp1_price,
                            "volume": 1500,
                        },
                        {
                            "timestamp": pd.Timestamp("2026-01-01T09:00:00Z"),
                            "open": position.tp1_price,
                            "high": position.tp2_price + 0.5,
                            "low": position.tp1_price - 0.2,
                            "close": position.tp2_price,
                            "volume": 1600,
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )
        replay_df = add_basic_indicators(
            replay_df[["timestamp", "open", "high", "low", "close", "volume"]]
        )

        replayed = run_paper_cycle(
            config=self.config,
            market_data_by_symbol={"BTCUSDT": replay_df},
            state=first.state,
        )

        self.assertEqual(replayed.updated_symbols, ["BTCUSDT"])
        self.assertEqual(replayed.closed_symbols, ["BTCUSDT"])
        self.assertNotIn("BTCUSDT", replayed.state.open_positions)
        self.assertEqual(replayed.state.total_trades, 1)
        self.assertEqual(
            replayed.state.processed_candle_timestamps["BTCUSDT"],
            "2026-01-01 09:00:00+00:00",
        )

    def test_paper_cycle_applies_allowed_side_policy_before_opening_position(self) -> None:
        self.config["strategy"]["backtest_policy"]["enabled"] = True  # type: ignore[index]
        self.config["strategy"]["backtest_policy"]["allowed_sides"] = {"BTCUSDT": ["SHORT"]}  # type: ignore[index]
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

        self.assertEqual(result.opened_symbols, [])
        self.assertNotIn("BTCUSDT", result.state.open_positions)
        self.assertTrue(any("strategy_policy" in event for event in result.events))

    def test_paper_cycle_blocks_candidate_when_dynamic_score_is_below_trade_threshold(self) -> None:
        self.config["strategy"]["dynamic_risk_by_score"] = {"enabled": True, "preserve_symbol_base_risk": True}  # type: ignore[index]
        self.config["score_thresholds"] = {"min_trade": 75, "aggressive": 85, "exceptional": 93}  # type: ignore[index]
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
        candidate = TradeCandidate(
            order_plan=OrderPlan(
                symbol="BTCUSDT",
                side="SHORT",
                entry_price=107.0,
                stop_price=109.0,
                tp1_price=105.0,
                tp2_price=103.0,
                rr_1=1.0,
                rr_2=2.0,
                breakout_level=106.8,
                setup_type="BREAKOUT",
                notes=[],
            ),
            setup_notes=[],
            trigger_index=len(market_df) - 1,
            trigger_timestamp=pd.Timestamp("2026-01-02T20:00:00Z"),
            setup_type="BREAKOUT",
            volume_ratio=0.5,
            trigger_too_extended=False,
        )

        with patch("src.live.paper_engine.scan_trade_candidates", return_value=[SymbolCandidate(symbol="BTCUSDT", candidate=candidate)]):
            result = run_paper_cycle(
                config=self.config,
                market_data_by_symbol={"BTCUSDT": market_df},
                bias_market_data_by_symbol={"BTCUSDT": _build_short_context_df("1h")},
                context_market_data_by_symbol={"BTCUSDT": _build_short_context_df("4h")},
                state=state,
            )

        self.assertEqual(result.opened_symbols, [])
        self.assertNotIn("BTCUSDT", result.state.open_positions)
        self.assertTrue(any("dynamic_risk" in event for event in result.events))

    def test_paper_cycle_preserves_symbol_base_risk_when_dynamic_score_is_lower(self) -> None:
        self.config["strategy"]["dynamic_risk_by_score"] = {"enabled": True, "preserve_symbol_base_risk": True}  # type: ignore[index]
        self.config["score_thresholds"] = {"min_trade": 75, "aggressive": 85, "exceptional": 93}  # type: ignore[index]
        self.config["risk"]["backtest_by_symbol"] = {"BTCUSDT": {"risk_pct": 0.01}}  # type: ignore[index]
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
        candidate = TradeCandidate(
            order_plan=OrderPlan(
                symbol="BTCUSDT",
                side="SHORT",
                entry_price=107.0,
                stop_price=109.0,
                tp1_price=105.0,
                tp2_price=103.0,
                rr_1=1.0,
                rr_2=2.0,
                breakout_level=106.8,
                setup_type="BREAKOUT",
                notes=[],
            ),
            setup_notes=[],
            trigger_index=len(market_df) - 1,
            trigger_timestamp=pd.Timestamp("2026-01-02T20:00:00Z"),
            setup_type="BREAKOUT",
            volume_ratio=1.0,
            trigger_too_extended=False,
        )

        with patch("src.live.paper_engine.scan_trade_candidates", return_value=[SymbolCandidate(symbol="BTCUSDT", candidate=candidate)]):
            result = run_paper_cycle(
                config=self.config,
                market_data_by_symbol={"BTCUSDT": market_df},
                bias_market_data_by_symbol={"BTCUSDT": _build_short_context_df("1h")},
                context_market_data_by_symbol={"BTCUSDT": _build_short_context_df("4h")},
                state=state,
            )

        position = result.state.open_positions["BTCUSDT"]
        self.assertAlmostEqual(position.risk_pct, 0.01, places=6)
        self.assertEqual(position.risk_bucket, "small")
        self.assertTrue(any("preserva riesgo base del simbolo en paper" in note for note in position.notes))


    def test_save_paper_state_writes_atomically_without_temp_leftovers(self) -> None:
        state = create_initial_paper_state(10000.0)
        state.realized_pnl_net_usdt = 12.5
        state.processed_candle_timestamps["BTCUSDT"] = "2026-01-01 09:00:00+00:00"

        temp_dir = Path("tests") / "_tmp_paper_state" / uuid.uuid4().hex
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            state_path = temp_dir / "paper_state.json"
            saved_path = save_paper_state(state, state_path)

            self.assertEqual(saved_path, state_path)
            self.assertTrue(state_path.exists())
            self.assertEqual(list(temp_dir.glob("*.tmp")), [])

            restored = load_paper_state(state_path, initial_capital=10000.0)
            self.assertEqual(restored.realized_pnl_net_usdt, 12.5)
            self.assertEqual(
                restored.processed_candle_timestamps["BTCUSDT"],
                "2026-01-01 09:00:00+00:00",
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
