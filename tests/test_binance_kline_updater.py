from __future__ import annotations

import unittest

import pandas as pd
import requests

from src.data.binance_kline_updater import (
    BinanceKlineUpdaterError,
    filter_closed_klines,
    fetch_binance_klines,
    merge_ohlcv_frames,
    refresh_ohlcv_dataframe,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: list[list[object]] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error

    def json(self) -> list[list[object]]:
        return self._payload


class _SequencedSession:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def get(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        self.call_count += 1
        if not self._responses:
            raise RuntimeError("No hay mas respuestas configuradas.")
        next_response = self._responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response  # type: ignore[return-value]


class BinanceKlineUpdaterTests(unittest.TestCase):
    def test_filter_closed_klines_drops_open_candle(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000.0,
                },
                {
                    "timestamp": pd.Timestamp("2026-01-01T00:15:00Z"),
                    "open": 100.5,
                    "high": 101.5,
                    "low": 100.0,
                    "close": 101.0,
                    "volume": 1100.0,
                },
            ]
        )

        filtered = filter_closed_klines(
            df,
            "15m",
            now_ms=int(pd.Timestamp("2026-01-01T00:20:00Z").timestamp() * 1000),
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(str(filtered.iloc[0]["timestamp"]), "2026-01-01 00:00:00+00:00")

    def test_merge_ohlcv_frames_deduplicates_and_keeps_latest_row(self) -> None:
        existing = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000.0,
                }
            ]
        )
        incoming = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.5,
                    "volume": 1200.0,
                },
                {
                    "timestamp": pd.Timestamp("2026-01-01T00:15:00Z"),
                    "open": 101.5,
                    "high": 103.0,
                    "low": 101.0,
                    "close": 102.0,
                    "volume": 1300.0,
                },
            ]
        )

        merged = merge_ohlcv_frames(existing, incoming, symbol="BTCUSDT", timeframe="15m")

        self.assertEqual(len(merged), 2)
        self.assertEqual(float(merged.iloc[0]["close"]), 101.5)
        self.assertEqual(float(merged.iloc[1]["close"]), 102.0)

    def test_refresh_ohlcv_dataframe_appends_only_new_closed_candles(self) -> None:
        existing = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000.0,
                }
            ]
        )

        def fake_fetch(_symbol: str, _timeframe: str, start_time_ms: int | None, _limit: int) -> list[list[object]]:
            if start_time_ms is None:
                return []
            return [
                [1767226500000, "100.5", "101.5", "100.0", "101.0", "1100", 0, 0, 0, 0, 0, 0],
                [1767227400000, "101.0", "102.0", "100.8", "101.8", "1200", 0, 0, 0, 0, 0, 0],
            ]

        refreshed = refresh_ohlcv_dataframe(
            existing_df=existing,
            symbol="BTCUSDT",
            timeframe="15m",
            fetch_klines_fn=fake_fetch,
            now_ms=int(pd.Timestamp("2026-01-01T00:40:00Z").timestamp() * 1000),
            limit=500,
        )

        self.assertEqual(len(refreshed), 2)
        self.assertEqual(str(refreshed.iloc[-1]["timestamp"]), "2026-01-01 00:15:00+00:00")

    def test_fetch_binance_klines_retries_on_retryable_http_status(self) -> None:
        session = _SequencedSession(
            [
                _FakeResponse(status_code=503),
                _FakeResponse(status_code=200, payload=[[1, "1", "1", "1", "1", "1"]]),
            ]
        )
        sleep_calls: list[float] = []

        result = fetch_binance_klines(
            "BTCUSDT",
            "15m",
            session=session,  # type: ignore[arg-type]
            max_retries=2,
            retry_backoff_ms=1000,
            sleep_fn=sleep_calls.append,
        )

        self.assertEqual(session.call_count, 2)
        self.assertEqual(sleep_calls, [1.0])
        self.assertEqual(result, [[1, "1", "1", "1", "1", "1"]])

    def test_fetch_binance_klines_does_not_retry_on_non_retryable_http_status(self) -> None:
        session = _SequencedSession(
            [
                _FakeResponse(status_code=451),
                _FakeResponse(status_code=200, payload=[[1, "1", "1", "1", "1", "1"]]),
            ]
        )
        sleep_calls: list[float] = []

        with self.assertRaises(BinanceKlineUpdaterError):
            fetch_binance_klines(
                "BTCUSDT",
                "15m",
                session=session,  # type: ignore[arg-type]
                max_retries=2,
                retry_backoff_ms=1000,
                sleep_fn=sleep_calls.append,
            )

        self.assertEqual(session.call_count, 1)
        self.assertEqual(sleep_calls, [])

    def test_fetch_binance_klines_retries_on_request_exception(self) -> None:
        session = _SequencedSession(
            [
                requests.ConnectionError("network down"),
                _FakeResponse(status_code=200, payload=[[1, "1", "1", "1", "1", "1"]]),
            ]
        )
        sleep_calls: list[float] = []

        result = fetch_binance_klines(
            "BTCUSDT",
            "15m",
            session=session,  # type: ignore[arg-type]
            max_retries=2,
            retry_backoff_ms=500,
            sleep_fn=sleep_calls.append,
        )

        self.assertEqual(session.call_count, 2)
        self.assertEqual(sleep_calls, [0.5])
        self.assertEqual(result, [[1, "1", "1", "1", "1", "1"]])


if __name__ == "__main__":
    unittest.main()
