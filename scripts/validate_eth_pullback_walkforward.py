from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from run_backtest import build_signal_fn, load_backtest_strategy_policy
from src.backtest.backtest_runner import BacktestRunner
from src.backtest.baseline_artifacts import build_symbol_baseline_record
from src.backtest.metrics import compute_backtest_metrics
from src.core.config_loader import get_default_config_path, load_config, resolve_project_paths
from src.data.data_loader import load_all_symbols
from src.features.indicators import add_basic_indicators


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida ETH BREAKOUT vs ETH BREAKOUT+PULLBACK por ventanas walk-forward."
    )
    parser.add_argument(
        "--config",
        default="config/research.eth_pullback.yaml",
        help="YAML del laboratorio ETH. Default: config/research.eth_pullback.yaml",
    )
    parser.add_argument(
        "--freq",
        choices=("quarterly", "monthly"),
        default="quarterly",
        help="Granularidad de validacion temporal. Default: quarterly.",
    )
    parser.add_argument(
        "--warmup-days",
        type=int,
        default=30,
        help="Dias previos de warmup antes de cada ventana. Default: 30.",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/eth_pullback_walkforward",
        help="Ruta base de outputs para la validacion.",
    )
    parser.add_argument(
        "--max-periods",
        type=int,
        default=None,
        help="Limita la cantidad de periodos a correr para smoke o debugging.",
    )
    return parser.parse_args()


def build_periods(
    *,
    timestamps: pd.Series,
    freq: str,
) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    if timestamps.empty:
        return []

    start = pd.to_datetime(timestamps.min(), utc=True)
    end = pd.to_datetime(timestamps.max(), utc=True)
    period_freq = "Q" if freq == "quarterly" else "M"
    periods = pd.period_range(start=start, end=end, freq=period_freq)

    results: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []
    for period in periods:
        period_start = pd.Timestamp(period.start_time, tz="UTC")
        period_end = pd.Timestamp(period.end_time, tz="UTC")
        bounded_start = max(period_start, start)
        bounded_end = min(period_end, end)
        if bounded_start > bounded_end:
            continue
        label = str(period)
        results.append((bounded_start, bounded_end, label))

    return results


def _setup_breakdown(trades_df: pd.DataFrame) -> list[dict[str, object]]:
    if trades_df.empty:
        return []

    grouped = (
        trades_df.groupby("setup_type")["pnl_net_usdt"]
        .agg(["count", "sum", "mean"])
        .reset_index()
    )
    return [
        {
            "setup_type": str(row["setup_type"]),
            "count": int(row["count"]),
            "sum": float(row["sum"]),
            "mean": float(row["mean"]),
        }
        for _, row in grouped.iterrows()
    ]


