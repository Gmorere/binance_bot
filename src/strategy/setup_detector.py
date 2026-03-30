from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


class SetupDetectorError(Exception):
    """Error relacionado con detección de setups."""


@dataclass
class ConsolidationRange:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    high: float
    low: float
    range_size: float
    atr_value: float
    candle_count: int


@dataclass
class BreakoutDetection:
    detected: bool
    side: str  # LONG | SHORT | NONE
    breakout_level: Optional[float]
    trigger_close: Optional[float]
    volume_ratio: float
    notes: list[str]


def _validate_entry_df(df: pd.DataFrame) -> None:
    required_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "atr_14",
    ]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise SetupDetectorError(
            f"Faltan columnas requeridas en entry dataframe: {', '.join(missing)}"
        )

    if len(df) < 30:
        raise SetupDetectorError(
            "No hay suficientes velas para detectar setup en 15m."
        )


def find_recent_consolidation(
    df_15m: pd.DataFrame,
    min_candles: int = 6,
    max_candles: int = 12,
    max_range_atr_multiple: float = 1.2,
) -> Optional[ConsolidationRange]:
    """
    Busca una consolidación reciente en la ventana final del dataframe.
    Recorre de mayor a menor número de velas.
    """
    _validate_entry_df(df_15m)

    latest_atr = float(df_15m["atr_14"].iloc[-2])  # usamos la vela previa a la gatillo
    if latest_atr <= 0:
        return None

    for window in range(max_candles, min_candles - 1, -1):
        segment = df_15m.iloc[-(window + 1):-1].copy()  # excluye la última vela
        seg_high = float(segment["high"].max())
        seg_low = float(segment["low"].min())
        seg_range = seg_high - seg_low

        if seg_range <= latest_atr * max_range_atr_multiple:
            return ConsolidationRange(
                start_time=segment["timestamp"].iloc[0],
                end_time=segment["timestamp"].iloc[-1],
                high=seg_high,
                low=seg_low,
                range_size=seg_range,
                atr_value=latest_atr,
                candle_count=window,
            )

    return None


def _compute_volume_ratio(
    df_15m: pd.DataFrame,
    lookback: int = 20,
) -> float:
    if len(df_15m) < lookback + 1:
        return 0.0

    trigger_volume = float(df_15m["volume"].iloc[-1])
    avg_volume = float(df_15m["volume"].iloc[-(lookback + 1):-1].mean())

    if avg_volume <= 0:
        return 0.0

    return trigger_volume / avg_volume


def _trigger_candle_too_extended(
    df_15m: pd.DataFrame,
    max_trigger_candle_atr_multiple: float = 1.8,
) -> bool:
    latest = df_15m.iloc[-1]
    candle_size = float(latest["high"] - latest["low"])
    atr_value = float(latest["atr_14"])

    if atr_value <= 0:
        return True

    return candle_size > atr_value * max_trigger_candle_atr_multiple


def detect_breakout_from_consolidation(
    df_15m: pd.DataFrame,
    consolidation: ConsolidationRange,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
) -> BreakoutDetection:
    """
    Detecta si la última vela rompe una consolidación previa.
    """
    _validate_entry_df(df_15m)

    latest = df_15m.iloc[-1]
    latest_close = float(latest["close"])
    volume_ratio = _compute_volume_ratio(df_15m)
    notes: list[str] = []

    if _trigger_candle_too_extended(df_15m, max_trigger_candle_atr_multiple):
        notes.append("Vela gatillo demasiado extendida.")
        return BreakoutDetection(
            detected=False,
            side="NONE",
            breakout_level=None,
            trigger_close=latest_close,
            volume_ratio=volume_ratio,
            notes=notes,
        )

    if volume_ratio < min_volume_ratio:
        notes.append("Volumen insuficiente para validar breakout.")
        return BreakoutDetection(
            detected=False,
            side="NONE",
            breakout_level=None,
            trigger_close=latest_close,
            volume_ratio=volume_ratio,
            notes=notes,
        )

    if latest_close > consolidation.high:
        notes.append("Breakout LONG detectado.")
        return BreakoutDetection(
            detected=True,
            side="LONG",
            breakout_level=consolidation.high,
            trigger_close=latest_close,
            volume_ratio=volume_ratio,
            notes=notes,
        )

    if latest_close < consolidation.low:
        notes.append("Breakout SHORT detectado.")
        return BreakoutDetection(
            detected=True,
            side="SHORT",
            breakout_level=consolidation.low,
            trigger_close=latest_close,
            volume_ratio=volume_ratio,
            notes=notes,
        )

    notes.append("Sin ruptura válida de consolidación.")
    return BreakoutDetection(
        detected=False,
        side="NONE",
        breakout_level=None,
        trigger_close=latest_close,
        volume_ratio=volume_ratio,
        notes=notes,
    )


def detect_breakout_setup(
    df_15m: pd.DataFrame,
    min_candles: int = 6,
    max_candles: int = 12,
    max_range_atr_multiple: float = 1.2,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
) -> dict[str, object]:
    """
    Wrapper principal para detectar setup de breakout.
    """
    consolidation = find_recent_consolidation(
        df_15m=df_15m,
        min_candles=min_candles,
        max_candles=max_candles,
        max_range_atr_multiple=max_range_atr_multiple,
    )

    if consolidation is None:
        return {
            "setup_type": "BREAKOUT",
            "detected": False,
            "consolidation": None,
            "breakout": None,
            "notes": ["No se detectó consolidación válida."],
        }

    breakout = detect_breakout_from_consolidation(
        df_15m=df_15m,
        consolidation=consolidation,
        min_volume_ratio=min_volume_ratio,
        max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
    )

    return {
        "setup_type": "BREAKOUT",
        "detected": breakout.detected,
        "consolidation": consolidation,
        "breakout": breakout,
        "notes": breakout.notes,
    }