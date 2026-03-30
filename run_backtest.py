from __future__ import annotations

from pathlib import Path

import pandas as pd

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


def build_signal_fn(
    *,
    symbol: str,
    capital_usdt: float,
    leverage: float,
    fee_rate_entry: float,
    fee_rate_exit: float,
    min_candles: int,
    max_candles: int,
    max_range_atr_multiple: float,
    min_volume_ratio: float,
    max_trigger_candle_atr_multiple: float,
    max_forward_bars: int,
    max_bars_in_trade: int,
    force_close_on_last_candle: bool,
):
    def signal_fn(df: pd.DataFrame, i: int) -> dict | None:
        signal = build_breakout_signal_for_index(
            symbol=symbol,
            market_df=df,
            trigger_index=i,
            capital_usdt=capital_usdt,
            risk_pct=0.01,
            leverage=leverage,
            max_forward_bars=max_forward_bars,
            fee_rate_entry=fee_rate_entry,
            fee_rate_exit=fee_rate_exit,
            stop_buffer_atr_fraction=0.10,
            min_candles=min_candles,
            max_candles=max_candles,
            max_range_atr_multiple=max_range_atr_multiple,
            min_volume_ratio=min_volume_ratio,
            max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
            force_close_on_last_candle=force_close_on_last_candle,
            max_bars_in_trade=max_bars_in_trade,
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


def main() -> None:
    config_path = get_default_config_path()

    print("Cargando configuracion...")
    config = load_config(config_path)
    ensure_project_directories(config)

    paths = resolve_project_paths(config)
    symbols = config["symbols"]["enabled"]

    print(f"Proyecto: {config['project']['name']}")
    print(f"Modo: {config['project']['mode']}")
    print(f"Simbolos habilitados: {symbols}")
    print(f"Config path: {Path(config['_meta']['config_path'])}")
    print(f"Ruta datos raw: {paths['raw_data_path']}")

    print("\nCargando datos historicos...")
    all_data = load_all_symbols(
        raw_data_path=paths["raw_data_path"],
        symbols=symbols,
        timeframes=("15m",),
    )

    print("\nResumen de carga:")
    for symbol, bundle in all_data.items():
        df = bundle["15m"]
        summary = summarize_dataframe(df)
        print(
            f"{symbol} 15m: filas={summary['rows']}, "
            f"inicio={summary['start']}, fin={summary['end']}"
        )

    output_dir = paths["outputs_path"] / "backtests"

    print("\nIniciando backtest...\n")

    for symbol in symbols:
        print(f"==================== {symbol} ====================")

        df_15m = add_basic_indicators(all_data[symbol]["15m"]).reset_index(drop=True)

        signal_fn = build_signal_fn(
            symbol=symbol,
            capital_usdt=float(config["capital"]["initial_capital"]),
            leverage=float(config["leverage"][symbol]),
            fee_rate_entry=float(config["execution"]["fee_rate_entry"]),
            fee_rate_exit=float(config["execution"]["fee_rate_exit"]),
            min_candles=6,
            max_candles=12,
            max_range_atr_multiple=float(config["filters"]["max_consolidation_range_atr_multiple"]),
            min_volume_ratio=float(config["filters"]["min_breakout_volume_multiple"]),
            max_trigger_candle_atr_multiple=float(config["filters"]["max_trigger_candle_atr_multiple"]),
            max_forward_bars=80,
            max_bars_in_trade=24,
            force_close_on_last_candle=True,
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

    print("Backtest finalizado.")


if __name__ == "__main__":
    main()
