from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


class ContextFilterError(Exception):
    """Error relacionado con evaluación de contexto de mercado."""


@dataclass
class ContextResult:
    symbol: str
    timeframe: str
    side_bias: str  # LONG, SHORT, NEUTRAL
    score: float
    price_vs_ema200: bool
    ema50_vs_ema200: bool
    ema_slope_positive: bool
    structure_bullish: bool
    structure_bearish: bool
    notes: list[str]


def _validate_context_df(df: pd.DataFrame, timeframe: str) -> None:
    required_cols = ["timestamp", "close", "ema_50", "ema_200"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ContextFilterError(
            f"Faltan columnas en contexto {timeframe}: {', '.join(missing)}"
        )

    if len(df) < 10:
        raise ContextFilterError(
            f"No hay suficientes filas para evaluar contexto en {timeframe}."
        )


def _ema50_slope_positive(df: pd.DataFrame, lookback: int = 5) -> bool:
    if len(df) < lookback + 1:
        return False
    return df["ema_50"].iloc[-1] > df["ema_50"].iloc[-1 - lookback]


def _ema50_slope_negative(df: pd.DataFrame, lookback: int = 5) -> bool:
    if len(df) < lookback + 1:
        return False
    return df["ema_50"].iloc[-1] < df["ema_50"].iloc[-1 - lookback]


def _detect_basic_structure(df: pd.DataFrame, lookback: int = 6) -> tuple[bool, bool]:
    """
    Estructura simple v1:
    - bullish si últimos cierres muestran progreso general alcista
    - bearish si muestran deterioro general bajista
    """
    closes = df["close"].tail(lookback).tolist()
    if len(closes) < lookback:
        return False, False

    bullish = closes[-1] > closes[0] and min(closes[-3:]) >= min(closes[:3])
    bearish = closes[-1] < closes[0] and max(closes[-3:]) <= max(closes[:3])

    return bullish, bearish


def evaluate_4h_context(symbol: str, df_4h: pd.DataFrame) -> ContextResult:
    _validate_context_df(df_4h, "4h")

    latest = df_4h.iloc[-1]
    notes: list[str] = []
    score = 0.0

    price_vs_ema200 = latest["close"] > latest["ema_200"]
    ema50_vs_ema200 = latest["ema_50"] > latest["ema_200"]
    ema_slope_positive = _ema50_slope_positive(df_4h)
    ema_slope_negative = _ema50_slope_negative(df_4h)
    structure_bullish, structure_bearish = _detect_basic_structure(df_4h)

    bullish_conditions = [
        price_vs_ema200,
        ema50_vs_ema200,
        ema_slope_positive,
        structure_bullish,
    ]
    bearish_conditions = [
        latest["close"] < latest["ema_200"],
        latest["ema_50"] < latest["ema_200"],
        ema_slope_negative,
        structure_bearish,
    ]

    bullish_count = sum(bullish_conditions)
    bearish_count = sum(bearish_conditions)

    if bullish_count >= 3:
        side_bias = "LONG"
        score = bullish_count / 4 * 100
        notes.append("Contexto 4H favorable para LONG.")
    elif bearish_count >= 3:
        side_bias = "SHORT"
        score = bearish_count / 4 * 100
        notes.append("Contexto 4H favorable para SHORT.")
    else:
        side_bias = "NEUTRAL"
        score = max(bullish_count, bearish_count) / 4 * 100
        notes.append("Contexto 4H neutral o mixto.")

    if price_vs_ema200:
        notes.append("Precio sobre EMA 200.")
    else:
        notes.append("Precio bajo EMA 200.")

    if ema50_vs_ema200:
        notes.append("EMA 50 sobre EMA 200.")
    else:
        notes.append("EMA 50 bajo EMA 200.")

    if ema_slope_positive:
        notes.append("Pendiente EMA 50 positiva.")
    elif ema_slope_negative:
        notes.append("Pendiente EMA 50 negativa.")
    else:
        notes.append("Pendiente EMA 50 plana o poco clara.")

    if structure_bullish:
        notes.append("Estructura reciente alcista.")
    if structure_bearish:
        notes.append("Estructura reciente bajista.")

    return ContextResult(
        symbol=symbol,
        timeframe="4h",
        side_bias=side_bias,
        score=score,
        price_vs_ema200=price_vs_ema200,
        ema50_vs_ema200=ema50_vs_ema200,
        ema_slope_positive=ema_slope_positive,
        structure_bullish=structure_bullish,
        structure_bearish=structure_bearish,
        notes=notes,
    )


def evaluate_1h_bias(symbol: str, df_1h: pd.DataFrame) -> ContextResult:
    _validate_context_df(df_1h, "1h")

    latest = df_1h.iloc[-1]
    notes: list[str] = []
    score = 0.0

    if "ema_20" not in df_1h.columns:
        raise ContextFilterError("Falta columna ema_20 en 1h.")

    price_above_ema50 = latest["close"] > latest["ema_50"]
    ema20_above_ema50 = latest["ema_20"] > latest["ema_50"]
    ema_slope_positive = _ema50_slope_positive(df_1h)
    ema_slope_negative = _ema50_slope_negative(df_1h)
    structure_bullish, structure_bearish = _detect_basic_structure(df_1h)

    bullish_conditions = [
        price_above_ema50,
        ema20_above_ema50,
        ema_slope_positive,
        structure_bullish,
    ]
    bearish_conditions = [
        latest["close"] < latest["ema_50"],
        latest["ema_20"] < latest["ema_50"],
        ema_slope_negative,
        structure_bearish,
    ]

    bullish_count = sum(bullish_conditions)
    bearish_count = sum(bearish_conditions)

    if bullish_count >= 3:
        side_bias = "LONG"
        score = bullish_count / 4 * 100
        notes.append("Sesgo 1H favorable para LONG.")
    elif bearish_count >= 3:
        side_bias = "SHORT"
        score = bearish_count / 4 * 100
        notes.append("Sesgo 1H favorable para SHORT.")
    else:
        side_bias = "NEUTRAL"
        score = max(bullish_count, bearish_count) / 4 * 100
        notes.append("Sesgo 1H neutral o mixto.")

    if price_above_ema50:
        notes.append("Precio sobre EMA 50.")
    else:
        notes.append("Precio bajo EMA 50.")

    if ema20_above_ema50:
        notes.append("EMA 20 sobre EMA 50.")
    else:
        notes.append("EMA 20 bajo EMA 50.")

    if ema_slope_positive:
        notes.append("Pendiente EMA 50 positiva.")
    elif ema_slope_negative:
        notes.append("Pendiente EMA 50 negativa.")
    else:
        notes.append("Pendiente EMA 50 plana o poco clara.")

    if structure_bullish:
        notes.append("Estructura reciente alcista.")
    if structure_bearish:
        notes.append("Estructura reciente bajista.")

    return ContextResult(
        symbol=symbol,
        timeframe="1h",
        side_bias=side_bias,
        score=score,
        price_vs_ema200=latest["close"] > latest["ema_200"],
        ema50_vs_ema200=latest["ema_50"] > latest["ema_200"],
        ema_slope_positive=ema_slope_positive,
        structure_bullish=structure_bullish,
        structure_bearish=structure_bearish,
        notes=notes,
    )


def evaluate_combined_context(
    symbol: str,
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame,
) -> dict[str, object]:
    context_4h = evaluate_4h_context(symbol, df_4h)
    bias_1h = evaluate_1h_bias(symbol, df_1h)

    combined_notes = context_4h.notes + bias_1h.notes

    if context_4h.side_bias == bias_1h.side_bias and context_4h.side_bias != "NEUTRAL":
        final_bias = context_4h.side_bias
        alignment = "ALIGNED"
    elif context_4h.side_bias == "NEUTRAL" or bias_1h.side_bias == "NEUTRAL":
        final_bias = "NEUTRAL"
        alignment = "PARTIAL"
    else:
        final_bias = "NEUTRAL"
        alignment = "CONFLICT"

    combined_score = (context_4h.score * 0.55) + (bias_1h.score * 0.45)

    return {
        "symbol": symbol,
        "final_bias": final_bias,
        "alignment": alignment,
        "combined_score": combined_score,
        "context_4h": context_4h,
        "bias_1h": bias_1h,
        "notes": combined_notes,
    }