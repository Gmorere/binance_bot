from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from src.data.data_loader import build_symbol_file_path, validate_ohlcv_dataframe


BASE_URL = "https://fapi.binance.com"
INTERVAL_TO_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
}


class BinanceKlineUpdaterError(Exception):
    """Error relacionado con refresh incremental de klines Binance."""


FetchKlinesFn = Callable[[str, str, int | None, int], list[list[Any]]]


@dataclass(frozen=True)
class RefreshResult:
    symbol: str
    timeframe: str
    rows_before: int
    rows_after: int
    new_rows: int
    latest_timestamp: str | None


def _validate_supported_timeframe(timeframe: str) -> None:
    if timeframe not in INTERVAL_TO_MS:
        raise BinanceKlineUpdaterError(
            f"Timeframe no soportado para refresh incremental: {timeframe}"
        )


def fetch_binance_klines(
    symbol: str,
    timeframe: str,
    start_time_ms: int | None = None,
    limit: int = 500,
    *,
    base_url: str = BASE_URL,
    timeout_seconds: int = 30,
    session: requests.Session | None = None,
) -> list[list[Any]]:
    _validate_supported_timeframe(timeframe)
    if not symbol:
        raise BinanceKlineUpdaterError("symbol no puede venir vacío.")
    if limit <= 0 or limit > 1500:
        raise BinanceKlineUpdaterError("limit debe estar entre 1 y 1500.")

    params: dict[str, Any] = {
        "symbol": symbol,
        "interval": timeframe,
        "limit": limit,
    }
    if start_time_ms is not None:
        params["startTime"] = start_time_ms

    http = session or requests.Session()
    try:
        response = http.get(
            f"{base_url}/fapi/v1/klines",
            params=params,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BinanceKlineUpdaterError(
            f"Error consultando klines Binance para {symbol} {timeframe}: {exc}"
        ) from exc

    payload = response.json()
    if not isinstance(payload, list):
        raise BinanceKlineUpdaterError("Respuesta inesperada de klines Binance.")

    return payload


def normalize_rest_klines(raw_klines: list[list[Any]]) -> pd.DataFrame:
    if not raw_klines:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(raw_klines)
    if df.shape[1] < 6:
        raise BinanceKlineUpdaterError("Payload de klines inválido: columnas insuficientes.")

    normalized = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df.iloc[:, 0], unit="ms", utc=True, errors="coerce"),
            "open": pd.to_numeric(df.iloc[:, 1], errors="coerce"),
            "high": pd.to_numeric(df.iloc[:, 2], errors="coerce"),
            "low": pd.to_numeric(df.iloc[:, 3], errors="coerce"),
            "close": pd.to_numeric(df.iloc[:, 4], errors="coerce"),
            "volume": pd.to_numeric(df.iloc[:, 5], errors="coerce"),
        }
    )

    normalized = normalized.dropna().reset_index(drop=True)
    return normalized[["timestamp", "open", "high", "low", "close", "volume"]]


def filter_closed_klines(
    df: pd.DataFrame,
    timeframe: str,
    *,
    now_ms: int,
) -> pd.DataFrame:
    _validate_supported_timeframe(timeframe)
    if df.empty:
        return df.copy()

    interval_ms = INTERVAL_TO_MS[timeframe]
    timestamps_ms = (df["timestamp"].astype("int64") // 10**6).astype("int64")
    closed_mask = (timestamps_ms + interval_ms) <= int(now_ms)
    return df.loc[closed_mask].reset_index(drop=True)


def merge_ohlcv_frames(
    existing_df: pd.DataFrame,
    incoming_df: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    if existing_df.empty:
        return validate_ohlcv_dataframe(incoming_df, symbol, timeframe)
    if incoming_df.empty:
        return validate_ohlcv_dataframe(existing_df, symbol, timeframe)

    merged = pd.concat([existing_df, incoming_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    return validate_ohlcv_dataframe(merged, symbol, timeframe)


def refresh_ohlcv_dataframe(
    *,
    existing_df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    fetch_klines_fn: FetchKlinesFn,
    now_ms: int,
    limit: int = 500,
) -> pd.DataFrame:
    _validate_supported_timeframe(timeframe)
    merged_df = existing_df.copy()
    cursor_ms = None
    if not existing_df.empty:
        cursor_ms = int(pd.Timestamp(existing_df["timestamp"].iloc[-1]).timestamp() * 1000)

    while True:
        batch = fetch_klines_fn(symbol, timeframe, cursor_ms, limit)
        normalized = normalize_rest_klines(batch)
        normalized = filter_closed_klines(normalized, timeframe, now_ms=now_ms)

        if cursor_ms is not None and not normalized.empty:
            normalized = normalized.loc[normalized["timestamp"] > pd.to_datetime(cursor_ms, unit="ms", utc=True)].reset_index(drop=True)

        if normalized.empty:
            break

        merged_df = merge_ohlcv_frames(
            merged_df,
            normalized,
            symbol=symbol,
            timeframe=timeframe,
        )

        last_timestamp_ms = int(pd.Timestamp(normalized["timestamp"].iloc[-1]).timestamp() * 1000)
        if cursor_ms is not None and last_timestamp_ms <= cursor_ms:
            break

        interval_ms = INTERVAL_TO_MS[timeframe]
        cursor_ms = last_timestamp_ms + interval_ms
        if len(batch) < limit:
            break

    if merged_df.empty:
        return merged_df

    return validate_ohlcv_dataframe(merged_df, symbol, timeframe)


def refresh_symbol_timeframe_csv(
    *,
    raw_data_path: str | Path,
    symbol: str,
    timeframe: str,
    now_ms: int,
    limit: int = 500,
    base_url: str = BASE_URL,
    timeout_seconds: int = 30,
) -> RefreshResult:
    file_path = build_symbol_file_path(raw_data_path, symbol, timeframe)
    if file_path.exists():
        existing_df = pd.read_csv(file_path)
        existing_df = validate_ohlcv_dataframe(existing_df, symbol, timeframe)
    else:
        existing_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def _fetch(symbol_arg: str, timeframe_arg: str, start_time_ms: int | None, batch_limit: int) -> list[list[Any]]:
        return fetch_binance_klines(
            symbol=symbol_arg,
            timeframe=timeframe_arg,
            start_time_ms=start_time_ms,
            limit=batch_limit,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    refreshed_df = refresh_ohlcv_dataframe(
        existing_df=existing_df,
        symbol=symbol,
        timeframe=timeframe,
        fetch_klines_fn=_fetch,
        now_ms=now_ms,
        limit=limit,
    )

    file_path.parent.mkdir(parents=True, exist_ok=True)
    refreshed_df.to_csv(file_path, index=False)

    latest_timestamp = None
    if not refreshed_df.empty:
        latest_timestamp = str(pd.to_datetime(refreshed_df["timestamp"].iloc[-1], utc=True))

    return RefreshResult(
        symbol=symbol,
        timeframe=timeframe,
        rows_before=len(existing_df),
        rows_after=len(refreshed_df),
        new_rows=len(refreshed_df) - len(existing_df),
        latest_timestamp=latest_timestamp,
    )
