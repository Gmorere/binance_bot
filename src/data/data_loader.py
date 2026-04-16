from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd


Timeframe = Literal["15m", "1h", "4h"]


class DataLoaderError(Exception):
    """Error relacionado con carga o validación de datos históricos."""


REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def build_symbol_file_path(
    raw_data_path: str | Path,
    symbol: str,
    timeframe: Timeframe,
) -> Path:
    """
    Construye la ruta esperada para un archivo CSV de un símbolo/timeframe.
    """
    return Path(raw_data_path) / f"{symbol}_{timeframe}.csv"


def validate_ohlcv_dataframe(
    df: pd.DataFrame,
    symbol: str,
    timeframe: Timeframe,
) -> pd.DataFrame:
    """
    Valida estructura mínima y tipos del dataframe OHLCV.
    """
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise DataLoaderError(
            f"Faltan columnas en {symbol} {timeframe}: {', '.join(missing_columns)}"
        )

    validated = df.loc[:, REQUIRED_COLUMNS].copy()

    # Pandas 3.0: no usar .loc para asignar tipos incompatibles con el dtype de la columna.
    validated = validated.assign(
        timestamp=pd.to_datetime(validated["timestamp"], utc=True, errors="coerce"),
        open=pd.to_numeric(validated["open"], errors="coerce"),
        high=pd.to_numeric(validated["high"], errors="coerce"),
        low=pd.to_numeric(validated["low"], errors="coerce"),
        close=pd.to_numeric(validated["close"], errors="coerce"),
        volume=pd.to_numeric(validated["volume"], errors="coerce"),
    )

    numeric_cols = ["open", "high", "low", "close", "volume"]

    if validated["timestamp"].isna().any():
        raise DataLoaderError(f"Hay timestamps inválidos en {symbol} {timeframe}.")

    if validated[numeric_cols].isna().any().any():
        raise DataLoaderError(f"Hay valores OHLCV inválidos en {symbol} {timeframe}.")

    validated = validated.sort_values("timestamp").reset_index(drop=True)

    if validated["timestamp"].duplicated().any():
        raise DataLoaderError(f"Hay timestamps duplicados en {symbol} {timeframe}.")

    if (validated["high"] < validated["low"]).any():
        raise DataLoaderError(f"Hay filas con high < low en {symbol} {timeframe}.")

    price_cols = ["open", "high", "low", "close"]
    if (validated[price_cols] <= 0).any().any():
        raise DataLoaderError(f"Hay precios no positivos en {symbol} {timeframe}.")

    if (validated["volume"] < 0).any():
        raise DataLoaderError(f"Hay volúmenes negativos en {symbol} {timeframe}.")

    return validated


def load_ohlcv_csv(
    file_path: str | Path,
    symbol: str,
    timeframe: Timeframe,
) -> pd.DataFrame:
    """
    Carga un archivo CSV OHLCV y lo valida.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo: {path}")

    if not path.is_file():
        raise DataLoaderError(f"La ruta no es un archivo válido: {path}")

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise DataLoaderError(f"Error leyendo CSV {path}: {exc}") from exc

    return validate_ohlcv_dataframe(df, symbol, timeframe)


def load_symbol_timeframe_data(
    raw_data_path: str | Path,
    symbol: str,
    timeframe: Timeframe,
) -> pd.DataFrame:
    """
    Carga los datos OHLCV de un símbolo y timeframe.
    """
    file_path = build_symbol_file_path(raw_data_path, symbol, timeframe)
    return load_ohlcv_csv(file_path, symbol, timeframe)


def load_symbol_bundle(
    raw_data_path: str | Path,
    symbol: str,
    timeframes: list[Timeframe] | tuple[Timeframe, ...] = ("15m", "1h", "4h"),
) -> dict[Timeframe, pd.DataFrame]:
    """
    Carga múltiples timeframes para un mismo símbolo.
    """
    bundle: dict[Timeframe, pd.DataFrame] = {}

    for timeframe in timeframes:
        bundle[timeframe] = load_symbol_timeframe_data(raw_data_path, symbol, timeframe)

    return bundle


def load_all_symbols(
    raw_data_path: str | Path,
    symbols: list[str],
    timeframes: list[Timeframe] | tuple[Timeframe, ...] = ("15m", "1h", "4h"),
) -> dict[str, dict[Timeframe, pd.DataFrame]]:
    """
    Carga todos los símbolos y timeframes configurados.
    """
    all_data: dict[str, dict[Timeframe, pd.DataFrame]] = {}

    for symbol in symbols:
        all_data[symbol] = load_symbol_bundle(raw_data_path, symbol, timeframes)

    return all_data


def summarize_dataframe(df: pd.DataFrame) -> dict[str, object]:
    """
    Devuelve un resumen simple del dataframe para debug rápido.
    """
    return {
        "rows": len(df),
        "start": df["timestamp"].min(),
        "end": df["timestamp"].max(),
        "columns": list(df.columns),
    }


if __name__ == "__main__":
    base_path = Path("D:/binance_futures_bot/data/raw")
    sample_symbol = "BTCUSDT"

    try:
        bundle = load_symbol_bundle(base_path, sample_symbol)
        for tf, df in bundle.items():
            summary = summarize_dataframe(df)
            print(f"{sample_symbol} {tf} -> {summary}")
    except Exception as exc:
        print(f"Error cargando datos: {exc}")