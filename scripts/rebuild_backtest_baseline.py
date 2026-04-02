from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.baseline_artifacts import (
    build_run_baseline_payload,
    save_run_baseline_artifacts,
)
from src.backtest.capital_usage import build_capital_usage_metrics
from src.core.config_loader import get_default_config_path, load_config, resolve_project_paths
from src.live.runtime_config import load_runtime_config
from src.risk.risk_engine import get_risk_pct_for_bucket


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconstruye baseline consolidada a partir de outputs existentes de backtest."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Subset de simbolos a incluir. Acepta valores separados por espacio o coma.",
    )
    return parser.parse_args()


def resolve_selected_symbols(
    configured_symbols: list[str],
    requested_symbols: list[str] | None,
) -> list[str]:
    if not requested_symbols:
        return configured_symbols

    requested: list[str] = []
    for raw_value in requested_symbols:
        for symbol in str(raw_value).split(","):
            normalized = symbol.strip().upper()
            if normalized:
                requested.append(normalized)

    invalid = [symbol for symbol in requested if symbol not in configured_symbols]
    if invalid:
        raise ValueError(f"Simbolos no habilitados en config: {', '.join(invalid)}")

    unique_requested: list[str] = []
    for symbol in requested:
        if symbol not in unique_requested:
            unique_requested.append(symbol)
    return unique_requested


def load_symbol_record_from_outputs(
    *,
    symbol: str,
    output_dir: Path,
    raw_data_path: Path,
    initial_capital: float,
) -> dict[str, object]:
    summary_path = output_dir / f"{symbol}_summary.json"
    trades_path = output_dir / f"{symbol}_trades.csv"
    market_path = raw_data_path / f"{symbol}_15m.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"Falta summary para {symbol}: {summary_path}")
    if not trades_path.exists():
        raise FileNotFoundError(f"Falta trades CSV para {symbol}: {trades_path}")
    if not market_path.exists():
        raise FileNotFoundError(f"Falta market data para {symbol}: {market_path}")

    metrics = json.loads(summary_path.read_text(encoding="utf-8"))
    trades_df = pd.read_csv(trades_path)
    market_index = pd.read_csv(market_path, usecols=["timestamp"])

    start = None
    end = None
    rows = int(len(market_index))
    if not market_index.empty:
        start = str(pd.to_datetime(market_index.iloc[0]["timestamp"], utc=True))
        end = str(pd.to_datetime(market_index.iloc[-1]["timestamp"], utc=True))

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


def main() -> None:
    args = parse_cli_args()
    config = load_config(get_default_config_path())
    runtime = load_runtime_config(config)
    paths = resolve_project_paths(config)
    configured_symbols = list(config["symbols"]["enabled"])
    symbols = resolve_selected_symbols(configured_symbols, args.symbols)
    backtest_risk_pct, _notes = get_risk_pct_for_bucket(
        risk_by_score=dict(config["risk"]["risk_by_score"]),
        risk_bucket=runtime.backtest_risk_bucket,
    )

    output_dir = paths["outputs_path"] / "backtests"
    symbol_records = [
        load_symbol_record_from_outputs(
            symbol=symbol,
            output_dir=output_dir,
            raw_data_path=paths["raw_data_path"],
            initial_capital=float(config["capital"]["initial_capital"]),
        )
        for symbol in symbols
    ]

    run_payload = build_run_baseline_payload(
        config=config,
        symbol_records=symbol_records,
        backtest_risk_bucket=runtime.backtest_risk_bucket,
        backtest_risk_pct=backtest_risk_pct,
    )
    artifact_paths = save_run_baseline_artifacts(
        output_dir=output_dir,
        config=config,
        run_payload=run_payload,
    )

    print("Baseline reconstruida.")
    print(f"Config snapshot -> {artifact_paths['config_snapshot_path']}")
    print(f"Baseline summary -> {artifact_paths['baseline_summary_path']}")
    print(f"Baseline symbols CSV -> {artifact_paths['baseline_symbols_path']}")
    print(
        "Portfolio proxy -> "
        f"net_pnl={run_payload['portfolio_proxy']['total_net_pnl_usdt']:.4f} USDT | "
        f"trades={run_payload['portfolio_proxy']['total_trades']}"
    )


if __name__ == "__main__":
    main()
