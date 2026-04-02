from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from src.backtest.baseline_artifacts import (
    build_run_baseline_payload,
    build_symbol_baseline_record,
    save_run_baseline_artifacts,
)
from src.backtest.backtest_runner import BacktestRunner
from src.backtest.signal_builder import build_breakout_signal_for_index
from src.core.config_loader import (
    ensure_project_directories,
    get_default_config_path,
    load_config,
    resolve_project_paths,
)
from src.data.data_loader import load_all_symbols, summarize_dataframe
from src.features.indicators import add_basic_indicators
from src.live.runtime_config import load_runtime_config
from src.risk.risk_engine import get_risk_pct_for_bucket
from src.strategy.context_policy import evaluate_trade_candidate_policy
from src.strategy.scoring_policy import (
    CandidateRiskResolution,
    resolve_candidate_risk_from_score,
)
from src.strategy.runtime_policy import (
    load_backtest_strategy_policy as _load_backtest_strategy_policy,
    load_dynamic_risk_policy as _load_dynamic_risk_policy,
    resolve_pullback_settings as _resolve_pullback_settings,
    resolve_symbol_allowed_setups as _resolve_symbol_allowed_setups,
    resolve_symbol_backtest_risk as _resolve_symbol_backtest_risk,
    resolve_symbol_filters as _resolve_symbol_filters,
    resolve_symbol_trade_management as _resolve_symbol_trade_management,
)


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta backtest por simbolo y genera outputs auditables."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Subset de simbolos a correr. Acepta valores separados por espacio o coma.",
    )
    return parser.parse_args()


def resolve_selected_symbols(
    configured_symbols: list[str],
    requested_symbols: list[str] | None,
    excluded_symbols: list[str] | None = None,
) -> list[str]:
    excluded_set = {str(symbol).strip().upper() for symbol in excluded_symbols or []}
    eligible_symbols = [
        symbol for symbol in configured_symbols if symbol not in excluded_set
    ]

    if not requested_symbols:
        return eligible_symbols

    requested: list[str] = []
    for raw_value in requested_symbols:
        for symbol in str(raw_value).split(","):
            normalized = symbol.strip().upper()
            if normalized:
                requested.append(normalized)

    if not requested:
        raise ValueError("La lista de simbolos solicitados quedo vacia.")

    invalid = [symbol for symbol in requested if symbol not in configured_symbols]
    if invalid:
        raise ValueError(
            f"Simbolos no habilitados en config: {', '.join(invalid)}"
        )

    excluded_requested = [symbol for symbol in requested if symbol in excluded_set]
    if excluded_requested:
        raise ValueError(
            "Simbolos excluidos por la estrategia research actual: "
            f"{', '.join(excluded_requested)}"
        )

    unique_requested: list[str] = []
    for symbol in requested:
        if symbol not in unique_requested:
            unique_requested.append(symbol)
    return unique_requested


def load_backtest_strategy_policy(
    config: dict[str, Any],
) -> dict[str, object]:
    return _load_backtest_strategy_policy(config)


def load_dynamic_risk_policy(
    config: dict[str, Any],
) -> dict[str, object]:
    return _load_dynamic_risk_policy(config)


def _resolve_symbol_scoped_values(
    section_cfg: dict[str, Any] | None,
    symbol: str,
    overrides: dict[str, float | int] | None = None,
) -> dict[str, float]:
    section_cfg = dict(section_cfg or {})
    symbol_overrides_cfg = section_cfg.get("by_symbol", {})
    if not isinstance(symbol_overrides_cfg, dict):
        symbol_overrides_cfg = {}

    base_values = {
        key: value
        for key, value in section_cfg.items()
        if key != "by_symbol"
    }
    symbol_values = dict(symbol_overrides_cfg.get(str(symbol).strip().upper(), {}))

    resolved = dict(base_values)
    resolved.update(symbol_values)
    if overrides:
        resolved.update(overrides)

    return {
        key: float(value)
        for key, value in resolved.items()
        if isinstance(value, int | float)
    }


