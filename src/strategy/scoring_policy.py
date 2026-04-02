from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from src.risk.risk_engine import RiskEngineError, map_score_to_risk
from src.strategy.context_filter import ContextFilterError, evaluate_combined_context
from src.strategy.scoring_engine import ScoringEngineError, build_score
from src.strategy.signal_service import TradeCandidate


class ScoringPolicyError(Exception):
    """Error relacionado con scoring operativo del setup."""


@dataclass
class CandidateRiskResolution:
    trade_allowed: bool
    risk_pct: float
    risk_bucket: str
    score_total: float
    notes: list[str]


def _slice_context_until_timestamp(
    df: pd.DataFrame,
    trigger_timestamp: pd.Timestamp,
) -> pd.DataFrame:
    sliced = df.loc[df["timestamp"] <= trigger_timestamp].copy()
    return sliced.reset_index(drop=True)


def resolve_candidate_risk_from_score(
    *,
    symbol: str,
    candidate: TradeCandidate,
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    score_thresholds: Mapping[str, float | int],
    risk_by_score: Mapping[str, float | int],
    open_positions: int = 0,
    same_side_exposure_count: int = 0,
) -> CandidateRiskResolution:
    if df_1h is None or df_4h is None:
        raise ScoringPolicyError(
            "No se puede resolver riesgo por score sin dataframes 1h y 4h."
        )

    context_1h = _slice_context_until_timestamp(df_1h, candidate.trigger_timestamp)
    context_4h = _slice_context_until_timestamp(df_4h, candidate.trigger_timestamp)

    try:
        combined = evaluate_combined_context(
            symbol=symbol,
            df_4h=context_4h,
            df_1h=context_1h,
        )
        scoring = build_score(
            symbol=symbol,
            final_bias=str(combined["final_bias"]).upper(),
            alignment=str(combined["alignment"]).upper(),
            context_score=float(combined["combined_score"]),
            setup_detected=True,
            consolidation_detected=candidate.setup_type == "BREAKOUT",
            breakout_detected=candidate.setup_type == "BREAKOUT",
            volume_ratio=float(candidate.volume_ratio),
            trigger_too_extended=bool(candidate.trigger_too_extended),
            open_positions=int(open_positions),
            same_side_exposure_count=int(same_side_exposure_count),
            min_trade_threshold=float(score_thresholds["min_trade"]),
            aggressive_threshold=float(score_thresholds["aggressive"]),
            exceptional_threshold=float(score_thresholds["exceptional"]),
        )
        risk_decision = map_score_to_risk(
            total_score=float(scoring.total_score),
            min_trade_threshold=float(score_thresholds["min_trade"]),
            aggressive_threshold=float(score_thresholds["aggressive"]),
            exceptional_threshold=float(score_thresholds["exceptional"]),
            risk_small=float(risk_by_score["small"]),
            risk_normal=float(risk_by_score["normal"]),
            risk_strong=float(risk_by_score["strong"]),
            risk_exceptional=float(risk_by_score["exceptional"]),
        )
    except (ContextFilterError, ScoringEngineError, RiskEngineError, KeyError) as exc:
        raise ScoringPolicyError(f"No se pudo resolver riesgo dinamico: {exc}") from exc

    notes = [
        (
            "Score setup="
            f"{scoring.total_score:.2f} "
            f"(mtf={scoring.mtf_alignment:.2f}, "
            f"structure={scoring.structure:.2f}, "
            f"momentum={scoring.momentum:.2f}, "
            f"regime={scoring.regime:.2f}, "
            f"volume={scoring.volume:.2f}, "
            f"liquidity={scoring.liquidity:.2f}, "
            f"correlation={scoring.correlation:.2f})"
        ),
        f"Score risk bucket resuelto: {risk_decision.risk_bucket.lower()}",
        f"Score risk_pct resuelto: {risk_decision.risk_pct:.4f}",
    ]
    notes.extend(str(note) for note in combined.get("notes", []))
    notes.extend(str(note) for note in scoring.notes)
    notes.extend(str(note) for note in risk_decision.notes)

    return CandidateRiskResolution(
        trade_allowed=bool(risk_decision.trade_allowed),
        risk_pct=float(risk_decision.risk_pct),
        risk_bucket=str(risk_decision.risk_bucket).strip().lower(),
        score_total=float(scoring.total_score),
        notes=notes,
    )
