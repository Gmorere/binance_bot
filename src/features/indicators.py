from __future__ import annotations

import pandas as pd


class IndicatorError(Exception):
    """Error relacionado con cálculo de indicadores."""


def validate_price_dataframe(df: pd.DataFrame) -> None:
    required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise IndicatorError(
            f"Faltan columnas requeridas para indicadores: {', '.join(missing)}"
        )

    if df.empty:
        raise IndicatorError("El dataframe está vacío; no se pueden calcular indicadores.")


def add_ema(df: pd.DataFrame, period: int, source_col: str = "close") -> pd.DataFrame:
    """
    Agrega una EMA al dataframe.
    """
    validate_price_dataframe(df)

    if source_col not in df.columns:
        raise IndicatorError(f"No existe la columna fuente: {source_col}")

    result = df.copy()
    ema_col = f"ema_{period}"
    result.loc[:, ema_col] = result[source_col].ewm(span=period, adjust=False).mean()
    return result


def add_multiple_emas(
    df: pd.DataFrame,
    periods: list[int] | tuple[int, ...] = (20, 50, 200),
    source_col: str = "close",
) -> pd.DataFrame:
    """
    Agrega múltiples EMAs al dataframe.
    """
    result = df.copy()
    for period in periods:
        result = add_ema(result, period, source_col=source_col)
    return result


def add_true_range(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega True Range (TR) al dataframe.
    """
    validate_price_dataframe(df)

    result = df.copy()
    prev_close = result["close"].shift(1)

    high_low = result["high"] - result["low"]
    high_prev_close = (result["high"] - prev_close).abs()
    low_prev_close = (result["low"] - prev_close).abs()

    tr_series = pd.concat(
        [high_low, high_prev_close, low_prev_close], axis=1
    ).max(axis=1)

    result.loc[:, "tr"] = tr_series
    return result


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Agrega ATR (Average True Range) al dataframe.
    """
    result = add_true_range(df)
    atr_col = f"atr_{period}"
    result.loc[:, atr_col] = result["tr"].ewm(alpha=1 / period, adjust=False).mean()
    return result


def add_atr_percent(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Agrega ATR expresado como porcentaje del cierre.
    """
    result = add_atr(df, period=period)
    atr_col = f"atr_{period}"
    atr_pct_col = f"atr_pct_{period}"

    result.loc[:, atr_pct_col] = result[atr_col] / result["close"]
    return result


def add_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline base de indicadores para la estrategia v1.
    Incluye:
    - EMA 20
    - EMA 50
    - EMA 200
    - TR
    - ATR 14
    - ATR % 14
    """
    result = df.copy()
    result = add_multiple_emas(result, periods=(20, 50, 200))
    result = add_atr(result, period=14)
    result = add_atr_percent(result, period=14)
    return result


if __name__ == "__main__":
    sample_data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=10, freq="h", tz="UTC"),
            "open": [100, 101, 102, 101, 103, 104, 105, 104, 106, 107],
            "high": [101, 102, 103, 102, 104, 105, 106, 105, 107, 108],
            "low": [99, 100, 101, 100, 102, 103, 104, 103, 105, 106],
            "close": [100.5, 101.5, 102.5, 101.2, 103.4, 104.2, 105.3, 104.6, 106.1, 107.2],
            "volume": [1000, 1200, 1100, 1050, 1300, 1500, 1700, 1600, 1800, 1900],
        }
    )

    enriched = add_basic_indicators(sample_data)
    print(enriched.tail())