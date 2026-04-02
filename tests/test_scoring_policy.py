from __future__ import annotations

import unittest

import pandas as pd

from src.strategy.scoring_policy import resolve_candidate_risk_from_score
from src.strategy.signal_service import TradeCandidate
from src.strategy.entry_rules import OrderPlan


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


class ScoringPolicyTests(unittest.TestCase):
    def _build_candidate(self, *, symbol: str, volume_ratio: float) -> TradeCandidate:
        trigger_timestamp = pd.Timestamp("2026-01-02T20:00:00Z")
        return TradeCandidate(
            order_plan=OrderPlan(
                symbol=symbol,
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
            trigger_timestamp=trigger_timestamp,
            setup_type="BREAKOUT",
            volume_ratio=volume_ratio,
            trigger_too_extended=False,
        )

    def test_resolve_candidate_risk_from_score_returns_strong_bucket_for_high_quality_setup(self) -> None:
        resolution = resolve_candidate_risk_from_score(
            symbol="BTCUSDT",
            candidate=self._build_candidate(symbol="BTCUSDT", volume_ratio=1.8),
            df_1h=_build_short_context_df("1h"),
            df_4h=_build_short_context_df("4h"),
            score_thresholds={"min_trade": 70, "aggressive": 85, "exceptional": 93},
            risk_by_score={"small": 0.004, "normal": 0.006, "strong": 0.0085, "exceptional": 0.011},
        )

        self.assertTrue(resolution.trade_allowed)
        self.assertEqual(resolution.risk_bucket, "strong")
        self.assertAlmostEqual(resolution.risk_pct, 0.0085, places=6)
        self.assertGreaterEqual(resolution.score_total, 85.0)

    def test_resolve_candidate_risk_from_score_blocks_low_quality_setup(self) -> None:
        resolution = resolve_candidate_risk_from_score(
            symbol="XRPUSDT",
            candidate=self._build_candidate(symbol="XRPUSDT", volume_ratio=0.5),
            df_1h=_build_short_context_df("1h"),
            df_4h=_build_short_context_df("4h"),
            score_thresholds={"min_trade": 70, "aggressive": 85, "exceptional": 93},
            risk_by_score={"small": 0.004, "normal": 0.006, "strong": 0.0085, "exceptional": 0.011},
        )

        self.assertFalse(resolution.trade_allowed)
        self.assertEqual(resolution.risk_bucket, "no_trade")
        self.assertEqual(resolution.risk_pct, 0.0)
        self.assertLess(resolution.score_total, 70.0)


if __name__ == "__main__":
    unittest.main()
