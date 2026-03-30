from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional
import json

import pandas as pd

from src.backtest.equity_curve import build_equity_curve
from src.backtest.metrics import compute_backtest_metrics
from src.backtest.trade_record import TradeRecord
from src.execution.execution_simulator import ExecutionResult
from src.strategy.entry_rules import OrderPlan


class BacktestRunnerError(Exception):
    """Error relacionado con el runner de backtest."""


SignalFn = Callable[[pd.DataFrame, int], Optional[dict]]


class BacktestRunner:
    def __init__(
        self,
        *,
        symbol: str,
        market_df: pd.DataFrame,
        signal_fn: SignalFn,
        output_dir: str = "outputs/backtests",
        initial_capital: float = 0.0,
        save_outputs: bool = True,
        print_progress: bool = True,
        progress_every_n_rows: int = 500,
    ) -> None:
        self.symbol = symbol
        self.market_df = market_df.reset_index(drop=True).copy()
        self.signal_fn = signal_fn
        self.output_dir = Path(output_dir)
        self.initial_capital = float(initial_capital)
        self.save_outputs = save_outputs
        self.print_progress = print_progress
        self.progress_every_n_rows = int(progress_every_n_rows)

        self._validate_market_df()

    def _validate_market_df(self) -> None:
        if self.market_df.empty:
            raise BacktestRunnerError("market_df viene vacío.")

        required_cols = ["timestamp", "open", "high", "low", "close"]
        missing = [col for col in required_cols if col not in self.market_df.columns]
        if missing:
            raise BacktestRunnerError(
                f"market_df no tiene las columnas requeridas: {', '.join(missing)}"
            )

        if not callable(self.signal_fn):
            raise BacktestRunnerError("signal_fn debe ser callable.")

        if not self.symbol or not isinstance(self.symbol, str):
            raise BacktestRunnerError("symbol debe ser un string no vacío.")

        if self.progress_every_n_rows <= 0:
            raise BacktestRunnerError("progress_every_n_rows debe ser mayor a 0.")

    def run(self) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
        trades: list[TradeRecord] = []
        i = 0
        total_rows = len(self.market_df)

        if self.print_progress:
            print(f"[{self.symbol}] Backtest iniciado. Filas a procesar: {total_rows}")

        while i < total_rows:
            if self.print_progress and (i == 0 or i % self.progress_every_n_rows == 0):
                pct = (i / total_rows) * 100 if total_rows > 0 else 0.0
                print(
                    f"[{self.symbol}] Progreso: índice {i}/{total_rows} "
                    f"({pct:.1f}%) | trades detectados: {len(trades)}"
                )

            try:
                signal = self.signal_fn(self.market_df, i)
            except Exception as exc:
                raise BacktestRunnerError(
                    f"signal_fn falló en el índice {i}: {exc}"
                ) from exc

            if not signal:
                i += 1
                continue

            order_plan = signal.get("order_plan")
            execution = signal.get("execution_result")
            position_size_units = signal.get("position_size_units")
            leverage = signal.get("leverage", 1.0)

            if not isinstance(order_plan, OrderPlan):
                raise BacktestRunnerError(
                    f"signal['order_plan'] debe ser un OrderPlan. Índice: {i}"
                )

            if not isinstance(execution, ExecutionResult):
                raise BacktestRunnerError(
                    f"signal['execution_result'] debe ser un ExecutionResult. Índice: {i}"
                )

            if position_size_units is None or float(position_size_units) <= 0:
                raise BacktestRunnerError(
                    f"signal['position_size_units'] debe ser mayor a 0. Índice: {i}"
                )

            try:
                trade = self._build_trade_record(
                    order_plan=order_plan,
                    execution=execution,
                    position_size_units=float(position_size_units),
                    leverage=float(leverage),
                )
            except Exception as exc:
                raise BacktestRunnerError(
                    f"No se pudo construir TradeRecord en el índice {i}: {exc}"
                ) from exc

            trades.append(trade)

            if self.print_progress:
                exit_label = execution.exit_reason
                print(
                    f"[{self.symbol}] Trade #{len(trades)} detectado en índice {i} "
                    f"| side={order_plan.side} | exit_reason={exit_label}"
                )

            if execution.exit_index is None:
                i += 1
            else:
                next_i = i + max(1, int(execution.exit_index) + 1)
                i = min(next_i, total_rows)

        if trades:
            trades_df = pd.DataFrame([asdict(t) for t in trades])
        else:
            trades_df = pd.DataFrame(
                columns=[
                    "symbol",
                    "side",
                    "entry_time",
                    "exit_time",
                    "entry_price",
                    "exit_price",
                    "stop_loss",
                    "tp1",
                    "tp2",
                    "size_qty",
                    "leverage",
                    "pnl_gross_usdt",
                    "fee_entry_usdt",
                    "fee_exit_usdt",
                    "pnl_net_usdt",
                    "exit_reason",
                    "exit_index",
                    "trade_closed",
                    "setup_type",
                    "rr_1",
                    "rr_2",
                    "breakout_level",
                    "notes",
                ]
            )

        metrics = compute_backtest_metrics(trades_df)
        equity_curve_df = build_equity_curve(
            trades_df,
            initial_capital=self.initial_capital,
        )

        if self.save_outputs:
            self._save_outputs(trades_df, metrics, equity_curve_df)

        if self.print_progress:
            print(
                f"[{self.symbol}] Backtest finalizado. "
                f"Trades totales: {len(trades_df)} | "
                f"Net PnL: {metrics.get('net_pnl_usdt', 0.0):.4f} USDT"
            )

        return trades_df, metrics, equity_curve_df

    def _build_trade_record(
        self,
        *,
        order_plan: OrderPlan,
        execution: ExecutionResult,
        position_size_units: float,
        leverage: float,
    ) -> TradeRecord:
        order_notes = order_plan.notes if order_plan.notes else []
        execution_notes = execution.notes if execution.notes else []
        merged_notes = order_notes + execution_notes

        return TradeRecord(
            symbol=order_plan.symbol,
            side=order_plan.side,
            entry_time=str(execution.entry_time),
            exit_time=str(execution.exit_time) if execution.exit_time is not None else None,
            entry_price=float(order_plan.entry_price),
            exit_price=float(execution.exit_price) if execution.exit_price is not None else None,
            stop_loss=float(order_plan.stop_price),
            tp1=float(order_plan.tp1_price),
            tp2=float(order_plan.tp2_price),
            size_qty=float(position_size_units),
            leverage=float(leverage),
            pnl_gross_usdt=float(execution.pnl_gross_usdt),
            fee_entry_usdt=float(execution.fee_entry_usdt),
            fee_exit_usdt=float(execution.fee_exit_usdt),
            pnl_net_usdt=float(execution.pnl_net_usdt),
            exit_reason=str(execution.exit_reason),
            exit_index=int(execution.exit_index) if execution.exit_index is not None else None,
            trade_closed=bool(execution.trade_closed),
            setup_type=order_plan.setup_type,
            rr_1=float(order_plan.rr_1),
            rr_2=float(order_plan.rr_2),
            breakout_level=float(order_plan.breakout_level) if order_plan.breakout_level is not None else None,
            notes=" | ".join(merged_notes) if merged_notes else None,
        )

    def _save_outputs(
        self,
        trades_df: pd.DataFrame,
        metrics: dict,
        equity_curve_df: pd.DataFrame,
    ) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        safe_symbol = self.symbol.replace("/", "_").replace(":", "_")

        trades_path = self.output_dir / f"{safe_symbol}_trades.csv"
        summary_path = self.output_dir / f"{safe_symbol}_summary.json"
        equity_curve_path = self.output_dir / f"{safe_symbol}_equity_curve.csv"

        trades_df.to_csv(trades_path, index=False)
        equity_curve_df.to_csv(equity_curve_path, index=False)

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)