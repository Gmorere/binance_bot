from __future__ import annotations

from typing import Any

from src.risk.risk_engine import get_risk_pct_for_bucket


def load_backtest_strategy_policy(
    config: dict[str, Any],
) -> dict[str, object]:
    strategy_cfg = dict(config.get("strategy", {}))
    backtest_policy_cfg = dict(strategy_cfg.get("backtest_policy", {}))
    raw_allowed_sides = dict(backtest_policy_cfg.get("allowed_sides", {}))
    raw_allowed_setups_by_symbol = dict(strategy_cfg.get("allowed_setups_by_symbol", {}))
    allowed_sides = {
        str(symbol).strip().upper(): [
            str(side).strip().upper()
            for side in sides
            if str(side).strip()
        ]
        for symbol, sides in raw_allowed_sides.items()
    }
    allowed_setups = [
        str(setup).strip().upper()
        for setup in strategy_cfg.get("allowed_setups", [])
        if str(setup).strip()
    ]
    allowed_setups_by_symbol = {
        str(symbol).strip().upper(): [
            str(setup).strip().upper()
            for setup in setups
            if str(setup).strip()
        ]
        for symbol, setups in raw_allowed_setups_by_symbol.items()
    }
    excluded_symbols = [
        str(symbol).strip().upper()
        for symbol in backtest_policy_cfg.get("excluded_symbols", [])
        if str(symbol).strip()
    ]

    return {
        "enabled": bool(backtest_policy_cfg.get("enabled", False)),
        "enforce_context_alignment": bool(
            backtest_policy_cfg.get("enforce_context_alignment", False)
        ),
        "excluded_symbols": excluded_symbols,
        "allowed_sides": allowed_sides,
        "allowed_setups": allowed_setups,
        "allowed_setups_by_symbol": allowed_setups_by_symbol,
    }


def load_dynamic_risk_policy(
    config: dict[str, Any],
) -> dict[str, object]:
    strategy_cfg = dict(config.get("strategy", {}))
    dynamic_cfg = dict(strategy_cfg.get("dynamic_risk_by_score", {}))
    return {
        "enabled": bool(dynamic_cfg.get("enabled", False)),
        "preserve_symbol_base_risk": bool(
            dynamic_cfg.get("preserve_symbol_base_risk", True)
        ),
    }


def _resolve_symbol_scoped_values(
    section_cfg: dict[str, Any] | None,
    symbol: str,
    overrides: dict[str, float | int] | None = None,
) -> dict[str, float]:
    section_cfg = dict(section_cfg or {})
    symbol_overrides_cfg = section_cfg.get("by_symbol", {})
    if not isinstance(symbol_overrides_cfg, dict):
        symbol_overrides_cfg = {}

    base_values = {
        key: value
        for key, value in section_cfg.items()
        if key != "by_symbol"
    }
    symbol_values = dict(symbol_overrides_cfg.get(str(symbol).strip().upper(), {}))

    resolved = dict(base_values)
    resolved.update(symbol_values)
    if overrides:
        resolved.update(overrides)

    return {
        key: float(value)
        for key, value in resolved.items()
        if isinstance(value, int | float)
    }


def resolve_symbol_filters(
    config: dict[str, Any],
    symbol: str,
    overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    return _resolve_symbol_scoped_values(
        dict(config.get("filters", {})),
        symbol,
        overrides=overrides,
    )


def resolve_symbol_trade_management(
    config: dict[str, Any],
    symbol: str,
    overrides: dict[str, float | int] | None = None,
) -> dict[str, float]:
    return _resolve_symbol_scoped_values(
        dict(config.get("trade_management", {})),
        symbol,
        overrides=overrides,
    )


def resolve_symbol_backtest_risk(
    config: dict[str, Any],
    symbol: str,
    default_risk_pct: float,
    default_risk_bucket: str,
) -> tuple[float, str]:
    risk_cfg = dict(config.get("risk", {}))
    backtest_by_symbol = dict(risk_cfg.get("backtest_by_symbol", {}))
    symbol_cfg = dict(backtest_by_symbol.get(str(symbol).strip().upper(), {}))

    if "risk_pct" in symbol_cfg:
        risk_pct = float(symbol_cfg["risk_pct"])
        if not (0 <= risk_pct < 1):
            raise ValueError(
                f"risk.backtest_by_symbol.{symbol}.risk_pct invalido: {risk_pct}"
            )
        return risk_pct, f"manual_{risk_pct:.4f}"

    if "risk_bucket" in symbol_cfg:
        risk_pct, _notes = get_risk_pct_for_bucket(
            risk_by_score=dict(risk_cfg.get("risk_by_score", {})),
            risk_bucket=str(symbol_cfg["risk_bucket"]),
        )
        return risk_pct, str(symbol_cfg["risk_bucket"]).strip().lower()

    return default_risk_pct, default_risk_bucket


def resolve_symbol_allowed_setups(
    config: dict[str, Any],
    symbol: str,
) -> list[str]:
    strategy_cfg = dict(config.get("strategy", {}))
    global_allowed_setups = [
        str(setup).strip().upper()
        for setup in strategy_cfg.get("allowed_setups", [])
        if str(setup).strip()
    ]
    raw_by_symbol = dict(strategy_cfg.get("allowed_setups_by_symbol", {}))
    symbol_allowed_setups = [
        str(setup).strip().upper()
        for setup in raw_by_symbol.get(str(symbol).strip().upper(), [])
        if str(setup).strip()
    ]
    return symbol_allowed_setups or global_allowed_setups or ["BREAKOUT"]


def resolve_pullback_settings(
    config: dict[str, Any],
    symbol: str,
) -> dict[str, float]:
    return _resolve_symbol_scoped_values(
        dict(config.get("pullback", {})),
        symbol,
    )
