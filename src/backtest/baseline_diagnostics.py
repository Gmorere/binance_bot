from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


def _safe_float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _build_group_stats(df: pd.DataFrame, group_col: str) -> list[dict[str, Any]]:
    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    grouped = df.groupby(group_col, dropna=False)
    for group_value, group_df in grouped:
        pnl = group_df["pnl_net_usdt"].astype(float)
        rows.append(
            {
                group_col: str(group_value),
                "trade_count": int(len(group_df)),
                "win_rate": float((pnl > 0).mean()) if len(group_df) else 0.0,
                "expectancy": float(pnl.mean()) if len(group_df) else 0.0,
                "net_pnl_usdt": float(pnl.sum()),
                "gross_profit_usdt": float(pnl[pnl > 0].sum()) if len(group_df) else 0.0,
                "gross_loss_usdt": float(abs(pnl[pnl < 0].sum())) if len(group_df) else 0.0,
            }
        )

    rows.sort(key=lambda item: item["net_pnl_usdt"])
    return rows


def _contains_notional_cap(notes: str | None) -> bool:
    if not notes:
        return False
    return "notional calculado supera" in str(notes).lower()


def build_symbol_diagnostic(
    symbol: str,
    trades_df: pd.DataFrame,
    baseline_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    capital_usage = dict(baseline_record or {})

    if trades_df.empty:
        return {
            "symbol": symbol,
            "trade_count": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "net_pnl_usdt": 0.0,
            "profit_factor": 0.0,
            "stop_loss_share": 0.0,
            "timeout_share": 0.0,
            "tp2_share": 0.0,
            "notional_capped_share": 0.0,
            "avg_notional_pct_of_capital": float(capital_usage.get("avg_notional_pct_of_capital", 0.0)),
            "avg_margin_pct_of_capital": float(capital_usage.get("avg_margin_pct_of_capital", 0.0)),
            "time_in_market_share": float(capital_usage.get("time_in_market_share", 0.0)),
            "time_weighted_notional_usage_pct": float(capital_usage.get("time_weighted_notional_usage_pct", 0.0)),
            "time_weighted_margin_usage_pct": float(capital_usage.get("time_weighted_margin_usage_pct", 0.0)),
            "capital_idle_share_proxy": float(capital_usage.get("capital_idle_share_proxy", 1.0)),
            "by_exit_reason": [],
            "by_side": [],
        }

    df = trades_df.copy()
    pnl = df["pnl_net_usdt"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = float(abs(losses.sum())) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999999.0

    exit_reason = df["exit_reason"].astype(str)
    notes_series = df["notes"].astype(str) if "notes" in df.columns else pd.Series(dtype=str)

    return {
        "symbol": symbol,
        "trade_count": int(len(df)),
        "win_rate": float((pnl > 0).mean()),
        "expectancy": float(pnl.mean()),
        "net_pnl_usdt": float(pnl.sum()),
        "profit_factor": float(profit_factor),
        "stop_loss_share": float((exit_reason == "STOP_LOSS").mean()),
        "timeout_share": float((exit_reason == "TIMEOUT").mean()),
        "tp2_share": float((exit_reason == "TP2").mean()),
        "notional_capped_share": float(notes_series.apply(_contains_notional_cap).mean())
        if not notes_series.empty
        else 0.0,
        "avg_notional_pct_of_capital": float(capital_usage.get("avg_notional_pct_of_capital", 0.0)),
        "avg_margin_pct_of_capital": float(capital_usage.get("avg_margin_pct_of_capital", 0.0)),
        "time_in_market_share": float(capital_usage.get("time_in_market_share", 0.0)),
        "time_weighted_notional_usage_pct": float(capital_usage.get("time_weighted_notional_usage_pct", 0.0)),
        "time_weighted_margin_usage_pct": float(capital_usage.get("time_weighted_margin_usage_pct", 0.0)),
        "capital_idle_share_proxy": float(capital_usage.get("capital_idle_share_proxy", 1.0)),
        "by_exit_reason": _build_group_stats(df, "exit_reason"),
        "by_side": _build_group_stats(df, "side"),
    }


def build_portfolio_diagnostic(symbol_diagnostics: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(symbol_diagnostics)
    if not records:
        return {
            "symbol_count": 0,
            "worst_expectancy_symbol": None,
            "best_expectancy_symbol": None,
            "highest_timeout_share_symbol": None,
            "highest_stop_loss_share_symbol": None,
            "highest_notional_capped_share_symbol": None,
        }

    worst_expectancy = min(records, key=lambda item: _safe_float(item["expectancy"]))
    best_expectancy = max(records, key=lambda item: _safe_float(item["expectancy"]))
    highest_timeout = max(records, key=lambda item: _safe_float(item["timeout_share"]))
    highest_stop = max(records, key=lambda item: _safe_float(item["stop_loss_share"]))
    highest_cap = max(records, key=lambda item: _safe_float(item["notional_capped_share"]))

    return {
        "symbol_count": int(len(records)),
        "worst_expectancy_symbol": str(worst_expectancy["symbol"]),
        "best_expectancy_symbol": str(best_expectancy["symbol"]),
        "highest_timeout_share_symbol": str(highest_timeout["symbol"]),
        "highest_stop_loss_share_symbol": str(highest_stop["symbol"]),
        "highest_notional_capped_share_symbol": str(highest_cap["symbol"]),
    }


def load_trades_by_symbol(output_dir: str | Path, symbols: Iterable[str]) -> dict[str, pd.DataFrame]:
    destination = Path(output_dir)
    results: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        trades_path = destination / f"{symbol}_trades.csv"
        if not trades_path.exists():
            raise FileNotFoundError(f"Falta trades CSV para {symbol}: {trades_path}")
        results[symbol] = pd.read_csv(trades_path)
    return results


def render_markdown_report(
    *,
    baseline_summary: Mapping[str, Any],
    symbol_diagnostics: Iterable[Mapping[str, Any]],
    portfolio_diagnostic: Mapping[str, Any],
) -> str:
    lines: list[str] = []
    proxy = dict(baseline_summary.get("portfolio_proxy", {}))
    lines.append("# Backtest Baseline Diagnostic")
    lines.append("")
    lines.append("## Portfolio")
    lines.append(
        f"- symbols: {proxy.get('symbol_count', 0)} | trades: {proxy.get('total_trades', 0)} | "
        f"net_pnl_usdt: {proxy.get('total_net_pnl_usdt', 0.0):.4f}"
    )
    lines.append(
        f"- average_win_rate: {proxy.get('average_win_rate', 0.0):.2%} | "
        f"best_symbol: {proxy.get('best_symbol_by_net_pnl')} | "
        f"worst_symbol: {proxy.get('worst_symbol_by_net_pnl')}"
    )
    lines.append(
        f"- aggregate_time_in_market_share_proxy: {proxy.get('aggregate_time_in_market_share_proxy', 0.0):.2%} | "
        f"aggregate_time_weighted_margin_usage_pct_proxy: "
        f"{proxy.get('aggregate_time_weighted_margin_usage_pct_proxy', 0.0):.2%} | "
        f"aggregate_capital_idle_share_proxy: {proxy.get('aggregate_capital_idle_share_proxy', 1.0):.2%}"
    )
    lines.append(
        f"- worst_expectancy_symbol: {portfolio_diagnostic.get('worst_expectancy_symbol')} | "
        f"highest_timeout_share_symbol: {portfolio_diagnostic.get('highest_timeout_share_symbol')} | "
        f"highest_notional_capped_share_symbol: {portfolio_diagnostic.get('highest_notional_capped_share_symbol')}"
    )
    lines.append("")

    for symbol_diag in symbol_diagnostics:
        lines.append(f"## {symbol_diag['symbol']}")
        lines.append(
            f"- trades: {symbol_diag['trade_count']} | net_pnl_usdt: {symbol_diag['net_pnl_usdt']:.4f} | "
            f"expectancy: {symbol_diag['expectancy']:.4f} | win_rate: {symbol_diag['win_rate']:.2%} | "
            f"profit_factor: {symbol_diag['profit_factor']:.4f}"
        )
        lines.append(
            f"- stop_loss_share: {symbol_diag['stop_loss_share']:.2%} | "
            f"timeout_share: {symbol_diag['timeout_share']:.2%} | "
            f"tp2_share: {symbol_diag['tp2_share']:.2%} | "
            f"notional_capped_share: {symbol_diag['notional_capped_share']:.2%}"
        )
        lines.append(
            f"- avg_notional_pct_of_capital: {symbol_diag.get('avg_notional_pct_of_capital', 0.0):.2%} | "
            f"avg_margin_pct_of_capital: {symbol_diag.get('avg_margin_pct_of_capital', 0.0):.2%} | "
            f"time_in_market_share: {symbol_diag.get('time_in_market_share', 0.0):.2%}"
        )
        lines.append(
            f"- time_weighted_notional_usage_pct: {symbol_diag.get('time_weighted_notional_usage_pct', 0.0):.2%} | "
            f"time_weighted_margin_usage_pct: {symbol_diag.get('time_weighted_margin_usage_pct', 0.0):.2%} | "
            f"capital_idle_share_proxy: {symbol_diag.get('capital_idle_share_proxy', 1.0):.2%}"
        )
        lines.append("- by_exit_reason:")
        for row in symbol_diag["by_exit_reason"]:
            lines.append(
                f"  - {row['exit_reason']}: trades={row['trade_count']} "
                f"net={row['net_pnl_usdt']:.4f} expectancy={row['expectancy']:.4f}"
            )
        lines.append("- by_side:")
        for row in symbol_diag["by_side"]:
            lines.append(
                f"  - {row['side']}: trades={row['trade_count']} "
                f"net={row['net_pnl_usdt']:.4f} expectancy={row['expectancy']:.4f}"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def save_diagnostic_artifacts(
    *,
    output_dir: str | Path,
    baseline_summary: Mapping[str, Any],
    symbol_diagnostics: list[Mapping[str, Any]],
    portfolio_diagnostic: Mapping[str, Any],
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    payload = {
        "baseline_summary_meta": {
            "generated_at_utc": baseline_summary.get("generated_at_utc"),
            "backtest_risk_bucket": baseline_summary.get("backtest_risk_bucket"),
            "backtest_risk_pct": baseline_summary.get("backtest_risk_pct"),
        },
        "portfolio_diagnostic": dict(portfolio_diagnostic),
        "symbols": symbol_diagnostics,
    }

    json_path = destination / "baseline_diagnostic.json"
    md_path = destination / "baseline_diagnostic.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown_report(
            baseline_summary=baseline_summary,
            symbol_diagnostics=symbol_diagnostics,
            portfolio_diagnostic=portfolio_diagnostic,
        ),
        encoding="utf-8",
    )

    return {"json_path": json_path, "md_path": md_path}
