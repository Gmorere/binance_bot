from __future__ import annotations


class SlippageModelError(Exception):
    """Error relacionado con el modelado de slippage."""


def _validate_slippage_pct(slippage_pct: float) -> None:
    if slippage_pct < 0:
        raise SlippageModelError("slippage_pct no puede ser negativo.")


def apply_adverse_entry_slippage(
    side: str,
    price: float,
    slippage_pct: float,
) -> float:
    _validate_slippage_pct(slippage_pct)
    if slippage_pct == 0:
        return float(price)

    if side == "LONG":
        return float(price) * (1.0 + float(slippage_pct))
    if side == "SHORT":
        return float(price) * (1.0 - float(slippage_pct))
    raise SlippageModelError(f"Side invalido para slippage de entrada: {side}")


def apply_adverse_exit_slippage(
    side: str,
    price: float,
    slippage_pct: float,
) -> float:
    _validate_slippage_pct(slippage_pct)
    if slippage_pct == 0:
        return float(price)

    if side == "LONG":
        return float(price) * (1.0 - float(slippage_pct))
    if side == "SHORT":
        return float(price) * (1.0 + float(slippage_pct))
    raise SlippageModelError(f"Side invalido para slippage de salida: {side}")
