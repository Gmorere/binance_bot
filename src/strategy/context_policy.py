from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from src.strategy.context_filter import ContextFilterError, evaluate_combined_context
from src.strategy.signal_service import TradeCandidate


class ContextPolicyError(Exception):
    """Error relacionado con restricciones de contexto para research."""


def _normalize_allowed_sides(
    allowed_sides_by_symbol: Mapping[str, Sequence[str]] | None,
    symbol: str,
) -> set[str]:
    if not allowed_sides_by_symbol or symbol not in allowed_sides_by_symbol:
        return set()

    normalized = {
        str(side).strip().upper()
        for side in allowed_sides_by_symbol[symbol]
        if str(side).strip()
    }
    invalid = normalized.difference({"LONG", "SHORT"})
    if invalid:
        raise ContextPolicyError(
            f"allowed_sides invalido para {symbol}: {', '.join(sorted(invalid))}"
        )
    return normalized


def _slice_context_until_timestamp(
    df: pd.DataFrame,
    trigger_timestamp: pd.Timestamp,
) -> pd.DataFrame:
    sliced = df.loc[df["timestamp"] <= trigger_timestamp].copy()
    return sliced.reset_index(drop=True)


def evaluate_trade_candidate_policy(
    *,
    symbol: str,
    candidate: TradeCandidate,
    df_1h: pd.DataFrame | None,
    df_4h: pd.DataFrame | None,
    allowed_sides_by_symbol: Mapping[str, Sequence[str]] | None = None,
    enforce_context_alignment: bool = False,
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    candidate_side = str(candidate.order_plan.side).upper()

    allowed_sides = _normalize_allowed_sides(allowed_sides_by_symbol, symbol)
    if allowed_sides:
        notes.append(
            f"Allowed sides para {symbol}: {', '.join(sorted(allowed_sides))}."
        )
        if candidate_side not in allowed_sides:
            notes.append(
                f"Trade bloqueado por restriccion de lado: {candidate_side} no permitido."
            )
            return False, notes

    if not enforce_context_alignment:
        return True, notes

    if df_1h is None or df_4h is None:
        raise ContextPolicyError(
            "No se puede exigir contexto sin dataframes 1h y 4h."
        )

    context_1h = _slice_context_until_timestamp(df_1h, candidate.trigger_timestamp)
    context_4h = _slice_context_until_timestamp(df_4h, candidate.trigger_timestamp)

    try:
        combined = evaluate_combined_context(
            symbol=symbol,
            df_4h=context_4h,
            df_1h=context_1h,
        )
    except ContextFilterError as exc:
        notes.append(f"Trade bloqueado por contexto insuficiente: {exc}")
        return False, notes

    final_bias = str(combined["final_bias"]).upper()
    alignment = str(combined["alignment"]).upper()
    combined_score = float(combined["combined_score"])
    notes.append(
        "Contexto combinado "
        f"bias={final_bias} alignment={alignment} score={combined_score:.2f}."
    )

    if final_bias == "NEUTRAL":
        notes.append("Trade bloqueado por contexto neutral o mixto.")
        return False, notes

    if final_bias != candidate_side:
        notes.append(
            "Trade bloqueado por conflicto entre side del breakout "
            f"({candidate_side}) y contexto ({final_bias})."
        )
        return False, notes

    notes.append("Trade permitido por contexto alineado.")
    return True, notes
