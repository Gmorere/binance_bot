from __future__ import annotations

import pandas as pd


def build_equity_curve(trades: pd.DataFrame, initial_capital: float = 0.0) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["exit_time", "pnl_net_usdt", "equity"])

    df = trades.copy().astype({"pnl_net_usdt": float})
    df = df.assign(equity=initial_capital + df["pnl_net_usdt"].cumsum())

    return df[["exit_time", "pnl_net_usdt", "equity"]]
