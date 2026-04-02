from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.execution.execution_simulator import ExecutionResult, simulate_trade_v1
from src.risk.sizing_engine import calculate_position_size
from src.strategy.entry_rules import OrderPlan
from src.strategy.scoring_policy import CandidateRiskResolution
from src.strategy.signal_service import (
    SignalServiceError,
    TradeCandidate,
    detect_trade_candidate,
)


class SignalBuilderError(Exception):
    """Error relacionado con construccion de senales para backtest."""


@dataclass
class BacktestSignal:
    order_plan: OrderPlan
    execution_result: ExecutionResult
    position_size_units: float
    notional_value_usdt: float
    leverage: float
    risk_pct: float
    risk_bucket: str
    setup_notes: list[str]


CandidateFilterFn = Callable[[TradeCandidate], tuple[bool, list[str]]]
CandidateRiskResolverFn = Callable[[TradeCandidate, float, str], CandidateRiskResolution]


def _validate_market_df(df: pd.DataFrame) -> None:
    required_cols = ["timestamp", "open", "high", "low", "close", "volume", "atr_14"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise SignalBuilderError(
            f"Faltan columnas requeridas en market_df: {', '.join(missing)}"
        )

    if len(df) < 30:
        raise SignalBuilderError("No hay suficientes velas para construir senal.")


def _validate_inputs(
    *,
    symbol: str,
    trigger_index: int,
    capital_usdt: float,
    risk_pct: float,
    risk_bucket: str,
    max_notional_pct: float,
    leverage: float,
    max_forward_bars: int,
    fee_rate_entry: float,
    fee_rate_exit: float,
    slippage_pct: float,
    stop_buffer_atr_fraction: float,
    min_candles: int,
    max_candles: int,
    max_range_atr_multiple: float,
    min_volume_ratio: float,
    max_trigger_candle_atr_multiple: float,
    max_bars_in_trade: Optional[int],
) -> None:
    if not symbol:
        raise SignalBuilderError("symbol no puede venir vacio.")

    if trigger_index < 0:
        raise SignalBuilderError("trigger_index no puede ser negativo.")

    if capital_usdt <= 0:
        raise SignalBuilderError("capital_usdt debe ser mayor a 0.")

    if not (0 < risk_pct < 1):
        raise SignalBuilderError("risk_pct debe estar entre 0 y 1.")

    if not str(risk_bucket).strip():
        raise SignalBuilderError("risk_bucket no puede venir vacio.")

    if max_notional_pct <= 0:
        raise SignalBuilderError("max_notional_pct debe ser mayor a 0.")

    if leverage <= 0:
        raise SignalBuilderError("leverage debe ser mayor a 0.")

    if max_forward_bars <= 0:
        raise SignalBuilderError("max_forward_bars debe ser mayor a 0.")

    if fee_rate_entry < 0 or fee_rate_exit < 0:
        raise SignalBuilderError("Las fees no pueden ser negativas.")
    if slippage_pct < 0:
        raise SignalBuilderError("slippage_pct no puede ser negativo.")

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
        raise SignalBuilderError("future_df quedo vacio.")
    return future_df.reset_index(drop=True)


def build_breakout_signal_for_index(
    *,
    symbol: str,
    market_df: pd.DataFrame,
    trigger_index: int,
    capital_usdt: float,
    risk_pct: float = 0.01,
    risk_bucket: str = "normal",
    max_notional_pct: float = 1.0,
    leverage: float = 1.0,
    max_forward_bars: int = 80,
    fee_rate_entry: float = 0.0004,
    fee_rate_exit: float = 0.0004,
    slippage_pct: float = 0.0,
    stop_buffer_atr_fraction: float = 0.10,
    min_candles: int = 6,
    max_candles: int = 12,
    max_range_atr_multiple: float = 1.2,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
    allowed_setups: list[str] | None = None,
    impulse_lookback_candles: int = 6,
    min_pullback_candles: int = 2,
    max_pullback_candles: int = 5,
    min_impulse_atr_multiple: float = 1.8,
    min_retrace_ratio: float = 0.25,
    max_retrace_ratio: float = 0.60,
    max_trigger_body_atr_multiple: float | None = None,
    force_close_on_last_candle: bool = True,
    max_bars_in_trade: Optional[int] = 24,
    candidate_filter: CandidateFilterFn | None = None,
    candidate_risk_resolver: CandidateRiskResolverFn | None = None,
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
        max_bars_in_trade=max_bars_in_trade,
    )

    if trigger_index < 29:
        return None

    if trigger_index >= len(market_df) - 1:
        return None

    next_open_price = float(market_df.iloc[trigger_index + 1]["open"])

    try:
        candidate = detect_trade_candidate(
            symbol=symbol,
            market_df=market_df,
            trigger_index=trigger_index,
            entry_reference_price=next_open_price,
            allowed_setups=allowed_setups,
            stop_buffer_atr_fraction=stop_buffer_atr_fraction,
            min_candles=min_candles,
            max_candles=max_candles,
            max_range_atr_multiple=max_range_atr_multiple,
            min_volume_ratio=min_volume_ratio,
            max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
            impulse_lookback_candles=impulse_lookback_candles,
            min_pullback_candles=min_pullback_candles,
            max_pullback_candles=max_pullback_candles,
            min_impulse_atr_multiple=min_impulse_atr_multiple,
            min_retrace_ratio=min_retrace_ratio,
            max_retrace_ratio=max_retrace_ratio,
            max_trigger_body_atr_multiple=max_trigger_body_atr_multiple,
        )
    except SignalServiceError as exc:
        raise SignalBuilderError(f"No se pudo construir TradeCandidate: {exc}") from exc

    if candidate is None:
        return None

    if candidate_filter is not None:
        candidate_allowed, filter_notes = candidate_filter(candidate)
        if filter_notes:
            candidate.order_plan.notes.extend(str(note) for note in filter_notes)
        if not candidate_allowed:
            return None

    effective_risk_pct = float(risk_pct)
    effective_risk_bucket = str(risk_bucket)
    if candidate_risk_resolver is not None:
        risk_resolution = candidate_risk_resolver(
            candidate,
            effective_risk_pct,
            effective_risk_bucket,
        )
        if risk_resolution.notes:
            candidate.order_plan.notes.extend(str(note) for note in risk_resolution.notes)
        if not risk_resolution.trade_allowed:
            return None
        effective_risk_pct = float(risk_resolution.risk_pct)
        effective_risk_bucket = str(risk_resolution.risk_bucket)

    order_plan = candidate.order_plan
    sizing = calculate_position_size(
        equity=capital_usdt,
        risk_pct=effective_risk_pct,
        entry_price=order_plan.entry_price,
        stop_price=order_plan.stop_price,
        leverage=leverage,
        max_notional_pct=max_notional_pct,
    )
    if not sizing.sizing_allowed:
        raise SignalBuilderError(
            f"Sizing invalido para {symbol}: {' | '.join(sizing.notes)}"
        )

    order_plan.notes.extend(
        [
            f"Backtest risk bucket: {effective_risk_bucket}",
            f"Backtest risk_pct: {effective_risk_pct:.4f}",
            f"Backtest notional_usdt: {sizing.notional_value_usdt:.4f}",
        ]
    )
    order_plan.notes.extend(str(note) for note in sizing.notes)

    future_df = _build_future_window(
        df=market_df,
        start_index=trigger_index + 1,
        max_forward_bars=max_forward_bars,
    )

    execution_result = simulate_trade_v1(
        symbol=symbol,
        future_df=future_df,
        order_plan=order_plan,
        position_size_units=sizing.position_size_units,
        fee_rate_entry=fee_rate_entry,
        fee_rate_exit=fee_rate_exit,
        slippage_pct=slippage_pct,
        max_bars_in_trade=max_bars_in_trade,
        force_close_on_last_candle=force_close_on_last_candle,
    )

    setup_notes = list(candidate.setup_notes)

    return BacktestSignal(
        order_plan=order_plan,
        execution_result=execution_result,
        position_size_units=float(sizing.position_size_units),
        notional_value_usdt=float(sizing.notional_value_usdt),
        leverage=float(leverage),
        risk_pct=float(effective_risk_pct),
        risk_bucket=str(effective_risk_bucket),
        setup_notes=setup_notes,
    )
