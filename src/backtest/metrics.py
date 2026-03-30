from __future__ import annotations

import math
import pandas as pd


def compute_backtest_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "total_trades": 0,
            "closed_trades": 0,
            "open_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "net_pnl_usdt": 0.0,
            "gross_profit_usdt": 0.0,
            "gross_loss_usdt": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "stop_loss_rate": 0.0,
            "tp2_rate": 0.0,
            "timeout_rate": 0.0,
            "end_of_data_rate": 0.0,
        }

    df = trades.copy()
    pnl = df["pnl_net_usdt"].astype(float)

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = float(abs(losses.sum())) if not losses.empty else 0.0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else math.inf
    win_rate = float((pnl > 0).mean()) if len(df) > 0 else 0.0
    expectancy = float(pnl.mean()) if len(df) > 0 else 0.0

    equity = pnl.cumsum()
    rolling_max = equity.cummax()
    drawdown = equity - rolling_max
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    exit_reason = df["exit_reason"].astype(str)

    return {
        "total_trades": int(len(df)),
        "closed_trades": int(df["trade_closed"].sum()) if "trade_closed" in df.columns else int(len(df)),
        "open_trades": int((~df["trade_closed"]).sum()) if "trade_closed" in df.columns else 0,
        "win_rate": win_rate,
        "profit_factor": float(profit_factor if math.isfinite(profit_factor) else 999999.0),
        "expectancy": expectancy,
        "max_drawdown": max_drawdown,
        "net_pnl_usdt": float(pnl.sum()),
        "gross_profit_usdt": gross_profit,
        "gross_loss_usdt": gross_loss,
        "avg_win": float(wins.mean()) if not wins.empty else 0.0,
        "avg_loss": float(losses.mean()) if not losses.empty else 0.0,
        "stop_loss_rate": float((exit_reason == "STOP_LOSS").mean()),
        "tp2_rate": float((exit_reason == "TP2").mean()),
        "timeout_rate": float((exit_reason == "TIMEOUT").mean()),
        "end_of_data_rate": float((exit_reason == "END_OF_DATA").mean()),
    }