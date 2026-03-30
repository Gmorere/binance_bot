from __future__ import annotations

import unittest

import pandas as pd

from src.data.binance_kline_updater import (
    filter_closed_klines,
    merge_ohlcv_frames,
    refresh_ohlcv_dataframe,
)


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


if __name__ == "__main__":
    unittest.main()
