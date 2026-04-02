from __future__ import annotations

import argparse
from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_backtest import (  # noqa: E402
    build_signal_fn,
    load_backtest_strategy_policy,
    resolve_symbol_backtest_risk,
    resolve_symbol_allowed_setups,
    resolve_symbol_filters,
    resolve_pullback_settings,
    resolve_symbol_trade_management,
    resolve_selected_symbols,
)
from src.backtest.backtest_runner import BacktestRunner  # noqa: E402
from src.backtest.baseline_artifacts import (  # noqa: E402
    build_run_baseline_payload,
    build_symbol_baseline_record,
    save_run_baseline_artifacts,
)
from src.backtest.baseline_diagnostics import (  # noqa: E402
    build_portfolio_diagnostic,
    build_symbol_diagnostic,
    save_diagnostic_artifacts,
)
from src.core.config_loader import (  # noqa: E402
    get_default_config_path,
    load_config,
    resolve_project_paths,
)
from src.data.data_loader import load_all_symbols  # noqa: E402
from src.features.indicators import add_basic_indicators  # noqa: E402
from src.live.runtime_config import load_runtime_config  # noqa: E402
from src.risk.risk_engine import get_risk_pct_for_bucket  # noqa: E402


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Corre una grilla de experimentos de filtros sobre el backtest."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Ruta del YAML a usar. Default: BOT_CONFIG_PATH o config/base.yaml.",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Nombre corto del lote de experimentos.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Subset de simbolos a correr. Acepta valores separados por espacio o coma.",
    )
    parser.add_argument(
        "--output-root",
        default="experiments",
        help="Subdirectorio bajo outputs/ donde se guardaran los resultados.",
    )
    parser.add_argument(
        "--min-volume-values",
        default="1.0",
        help="Lista separada por coma para filters.min_breakout_volume_multiple.",
    )
    parser.add_argument(
        "--max-range-values",
        default="1.2",
        help="Lista separada por coma para filters.max_consolidation_range_atr_multiple.",
    )
    parser.add_argument(
        "--max-trigger-values",
        default="1.8",
        help="Lista separada por coma para filters.max_trigger_candle_atr_multiple.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce logs del runner por experimento.",
    )
    return parser.parse_args()


def parse_float_grid(raw_value: str) -> list[float]:
    values: list[float] = []
    for item in str(raw_value).split(","):
        normalized = item.strip()
        if not normalized:
            continue
        values.append(float(normalized))

    if not values:
        raise ValueError("La grilla de filtros no puede quedar vacia.")
    return values


def build_experiment_label(
    *,
    min_volume_ratio: float,
    max_range_atr_multiple: float,
    max_trigger_candle_atr_multiple: float,
) -> str:
    raw_label = (
        f"vol_{min_volume_ratio:.2f}_"
        f"range_{max_range_atr_multiple:.2f}_"
        f"trigger_{max_trigger_candle_atr_multiple:.2f}"
    )
    return raw_label.replace(".", "p")


def _resolve_output_root(base_outputs_path: Path, output_root: str, name: str) -> Path:
    candidate = Path(output_root).expanduser()
    if candidate.is_absolute():
        return (candidate / name).resolve()
    return (base_outputs_path / candidate / name).resolve()


