from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategy.entry_rules import (
    EntryRulesError,
    OrderPlan,
    build_breakout_order_plan,
    validate_order_plan,
)
from src.strategy.setup_detector import (
    BreakoutDetection,
    ConsolidationRange,
    detect_breakout_setup,
)


class SignalServiceError(Exception):
    """Error relacionado con detección de señales operables."""


@dataclass
class TradeCandidate:
    order_plan: OrderPlan
    setup_notes: list[str]
    trigger_index: int
    trigger_timestamp: pd.Timestamp


def _validate_market_df(df: pd.DataFrame) -> None:
    required_cols = ["timestamp", "open", "high", "low", "close", "volume", "atr_14"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise SignalServiceError(
            f"Faltan columnas requeridas en market_df: {', '.join(missing)}"
        )

    if len(df) < 30:
        raise SignalServiceError("No hay suficientes velas para detectar señales.")


def detect_breakout_trade_candidate(
    *,
    symbol: str,
    market_df: pd.DataFrame,
    trigger_index: int,
    entry_reference_price: float,
    stop_buffer_atr_fraction: float = 0.10,
    min_candles: int = 6,
    max_candles: int = 12,
    max_range_atr_multiple: float = 1.2,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
) -> TradeCandidate | None:
    """
    Detecta un setup en el histórico hasta trigger_index y construye un OrderPlan
    usando un precio de entrada de referencia inyectado por el caller.

    Esto desacopla la detección de señal de la simulación del backtest para que la
    misma lógica pueda reutilizarse más adelante en paper/live.
    """
    _validate_market_df(market_df)

    if not symbol:
        raise SignalServiceError("symbol no puede venir vacío.")

    if trigger_index < 29:
        return None

    if trigger_index >= len(market_df):
        raise SignalServiceError("trigger_index fuera de rango.")

    if entry_reference_price <= 0:
        raise SignalServiceError("entry_reference_price debe ser mayor a 0.")

    history_df = market_df.iloc[: trigger_index + 1].copy().reset_index(drop=True)

    setup = detect_breakout_setup(
        df_15m=history_df,
        min_candles=min_candles,
        max_candles=max_candles,
        max_range_atr_multiple=max_range_atr_multiple,
        min_volume_ratio=min_volume_ratio,
        max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
    )

    if not bool(setup.get("detected", False)):
        return None

    consolidation = setup.get("consolidation")
    breakout = setup.get("breakout")

    if not isinstance(consolidation, ConsolidationRange):
        raise SignalServiceError("consolidation inválido.")

    if not isinstance(breakout, BreakoutDetection):
        raise SignalServiceError("breakout inválido.")

    try:
        order_plan = build_breakout_order_plan(
            symbol=symbol,
            breakout=breakout,
            consolidation=consolidation,
            next_open_price=entry_reference_price,
            stop_buffer_atr_fraction=stop_buffer_atr_fraction,
        )
    except EntryRulesError:
        return None

    is_valid, validation_notes = validate_order_plan(order_plan)
    if not is_valid:
        return None

    setup_notes: list[str] = []
    raw_setup_notes = setup.get("notes", [])
    if raw_setup_notes:
        setup_notes.extend(str(note) for note in raw_setup_notes)
    if validation_notes:
        setup_notes.extend(str(note) for note in validation_notes)

    if setup_notes:
        order_plan.notes.extend(setup_notes)

    trigger_timestamp = pd.to_datetime(
        market_df.iloc[trigger_index]["timestamp"], utc=True
    )

    return TradeCandidate(
        order_plan=order_plan,
        setup_notes=setup_notes,
        trigger_index=trigger_index,
        trigger_timestamp=trigger_timestamp,
    )
