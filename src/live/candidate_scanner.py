from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import pandas as pd

from src.strategy.signal_service import TradeCandidate, detect_breakout_trade_candidate


class CandidateScannerError(Exception):
    """Error relacionado con scan de candidatos operables."""


EntryPriceResolver = Callable[[str, pd.DataFrame, int], float]


@dataclass(frozen=True)
class SymbolCandidate:
    symbol: str
    candidate: TradeCandidate


def _default_entry_price_resolver(
    symbol: str,
    market_df: pd.DataFrame,
    trigger_index: int,
) -> float:
    del symbol
    if trigger_index >= len(market_df):
        raise CandidateScannerError("trigger_index fuera de rango para resolver entry.")
    return float(market_df.iloc[trigger_index]["close"])


def scan_trade_candidates(
    *,
    market_data_by_symbol: Mapping[str, pd.DataFrame],
    entry_price_resolver: EntryPriceResolver | None = None,
    trigger_index_by_symbol: Mapping[str, int] | None = None,
    stop_buffer_atr_fraction: float = 0.10,
    min_candles: int = 6,
    max_candles: int = 12,
    max_range_atr_multiple: float = 1.2,
    min_volume_ratio: float = 1.0,
    max_trigger_candle_atr_multiple: float = 1.8,
) -> list[SymbolCandidate]:
    resolver = entry_price_resolver or _default_entry_price_resolver
    results: list[SymbolCandidate] = []

    for symbol, market_df in market_data_by_symbol.items():
        if market_df.empty:
            continue

        trigger_index = (
            int(trigger_index_by_symbol[symbol])
            if trigger_index_by_symbol and symbol in trigger_index_by_symbol
            else len(market_df) - 1
        )

        entry_reference_price = resolver(symbol, market_df, trigger_index)
        candidate = detect_breakout_trade_candidate(
            symbol=symbol,
            market_df=market_df,
            trigger_index=trigger_index,
            entry_reference_price=entry_reference_price,
            stop_buffer_atr_fraction=stop_buffer_atr_fraction,
            min_candles=min_candles,
            max_candles=max_candles,
            max_range_atr_multiple=max_range_atr_multiple,
            min_volume_ratio=min_volume_ratio,
            max_trigger_candle_atr_multiple=max_trigger_candle_atr_multiple,
        )

        if candidate is not None:
            results.append(SymbolCandidate(symbol=symbol, candidate=candidate))

    return results
