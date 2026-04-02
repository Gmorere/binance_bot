from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.core.models import ExitReason
from src.execution.slippage import apply_adverse_entry_slippage, apply_adverse_exit_slippage
from src.strategy.entry_rules import OrderPlan


class ExecutionSimulatorError(Exception):
    """Error relacionado con simulación de ejecución."""


@dataclass
class ExecutionResult:
    symbol: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: Optional[pd.Timestamp]
    exit_price: Optional[float]
    exit_reason: ExitReason
    exit_index: Optional[int]
    position_size_units: float
    remaining_position_units: float
    notional_value_usdt: float
    pnl_gross_usdt: float
    fee_entry_usdt: float
    fee_exit_usdt: float
    pnl_net_usdt: float
    trade_closed: bool
    notes: list[str]


def _validate_inputs(
    future_df: pd.DataFrame,
    order_plan: OrderPlan,
    position_size_units: float,
    fee_rate_entry: float,
    fee_rate_exit: float,
    slippage_pct: float,
    tp1_fraction: float,
    tp2_fraction: float,
    max_bars_in_trade: Optional[int],
) -> None:
    required_cols = ["timestamp", "open", "high", "low", "close"]
    missing = [col for col in required_cols if col not in future_df.columns]
    if missing:
        raise ExecutionSimulatorError(
            f"Faltan columnas para simulación: {', '.join(missing)}"
        )

    if future_df.empty:
        raise ExecutionSimulatorError("No hay velas futuras para simular la ejecución.")

    if position_size_units <= 0:
        raise ExecutionSimulatorError("position_size_units debe ser mayor a 0.")

    if fee_rate_entry < 0 or fee_rate_exit < 0:
        raise ExecutionSimulatorError("Las comisiones no pueden ser negativas.")
    if slippage_pct < 0:
        raise ExecutionSimulatorError("slippage_pct no puede ser negativo.")

    if tp1_fraction <= 0 or tp2_fraction <= 0:
        raise ExecutionSimulatorError("Las fracciones TP deben ser mayores a 0.")

    total_fraction = tp1_fraction + tp2_fraction
    if abs(total_fraction - 1.0) > 1e-9:
        raise ExecutionSimulatorError("tp1_fraction + tp2_fraction debe ser igual a 1.0.")

    if max_bars_in_trade is not None and max_bars_in_trade <= 0:
        raise ExecutionSimulatorError("max_bars_in_trade debe ser mayor a 0 si se informa.")

    if order_plan.side not in {"LONG", "SHORT"}:
        raise ExecutionSimulatorError(f"Side inválido: {order_plan.side}")

    if order_plan.entry_price <= 0:
        raise ExecutionSimulatorError("entry_price debe ser mayor a 0.")

    if order_plan.stop_price <= 0 or order_plan.tp1_price <= 0 or order_plan.tp2_price <= 0:
        raise ExecutionSimulatorError("stop/tp1/tp2 deben ser mayores a 0.")


def _compute_exit_fee(exit_price: float, size_units: float, fee_out: float) -> float:
    return exit_price * size_units * fee_out


def _compute_entry_fee(entry_price: float, size_units: float, fee_in: float) -> float:
    return entry_price * size_units * fee_in


def _compute_pnl_gross(
    side: str,
    entry_price: float,
    exit_price: float,
    size_units: float,
) -> float:
    if side == "LONG":
        return (exit_price - entry_price) * size_units
    if side == "SHORT":
        return (entry_price - exit_price) * size_units
    raise ExecutionSimulatorError(f"Side inválido para PnL: {side}")


def _resolve_long_stop_exit_price(candle_open: float, stop_price: float) -> float:
    """
    Si abre bajo el stop, asumimos slippage adverso y salimos al open.
    Si no, salimos al precio de stop.
    """
    return candle_open if candle_open < stop_price else stop_price


def _resolve_short_stop_exit_price(candle_open: float, stop_price: float) -> float:
    """
    Si abre sobre el stop, asumimos slippage adverso y salimos al open.
    Si no, salimos al precio de stop.
    """
    return candle_open if candle_open > stop_price else stop_price


