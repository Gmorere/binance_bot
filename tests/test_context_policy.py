from __future__ import annotations

import unittest

import pandas as pd

from src.strategy.context_policy import evaluate_trade_candidate_policy
from src.strategy.entry_rules import OrderPlan
from src.strategy.signal_service import TradeCandidate


def _build_trade_candidate(side: str) -> TradeCandidate:
    return TradeCandidate(
        order_plan=OrderPlan(
            symbol="BTCUSDT",
            side=side,  # type: ignore[arg-type]
            entry_price=100.0,
            stop_price=99.0 if side == "LONG" else 101.0,
            tp1_price=101.0 if side == "LONG" else 99.0,
            tp2_price=102.0 if side == "LONG" else 98.0,
            rr_1=1.0,
            rr_2=2.0,
            breakout_level=100.0,
            setup_type="BREAKOUT",
            notes=[],
        ),
        setup_notes=[],
        trigger_index=10,
        trigger_timestamp=pd.Timestamp("2026-01-01T10:00:00Z"),
    )


def _build_context_df(side: str) -> pd.DataFrame:
    timestamps = pd.date_range("2025-12-31T22:00:00Z", periods=13, freq="h", tz="UTC")
    rows: list[dict[str, object]] = []

    for index, timestamp in enumerate(timestamps):
        if side == "LONG":
            ema_200 = 90.0
            ema_50 = 95.0 + index
            ema_20 = 97.0 + index
            close = 98.0 + index
        else:
            ema_200 = 110.0
            ema_50 = 105.0 - index
            ema_20 = 103.0 - index
            close = 102.0 - index

        rows.append(
            {
                "timestamp": timestamp,
                "close": close,
                "ema_20": ema_20,
                "ema_50": ema_50,
                "ema_200": ema_200,
            }
        )

    return pd.DataFrame(rows)


class ContextPolicyTests(unittest.TestCase):
    def test_policy_blocks_side_not_allowed(self) -> None:
        allowed, notes = evaluate_trade_candidate_policy(
            symbol="BTCUSDT",
            candidate=_build_trade_candidate("LONG"),
            df_1h=_build_context_df("LONG"),
            df_4h=_build_context_df("LONG"),
            allowed_sides_by_symbol={"BTCUSDT": ["SHORT"]},
            enforce_context_alignment=False,
        )

        self.assertFalse(allowed)
        self.assertTrue(any("restriccion de lado" in note for note in notes))

    def test_policy_blocks_context_conflict(self) -> None:
        allowed, notes = evaluate_trade_candidate_policy(
            symbol="BTCUSDT",
            candidate=_build_trade_candidate("LONG"),
            df_1h=_build_context_df("SHORT"),
            df_4h=_build_context_df("SHORT"),
            enforce_context_alignment=True,
        )

        self.assertFalse(allowed)
        self.assertTrue(any("conflicto" in note for note in notes))

    def test_policy_allows_aligned_context_and_side(self) -> None:
        allowed, notes = evaluate_trade_candidate_policy(
            symbol="BTCUSDT",
            candidate=_build_trade_candidate("SHORT"),
            df_1h=_build_context_df("SHORT"),
            df_4h=_build_context_df("SHORT"),
            allowed_sides_by_symbol={"BTCUSDT": ["SHORT"]},
            enforce_context_alignment=True,
        )

        self.assertTrue(allowed)
        self.assertTrue(any("contexto alineado" in note.lower() for note in notes))


if __name__ == "__main__":
    unittest.main()
