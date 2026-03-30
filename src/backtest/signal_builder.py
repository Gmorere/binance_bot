from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.execution.execution_simulator import ExecutionResult, simulate_trade_v1
from src.strategy.entry_rules import OrderPlan
from src.strategy.signal_service import (
    SignalServiceError,
    detect_breakout_trade_candidate,
)


class SignalBuilderError(Exception):
    """Error relacionado con construcción de señales para backtest."""


@dataclass
class BacktestSignal:
    order_plan: OrderPlan
    execution_result: ExecutionResult
    position_size_units: float
    leverage: float
    risk_pct: float
    setup_notes: list[str]


def _validate_market_df(df: pd.DataFrame) -> None:
    required_cols = ["timestamp", "open", "high", "low", "close", "volume", "atr_14"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise SignalBuilderError(
            f"Faltan columnas requeridas en market_df: {', '.join(missing)}"
        )

    if len(df) < 30:
        raise SignalBuilderError("No hay suficientes velas para construir señal.")


def _validate_inputs(
    *,
    symbol: str,
    trigger_index: int,
    capital_usdt: float,
    risk_pct: float,
    leverage: float,
    max_forward_bars: int,
    fee_rate_entry: float,
    fee_rate_exit: float,
    stop_buffer_atr_fraction: float,
    min_candles: int,
    max_candles: int,
    max_range_atr_multiple: float,
    min_volume_ratio: float,
    max_trigger_candle_atr_multiple: float,
    max_bars_in_trade: Optional[int],
) -> None:
    if not symbol:
        raise SignalBuilderError("symbol no puede venir vacío.")

    if trigger_index < 0:
        raise SignalBuilderError("trigger_index no puede ser negativo.")

    if capital_usdt <= 0:
        raise SignalBuilderError("capital_usdt debe ser mayor a 0.")

    if not (0 < risk_pct < 1):
        raise SignalBuilderError("risk_pct debe estar entre 0 y 1.")

    if leverage <= 0:
        raise SignalBuilderError("leverage debe ser mayor a 0.")

    if max_forward_bars <= 0:
        raise SignalBuilderError("max_forward_bars debe ser mayor a 0.")

    if fee_rate_entry < 0 or fee_rate_exit < 0:
        raise SignalBuilderError("Las fees no pueden ser negativas.")

    if stop_buffer_atr_fraction < 0:
        raise SignalBuilderError("stop_buffer_atr_fraction no puede ser negativo.")

    if min_candles <= 0 or max_candles <= 0:
        raise SignalBuilderError("min_candles y max_candles deben ser mayores a 0.")

    if min_candles > max_candles:
        raise SignalBuilderError("min_candles no puede ser mayor que max_candles.")

    if max_range_atr_multiple <= 0:
        raise SignalBuilderError("max_range_atr_multiple debe ser mayor a 0.")

    if min_volume_ratio < 0:
        raise SignalBuilderError("min_volume_ratio no puede ser negativo.")

    if max_trigger_candle_atr_multiple <= 0:
        raise SignalBuilderError("max_trigger_candle_atr_multiple debe ser mayor a 0.")

    if max_bars_in_trade is not None and max_bars_in_trade <= 0:
        raise SignalBuilderError("max_bars_in_trade debe ser mayor a 0 si se informa.")


def _build_future_window(df: pd.DataFrame, start_index: int, max_forward_bars: int) -> pd.DataFrame:
    future_df = df.iloc[start_index : start_index + max_forward_bars].copy()
    if future_df.empty:
        raise SignalBuilderError("future_df quedó vacío.")
    return future_df.reset_index(drop=True)


def _default_position_size_units(
    *,
    capital_usdt: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
) -> float:
    """
    Sizing provisional.
    Riesgo fijo por trade / distancia al stop.
    """
    risk_amount = capital_usdt * risk_pct
    stop_distance = abs(entry_price - stop_price)

    if stop_distance <= 0:
        raise SignalBuilderError("stop_distance debe ser mayor a 0 para sizing.")

    size_units = risk_amount / stop_distance
    if size_units <= 0:
        raise SignalBuilderError("size_units calculado inválido.")

    return size_units


def build_breakout_signal_for_index(
    *,
    symbol: str,
    market_df: pd.DataFrame,
    trigger_index: int,
    capital_usdt: float,
    risk_pct: float = 0.01,
    leverage: float = 1.0,
    max_forward_bars: int = 80,
    fee_rate_entry: float = 0.0004,
    fee_rate_exit: float = 0.0004,
    stop_buffer_atr_fraction: float = 0.10,
    min_candles: int = 6,
    max_candles: int = 12,
    max_range_atr_multiple: float = 1.2,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
    force_close_on_last_candle: bool = True,
    max_bars_in_trade: Optional[int] = 24,
) -> Optional[BacktestSignal]:
    """
    Usa market_df hasta trigger_index para detectar setup,
    entra en la siguiente vela abierta y simula desde esa vela en adelante.
    """
    _validate_market_df(market_df)
    _validate_inputs(
        symbol=symbol,
        trigger_index=trigger_index,
        capital_usdt=capital_usdt,
        risk_pct=risk_pct,
        leverage=leverage,
        max_forward_bars=max_forward_bars,
        fee_rate_entry=fee_rate_entry,
        fee_rate_exit=fee_rate_exit,
        stop_buffer_atr_fraction=stop_buffer_atr_fraction,
        min_candles=min_candles,
        max_candles=max_candles,
        max_range_atr_multiple=max_range_atr_multiple,
        min_volume_ratio=min_volume_ratio,
        max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
        max_bars_in_trade=max_bars_in_trade,
    )

    if trigger_index < 29:
        return None

    if trigger_index >= len(market_df) - 1:
        return None

    next_open_price = float(market_df.iloc[trigger_index + 1]["open"])

    try:
        candidate = detect_breakout_trade_candidate(
            symbol=symbol,
            market_df=market_df,
            trigger_index=trigger_index,
            entry_reference_price=next_open_price,
            stop_buffer_atr_fraction=stop_buffer_atr_fraction,
            min_candles=min_candles,
            max_candles=max_candles,
            max_range_atr_multiple=max_range_atr_multiple,
            min_volume_ratio=min_volume_ratio,
            max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
        )
    except SignalServiceError as exc:
        raise SignalBuilderError(f"No se pudo construir TradeCandidate: {exc}") from exc

    if candidate is None:
        return None

    order_plan = candidate.order_plan

    position_size_units = _default_position_size_units(
        capital_usdt=capital_usdt,
        risk_pct=risk_pct,
        entry_price=order_plan.entry_price,
        stop_price=order_plan.stop_price,
    )

    future_df = _build_future_window(
        df=market_df,
        start_index=trigger_index + 1,
        max_forward_bars=max_forward_bars,
    )

    execution_result = simulate_trade_v1(
        symbol=symbol,
        future_df=future_df,
        order_plan=order_plan,
        position_size_units=position_size_units,
        fee_rate_entry=fee_rate_entry,
        fee_rate_exit=fee_rate_exit,
        max_bars_in_trade=max_bars_in_trade,
        force_close_on_last_candle=force_close_on_last_candle,
    )

    setup_notes = list(candidate.setup_notes)

    return BacktestSignal(
        order_plan=order_plan,
        execution_result=execution_result,
        position_size_units=float(position_size_units),
        leverage=float(leverage),
        risk_pct=float(risk_pct),
        setup_notes=setup_notes,
    )