def main() -> None:
    args = parse_cli_args()
    config_path = Path(args.config) if args.config else get_default_config_path()
    config = load_config(config_path)
    runtime = load_runtime_config(config)
    paths = resolve_project_paths(config)
    backtest_policy = load_backtest_strategy_policy(config)

    configured_symbols = list(config["symbols"]["enabled"])
    symbols = resolve_selected_symbols(
        configured_symbols,
        args.symbols,
        excluded_symbols=list(backtest_policy["excluded_symbols"]),
    )
    backtest_risk_pct, _risk_notes = get_risk_pct_for_bucket(
        risk_by_score=dict(config["risk"]["risk_by_score"]),
        risk_bucket=runtime.backtest_risk_bucket,
    )

    min_volume_values = parse_float_grid(args.min_volume_values)
    max_range_values = parse_float_grid(args.max_range_values)
    max_trigger_values = parse_float_grid(args.max_trigger_values)
    combinations = list(
        itertools.product(min_volume_values, max_range_values, max_trigger_values)
    )

    experiment_root = _resolve_output_root(
        base_outputs_path=paths["outputs_path"],
        output_root=args.output_root,
        name=args.name,
    )
    experiment_root.mkdir(parents=True, exist_ok=True)

    print(f"Config: {config_path}")
    print(f"Experimento: {args.name}")
    print(f"Simbolos: {symbols}")
    print(f"Combinaciones: {len(combinations)}")
    print(f"Output root: {experiment_root}")

    raw_data = load_all_symbols(
        raw_data_path=paths["raw_data_path"],
        symbols=symbols,
        timeframes=("15m", "1h", "4h"),
    )
    enriched_data = {
        symbol: {
            timeframe: add_basic_indicators(df).reset_index(drop=True)
            for timeframe, df in bundle.items()
        }
        for symbol, bundle in raw_data.items()
    }

    results: list[dict[str, object]] = []
    initial_capital = float(config["capital"]["initial_capital"])

    for index, combination in enumerate(combinations, start=1):
        min_volume_ratio, max_range_atr_multiple, max_trigger_candle_atr_multiple = combination
        label = build_experiment_label(
            min_volume_ratio=min_volume_ratio,
            max_range_atr_multiple=max_range_atr_multiple,
            max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
        )
        variant_output_base = (experiment_root / label).resolve()
        variant_backtests_dir = variant_output_base / "backtests"

        variant_config = deepcopy(config)
        variant_config["filters"]["min_breakout_volume_multiple"] = min_volume_ratio
        variant_config["filters"]["max_consolidation_range_atr_multiple"] = (
            max_range_atr_multiple
        )
        variant_config["filters"]["max_trigger_candle_atr_multiple"] = (
            max_trigger_candle_atr_multiple
        )
        variant_config["data"]["outputs_path"] = str(variant_output_base)

        print(f"\n[{index}/{len(combinations)}] {label}")

        symbol_records: list[dict[str, object]] = []
        trades_by_symbol: dict[str, pd.DataFrame] = {}

        for symbol in symbols:
            bundle = enriched_data[symbol]
            symbol_filters = resolve_symbol_filters(
                variant_config,
                symbol,
                overrides={
                    "min_breakout_volume_multiple": min_volume_ratio,
                    "max_consolidation_range_atr_multiple": max_range_atr_multiple,
                    "max_trigger_candle_atr_multiple": max_trigger_candle_atr_multiple,
                },
            )
            symbol_trade_management = resolve_symbol_trade_management(
                variant_config,
                symbol,
            )
            symbol_risk_pct, symbol_risk_bucket = resolve_symbol_backtest_risk(
                variant_config,
                symbol,
                backtest_risk_pct,
                runtime.backtest_risk_bucket,
            )
            symbol_allowed_setups = resolve_symbol_allowed_setups(
                variant_config,
                symbol,
            )
            pullback_settings = resolve_pullback_settings(
                variant_config,
                symbol,
            )
            signal_fn = build_signal_fn(
                symbol=symbol,
                capital_usdt=initial_capital,
                risk_pct=symbol_risk_pct,
                risk_bucket=symbol_risk_bucket,
                leverage=float(config["leverage"][symbol]),
                max_notional_pct=float(config["position_limits"]["max_notional_pct"][symbol]),
                fee_rate_entry=float(config["execution"]["fee_rate_entry"]),
                fee_rate_exit=float(config["execution"]["fee_rate_exit"]),
                min_candles=6,
                max_candles=12,
                max_range_atr_multiple=float(
                    symbol_filters["max_consolidation_range_atr_multiple"]
                ),
                min_volume_ratio=float(symbol_filters["min_breakout_volume_multiple"]),
                max_trigger_candle_atr_multiple=float(
                    symbol_filters["max_trigger_candle_atr_multiple"]
                ),
                allowed_setups=symbol_allowed_setups,
                impulse_lookback_candles=int(
                    pullback_settings.get("impulse_lookback_candles", 6)
                ),
                min_pullback_candles=int(
                    pullback_settings.get("min_pullback_candles", 2)
                ),
                max_pullback_candles=int(
                    pullback_settings.get("max_pullback_candles", 5)
                ),
                min_impulse_atr_multiple=float(
                    pullback_settings.get("min_impulse_atr_multiple", 1.8)
                ),
                min_retrace_ratio=float(
                    pullback_settings.get("min_retrace_ratio", 0.25)
                ),
                max_retrace_ratio=float(
                    pullback_settings.get("max_retrace_ratio", 0.60)
                ),
                max_trigger_body_atr_multiple=(
                    float(pullback_settings["max_trigger_body_atr_multiple"])
                    if "max_trigger_body_atr_multiple" in pullback_settings
                    else None
                ),
                max_forward_bars=80,
                max_bars_in_trade=int(symbol_trade_management["max_bars_in_trade"]),
                force_close_on_last_candle=True,
                df_1h=bundle["1h"] if bool(backtest_policy["enabled"]) else None,
                df_4h=bundle["4h"] if bool(backtest_policy["enabled"]) else None,
                enforce_context_alignment=bool(
                    backtest_policy["enabled"]
                    and backtest_policy["enforce_context_alignment"]
                ),
                allowed_sides_by_symbol=(
                    dict(backtest_policy["allowed_sides"])
                    if bool(backtest_policy["enabled"])
                    else None
                ),
            )

            runner = BacktestRunner(
                symbol=symbol,
                market_df=bundle["15m"],
                signal_fn=signal_fn,
                output_dir=str(variant_backtests_dir),
                initial_capital=initial_capital,
                save_outputs=True,
                print_progress=not args.quiet,
            )
            trades_df, metrics, _equity_curve_df = runner.run()
            trades_by_symbol[symbol] = trades_df
            symbol_records.append(
                build_symbol_baseline_record(
                    symbol=symbol,
                    market_df=bundle["15m"],
                    trades_df=trades_df,
                    metrics=metrics,
                    initial_capital=initial_capital,
                )
            )

        run_payload = build_run_baseline_payload(
            config=variant_config,
            symbol_records=symbol_records,
            backtest_risk_bucket=runtime.backtest_risk_bucket,
            backtest_risk_pct=backtest_risk_pct,
        )
        save_run_baseline_artifacts(
            output_dir=variant_backtests_dir,
            config=variant_config,
            run_payload=run_payload,
        )

        baseline_records_by_symbol = {item["symbol"]: item for item in symbol_records}
        symbol_diagnostics = [
            build_symbol_diagnostic(
                symbol,
                trades_by_symbol[symbol],
                baseline_record=baseline_records_by_symbol.get(symbol),
            )
            for symbol in symbols
        ]
        portfolio_diagnostic = build_portfolio_diagnostic(symbol_diagnostics)
        save_diagnostic_artifacts(
            output_dir=variant_backtests_dir,
            baseline_summary=run_payload,
            symbol_diagnostics=symbol_diagnostics,
            portfolio_diagnostic=portfolio_diagnostic,
        )

        proxy = dict(run_payload["portfolio_proxy"])
        gross_loss = float(proxy.get("total_gross_loss_usdt", 0.0))
        portfolio_profit_factor = (
            float(proxy.get("total_gross_profit_usdt", 0.0)) / gross_loss
            if gross_loss > 0
            else 999999.0
        )

        results.append(
            {
                "label": label,
                "symbols": ",".join(symbols),
                "min_breakout_volume_multiple": min_volume_ratio,
                "max_consolidation_range_atr_multiple": max_range_atr_multiple,
                "max_trigger_candle_atr_multiple": max_trigger_candle_atr_multiple,
                "symbol_count": int(proxy.get("symbol_count", 0)),
                "total_trades": int(proxy.get("total_trades", 0)),
                "total_net_pnl_usdt": float(proxy.get("total_net_pnl_usdt", 0.0)),
                "return_on_capital_pct": float(
                    proxy.get("total_net_pnl_usdt", 0.0) / initial_capital
                ),
                "portfolio_profit_factor_proxy": float(portfolio_profit_factor),
                "average_win_rate": float(proxy.get("average_win_rate", 0.0)),
                "aggregate_time_in_market_share_proxy": float(
                    proxy.get("aggregate_time_in_market_share_proxy", 0.0)
                ),
                "aggregate_time_weighted_notional_usage_pct_proxy": float(
                    proxy.get("aggregate_time_weighted_notional_usage_pct_proxy", 0.0)
                ),
                "aggregate_time_weighted_margin_usage_pct_proxy": float(
                    proxy.get("aggregate_time_weighted_margin_usage_pct_proxy", 0.0)
                ),
                "aggregate_capital_idle_share_proxy": float(
                    proxy.get("aggregate_capital_idle_share_proxy", 1.0)
                ),
                "best_symbol_by_net_pnl": proxy.get("best_symbol_by_net_pnl"),
                "worst_symbol_by_net_pnl": proxy.get("worst_symbol_by_net_pnl"),
                "output_dir": str(variant_backtests_dir),
            }
        )

    results.sort(key=lambda item: float(item["total_net_pnl_usdt"]), reverse=True)
    results_df = pd.DataFrame(results)
    results_csv_path = experiment_root / "experiment_results.csv"
    results_json_path = experiment_root / "experiment_results.json"
    results_df.to_csv(results_csv_path, index=False)
    results_json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nExperimentos finalizados.")
    print(f"CSV -> {results_csv_path}")
    print(f"JSON -> {results_json_path}")
    if not results_df.empty:
        print("\nTop 5:")
        preview_cols = [
            "label",
            "total_trades",
            "total_net_pnl_usdt",
            "return_on_capital_pct",
            "portfolio_profit_factor_proxy",
            "aggregate_time_weighted_margin_usage_pct_proxy",
            "aggregate_capital_idle_share_proxy",
        ]
        print(results_df[preview_cols].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
