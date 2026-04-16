from __future__ import annotations

import unittest

import pandas as pd

from src.backtest.backtest_runner import BacktestRunner
from run_backtest import (
    _resolve_candidate_risk,
    load_dynamic_risk_policy,
    resolve_selected_symbols,
    resolve_symbol_allowed_setups,
    resolve_symbol_backtest_risk,
    resolve_symbol_filters,
    resolve_pullback_settings,
    resolve_symbol_trade_management,
)
from src.strategy.entry_rules import OrderPlan
from src.strategy.signal_service import TradeCandidate


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

    def test_resolve_selected_symbols_keeps_config_order_and_deduplicates(self) -> None:
        selected = resolve_selected_symbols(
            ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            ["ETHUSDT", "BTCUSDT", "ETHUSDT"],
        )
        self.assertEqual(selected, ["ETHUSDT", "BTCUSDT"])

    def test_resolve_selected_symbols_accepts_comma_separated_values(self) -> None:
        selected = resolve_selected_symbols(
            ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            ["BTCUSDT, SOLUSDT"],
        )
        self.assertEqual(selected, ["BTCUSDT", "SOLUSDT"])

    def test_resolve_selected_symbols_excludes_symbols_from_strategy_scope(self) -> None:
        selected = resolve_selected_symbols(
            ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            None,
            excluded_symbols=["BNBUSDT"],
        )
        self.assertEqual(selected, ["BTCUSDT", "ETHUSDT"])

    def test_resolve_selected_symbols_rejects_requested_excluded_symbol(self) -> None:
        with self.assertRaises(ValueError):
            resolve_selected_symbols(
                ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
                ["BNBUSDT"],
                excluded_symbols=["BNBUSDT"],
            )

    def test_resolve_symbol_filters_returns_global_filters_when_symbol_has_no_override(self) -> None:
        resolved = resolve_symbol_filters(
            {
                "filters": {
                    "min_breakout_volume_multiple": 1.0,
                    "max_consolidation_range_atr_multiple": 1.2,
                    "max_trigger_candle_atr_multiple": 1.6,
                }
            },
            "BTCUSDT",
        )
        self.assertEqual(
            resolved,
            {
                "min_breakout_volume_multiple": 1.0,
                "max_consolidation_range_atr_multiple": 1.2,
                "max_trigger_candle_atr_multiple": 1.6,
            },
        )

    def test_resolve_symbol_filters_merges_symbol_override_over_global_filters(self) -> None:
        resolved = resolve_symbol_filters(
            {
                "filters": {
                    "stop_buffer_atr_fraction": 0.10,
                    "min_breakout_volume_multiple": 1.0,
                    "max_consolidation_range_atr_multiple": 1.2,
                    "max_trigger_candle_atr_multiple": 1.6,
                    "by_symbol": {
                        "ETHUSDT": {
                            "max_consolidation_range_atr_multiple": 1.4,
                        }
                    },
                }
            },
            "ETHUSDT",
        )
        self.assertEqual(
            resolved,
            {
                "stop_buffer_atr_fraction": 0.10,
                "min_breakout_volume_multiple": 1.0,
                "max_consolidation_range_atr_multiple": 1.4,
                "max_trigger_candle_atr_multiple": 1.6,
            },
        )

    def test_resolve_symbol_filters_supports_stop_buffer_override(self) -> None:
        resolved = resolve_symbol_filters(
            {
                "filters": {
                    "stop_buffer_atr_fraction": 0.10,
                    "min_breakout_volume_multiple": 1.0,
                    "max_consolidation_range_atr_multiple": 1.2,
                    "max_trigger_candle_atr_multiple": 1.6,
                    "by_symbol": {
                        "ETHUSDT": {
                            "stop_buffer_atr_fraction": 0.15,
                        }
                    },
                }
            },
            "ETHUSDT",
        )
        self.assertEqual(resolved["stop_buffer_atr_fraction"], 0.15)

    def test_resolve_symbol_filters_applies_runtime_overrides_last(self) -> None:
        resolved = resolve_symbol_filters(
            {
                "filters": {
                    "min_breakout_volume_multiple": 1.0,
                    "max_consolidation_range_atr_multiple": 1.2,
                    "max_trigger_candle_atr_multiple": 1.6,
                    "by_symbol": {
                        "ETHUSDT": {
                            "max_consolidation_range_atr_multiple": 1.4,
                        }
                    },
                }
            },
            "ETHUSDT",
            overrides={
                "max_consolidation_range_atr_multiple": 1.5,
                "max_trigger_candle_atr_multiple": 1.7,
            },
        )
        self.assertEqual(
            resolved,
            {
                "min_breakout_volume_multiple": 1.0,
                "max_consolidation_range_atr_multiple": 1.5,
                "max_trigger_candle_atr_multiple": 1.7,
            },
        )

    def test_resolve_symbol_trade_management_returns_global_timeout_by_default(self) -> None:
        resolved = resolve_symbol_trade_management(
            {
                "trade_management": {
                    "max_bars_in_trade": 24,
                }
            },
            "BTCUSDT",
        )
        self.assertEqual(resolved, {"max_bars_in_trade": 24.0})

    def test_resolve_symbol_trade_management_merges_symbol_override(self) -> None:
        resolved = resolve_symbol_trade_management(
            {
                "trade_management": {
                    "max_bars_in_trade": 24,
                    "by_symbol": {
                        "ETHUSDT": {
                            "max_bars_in_trade": 32,
                        }
                    },
                }
            },
            "ETHUSDT",
        )
        self.assertEqual(resolved, {"max_bars_in_trade": 32.0})

    def test_resolve_symbol_backtest_risk_returns_defaults_without_override(self) -> None:
        risk_pct, risk_bucket = resolve_symbol_backtest_risk(
            {"risk": {"risk_by_score": {"strong": 0.0085}}},
            "BTCUSDT",
            0.0085,
            "strong",
        )
        self.assertEqual(risk_pct, 0.0085)
        self.assertEqual(risk_bucket, "strong")

    def test_resolve_symbol_backtest_risk_applies_manual_risk_pct_override(self) -> None:
        risk_pct, risk_bucket = resolve_symbol_backtest_risk(
            {
                "risk": {
                    "risk_by_score": {"strong": 0.0085},
                    "backtest_by_symbol": {
                        "ETHUSDT": {
                            "risk_pct": 0.01,
                        }
                    },
                }
            },
            "ETHUSDT",
            0.0085,
            "strong",
        )
        self.assertEqual(risk_pct, 0.01)
        self.assertEqual(risk_bucket, "manual_0.0100")

    def test_load_dynamic_risk_policy_defaults_to_preserve_symbol_base_risk(self) -> None:
        policy = load_dynamic_risk_policy(
            {"strategy": {"dynamic_risk_by_score": {"enabled": True}}}
        )
        self.assertTrue(policy["enabled"])
        self.assertTrue(policy["preserve_symbol_base_risk"])

    def test_resolve_candidate_risk_can_preserve_symbol_base_risk_as_floor(self) -> None:
        candidate = TradeCandidate(
            order_plan=OrderPlan(
                symbol="BTCUSDT",
                side="SHORT",
                entry_price=95.0,
                stop_price=97.0,
                tp1_price=93.0,
                tp2_price=91.0,
                rr_1=1.0,
                rr_2=2.0,
                breakout_level=96.0,
                setup_type="BREAKOUT",
                notes=[],
            ),
            setup_notes=[],
            trigger_index=35,
            trigger_timestamp=pd.Timestamp("2026-01-02T20:00:00Z"),
            setup_type="BREAKOUT",
            volume_ratio=1.0,
            trigger_too_extended=False,
        )
        df_1h = _build_short_context_df("1h")
        df_4h = _build_short_context_df("4h")

        resolution = _resolve_candidate_risk(
            symbol="BTCUSDT",
            candidate=candidate,
            default_risk_pct=0.0085,
            default_risk_bucket="strong",
            df_1h=df_1h,
            df_4h=df_4h,
            score_thresholds={"min_trade": 75.0, "aggressive": 85.0, "exceptional": 93.0},
            risk_by_score={
                "small": 0.0040,
                "normal": 0.0060,
                "strong": 0.0085,
                "exceptional": 0.0110,
            },
            preserve_symbol_base_risk=True,
        )

        self.assertTrue(resolution.trade_allowed)
        self.assertAlmostEqual(resolution.risk_pct, 0.0085, places=6)
        self.assertTrue(
            any("preserva riesgo base del simbolo" in note for note in resolution.notes)
        )

    def test_resolve_candidate_risk_falls_back_to_default_when_context_is_insufficient(self) -> None:
        candidate = TradeCandidate(
            order_plan=OrderPlan(
                symbol="BTCUSDT",
                side="SHORT",
                entry_price=95.0,
                stop_price=97.0,
                tp1_price=93.0,
                tp2_price=91.0,
                rr_1=1.0,
                rr_2=2.0,
                breakout_level=96.0,
                setup_type="BREAKOUT",
                notes=[],
            ),
            setup_notes=[],
            trigger_index=35,
            trigger_timestamp=pd.Timestamp("2026-01-02T20:00:00Z"),
            setup_type="BREAKOUT",
            volume_ratio=1.0,
            trigger_too_extended=False,
        )
        df_1h = _build_short_context_df("1h").head(2)
        df_4h = _build_short_context_df("4h").head(2)

        resolution = _resolve_candidate_risk(
            symbol="BTCUSDT",
            candidate=candidate,
            default_risk_pct=0.0085,
            default_risk_bucket="strong",
            df_1h=df_1h,
            df_4h=df_4h,
            score_thresholds={"min_trade": 75.0, "aggressive": 85.0, "exceptional": 93.0},
            risk_by_score={
                "small": 0.0040,
                "normal": 0.0060,
                "strong": 0.0085,
                "exceptional": 0.0110,
            },
            preserve_symbol_base_risk=True,
        )

        self.assertTrue(resolution.trade_allowed)
        self.assertAlmostEqual(resolution.risk_pct, 0.0085, places=6)
        self.assertEqual(resolution.risk_bucket, "strong")
        self.assertTrue(
            any("Dynamic risk fallback por error de contexto/score." in note for note in resolution.notes)
        )

    def test_resolve_symbol_allowed_setups_prefers_symbol_override(self) -> None:
        resolved = resolve_symbol_allowed_setups(
            {
                "strategy": {
                    "allowed_setups": ["BREAKOUT", "PULLBACK"],
                    "allowed_setups_by_symbol": {
                        "BTCUSDT": ["BREAKOUT"],
                    },
                }
            },
            "BTCUSDT",
        )
        self.assertEqual(resolved, ["BREAKOUT"])

    def test_resolve_pullback_settings_returns_global_values(self) -> None:
        resolved = resolve_pullback_settings(
            {
                "pullback": {
                    "impulse_lookback_candles": 6,
                    "min_pullback_candles": 2,
                    "max_pullback_candles": 5,
                }
            },
            "ETHUSDT",
        )
        self.assertEqual(
            resolved,
            {
                "impulse_lookback_candles": 6.0,
                "min_pullback_candles": 2.0,
                "max_pullback_candles": 5.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
