from __future__ import annotations

import unittest

import pandas as pd

from src.features.indicators import add_basic_indicators
from src.live.candidate_scanner import scan_trade_candidates


def _build_breakout_market_df() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    start = pd.Timestamp("2026-01-01T00:00:00Z")

    for i in range(35):
        timestamp = start + pd.Timedelta(minutes=15 * i)

        if i < 22:
            open_price = 100 + (i * 0.3)
            close_price = open_price + 0.1
            high_price = close_price + 0.2
            low_price = open_price - 0.2
            volume = 1000
        elif 22 <= i <= 33:
            open_price = 105.0
            close_price = 105.1
            high_price = 105.4
            low_price = 104.8
            volume = 1000
        else:
            open_price = 106.5
            close_price = 107.0
            high_price = 107.2
            low_price = 106.2
            volume = 2200

        rows.append(
            {
                "timestamp": timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )

    return add_basic_indicators(pd.DataFrame(rows))


class CandidateScannerTests(unittest.TestCase):
    def test_scan_trade_candidates_returns_only_symbols_with_candidate(self) -> None:
        candidate_df = _build_breakout_market_df()
        flat_rows: list[dict[str, object]] = []
        start = pd.Timestamp("2026-01-01T00:00:00Z")

        for i in range(35):
            flat_rows.append(
                {
                    "timestamp": start + pd.Timedelta(minutes=15 * i),
                    "open": 100.0,
                    "high": 100.2,
                    "low": 99.8,
                    "close": 100.0,
                    "volume": 500.0,
                }
            )

        flat_df = add_basic_indicators(pd.DataFrame(flat_rows))

        results = scan_trade_candidates(
            market_data_by_symbol={
                "BTCUSDT": candidate_df,
                "ETHUSDT": flat_df,
            },
            entry_price_resolver=lambda _symbol, df, idx: float(df.iloc[idx]["close"]),
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].symbol, "BTCUSDT")
        self.assertEqual(results[0].candidate.order_plan.symbol, "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
