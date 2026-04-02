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


@dataclass
class PullbackRange:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    high: float
    low: float
    candle_count: int
    atr_value: float
    impulse_start_time: pd.Timestamp
    impulse_end_time: pd.Timestamp
    impulse_start_close: float
    impulse_end_close: float
    impulse_size: float
    retrace_size: float
    side: str  # LONG | SHORT


@dataclass
class PullbackDetection:
    detected: bool
    side: str  # LONG | SHORT | NONE
    trigger_level: Optional[float]
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


def _trigger_candle_body_too_extended(
    df_15m: pd.DataFrame,
    max_trigger_body_atr_multiple: float | None = None,
) -> bool:
    if max_trigger_body_atr_multiple is None:
        return False

    latest = df_15m.iloc[-1]
    candle_body = abs(float(latest["close"] - latest["open"]))
    atr_value = float(latest["atr_14"])

    if atr_value <= 0:
        return True

    return candle_body > atr_value * max_trigger_body_atr_multiple


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


def find_recent_pullback(
    df_15m: pd.DataFrame,
    *,
    impulse_lookback_candles: int = 6,
    min_pullback_candles: int = 2,
    max_pullback_candles: int = 5,
    min_impulse_atr_multiple: float = 1.8,
    min_retrace_ratio: float = 0.25,
    max_retrace_ratio: float = 0.60,
) -> Optional[PullbackRange]:
    _validate_entry_df(df_15m)

    if impulse_lookback_candles <= 0:
        raise SetupDetectorError("impulse_lookback_candles debe ser mayor a 0.")
    if min_pullback_candles <= 0 or max_pullback_candles <= 0:
        raise SetupDetectorError("min_pullback_candles y max_pullback_candles deben ser mayores a 0.")
    if min_pullback_candles > max_pullback_candles:
        raise SetupDetectorError("min_pullback_candles no puede ser mayor que max_pullback_candles.")

    latest_atr = float(df_15m["atr_14"].iloc[-2])
    if latest_atr <= 0:
        return None

    for pullback_window in range(max_pullback_candles, min_pullback_candles - 1, -1):
        pullback_end_index = len(df_15m) - 2
        pullback_start_index = pullback_end_index - pullback_window + 1
        impulse_end_index = pullback_start_index - 1
        impulse_start_index = impulse_end_index - impulse_lookback_candles + 1

        if impulse_start_index < 0:
            continue

        pullback_segment = df_15m.iloc[pullback_start_index : pullback_end_index + 1].copy()
        impulse_segment = df_15m.iloc[impulse_start_index : impulse_end_index + 1].copy()

        impulse_start_close = float(impulse_segment["close"].iloc[0])
        impulse_end_close = float(impulse_segment["close"].iloc[-1])
        pullback_start_close = float(pullback_segment["close"].iloc[0])
        pullback_end_close = float(pullback_segment["close"].iloc[-1])
        pullback_high = float(pullback_segment["high"].max())
        pullback_low = float(pullback_segment["low"].min())

        impulse_down_size = impulse_start_close - impulse_end_close
        if impulse_down_size >= latest_atr * min_impulse_atr_multiple:
            retrace_size = pullback_high - impulse_end_close
            retrace_ratio = retrace_size / impulse_down_size if impulse_down_size > 0 else 0.0
            if (
                min_retrace_ratio <= retrace_ratio <= max_retrace_ratio
                and pullback_end_close > pullback_start_close
            ):
                return PullbackRange(
                    start_time=pullback_segment["timestamp"].iloc[0],
                    end_time=pullback_segment["timestamp"].iloc[-1],
                    high=pullback_high,
                    low=pullback_low,
                    candle_count=int(pullback_window),
                    atr_value=latest_atr,
                    impulse_start_time=impulse_segment["timestamp"].iloc[0],
                    impulse_end_time=impulse_segment["timestamp"].iloc[-1],
                    impulse_start_close=impulse_start_close,
                    impulse_end_close=impulse_end_close,
                    impulse_size=impulse_down_size,
                    retrace_size=retrace_size,
                    side="SHORT",
                )

        impulse_up_size = impulse_end_close - impulse_start_close
        if impulse_up_size >= latest_atr * min_impulse_atr_multiple:
            retrace_size = impulse_end_close - pullback_low
            retrace_ratio = retrace_size / impulse_up_size if impulse_up_size > 0 else 0.0
            if (
                min_retrace_ratio <= retrace_ratio <= max_retrace_ratio
                and pullback_end_close < pullback_start_close
            ):
                return PullbackRange(
                    start_time=pullback_segment["timestamp"].iloc[0],
                    end_time=pullback_segment["timestamp"].iloc[-1],
                    high=pullback_high,
                    low=pullback_low,
                    candle_count=int(pullback_window),
                    atr_value=latest_atr,
                    impulse_start_time=impulse_segment["timestamp"].iloc[0],
                    impulse_end_time=impulse_segment["timestamp"].iloc[-1],
                    impulse_start_close=impulse_start_close,
                    impulse_end_close=impulse_end_close,
                    impulse_size=impulse_up_size,
                    retrace_size=retrace_size,
                    side="LONG",
                )

    return None