def simulate_trade_v1(
    *,
    symbol: str,
    future_df: pd.DataFrame,
    order_plan: OrderPlan,
    position_size_units: float,
    fee_rate_entry: float,
    fee_rate_exit: float,
    slippage_pct: float = 0.0,
    tp1_fraction: float = 0.40,
    tp2_fraction: float = 0.60,
    max_bars_in_trade: Optional[int] = None,
    force_close_on_last_candle: bool = False,
) -> ExecutionResult:
    """
    Simulación v1 mejorada:
    - El trade se considera abierto en la primera vela de future_df al entry_price del order_plan.
    - Maneja salidas parciales:
      * tp1_fraction en TP1
      * tp2_fraction en TP2
    - Si antes de TP1 o TP2 toca stop, cierra el remanente al stop.
    - Si TP1 ocurre primero, sigue buscando TP2 o stop para el remanente.
    - Criterio intrabar conservador: si en la misma vela se tocan stop y target, manda stop.
    - Modela slippage adverso en gaps de stop usando el open de la vela.
    - Puede forzar cierre por timeout o al final de la ventana simulada.
    """
    _validate_inputs(
        future_df=future_df,
        order_plan=order_plan,
        position_size_units=position_size_units,
        fee_rate_entry=fee_rate_entry,
        fee_rate_exit=fee_rate_exit,
        slippage_pct=slippage_pct,
        tp1_fraction=tp1_fraction,
        tp2_fraction=tp2_fraction,
        max_bars_in_trade=max_bars_in_trade,
    )

    entry_time = pd.to_datetime(future_df.iloc[0]["timestamp"], utc=True)
    reference_entry_price = float(order_plan.entry_price)
    entry_price = apply_adverse_entry_slippage(
        side=order_plan.side,
        price=reference_entry_price,
        slippage_pct=slippage_pct,
    )
    side = order_plan.side
    notes: list[str] = ["Trade abierto para simulación v1 con parciales TP1/TP2."]
    if slippage_pct > 0:
        notes.append(
            f"Slippage adverso aplicado: {slippage_pct:.4%} | "
            f"entry_ref={reference_entry_price:.4f} entry_fill={entry_price:.4f}"
        )

    total_size = float(position_size_units)
    tp1_size = total_size * tp1_fraction
    remaining_size = total_size

    notional_value_usdt = entry_price * total_size
    fee_entry_usdt = _compute_entry_fee(entry_price, total_size, fee_rate_entry)

    pnl_gross_total = 0.0
    fee_exit_total = 0.0
    total_exit_notional = 0.0

    tp1_hit = False
    final_exit_time: Optional[pd.Timestamp] = None
    final_exit_price: Optional[float] = None
    final_exit_reason: ExitReason = "NO_EXIT"
    final_exit_index: Optional[int] = None

    def register_exit(
        *,
        exit_price: float,
        size_units: float,
        candle_time: pd.Timestamp,
        candle_index: int,
        exit_reason: ExitReason,
        note: str,
        apply_slippage: bool = True,
    ) -> None:
        nonlocal pnl_gross_total
        nonlocal fee_exit_total
        nonlocal total_exit_notional
        nonlocal remaining_size
        nonlocal final_exit_time
        nonlocal final_exit_price
        nonlocal final_exit_reason
        nonlocal final_exit_index

        filled_exit_price = (
            apply_adverse_exit_slippage(side, exit_price, slippage_pct)
            if apply_slippage
            else exit_price
        )

        pnl_gross_total += _compute_pnl_gross(side, entry_price, filled_exit_price, size_units)
        fee_exit_total += _compute_exit_fee(filled_exit_price, size_units, fee_rate_exit)
        total_exit_notional += filled_exit_price * size_units
        remaining_size -= size_units

        if apply_slippage and slippage_pct > 0:
            notes.append(f"{note} | exit_ref={exit_price:.4f} exit_fill={filled_exit_price:.4f}")
        else:
            notes.append(note)

        if remaining_size < -1e-12:
            raise ExecutionSimulatorError("remaining_size quedó negativo. Revisa lógica de parciales.")

        if remaining_size <= 1e-12:
            remaining_size = 0.0
            final_exit_time = candle_time
            final_exit_reason = exit_reason
            final_exit_index = candle_index
            final_exit_price = total_exit_notional / total_size

    for idx, row in future_df.reset_index(drop=True).iterrows():
        candle_time = pd.to_datetime(row["timestamp"], utc=True)
        candle_open = float(row["open"])
        candle_high = float(row["high"])
        candle_low = float(row["low"])
        candle_close = float(row["close"])

        if remaining_size == 0.0:
            break

        if max_bars_in_trade is not None and idx >= max_bars_in_trade:
            register_exit(
                exit_price=candle_close,
                size_units=remaining_size,
                candle_time=candle_time,
                candle_index=idx,
                exit_reason="TIMEOUT",
                note="Cierre forzado por max_bars_in_trade al close de la vela.",
            )
            break

        if side == "LONG":
            if not tp1_hit:
                if candle_low <= order_plan.stop_price:
                    stop_exit_price = _resolve_long_stop_exit_price(
                        candle_open=candle_open,
                        stop_price=float(order_plan.stop_price),
                    )
                    register_exit(
                        exit_price=stop_exit_price,
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="STOP_LOSS",
                        note="Salida total por STOP_LOSS antes de TP1.",
                        apply_slippage=stop_exit_price == float(order_plan.stop_price),
                    )
                    break

                if candle_high >= order_plan.tp2_price:
                    register_exit(
                        exit_price=float(order_plan.tp2_price),
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="TP2",
                        note="Salida total directa por TP2 sin pasar por TP1 parcial.",
                    )
                    break

                if candle_high >= order_plan.tp1_price:
                    register_exit(
                        exit_price=float(order_plan.tp1_price),
                        size_units=tp1_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="TP1",
                        note=f"Salida parcial {tp1_fraction:.0%} por TP1.",
                    )
                    tp1_hit = True
                    continue

            else:
                if candle_low <= order_plan.stop_price:
                    stop_exit_price = _resolve_long_stop_exit_price(
                        candle_open=candle_open,
                        stop_price=float(order_plan.stop_price),
                    )
                    register_exit(
                        exit_price=stop_exit_price,
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="STOP_LOSS",
                        note="Stop del remanente después de TP1.",
                        apply_slippage=stop_exit_price == float(order_plan.stop_price),
                    )
                    break

                if candle_high >= order_plan.tp2_price:
                    register_exit(
                        exit_price=float(order_plan.tp2_price),
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="TP2",
                        note="Salida del remanente por TP2.",
                    )
                    break

        elif side == "SHORT":
            if not tp1_hit:
                if candle_high >= order_plan.stop_price:
                    stop_exit_price = _resolve_short_stop_exit_price(
                        candle_open=candle_open,
                        stop_price=float(order_plan.stop_price),
                    )
                    register_exit(
                        exit_price=stop_exit_price,
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="STOP_LOSS",
                        note="Salida total por STOP_LOSS antes de TP1.",
                        apply_slippage=stop_exit_price == float(order_plan.stop_price),
                    )
                    break

                if candle_low <= order_plan.tp2_price:
                    register_exit(
                        exit_price=float(order_plan.tp2_price),
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="TP2",
                        note="Salida total directa por TP2 sin pasar por TP1 parcial.",
                    )
                    break

                if candle_low <= order_plan.tp1_price:
                    register_exit(
                        exit_price=float(order_plan.tp1_price),
                        size_units=tp1_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="TP1",
                        note=f"Salida parcial {tp1_fraction:.0%} por TP1.",
                    )
                    tp1_hit = True
                    continue

            else:
                if candle_high >= order_plan.stop_price:
                    stop_exit_price = _resolve_short_stop_exit_price(
                        candle_open=candle_open,
                        stop_price=float(order_plan.stop_price),
                    )
                    register_exit(
                        exit_price=stop_exit_price,
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="STOP_LOSS",
                        note="Stop del remanente después de TP1.",
                        apply_slippage=stop_exit_price == float(order_plan.stop_price),
                    )
                    break

                if candle_low <= order_plan.tp2_price:
                    register_exit(
                        exit_price=float(order_plan.tp2_price),
                        size_units=remaining_size,
                        candle_time=candle_time,
                        candle_index=idx,
                        exit_reason="TP2",
                        note="Salida del remanente por TP2.",
                    )
                    break
        else:
            raise ExecutionSimulatorError(f"Side inválido: {side}")

    if remaining_size > 0.0 and force_close_on_last_candle:
        last_idx = len(future_df) - 1
        last_row = future_df.iloc[last_idx]
        last_time = pd.to_datetime(last_row["timestamp"], utc=True)
        last_close = float(last_row["close"])

        register_exit(
            exit_price=last_close,
            size_units=remaining_size,
            candle_time=last_time,
            candle_index=last_idx,
            exit_reason="END_OF_DATA",
            note="Cierre forzado del remanente al close de la última vela disponible.",
        )

    trade_closed = remaining_size == 0.0
    pnl_net_total = pnl_gross_total - fee_entry_usdt - fee_exit_total

    if not trade_closed:
        notes.append("No se alcanzó cierre completo en la ventana simulada.")
        final_exit_time = None
        final_exit_price = None
        final_exit_reason = "NO_EXIT"
        final_exit_index = None

    return ExecutionResult(
        symbol=symbol,
        side=side,
        entry_time=entry_time,
        entry_price=entry_price,
        exit_time=final_exit_time,
        exit_price=final_exit_price,
        exit_reason=final_exit_reason,
        exit_index=final_exit_index,
        position_size_units=total_size,
        remaining_position_units=remaining_size,
        notional_value_usdt=notional_value_usdt,
        pnl_gross_usdt=pnl_gross_total,
        fee_entry_usdt=fee_entry_usdt,
        fee_exit_usdt=fee_exit_total,
        pnl_net_usdt=pnl_net_total,
        trade_closed=trade_closed,
        notes=notes,
    )
