from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

import pandas as pd

from src.data.binance_kline_updater import (
    BinanceKlineUpdaterError,
    INTERVAL_TO_MS,
    RefreshResult,
    refresh_symbol_timeframe_csv,
)
from src.data.data_loader import load_all_symbols
from src.exchange.binance_usdm_client import BinanceUsdmClient
from src.features.indicators import add_basic_indicators
from src.live.runtime_config import load_runtime_config


class MarketDataRuntimeError(Exception):
    """Error relacionado con carga de market data para runtime."""


OutputFn = Callable[[str], None]
RefreshCsvFn = Callable[..., RefreshResult]


@dataclass(frozen=True)
class MarketDataSnapshot:
    entry_timeframe: str
    market_data_by_symbol: dict[str, pd.DataFrame]
    latest_timestamps: dict[str, str]
    bias_market_data_by_symbol: dict[str, pd.DataFrame] = field(default_factory=dict)
    context_market_data_by_symbol: dict[str, pd.DataFrame] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketDataPollResult:
    snapshot: MarketDataSnapshot
    refresh_results: list[RefreshResult]
    next_poll_after_ms: int | None


class PollingMarketDataService:
    def __init__(
        self,
        config: Mapping[str, object],
        *,
        output_fn: OutputFn = print,
        refresh_symbol_timeframe_csv_fn: RefreshCsvFn = refresh_symbol_timeframe_csv,
    ) -> None:
        self.config = config
        self.output_fn = output_fn
        self.refresh_symbol_timeframe_csv_fn = refresh_symbol_timeframe_csv_fn
        self.runtime = load_runtime_config(config)
        self._cached_snapshot: MarketDataSnapshot | None = None
        self._next_refresh_after_ms: int | None = None
        self._last_refresh_error_count: int = 0

    def poll(self, *, now_ms: int | None = None) -> MarketDataPollResult:
        resolved_now_ms = _resolve_now_ms(now_ms)

        if self.runtime.refresh_from_binance_rest and self._should_skip_refresh(resolved_now_ms):
            self.output_fn(
                "data_refresh_skip "
                f"now_ms={resolved_now_ms} next_refresh_after_ms={self._next_refresh_after_ms}"
            )
            return MarketDataPollResult(
                snapshot=self._cached_snapshot,  # type: ignore[arg-type]
                refresh_results=[],
                next_poll_after_ms=self._next_refresh_after_ms,
            )

        refresh_results = self.refresh_entry_market_data(now_ms=resolved_now_ms)
        try:
            snapshot = self.load_entry_market_snapshot()
        except Exception as exc:
            if self._cached_snapshot is None:
                raise
            snapshot = self._cached_snapshot
            self.output_fn(
                "data_snapshot_fallback "
                f"error={type(exc).__name__}: {exc} using_cached_snapshot=true"
            )
        next_poll_after_ms = resolved_now_ms + int(self.runtime.poll_interval_seconds) * 1000

        if self.runtime.refresh_from_binance_rest:
            self._cached_snapshot = snapshot
            self._next_refresh_after_ms = self._calculate_next_refresh_after_ms(
                snapshot,
                now_ms=resolved_now_ms,
            )
            if self._last_refresh_error_count > 0:
                error_cooldown_ms = int(self.runtime.refresh_error_backoff_seconds) * 1000
                self._next_refresh_after_ms = max(
                    int(self._next_refresh_after_ms),
                    resolved_now_ms + error_cooldown_ms,
                )
                self.output_fn(
                    "data_refresh_error_backoff "
                    f"errors={self._last_refresh_error_count} "
                    f"backoff_seconds={self.runtime.refresh_error_backoff_seconds}"
                )
            next_poll_after_ms = self._next_refresh_after_ms
            self.output_fn(
                "data_refresh_schedule "
                f"next_refresh_after_ms={self._next_refresh_after_ms}"
            )

        return MarketDataPollResult(
            snapshot=snapshot,
            refresh_results=refresh_results,
            next_poll_after_ms=next_poll_after_ms,
        )

    def refresh_entry_market_data(self, *, now_ms: int | None = None) -> list[RefreshResult]:
        if not self.runtime.refresh_from_binance_rest:
            return []

        try:
            data_cfg = self.config["data"]  # type: ignore[index]
            timeframes_cfg = self.config["timeframes"]  # type: ignore[index]
            symbols_cfg = self.config["symbols"]  # type: ignore[index]
        except KeyError as exc:
            raise MarketDataRuntimeError(f"Config incompleta para refresh market data: {exc}") from exc

        raw_data_path = str(data_cfg["raw_data_path"])
        symbols = list(symbols_cfg["enabled"])
        resolved_now_ms = _resolve_now_ms(now_ms)
        base_url = _resolve_market_data_base_url(self.runtime.use_testnet_market_data)
        timeframes_to_refresh = _resolve_runtime_timeframes(timeframes_cfg)

        results: list[RefreshResult] = []
        refresh_errors = 0
        for symbol in symbols:
            for timeframe in timeframes_to_refresh:
                try:
                    result = self.refresh_symbol_timeframe_csv_fn(
                        raw_data_path=raw_data_path,
                        symbol=symbol,
                        timeframe=timeframe,
                        now_ms=resolved_now_ms,
                        limit=self.runtime.market_data_limit,
                        base_url=base_url,
                        timeout_seconds=self.runtime.timeout_seconds,
                        max_retries=self.runtime.rest_max_retries,
                        retry_backoff_ms=self.runtime.rest_retry_backoff_ms,
                    )
                except (BinanceKlineUpdaterError, OSError, ValueError) as exc:
                    refresh_errors += 1
                    self.output_fn(
                        "data_refresh_error "
                        f"symbol={symbol} timeframe={timeframe} error={type(exc).__name__}: {exc}"
                    )
                    continue

                results.append(result)
                self.output_fn(
                    "data_refresh "
                    f"symbol={result.symbol} timeframe={result.timeframe} "
                    f"new_rows={result.new_rows} rows_after={result.rows_after} "
                    f"latest_timestamp={result.latest_timestamp}"
                )

        self._last_refresh_error_count = refresh_errors
        return results

    def load_entry_market_snapshot(self) -> MarketDataSnapshot:
        try:
            data_cfg = self.config["data"]  # type: ignore[index]
            timeframes_cfg = self.config["timeframes"]  # type: ignore[index]
            symbols_cfg = self.config["symbols"]  # type: ignore[index]
        except KeyError as exc:
            raise MarketDataRuntimeError(f"Config incompleta para market data: {exc}") from exc

        raw_data_path = str(data_cfg["raw_data_path"])
        entry_timeframe = str(timeframes_cfg["entry"])
        bias_timeframe = str(timeframes_cfg["bias"]) if "bias" in timeframes_cfg else None
        context_timeframe = str(timeframes_cfg["context"]) if "context" in timeframes_cfg else None
        symbols = list(symbols_cfg["enabled"])
        load_timeframes = _resolve_runtime_timeframes(timeframes_cfg)

        bundles = load_all_symbols(
            raw_data_path=raw_data_path,
            symbols=symbols,
            timeframes=tuple(load_timeframes),
        )

        market_data_by_symbol = {
            symbol: add_basic_indicators(bundle[entry_timeframe]).reset_index(drop=True)
            for symbol, bundle in bundles.items()
        }
        bias_market_data_by_symbol = {
            symbol: add_basic_indicators(bundle[bias_timeframe]).reset_index(drop=True)
            for symbol, bundle in bundles.items()
            if bias_timeframe is not None
        }
        context_market_data_by_symbol = {
            symbol: add_basic_indicators(bundle[context_timeframe]).reset_index(drop=True)
            for symbol, bundle in bundles.items()
            if context_timeframe is not None
        }
        latest_timestamps = {
            symbol: str(pd.to_datetime(df.iloc[-1]["timestamp"], utc=True))
            for symbol, df in market_data_by_symbol.items()
            if not df.empty
        }

        return MarketDataSnapshot(
            entry_timeframe=entry_timeframe,
            market_data_by_symbol=market_data_by_symbol,
            latest_timestamps=latest_timestamps,
            bias_market_data_by_symbol=bias_market_data_by_symbol,
            context_market_data_by_symbol=context_market_data_by_symbol,
        )

    def _should_skip_refresh(self, now_ms: int) -> bool:
        return (
            self._cached_snapshot is not None
            and self._next_refresh_after_ms is not None
            and now_ms < self._next_refresh_after_ms
        )

    def _calculate_next_refresh_after_ms(
        self,
        snapshot: MarketDataSnapshot,
        *,
        now_ms: int,
    ) -> int:
        interval_ms = _resolve_interval_ms(snapshot.entry_timeframe)
        grace_ms = int(self.runtime.candle_close_grace_seconds) * 1000
        min_spacing_ms = int(self.runtime.poll_interval_seconds) * 1000

        if snapshot.latest_timestamps:
            # Los timestamps OHLCV de Binance representan apertura de vela.
            # Si la ultima vela cerrada tiene apertura T, la siguiente vela
            # "nueva cerrada" aparece recien en T + 2*intervalo.
            candidate_refreshes = [
                _timestamp_to_ms(timestamp_str) + (2 * interval_ms) + grace_ms
                for timestamp_str in snapshot.latest_timestamps.values()
            ]
            candle_close_due_ms = min(candidate_refreshes)
        else:
            candle_close_due_ms = (
                _next_interval_boundary_ms(now_ms, interval_ms) + interval_ms + grace_ms
            )

        return max(candle_close_due_ms, now_ms + min_spacing_ms)


