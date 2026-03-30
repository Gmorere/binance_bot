from __future__ import annotations

from dataclasses import dataclass


class SizingEngineError(Exception):
    """Error relacionado con cálculo de tamaño de posición."""


@dataclass
class PositionSizingResult:
    equity: float
    risk_pct: float
    risk_amount_usdt: float
    entry_price: float
    stop_price: float
    stop_distance: float
    position_size_units: float
    notional_value_usdt: float
    leverage: float
    max_notional_allowed_usdt: float
    sizing_allowed: bool
    notes: list[str]


def calculate_position_size(
    *,
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    leverage: float,
    max_notional_pct: float,
) -> PositionSizingResult:
    notes: list[str] = []

    if equity <= 0:
        raise SizingEngineError("Equity debe ser mayor a 0.")

    if risk_pct < 0:
        raise SizingEngineError("risk_pct no puede ser negativo.")

    if entry_price <= 0 or stop_price <= 0:
        raise SizingEngineError("entry_price y stop_price deben ser mayores a 0.")

    if leverage <= 0:
        raise SizingEngineError("leverage debe ser mayor a 0.")

    if max_notional_pct <= 0:
        raise SizingEngineError("max_notional_pct debe ser mayor a 0.")

    stop_distance = abs(entry_price - stop_price)
    if stop_distance == 0:
        raise SizingEngineError("La distancia al stop no puede ser 0.")

    risk_amount_usdt = equity * risk_pct
    raw_position_size_units = risk_amount_usdt / stop_distance
    raw_notional_value_usdt = raw_position_size_units * entry_price

    max_notional_allowed_usdt = equity * max_notional_pct

    sizing_allowed = True

    if raw_notional_value_usdt > max_notional_allowed_usdt:
        notes.append(
            "El notional calculado supera el máximo permitido para este símbolo. "
            "Se ajustará al techo permitido."
        )

        adjusted_notional_value_usdt = max_notional_allowed_usdt
        adjusted_position_size_units = adjusted_notional_value_usdt / entry_price
    else:
        adjusted_notional_value_usdt = raw_notional_value_usdt
        adjusted_position_size_units = raw_position_size_units

    if adjusted_position_size_units <= 0:
        sizing_allowed = False
        notes.append("El tamaño ajustado de posición no es válido.")

    margin_required_usdt = adjusted_notional_value_usdt / leverage
    if margin_required_usdt > equity:
        sizing_allowed = False
        notes.append(
            "El margen requerido supera el equity disponible con el leverage configurado."
        )

    if risk_pct == 0:
        sizing_allowed = False
        notes.append("risk_pct es 0; no corresponde abrir posición.")

    if sizing_allowed and not notes:
        notes.append("Sizing válido calculado correctamente.")

    return PositionSizingResult(
        equity=equity,
        risk_pct=risk_pct,
        risk_amount_usdt=risk_amount_usdt,
        entry_price=entry_price,
        stop_price=stop_price,
        stop_distance=stop_distance,
        position_size_units=adjusted_position_size_units,
        notional_value_usdt=adjusted_notional_value_usdt,
        leverage=leverage,
        max_notional_allowed_usdt=max_notional_allowed_usdt,
        sizing_allowed=sizing_allowed,
        notes=notes,
    )