def resolve_symbol_filters(
    config: dict[str, Any],
    symbol: str,
    overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    return _resolve_symbol_filters(config, symbol, overrides=overrides)


def resolve_symbol_trade_management(
    config: dict[str, Any],
    symbol: str,
    overrides: dict[str, float | int] | None = None,
) -> dict[str, float]:
    return _resolve_symbol_trade_management(config, symbol, overrides=overrides)


def resolve_symbol_backtest_risk(
    config: dict[str, Any],
    symbol: str,
    default_risk_pct: float,
    default_risk_bucket: str,
) -> tuple[float, str]:
    return _resolve_symbol_backtest_risk(
        config,
        symbol,
        default_risk_pct,
        default_risk_bucket,
    )


def resolve_symbol_allowed_setups(
    config: dict[str, Any],
    symbol: str,
) -> list[str]:
    return _resolve_symbol_allowed_setups(config, symbol)


def resolve_pullback_settings(
    config: dict[str, Any],
    symbol: str,
) -> dict[str, float]:
    return _resolve_pullback_settings(config, symbol)


def build_signal_fn(
    *,
    symbol: str,
    capital_usdt: float,
    risk_pct: float,
    risk_bucket: str,
    leverage: float,
    max_notional_pct: float,
    fee_rate_entry: float,
    fee_rate_exit: float,
    slippage_pct: float,
    stop_buffer_atr_fraction: float,
    min_candles: int,
    max_candles: int,
    max_range_atr_multiple: float,
    min_volume_ratio: float,
    max_trigger_candle_atr_multiple: float,
    allowed_setups: list[str] | None = None,
    impulse_lookback_candles: int = 6,
    min_pullback_candles: int = 2,
    max_pullback_candles: int = 5,
    min_impulse_atr_multiple: float = 1.8,
    min_retrace_ratio: float = 0.25,
    max_retrace_ratio: float = 0.60,
    max_trigger_body_atr_multiple: float | None = None,
    max_forward_bars: int,
    max_bars_in_trade: int,
    force_close_on_last_candle: bool,
    df_1h: pd.DataFrame | None = None,
    df_4h: pd.DataFrame | None = None,
    enforce_context_alignment: bool = False,
    allowed_sides_by_symbol: dict[str, list[str]] | None = None,
    score_thresholds: dict[str, float] | None = None,
    risk_by_score: dict[str, float] | None = None,
    dynamic_risk_enabled: bool = False,
    preserve_symbol_base_risk: bool = True,
):
    def signal_fn(df: pd.DataFrame, i: int) -> dict | None:
        signal = build_breakout_signal_for_index(
            symbol=symbol,
            market_df=df,
            trigger_index=i,
            capital_usdt=capital_usdt,
            risk_pct=risk_pct,
            risk_bucket=risk_bucket,
            max_notional_pct=max_notional_pct,
            leverage=leverage,
            max_forward_bars=max_forward_bars,
            fee_rate_entry=fee_rate_entry,
            fee_rate_exit=fee_rate_exit,
            slippage_pct=slippage_pct,
            stop_buffer_atr_fraction=stop_buffer_atr_fraction,
            min_candles=min_candles,
            max_candles=max_candles,
            max_range_atr_multiple=max_range_atr_multiple,
            min_volume_ratio=min_volume_ratio,
            max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
            allowed_setups=allowed_setups,
            impulse_lookback_candles=impulse_lookback_candles,
            min_pullback_candles=min_pullback_candles,
            max_pullback_candles=max_pullback_candles,
            min_impulse_atr_multiple=min_impulse_atr_multiple,
            min_retrace_ratio=min_retrace_ratio,
            max_retrace_ratio=max_retrace_ratio,
            max_trigger_body_atr_multiple=max_trigger_body_atr_multiple,
            force_close_on_last_candle=force_close_on_last_candle,
            max_bars_in_trade=max_bars_in_trade,
            candidate_filter=lambda candidate: evaluate_trade_candidate_policy(
                symbol=symbol,
                candidate=candidate,
                df_1h=df_1h,
                df_4h=df_4h,
                allowed_sides_by_symbol=allowed_sides_by_symbol,
                enforce_context_alignment=enforce_context_alignment,
            ),
            candidate_risk_resolver=(
                (
                    lambda candidate, default_risk_pct, default_risk_bucket: _resolve_candidate_risk(
                        symbol=symbol,
                        candidate=candidate,
                        default_risk_pct=default_risk_pct,
                        default_risk_bucket=default_risk_bucket,
                        df_1h=df_1h,
                        df_4h=df_4h,
                        score_thresholds=score_thresholds or {},
                        risk_by_score=risk_by_score or {},
                        preserve_symbol_base_risk=preserve_symbol_base_risk,
                    )
                )
                if dynamic_risk_enabled
                else None
            ),
        )

        if signal is None:
            return None

        return {
            "order_plan": signal.order_plan,
            "execution_result": signal.execution_result,
            "position_size_units": signal.position_size_units,
            "leverage": signal.leverage,
        }

    return signal_fn


def _resolve_candidate_risk(
    *,
    symbol: str,
    candidate: Any,
    default_risk_pct: float,
    default_risk_bucket: str,
    df_1h: pd.DataFrame | None,
    df_4h: pd.DataFrame | None,
    score_thresholds: dict[str, float],
    risk_by_score: dict[str, float],
    preserve_symbol_base_risk: bool,
) -> CandidateRiskResolution:
    if df_1h is None or df_4h is None:
        return CandidateRiskResolution(
            trade_allowed=True,
            risk_pct=float(default_risk_pct),
            risk_bucket=str(default_risk_bucket),
            score_total=0.0,
            notes=["Dynamic risk deshabilitado por falta de contexto 1h/4h."],
        )

    risk_resolution = resolve_candidate_risk_from_score(
        symbol=symbol,
        candidate=candidate,
        df_1h=df_1h,
        df_4h=df_4h,
        score_thresholds=score_thresholds,
        risk_by_score=risk_by_score,
        open_positions=0,
        same_side_exposure_count=0,
    )

    if (
        preserve_symbol_base_risk
        and risk_resolution.trade_allowed
        and float(risk_resolution.risk_pct) < float(default_risk_pct)
    ):
        updated_notes = list(risk_resolution.notes)
        updated_notes.append(
            "Dynamic risk preserva riesgo base del simbolo: "
            f"{risk_resolution.risk_pct:.4f} -> {float(default_risk_pct):.4f}"
        )
        return CandidateRiskResolution(
            trade_allowed=True,
            risk_pct=float(default_risk_pct),
            risk_bucket=str(risk_resolution.risk_bucket),
            score_total=float(risk_resolution.score_total),
            notes=updated_notes,
        )

    return risk_resolution


def main() -> None:
    args = parse_cli_args()
    config_path = get_default_config_path()

    print("Cargando configuracion...")
    config = load_config(config_path)
    runtime = load_runtime_config(config)
    ensure_project_directories(config)
    backtest_policy = load_backtest_strategy_policy(config)
    dynamic_risk_policy = load_dynamic_risk_policy(config)

    paths = resolve_project_paths(config)
    configured_symbols = list(config["symbols"]["enabled"])
    symbols = resolve_selected_symbols(
        configured_symbols,
        args.symbols,
        excluded_symbols=list(backtest_policy["excluded_symbols"]),
    )
    backtest_risk_pct, backtest_risk_notes = get_risk_pct_for_bucket(
        risk_by_score=dict(config["risk"]["risk_by_score"]),
        risk_bucket=runtime.backtest_risk_bucket,
    )

    print(f"Proyecto: {config['project']['name']}")
    print(f"Modo: {config['project']['mode']}")
    print(f"Simbolos configurados: {configured_symbols}")
    print(f"Simbolos a correr: {symbols}")
    print(f"Config path: {Path(config['_meta']['config_path'])}")
    print(f"Ruta datos raw: {paths['raw_data_path']}")
    print(
        "Backtest risk bucket: "
        f"{runtime.backtest_risk_bucket} | risk_pct={backtest_risk_pct:.4f}"
    )
    print(
        "Backtest policy: "
        f"enabled={backtest_policy['enabled']} | "
        f"context={backtest_policy['enforce_context_alignment']} | "
        f"excluded={backtest_policy['excluded_symbols']}"
    )
    print(
        "Dynamic risk by score: "
        f"enabled={dynamic_risk_policy['enabled']} | "
        "preserve_symbol_base_risk="
        f"{dynamic_risk_policy['preserve_symbol_base_risk']}"
    )
    for note in backtest_risk_notes:
        print(f"- {note}")

    print("\nCargando datos historicos...")
    all_data = load_all_symbols(
        raw_data_path=paths["raw_data_path"],
        symbols=symbols,
        timeframes=("15m", "1h", "4h"),
    )

    print("\nResumen de carga:")
    for symbol, bundle in all_data.items():
        for timeframe in ("15m", "1h", "4h"):
            summary = summarize_dataframe(bundle[timeframe])
            print(
                f"{symbol} {timeframe}: filas={summary['rows']}, "
                f"inicio={summary['start']}, fin={summary['end']}"
            )

    output_dir = paths["outputs_path"] / "backtests"
    symbol_records: list[dict[str, object]] = []

    print("\nIniciando backtest...\n")

    for symbol in symbols:
        print(f"==================== {symbol} ====================")

        df_15m = add_basic_indicators(all_data[symbol]["15m"]).reset_index(drop=True)
        df_1h = add_basic_indicators(all_data[symbol]["1h"]).reset_index(drop=True)
        df_4h = add_basic_indicators(all_data[symbol]["4h"]).reset_index(drop=True)
        symbol_filters = resolve_symbol_filters(config, symbol)
        symbol_trade_management = resolve_symbol_trade_management(config, symbol)
        symbol_risk_pct, symbol_risk_bucket = resolve_symbol_backtest_risk(
            config,
            symbol,
            backtest_risk_pct,
            runtime.backtest_risk_bucket,
        )
        symbol_allowed_setups = resolve_symbol_allowed_setups(config, symbol)
        pullback_settings = resolve_pullback_settings(config, symbol)

        signal_fn = build_signal_fn(
            symbol=symbol,
            capital_usdt=float(config["capital"]["initial_capital"]),
            risk_pct=symbol_risk_pct,
            risk_bucket=symbol_risk_bucket,
            leverage=float(config["leverage"][symbol]),
            max_notional_pct=float(config["position_limits"]["max_notional_pct"][symbol]),
            fee_rate_entry=float(config["execution"]["fee_rate_entry"]),
            fee_rate_exit=float(config["execution"]["fee_rate_exit"]),
            slippage_pct=float(dict(config["execution"].get("slippage", {})).get(symbol, 0.0)),
            stop_buffer_atr_fraction=float(
                symbol_filters.get("stop_buffer_atr_fraction", 0.10)
            ),
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
            df_1h=df_1h if bool(backtest_policy["enabled"]) else None,
            df_4h=df_4h if bool(backtest_policy["enabled"]) else None,
            enforce_context_alignment=bool(
                backtest_policy["enabled"]
                and backtest_policy["enforce_context_alignment"]
            ),
            allowed_sides_by_symbol=(
                dict(backtest_policy["allowed_sides"])
                if bool(backtest_policy["enabled"])
                else None
            ),
            score_thresholds={
                "min_trade": float(config["score_thresholds"]["min_trade"]),
                "aggressive": float(config["score_thresholds"]["aggressive"]),
                "exceptional": float(config["score_thresholds"]["exceptional"]),
            },
            risk_by_score={
                key: float(value)
                for key, value in dict(config["risk"]["risk_by_score"]).items()
            },
            dynamic_risk_enabled=bool(dynamic_risk_policy["enabled"]),
            preserve_symbol_base_risk=bool(
                dynamic_risk_policy["preserve_symbol_base_risk"]
            ),
        )
        print(
            "Filters -> "
            f"volume={symbol_filters['min_breakout_volume_multiple']:.2f} | "
            f"range={symbol_filters['max_consolidation_range_atr_multiple']:.2f} | "
            f"trigger={symbol_filters['max_trigger_candle_atr_multiple']:.2f} | "
            f"max_bars={int(symbol_trade_management['max_bars_in_trade'])} | "
            f"risk_pct={symbol_risk_pct:.4f} | "
            f"setups={','.join(symbol_allowed_setups)}"
        )

        runner = BacktestRunner(
            symbol=symbol,
            market_df=df_15m,
            signal_fn=signal_fn,
            output_dir=str(output_dir),
            initial_capital=float(config["capital"]["initial_capital"]),
            save_outputs=True,
        )

        trades_df, metrics, equity_curve_df = runner.run()
        _ = equity_curve_df

        print(f"Trades totales -> {metrics['total_trades']}")
        print(f"Trades cerrados -> {metrics['closed_trades']}")
        print(f"Trades abiertos -> {metrics['open_trades']}")
        print(f"Win rate -> {metrics['win_rate']:.2%}")
        print(f"Profit factor -> {metrics['profit_factor']:.4f}")
        print(f"Expectancy -> {metrics['expectancy']:.4f} USDT")
        print(f"Max drawdown -> {metrics['max_drawdown']:.4f} USDT")
        print(f"Net PnL -> {metrics['net_pnl_usdt']:.4f} USDT")
        print(f"Gross profit -> {metrics['gross_profit_usdt']:.4f} USDT")
        print(f"Gross loss -> {metrics['gross_loss_usdt']:.4f} USDT")
        print(f"Stop loss rate -> {metrics['stop_loss_rate']:.2%}")
        print(f"TP2 rate -> {metrics['tp2_rate']:.2%}")
        print(f"Timeout rate -> {metrics['timeout_rate']:.2%}")
        print(f"End of data rate -> {metrics['end_of_data_rate']:.2%}")

        print(f"Trades CSV -> {output_dir / f'{symbol}_trades.csv'}")
        print(f"Summary JSON -> {output_dir / f'{symbol}_summary.json'}")
        print(f"Equity curve CSV -> {output_dir / f'{symbol}_equity_curve.csv'}")
        print()

        symbol_records.append(
            build_symbol_baseline_record(
                symbol=symbol,
                market_df=df_15m,
                trades_df=trades_df,
                metrics=metrics,
                initial_capital=float(config["capital"]["initial_capital"]),
            )
        )

        run_payload = build_run_baseline_payload(
            config=config,
            symbol_records=symbol_records,
            backtest_risk_bucket=runtime.backtest_risk_bucket,
            backtest_risk_pct=backtest_risk_pct,
        )
        baseline_paths = save_run_baseline_artifacts(
            output_dir=output_dir,
            config=config,
            run_payload=run_payload,
        )
        print(
            "Baseline parcial -> "
            f"{len(symbol_records)} simbolos procesados | "
            f"summary={baseline_paths['baseline_summary_path']}"
        )

        if not trades_df.empty:
            print("Primeros 5 trades:")
            preview_cols = [
                "entry_time",
                "exit_time",
                "side",
                "entry_price",
                "exit_price",
                "pnl_net_usdt",
                "exit_reason",
            ]
            print(trades_df[preview_cols].head(5).to_string(index=False))
            print()
        else:
            print("No se generaron trades para este simbolo.\n")

    run_payload = build_run_baseline_payload(
        config=config,
        symbol_records=symbol_records,
        backtest_risk_bucket=runtime.backtest_risk_bucket,
        backtest_risk_pct=backtest_risk_pct,
    )
    baseline_paths = save_run_baseline_artifacts(
        output_dir=output_dir,
        config=config,
        run_payload=run_payload,
    )

    print("Baseline multi-simbolo:")
    print(f"Config snapshot -> {baseline_paths['config_snapshot_path']}")
    print(f"Baseline summary -> {baseline_paths['baseline_summary_path']}")
    print(f"Baseline symbols CSV -> {baseline_paths['baseline_symbols_path']}")
    print(
        "Portfolio proxy -> "
        f"net_pnl={run_payload['portfolio_proxy']['total_net_pnl_usdt']:.4f} USDT | "
        f"trades={run_payload['portfolio_proxy']['total_trades']}"
    )

    print("Backtest finalizado.")


if __name__ == "__main__":
    main()