def _resolve_runtime_timeframes(timeframes_cfg: Mapping[str, object]) -> list[str]:
    timeframes: list[str] = []
    for key in ("entry", "bias", "context"):
        if key not in timeframes_cfg:
            continue
        normalized = str(timeframes_cfg[key]).strip()
        if normalized and normalized not in timeframes:
            timeframes.append(normalized)
    if not timeframes:
        raise MarketDataRuntimeError("Config incompleta para market data: falta timeframe entry.")
    return timeframes


def _resolve_market_data_base_url(use_testnet_market_data: bool) -> str:
    return (
        BinanceUsdmClient.TESTNET_BASE_URL
        if use_testnet_market_data
        else BinanceUsdmClient.PROD_BASE_URL
    )


def _resolve_now_ms(now_ms: int | None) -> int:
    return int(now_ms if now_ms is not None else time.time() * 1000)


def _resolve_interval_ms(timeframe: str) -> int:
    try:
        return int(INTERVAL_TO_MS[timeframe])
    except KeyError as exc:
        raise MarketDataRuntimeError(
            f"Timeframe no soportado para polling market data: {timeframe}"
        ) from exc


def _timestamp_to_ms(timestamp_str: str) -> int:
    return int(pd.Timestamp(timestamp_str).timestamp() * 1000)


