from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from src.strategy.setup_detector import BreakoutDetection, ConsolidationRange


class EntryRulesError(Exception):
    """Error relacionado con construcción del plan de entrada."""


Side = Literal["LONG", "SHORT"]


@dataclass
class OrderPlan:
    symbol: str
    side: Side
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    rr_1: float
    rr_2: float
    breakout_level: Optional[float]
    setup_type: str
    notes: list[str]


def _validate_positive(value: float, field_name: str) -> None:
    if value <= 0:
        raise EntryRulesError(f"{field_name} debe ser mayor a 0.")


def _compute_risk_distance(entry_price: float, stop_price: float) -> float:
    risk_distance = abs(entry_price - stop_price)
    if risk_distance == 0:
        raise EntryRulesError("La distancia entre entry y stop no puede ser 0.")
    return risk_distance


def _compute_tp_prices(side: Side, entry_price: float, stop_price: float) -> tuple[float, float]:
    risk_distance = _compute_risk_distance(entry_price, stop_price)

    if side == "LONG":
        tp1 = entry_price + risk_distance
        tp2 = entry_price + (2 * risk_distance)
    elif side == "SHORT":
        tp1 = entry_price - risk_distance
        tp2 = entry_price - (2 * risk_distance)
    else:
        raise EntryRulesError(f"Side inválido: {side}")

    return tp1, tp2


def build_breakout_order_plan(
    *,
    symbol: str,
    breakout: BreakoutDetection,
    consolidation: ConsolidationRange,
    next_open_price: float,
    stop_buffer_atr_fraction: float = 0.10,
) -> OrderPlan:
    """
    Construye una orden para breakout de consolidación.
    La entrada se asume en el open de la siguiente vela.
    """
    _validate_positive(next_open_price, "next_open_price")

    if not breakout.detected:
        raise EntryRulesError("No se puede construir order plan: breakout.detected=False.")

    if breakout.side not in ("LONG", "SHORT"):
        raise EntryRulesError(f"Side de breakout inválido: {breakout.side}")

    atr_value = consolidation.atr_value
    _validate_positive(atr_value, "consolidation.atr_value")

    stop_buffer = atr_value * stop_buffer_atr_fraction
    notes: list[str] = []

    if breakout.side == "LONG":
        stop_price = consolidation.low - stop_buffer
        if stop_price >= next_open_price:
            raise EntryRulesError("Stop LONG inválido: stop_price >= entry_price.")
    else:
        stop_price = consolidation.high + stop_buffer
        if stop_price <= next_open_price:
            raise EntryRulesError("Stop SHORT inválido: stop_price <= entry_price.")

    tp1_price, tp2_price = _compute_tp_prices(
        side=breakout.side,
        entry_price=next_open_price,
        stop_price=stop_price,
    )

    notes.append("Order plan construido para breakout.")
    notes.append(f"Entrada en open siguiente vela: {next_open_price:.4f}")
    notes.append(f"Nivel de breakout: {breakout.breakout_level:.4f}" if breakout.breakout_level else "Sin breakout level.")
    notes.append(f"Stop buffer aplicado: {stop_buffer:.4f}")

    return OrderPlan(
        symbol=symbol,
        side=breakout.side,
        entry_price=next_open_price,
        stop_price=stop_price,
        tp1_price=tp1_price,
        tp2_price=tp2_price,
        rr_1=1.0,
        rr_2=2.0,
        breakout_level=breakout.breakout_level,
        setup_type="BREAKOUT",
        notes=notes,
    )


def validate_order_plan(order_plan: OrderPlan) -> tuple[bool, list[str]]:
    notes: list[str] = []

    _validate_positive(order_plan.entry_price, "entry_price")
    _validate_positive(order_plan.stop_price, "stop_price")
    _validate_positive(order_plan.tp1_price, "tp1_price")
    _validate_positive(order_plan.tp2_price, "tp2_price")

    if order_plan.side == "LONG":
        if not (order_plan.stop_price < order_plan.entry_price < order_plan.tp1_price < order_plan.tp2_price):
            notes.append("Secuencia de precios inválida para LONG.")
            return False, notes

    elif order_plan.side == "SHORT":
        if not (order_plan.tp2_price < order_plan.tp1_price < order_plan.entry_price < order_plan.stop_price):
            notes.append("Secuencia de precios inválida para SHORT.")
            return False, notes

    else:
        notes.append(f"Side inválido: {order_plan.side}")
        return False, notes

    notes.append("Order plan válido.")
    return True, notes