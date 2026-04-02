from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import pandas as pd

from src.strategy.signal_service import TradeCandidate, detect_breakout_trade_candidate


class CandidateScannerError(Exception):
    """Error relacionado con scan de candidatos operables."""


EntryPriceResolver = Callable[[str, pd.DataFrame, int], float]
TradeCandidateResolver = Callable[[str, pd.DataFrame, int, float], TradeCandidate | None]


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


def _default_trade_candidate_resolver(
    symbol: str,
    market_df: pd.DataFrame,
    trigger_index: int,
    entry_reference_price: float,
) -> TradeCandidate | None:
    return detect_breakout_trade_candidate(
        symbol=symbol,
        market_df=market_df,
        trigger_index=trigger_index,
        entry_reference_price=entry_reference_price,
    )


def scan_trade_candidates(
    *,
    market_data_by_symbol: Mapping[str, pd.DataFrame],
    entry_price_resolver: EntryPriceResolver | None = None,
    trade_candidate_resolver: TradeCandidateResolver | None = None,
    trigger_index_by_symbol: Mapping[str, int] | None = None,
) -> list[SymbolCandidate]:
    resolver = entry_price_resolver or _default_entry_price_resolver
    candidate_resolver = trade_candidate_resolver or _default_trade_candidate_resolver
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
        candidate = candidate_resolver(
            symbol,
            market_df,
            trigger_index,
            entry_reference_price,
        )

        if candidate is not None:
            results.append(SymbolCandidate(symbol=symbol, candidate=candidate))

    return results
