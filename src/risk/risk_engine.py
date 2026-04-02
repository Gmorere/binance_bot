from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class RiskEngineError(Exception):
    """Error relacionado con reglas de riesgo del sistema."""


@dataclass
class RiskDecision:
    trade_allowed: bool
    risk_pct: float
    risk_bucket: str
    aggressive_allowed: bool
    exceptional_allowed: bool
    notes: list[str]


def get_risk_pct_for_bucket(
    *,
    risk_by_score: Mapping[str, float],
    risk_bucket: str,
) -> tuple[float, list[str]]:
    normalized_bucket = str(risk_bucket).strip().lower()
    if not normalized_bucket:
        raise RiskEngineError("risk_bucket no puede venir vacio.")

    if normalized_bucket not in risk_by_score:
        raise RiskEngineError(f"No existe risk.risk_by_score.{normalized_bucket}.")

    risk_pct = float(risk_by_score[normalized_bucket])
    if not (0 <= risk_pct < 1):
        raise RiskEngineError(
            f"risk_pct invalido para bucket {normalized_bucket}: {risk_pct}"
        )

    notes = [
        f"Risk bucket aplicado: {normalized_bucket}",
        f"risk_pct configurado: {risk_pct:.4f}",
    ]
    return risk_pct, notes


def map_score_to_risk(
    total_score: float,
    min_trade_threshold: float,
    aggressive_threshold: float,
    exceptional_threshold: float,
    risk_small: float,
    risk_normal: float,
    risk_strong: float,
    risk_exceptional: float,
) -> RiskDecision:
    notes: list[str] = []

    if total_score < min_trade_threshold:
        notes.append("Score bajo el mínimo requerido. No se permite trade.")
        return RiskDecision(
            trade_allowed=False,
            risk_pct=0.0,
            risk_bucket="NO_TRADE",
            aggressive_allowed=False,
            exceptional_allowed=False,
            notes=notes,
        )

    if total_score >= exceptional_threshold:
        notes.append("Score excepcional. Se permite riesgo excepcional.")
        return RiskDecision(
            trade_allowed=True,
            risk_pct=risk_exceptional,
            risk_bucket="EXCEPTIONAL",
            aggressive_allowed=True,
            exceptional_allowed=True,
            notes=notes,
        )

    if total_score >= aggressive_threshold:
        notes.append("Score fuerte. Se permite riesgo agresivo.")
        return RiskDecision(
            trade_allowed=True,
            risk_pct=risk_strong,
            risk_bucket="STRONG",
            aggressive_allowed=True,
            exceptional_allowed=False,
            notes=notes,
        )

    if total_score >= min_trade_threshold + 5:
        notes.append("Score normal. Se asigna riesgo base.")
        return RiskDecision(
            trade_allowed=True,
            risk_pct=risk_normal,
            risk_bucket="NORMAL",
            aggressive_allowed=False,
            exceptional_allowed=False,
            notes=notes,
        )

    notes.append("Score mínimo apenas cumplido. Se asigna riesgo pequeño.")
    return RiskDecision(
        trade_allowed=True,
        risk_pct=risk_small,
        risk_bucket="SMALL",
        aggressive_allowed=False,
        exceptional_allowed=False,
        notes=notes,
    )


def portfolio_allows_new_trade(
    *,
    current_open_positions: int,
    max_open_positions: int,
    current_open_risk_pct: float,
    candidate_risk_pct: float,
    max_open_risk_pct: float,
) -> tuple[bool, list[str]]:
    notes: list[str] = []

    if current_open_positions >= max_open_positions:
        notes.append("Máximo de posiciones abiertas alcanzado.")
        return False, notes

    projected_open_risk = current_open_risk_pct + candidate_risk_pct
    if projected_open_risk > max_open_risk_pct:
        notes.append(
            f"El riesgo agregado proyectado ({projected_open_risk:.4f}) supera el máximo permitido ({max_open_risk_pct:.4f})."
        )
        return False, notes

    notes.append("Portafolio permite abrir nueva posición.")
    return True, notes


def system_loss_limits_allow_trade(
    *,
    daily_drawdown_pct: float,
    weekly_drawdown_pct: float,
    daily_limit_pct: float,
    weekly_limit_pct: float,
) -> tuple[bool, list[str]]:
    notes: list[str] = []

    if daily_drawdown_pct >= daily_limit_pct:
        notes.append("Límite diario de pérdida alcanzado.")
        return False, notes

    if weekly_drawdown_pct >= weekly_limit_pct:
        notes.append("Límite semanal de pérdida alcanzado.")
        return False, notes

    notes.append("Límites diarios y semanales OK.")
    return True, notes