def run_period_variant(
    *,
    config: dict[str, Any],
    symbol: str,
    df_15m: pd.DataFrame,
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    allowed_setups: list[str],
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    warmup_days: int,
    output_dir: Path,
) -> dict[str, object]:
    backtest_policy = load_backtest_strategy_policy(config)
    warmup_start = period_start - pd.Timedelta(days=warmup_days)

    scoped_15m = df_15m[
        (df_15m["timestamp"] >= warmup_start) & (df_15m["timestamp"] <= period_end)
    ].reset_index(drop=True)
    scoped_1h = df_1h[
        (df_1h["timestamp"] >= warmup_start) & (df_1h["timestamp"] <= period_end)
    ].reset_index(drop=True)
    scoped_4h = df_4h[
        (df_4h["timestamp"] >= warmup_start) & (df_4h["timestamp"] <= period_end)
    ].reset_index(drop=True)

    signal_fn = build_signal_fn(
        symbol=symbol,
        capital_usdt=float(config["capital"]["initial_capital"]),
        risk_pct=float(config["risk"]["backtest_by_symbol"][symbol]["risk_pct"]),
        risk_bucket=f"manual_{float(config['risk']['backtest_by_symbol'][symbol]['risk_pct']):.4f}",
        leverage=float(config["leverage"][symbol]),
        max_notional_pct=float(config["position_limits"]["max_notional_pct"][symbol]),
        fee_rate_entry=float(config["execution"]["fee_rate_entry"]),
        fee_rate_exit=float(config["execution"]["fee_rate_exit"]),
        slippage_pct=float(config["execution"]["slippage"].get(symbol, 0.0003)),
        stop_buffer_atr_fraction=float(config["filters"].get("stop_buffer_atr_fraction", 0.10)),
        min_candles=6,
        max_candles=12,
        max_range_atr_multiple=float(
            config["filters"]["by_symbol"][symbol]["max_consolidation_range_atr_multiple"]
        ),
        min_volume_ratio=float(config["filters"]["min_breakout_volume_multiple"]),
        max_trigger_candle_atr_multiple=float(
            config["filters"]["max_trigger_candle_atr_multiple"]
        ),
        allowed_setups=allowed_setups,
        impulse_lookback_candles=int(config["pullback"].get("impulse_lookback_candles", 6)),
        min_pullback_candles=int(config["pullback"].get("min_pullback_candles", 2)),
        max_pullback_candles=int(config["pullback"].get("max_pullback_candles", 5)),
        min_impulse_atr_multiple=float(config["pullback"].get("min_impulse_atr_multiple", 1.8)),
        min_retrace_ratio=float(config["pullback"].get("min_retrace_ratio", 0.25)),
        max_retrace_ratio=float(config["pullback"].get("max_retrace_ratio", 0.60)),
        max_trigger_body_atr_multiple=(
            float(config["pullback"]["max_trigger_body_atr_multiple"])
            if "max_trigger_body_atr_multiple" in config["pullback"]
            else None
        ),
        max_forward_bars=80,
        max_bars_in_trade=int(config["trade_management"]["by_symbol"][symbol]["max_bars_in_trade"]),
        force_close_on_last_candle=True,
        df_1h=scoped_1h if bool(backtest_policy["enabled"]) else None,
        df_4h=scoped_4h if bool(backtest_policy["enabled"]) else None,
        enforce_context_alignment=bool(
            backtest_policy["enabled"] and backtest_policy["enforce_context_alignment"]
        ),
        allowed_sides_by_symbol=(
            dict(backtest_policy["allowed_sides"]) if bool(backtest_policy["enabled"]) else None
        ),
    )

    runner = BacktestRunner(
        symbol=symbol,
        market_df=scoped_15m,
        signal_fn=signal_fn,
        output_dir=str(output_dir),
        initial_capital=float(config["capital"]["initial_capital"]),
        save_outputs=True,
        print_progress=False,
    )
    trades_df, metrics, _equity_curve_df = runner.run()
    trades_df = trades_df.copy()
    if not trades_df.empty:
        trades_df = trades_df.assign(entry_time=pd.to_datetime(trades_df["entry_time"], utc=True))
        trades_df = trades_df[
            (trades_df["entry_time"] >= period_start)
            & (trades_df["entry_time"] <= period_end)
        ].copy()
        metrics = compute_backtest_metrics(trades_df)

    period_market_df = scoped_15m[
        (scoped_15m["timestamp"] >= period_start)
        & (scoped_15m["timestamp"] <= period_end)
    ].copy()
    baseline_record = build_symbol_baseline_record(
        symbol=symbol,
        market_df=period_market_df,
        trades_df=trades_df,
        metrics=metrics,
        initial_capital=float(config["capital"]["initial_capital"]),
    )

    return {
        "total_trades": int(metrics["total_trades"]),
        "net_pnl_usdt": float(metrics["net_pnl_usdt"]),
        "profit_factor": float(metrics["profit_factor"]),
        "expectancy": float(metrics["expectancy"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "time_in_market_share": float(baseline_record.get("time_in_market_share", 0.0)),
        "time_weighted_margin_usage_pct": float(
            baseline_record.get("time_weighted_margin_usage_pct_proxy", 0.0)
        ),
        "setup_breakdown": _setup_breakdown(trades_df),
    }


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path if config_path.is_absolute() else str(config_path))
    paths = resolve_project_paths(config)

    symbol = "ETHUSDT"
    bundle = load_all_symbols(
        raw_data_path=paths["raw_data_path"],
        symbols=[symbol],
        timeframes=("15m", "1h", "4h"),
    )[symbol]
    df_15m = add_basic_indicators(bundle["15m"]).reset_index(drop=True)
    df_1h = add_basic_indicators(bundle["1h"]).reset_index(drop=True)
    df_4h = add_basic_indicators(bundle["4h"]).reset_index(drop=True)

    for df in (df_15m, df_1h, df_4h):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    periods = build_periods(timestamps=df_15m["timestamp"], freq=args.freq)
    if args.max_periods is not None:
        periods = periods[: max(args.max_periods, 0)]
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = (paths["outputs_path"] / output_root.name).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    combo_setups = list(config["strategy"]["allowed_setups_by_symbol"][symbol])
    breakout_only = ["BREAKOUT"]

    results: list[dict[str, object]] = []
    for period_start, period_end, label in periods:
        breakout_dir = output_root / label / "breakout_only" / "backtests"
        combo_dir = output_root / label / "configured_variant" / "backtests"

        breakout_result = run_period_variant(
            config=deepcopy(config),
            symbol=symbol,
            df_15m=df_15m,
            df_1h=df_1h,
            df_4h=df_4h,
            allowed_setups=breakout_only,
            period_start=period_start,
            period_end=period_end,
            warmup_days=args.warmup_days,
            output_dir=breakout_dir,
        )
        combo_result = run_period_variant(
            config=deepcopy(config),
            symbol=symbol,
            df_15m=df_15m,
            df_1h=df_1h,
            df_4h=df_4h,
            allowed_setups=combo_setups,
            period_start=period_start,
            period_end=period_end,
            warmup_days=args.warmup_days,
            output_dir=combo_dir,
        )

        results.append(
            {
                "period": label,
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "breakout_only": breakout_result,
                "configured_variant": combo_result,
                "delta_net_pnl_usdt": float(
                    combo_result["net_pnl_usdt"] - breakout_result["net_pnl_usdt"]
                ),
                "delta_trade_count": int(
                    combo_result["total_trades"] - breakout_result["total_trades"]
                ),
            }
        )

    (output_root / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# ETH Pullback Walk-Forward",
        "",
        f"- config: {config_path}",
        f"- freq: {args.freq}",
        f"- warmup_days: {args.warmup_days}",
        "",
    ]
    for row in results:
        lines.append(f"## {row['period']}")
        lines.append(f"- start: {row['start']}")
        lines.append(f"- end: {row['end']}")
        lines.append(
            f"- breakout_only: trades={row['breakout_only']['total_trades']}, "
            f"net_pnl={row['breakout_only']['net_pnl_usdt']:.4f}, "
            f"pf={row['breakout_only']['profit_factor']:.4f}"
        )
        lines.append(
            f"- configured_variant: trades={row['configured_variant']['total_trades']}, "
            f"net_pnl={row['configured_variant']['net_pnl_usdt']:.4f}, "
            f"pf={row['configured_variant']['profit_factor']:.4f}"
        )
        lines.append(f"- delta_net_pnl_usdt: {row['delta_net_pnl_usdt']:.4f}")
        lines.append(f"- delta_trade_count: {row['delta_trade_count']}")
        lines.append("")

    (output_root / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"JSON -> {output_root / 'results.json'}")
    print(f"MD -> {output_root / 'results.md'}")


if __name__ == "__main__":
    main()
