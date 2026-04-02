from __future__ import annotations

from typing import Any

import pandas as pd


def _contains_notional_cap(notes: str | None) -> bool:
    if not notes:
        return False
    return "notional calculado supera" in str(notes).lower()


def build_capital_usage_metrics(
    *,
    trades_df: pd.DataFrame,
    initial_capital: float,
    market_rows: int,
) -> dict[str, Any]:
    if initial_capital <= 0:
        raise ValueError("initial_capital debe ser mayor a 0.")

    if trades_df.empty:
        return {
            "avg_notional_per_trade_usdt": 0.0,
            "avg_margin_required_usdt": 0.0,
            "max_notional_per_trade_usdt": 0.0,
            "max_margin_required_usdt": 0.0,
            "avg_notional_pct_of_capital": 0.0,
            "avg_margin_pct_of_capital": 0.0,
            "max_notional_pct_of_capital": 0.0,
            "max_margin_pct_of_capital": 0.0,
            "time_in_market_share": 0.0,
            "time_weighted_notional_usage_pct": 0.0,
            "time_weighted_margin_usage_pct": 0.0,
            "capital_idle_share_proxy": 1.0,
            "notional_capped_share": 0.0,
        }

    required_cols = {"entry_price", "size_qty", "leverage", "exit_index"}
    if not required_cols.issubset(trades_df.columns):
        notes_series = (
            trades_df["notes"].astype(str)
            if "notes" in trades_df.columns
            else pd.Series(dtype=str)
        )
        return {
            "avg_notional_per_trade_usdt": 0.0,
            "avg_margin_required_usdt": 0.0,
            "max_notional_per_trade_usdt": 0.0,
            "max_margin_required_usdt": 0.0,
            "avg_notional_pct_of_capital": 0.0,
            "avg_margin_pct_of_capital": 0.0,
            "max_notional_pct_of_capital": 0.0,
            "max_margin_pct_of_capital": 0.0,
            "time_in_market_share": 0.0,
            "time_weighted_notional_usage_pct": 0.0,
            "time_weighted_margin_usage_pct": 0.0,
            "capital_idle_share_proxy": 1.0,
            "notional_capped_share": float(notes_series.apply(_contains_notional_cap).mean())
            if not notes_series.empty
            else 0.0,
        }

    df = trades_df.copy()
    entry_price = pd.to_numeric(df["entry_price"], errors="coerce").fillna(0.0)
    size_qty = pd.to_numeric(df["size_qty"], errors="coerce").fillna(0.0)
    leverage = pd.to_numeric(df["leverage"], errors="coerce").replace(0, pd.NA).fillna(1.0)
    exit_index = (
        pd.to_numeric(df["exit_index"], errors="coerce").fillna(0).astype(int).clip(lower=0)
    )
    duration_bars = exit_index + 1

    notional_usdt = entry_price * size_qty
    margin_required_usdt = notional_usdt / leverage

    total_duration_bars = float(duration_bars.sum())
    denominator_bars = float(max(market_rows, 1))

    time_weighted_notional_usage_pct = float(
        (notional_usdt * duration_bars).sum() / (initial_capital * denominator_bars)
    )
    time_weighted_margin_usage_pct = float(
        (margin_required_usdt * duration_bars).sum()
        / (initial_capital * denominator_bars)
    )

    notes_series = df["notes"].astype(str) if "notes" in df.columns else pd.Series(dtype=str)

    return {
        "avg_notional_per_trade_usdt": float(notional_usdt.mean()),
        "avg_margin_required_usdt": float(margin_required_usdt.mean()),
        "max_notional_per_trade_usdt": float(notional_usdt.max()),
        "max_margin_required_usdt": float(margin_required_usdt.max()),
        "avg_notional_pct_of_capital": float(notional_usdt.mean() / initial_capital),
        "avg_margin_pct_of_capital": float(margin_required_usdt.mean() / initial_capital),
        "max_notional_pct_of_capital": float(notional_usdt.max() / initial_capital),
        "max_margin_pct_of_capital": float(margin_required_usdt.max() / initial_capital),
        "time_in_market_share": float(total_duration_bars / denominator_bars),
        "time_weighted_notional_usage_pct": time_weighted_notional_usage_pct,
        "time_weighted_margin_usage_pct": time_weighted_margin_usage_pct,
        "capital_idle_share_proxy": float(max(0.0, 1.0 - time_weighted_margin_usage_pct)),
        "notional_capped_share": float(notes_series.apply(_contains_notional_cap).mean())
        if not notes_series.empty
        else 0.0,
    }