def _next_interval_boundary_ms(now_ms: int, interval_ms: int) -> int:
    return ((now_ms // interval_ms) + 1) * interval_ms


def build_market_data_service(
    config: Mapping[str, object],
    *,
    output_fn: OutputFn = print,
    refresh_symbol_timeframe_csv_fn: RefreshCsvFn = refresh_symbol_timeframe_csv,
) -> PollingMarketDataService:
    return PollingMarketDataService(
        config,
        output_fn=output_fn,
        refresh_symbol_timeframe_csv_fn=refresh_symbol_timeframe_csv_fn,
    )


def refresh_entry_market_data(
    config: Mapping[str, object],
    *,
    now_ms: int | None = None,
    output_fn: OutputFn = print,
    refresh_symbol_timeframe_csv_fn: RefreshCsvFn = refresh_symbol_timeframe_csv,
) -> list[RefreshResult]:
    service = build_market_data_service(
        config,
        output_fn=output_fn,
        refresh_symbol_timeframe_csv_fn=refresh_symbol_timeframe_csv_fn,
    )
    return service.refresh_entry_market_data(now_ms=now_ms)


def load_entry_market_snapshot(
    config: Mapping[str, object],
    *,
    now_ms: int | None = None,
    output_fn: OutputFn = print,
    refresh_symbol_timeframe_csv_fn: RefreshCsvFn = refresh_symbol_timeframe_csv,
) -> MarketDataSnapshot:
    service = build_market_data_service(
        config,
        output_fn=output_fn,
        refresh_symbol_timeframe_csv_fn=refresh_symbol_timeframe_csv_fn,
    )
    if now_ms is not None:
        return service.poll(now_ms=now_ms).snapshot
    return service.poll().snapshot


def detect_symbols_with_new_candles(
    latest_timestamps: Mapping[str, str],
    processed_candle_timestamps: Mapping[str, str],
) -> list[str]:
    return sorted(
        symbol
        for symbol, latest_timestamp in latest_timestamps.items()
        if processed_candle_timestamps.get(symbol) != latest_timestamp
    )