def detect_pullback_continuation(
    df_15m: pd.DataFrame,
    pullback: PullbackRange,
    *,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
    max_trigger_body_atr_multiple: float | None = None,
) -> PullbackDetection:
    _validate_entry_df(df_15m)

    latest = df_15m.iloc[-1]
    latest_close = float(latest["close"])
    latest_open = float(latest["open"])
    volume_ratio = _compute_volume_ratio(df_15m)
    notes: list[str] = []

    if _trigger_candle_too_extended(df_15m, max_trigger_candle_atr_multiple):
        notes.append("Vela gatillo demasiado extendida para pullback.")
        return PullbackDetection(
            detected=False,
            side="NONE",
            trigger_level=None,
            trigger_close=latest_close,
            volume_ratio=volume_ratio,
            notes=notes,
        )

    if _trigger_candle_body_too_extended(df_15m, max_trigger_body_atr_multiple):
        notes.append("Cuerpo de vela gatillo demasiado extendido para pullback.")
        return PullbackDetection(
            detected=False,
            side="NONE",
            trigger_level=None,
            trigger_close=latest_close,
            volume_ratio=volume_ratio,
            notes=notes,
        )

    if volume_ratio < min_volume_ratio:
        notes.append("Volumen insuficiente para validar pullback.")
        return PullbackDetection(
            detected=False,
            side="NONE",
            trigger_level=None,
            trigger_close=latest_close,
            volume_ratio=volume_ratio,
            notes=notes,
        )

    if pullback.side == "SHORT":
        trigger_level = pullback.low
        if latest_close < trigger_level and latest_close < latest_open:
            notes.append("Pullback continuation SHORT detectado.")
            return PullbackDetection(
                detected=True,
                side="SHORT",
                trigger_level=trigger_level,
                trigger_close=latest_close,
                volume_ratio=volume_ratio,
                notes=notes,
            )
    elif pullback.side == "LONG":
        trigger_level = pullback.high
        if latest_close > trigger_level and latest_close > latest_open:
            notes.append("Pullback continuation LONG detectado.")
            return PullbackDetection(
                detected=True,
                side="LONG",
                trigger_level=trigger_level,
                trigger_close=latest_close,
                volume_ratio=volume_ratio,
                notes=notes,
            )

    notes.append("Sin reanudacion valida de pullback.")
    return PullbackDetection(
        detected=False,
        side="NONE",
        trigger_level=None,
        trigger_close=latest_close,
        volume_ratio=volume_ratio,
        notes=notes,
    )


def detect_pullback_setup(
    df_15m: pd.DataFrame,
    *,
    impulse_lookback_candles: int = 6,
    min_pullback_candles: int = 2,
    max_pullback_candles: int = 5,
    min_impulse_atr_multiple: float = 1.8,
    min_retrace_ratio: float = 0.25,
    max_retrace_ratio: float = 0.60,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
    max_trigger_body_atr_multiple: float | None = None,
) -> dict[str, object]:
    pullback = find_recent_pullback(
        df_15m=df_15m,
        impulse_lookback_candles=impulse_lookback_candles,
        min_pullback_candles=min_pullback_candles,
        max_pullback_candles=max_pullback_candles,
        min_impulse_atr_multiple=min_impulse_atr_multiple,
        min_retrace_ratio=min_retrace_ratio,
        max_retrace_ratio=max_retrace_ratio,
    )

    if pullback is None:
        return {
            "setup_type": "PULLBACK",
            "detected": False,
            "pullback": None,
            "reentry": None,
            "notes": ["No se detecto estructura de pullback valida."],
        }

    reentry = detect_pullback_continuation(
        df_15m=df_15m,
        pullback=pullback,
        min_volume_ratio=min_volume_ratio,
        max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
        max_trigger_body_atr_multiple=max_trigger_body_atr_multiple,
    )

    return {
        "setup_type": "PULLBACK",
        "detected": reentry.detected,
        "pullback": pullback,
        "reentry": reentry,
        "notes": reentry.notes,
    }
