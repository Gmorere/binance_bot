from __future__ import annotations

from dataclasses import dataclass


class ScoringEngineError(Exception):
    """Error relacionado con cálculo de score del setup."""


@dataclass
class ScoringResult:
    total_score: float
    mtf_alignment: float
    structure: float
    momentum: float
    regime: float
    volume: float
    liquidity: float
    correlation: float
    trade_allowed: bool
    aggressive_allowed: bool
    exceptional_allowed: bool
    notes: list[str]


def _score_mtf_alignment(final_bias: str, alignment: str) -> tuple[float, list[str]]:
    notes: list[str] = []

    if final_bias == "NEUTRAL":
        notes.append("Bias final neutral.")
        return 0.0, notes

    if alignment == "ALIGNED":
        notes.append("4H y 1H alineados.")
        return 15.0, notes

    if alignment == "PARTIAL":
        notes.append("Alineación parcial entre 4H y 1H.")
        return 8.0, notes

    notes.append("Conflicto entre timeframes.")
    return 0.0, notes


def _score_structure(
    setup_detected: bool,
    consolidation_detected: bool,
    breakout_detected: bool,
) -> tuple[float, list[str]]:
    notes: list[str] = []

    if not setup_detected:
        notes.append("No hay setup detectado.")
        return 0.0, notes

    if consolidation_detected and breakout_detected:
        notes.append("Consolidación + breakout detectados.")
        return 15.0, notes

    if consolidation_detected:
        notes.append("Hay consolidación, pero no breakout confirmado.")
        return 7.0, notes

    notes.append("Estructura insuficiente.")
    return 0.0, notes


def _score_momentum(volume_ratio: float, trigger_too_extended: bool) -> tuple[float, list[str]]:
    notes: list[str] = []

    if trigger_too_extended:
        notes.append("Vela gatillo demasiado extendida.")
        return 0.0, notes

    if volume_ratio >= 1.5:
        notes.append("Momentum fuerte por volumen.")
        return 12.0, notes

    if volume_ratio >= 1.0:
        notes.append("Momentum aceptable por volumen.")
        return 8.0, notes

    notes.append("Momentum débil.")
    return 3.0, notes


def _score_regime(context_score: float, final_bias: str) -> tuple[float, list[str]]:
    notes: list[str] = []

    if final_bias == "NEUTRAL":
        notes.append("Régimen mixto o neutral.")
        return 2.0, notes

    if context_score >= 85:
        notes.append("Régimen muy favorable.")
        return 12.0, notes

    if context_score >= 70:
        notes.append("Régimen favorable.")
        return 9.0, notes

    if context_score >= 55:
        notes.append("Régimen aceptable.")
        return 6.0, notes

    notes.append("Régimen débil.")
    return 2.0, notes


def _score_volume(volume_ratio: float) -> tuple[float, list[str]]:
    notes: list[str] = []

    if volume_ratio >= 1.8:
        notes.append("Volumen excelente.")
        return 10.0, notes

    if volume_ratio >= 1.3:
        notes.append("Volumen fuerte.")
        return 8.0, notes

    if volume_ratio >= 1.0:
        notes.append("Volumen suficiente.")
        return 6.0, notes

    notes.append("Volumen pobre.")
    return 2.0, notes


def _score_liquidity(symbol: str) -> tuple[float, list[str]]:
    notes: list[str] = []

    top_liquidity = {"BTCUSDT", "ETHUSDT"}
    good_liquidity = {"SOLUSDT", "BNBUSDT", "XRPUSDT"}

    if symbol in top_liquidity:
        notes.append("Liquidez excelente.")
        return 9.0, notes

    if symbol in good_liquidity:
        notes.append("Liquidez buena.")
        return 7.0, notes

    notes.append("Liquidez media o desconocida.")
    return 5.0, notes


def _score_correlation(open_positions: int, same_side_exposure_count: int) -> tuple[float, list[str]]:
    notes: list[str] = []

    if open_positions == 0:
        notes.append("Sin posiciones abiertas.")
        return 12.0, notes

    if same_side_exposure_count == 0:
        notes.append("Sin exposición correlacionada relevante.")
        return 10.0, notes

    if same_side_exposure_count == 1:
        notes.append("Exposición correlacionada moderada.")
        return 7.0, notes

    if same_side_exposure_count == 2:
        notes.append("Exposición correlacionada alta.")
        return 4.0, notes

    notes.append("Exposición correlacionada excesiva.")
    return 0.0, notes


def build_score(
    *,
    symbol: str,
    final_bias: str,
    alignment: str,
    context_score: float,
    setup_detected: bool,
    consolidation_detected: bool,
    breakout_detected: bool,
    volume_ratio: float,
    trigger_too_extended: bool,
    open_positions: int,
    same_side_exposure_count: int,
    min_trade_threshold: float = 70.0,
    aggressive_threshold: float = 85.0,
    exceptional_threshold: float = 93.0,
) -> ScoringResult:
    notes: list[str] = []

    mtf_alignment, mtf_notes = _score_mtf_alignment(final_bias, alignment)
    structure, structure_notes = _score_structure(
        setup_detected=setup_detected,
        consolidation_detected=consolidation_detected,
        breakout_detected=breakout_detected,
    )
    momentum, momentum_notes = _score_momentum(
        volume_ratio=volume_ratio,
        trigger_too_extended=trigger_too_extended,
    )
    regime, regime_notes = _score_regime(
        context_score=context_score,
        final_bias=final_bias,
    )
    volume, volume_notes = _score_volume(volume_ratio)
    liquidity, liquidity_notes = _score_liquidity(symbol)
    correlation, correlation_notes = _score_correlation(
        open_positions=open_positions,
        same_side_exposure_count=same_side_exposure_count,
    )

    notes.extend(mtf_notes)
    notes.extend(structure_notes)
    notes.extend(momentum_notes)
    notes.extend(regime_notes)
    notes.extend(volume_notes)
    notes.extend(liquidity_notes)
    notes.extend(correlation_notes)

    total_score = (
        mtf_alignment
        + structure
        + momentum
        + regime
        + volume
        + liquidity
        + correlation
    )

    trade_allowed = total_score >= min_trade_threshold
    aggressive_allowed = total_score >= aggressive_threshold
    exceptional_allowed = total_score >= exceptional_threshold

    return ScoringResult(
        total_score=total_score,
        mtf_alignment=mtf_alignment,
        structure=structure,
        momentum=momentum,
        regime=regime,
        volume=volume,
        liquidity=liquidity,
        correlation=correlation,
        trade_allowed=trade_allowed,
        aggressive_allowed=aggressive_allowed,
        exceptional_allowed=exceptional_allowed,
        notes=notes,
    )