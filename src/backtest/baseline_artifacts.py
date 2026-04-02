from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from src.backtest.capital_usage import build_capital_usage_metrics


def build_symbol_baseline_record(
    *,
    symbol: str,
    market_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    metrics: Mapping[str, Any],
    initial_capital: float,
) -> dict[str, Any]:
    start = None
    end = None
    rows = int(len(market_df))
    if not market_df.empty and "timestamp" in market_df.columns:
        start = str(pd.to_datetime(market_df.iloc[0]["timestamp"], utc=True))
        end = str(pd.to_datetime(market_df.iloc[-1]["timestamp"], utc=True))

    capital_usage = build_capital_usage_metrics(
        trades_df=trades_df,
        initial_capital=initial_capital,
        market_rows=rows,
    )

    return {
        "symbol": symbol,
        "rows": rows,
        "start": start,
        "end": end,
        "total_trades": int(metrics.get("total_trades", 0)),
        "closed_trades": int(metrics.get("closed_trades", 0)),
        "open_trades": int(metrics.get("open_trades", 0)),
        "win_rate": float(metrics.get("win_rate", 0.0)),
        "profit_factor": float(metrics.get("profit_factor", 0.0)),
        "expectancy": float(metrics.get("expectancy", 0.0)),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
        "net_pnl_usdt": float(metrics.get("net_pnl_usdt", 0.0)),
        "gross_profit_usdt": float(metrics.get("gross_profit_usdt", 0.0)),
        "gross_loss_usdt": float(metrics.get("gross_loss_usdt", 0.0)),
        "avg_win": float(metrics.get("avg_win", 0.0)),
        "avg_loss": float(metrics.get("avg_loss", 0.0)),
        "stop_loss_rate": float(metrics.get("stop_loss_rate", 0.0)),
        "tp2_rate": float(metrics.get("tp2_rate", 0.0)),
        "timeout_rate": float(metrics.get("timeout_rate", 0.0)),
        "end_of_data_rate": float(metrics.get("end_of_data_rate", 0.0)),
        "trade_rows_exported": int(len(trades_df)),
        **capital_usage,
    }


def build_portfolio_proxy_summary(
    *,
    symbol_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not symbol_records:
        return {
            "symbol_count": 0,
            "total_trades": 0,
            "total_closed_trades": 0,
            "total_open_trades": 0,
            "total_net_pnl_usdt": 0.0,
            "total_gross_profit_usdt": 0.0,
            "total_gross_loss_usdt": 0.0,
            "average_win_rate": 0.0,
            "best_symbol_by_net_pnl": None,
            "worst_symbol_by_net_pnl": None,
            "aggregate_time_in_market_share_proxy": 0.0,
            "aggregate_time_weighted_notional_usage_pct_proxy": 0.0,
            "aggregate_time_weighted_margin_usage_pct_proxy": 0.0,
            "aggregate_capital_idle_share_proxy": 1.0,
        }

    records = list(symbol_records)
    best_symbol = max(records, key=lambda item: float(item["net_pnl_usdt"]))
    worst_symbol = min(records, key=lambda item: float(item["net_pnl_usdt"]))

    return {
        "symbol_count": int(len(records)),
        "total_trades": int(sum(int(item["total_trades"]) for item in records)),
        "total_closed_trades": int(sum(int(item["closed_trades"]) for item in records)),
        "total_open_trades": int(sum(int(item["open_trades"]) for item in records)),
        "total_net_pnl_usdt": float(sum(float(item["net_pnl_usdt"]) for item in records)),
        "total_gross_profit_usdt": float(
            sum(float(item["gross_profit_usdt"]) for item in records)
        ),
        "total_gross_loss_usdt": float(
            sum(float(item["gross_loss_usdt"]) for item in records)
        ),
        "average_win_rate": float(
            sum(float(item["win_rate"]) for item in records) / len(records)
        ),
        "best_symbol_by_net_pnl": str(best_symbol["symbol"]),
        "worst_symbol_by_net_pnl": str(worst_symbol["symbol"]),
        "aggregate_time_in_market_share_proxy": float(
            sum(float(item.get("time_in_market_share", 0.0)) for item in records)
        ),
        "aggregate_time_weighted_notional_usage_pct_proxy": float(
            sum(float(item.get("time_weighted_notional_usage_pct", 0.0)) for item in records)
        ),
        "aggregate_time_weighted_margin_usage_pct_proxy": float(
            sum(float(item.get("time_weighted_margin_usage_pct", 0.0)) for item in records)
        ),
        "aggregate_capital_idle_share_proxy": float(
            max(
                0.0,
                1.0
                - sum(
                    float(item.get("time_weighted_margin_usage_pct", 0.0))
                    for item in records
                ),
            )
        ),
    }


def build_run_baseline_payload(
    *,
    config: Mapping[str, Any],
    symbol_records: Sequence[Mapping[str, Any]],
    backtest_risk_bucket: str,
    backtest_risk_pct: float,
) -> dict[str, Any]:
    portfolio_summary = build_portfolio_proxy_summary(symbol_records=symbol_records)
    strategy_cfg = dict(config.get("strategy", {}))
    dynamic_risk_cfg = dict(strategy_cfg.get("dynamic_risk_by_score", {}))

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_name": str(config["project"]["name"]),
        "project_version": str(config["project"]["version"]),
        "runtime_mode": str(config["runtime"]["mode"]),
        "entry_timeframe": str(config["timeframes"]["entry"]),
        "enabled_symbols": list(config["symbols"]["enabled"]),
        "initial_capital": float(config["capital"]["initial_capital"]),
        "quote_asset": str(config["capital"]["quote_asset"]),
        "backtest_risk_bucket": str(backtest_risk_bucket),
        "backtest_risk_pct": float(backtest_risk_pct),
        "dynamic_risk_by_score_enabled": bool(dynamic_risk_cfg.get("enabled", False)),
        "portfolio_proxy": portfolio_summary,
        "symbols": list(symbol_records),
    }


def sanitize_config_for_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(dict(config))
    snapshot.pop("_meta", None)
    return snapshot


def save_run_baseline_artifacts(
    *,
    output_dir: str | Path,
    config: Mapping[str, Any],
    run_payload: Mapping[str, Any],
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    config_snapshot_path = destination / "config_snapshot.json"
    baseline_summary_path = destination / "baseline_summary.json"
    baseline_symbols_path = destination / "baseline_symbols.csv"

    config_snapshot = sanitize_config_for_snapshot(config)
    config_snapshot_path.write_text(
        json.dumps(config_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    baseline_summary_path.write_text(
        json.dumps(dict(run_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    symbol_rows = list(run_payload.get("symbols", []))
    pd.DataFrame(symbol_rows).to_csv(baseline_symbols_path, index=False)

    return {
        "config_snapshot_path": config_snapshot_path,
        "baseline_summary_path": baseline_summary_path,
        "baseline_symbols_path": baseline_symbols_path,
    }
