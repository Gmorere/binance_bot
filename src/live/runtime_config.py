from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


RuntimeMode = Literal["backtest", "paper", "live"]


class RuntimeConfigError(Exception):
    """Error relacionado con configuracion operativa del bot."""


@dataclass(frozen=True)
class RuntimeConfig:
    mode: RuntimeMode
    exchange: str
    use_testnet: bool
    recv_window_ms: int
    timeout_seconds: int
    market_data_limit: int
    poll_interval_seconds: int
    paper_risk_bucket: str
    refresh_from_binance_rest: bool
    candle_close_grace_seconds: int


def load_runtime_config(
    config: Mapping[str, Any],
) -> RuntimeConfig:
    runtime_cfg = dict(config.get("runtime", {}))
    exchange_cfg = dict(config.get("binance", {}))
    data_cfg = dict(config.get("data", {}))

    mode = str(runtime_cfg.get("mode", config.get("project", {}).get("mode", "backtest"))).lower()
    allowed_modes = {"backtest", "paper", "live"}
    if mode not in allowed_modes:
        raise RuntimeConfigError(
            f"runtime.mode invalido: {mode}. Esperado: backtest, paper o live."
        )

    exchange = str(runtime_cfg.get("exchange", "binance_usdm")).strip()
    if not exchange:
        raise RuntimeConfigError("runtime.exchange no puede venir vacio.")

    use_testnet = bool(exchange_cfg.get("use_testnet", True))
    recv_window_ms = int(exchange_cfg.get("recv_window_ms", 5000))
    timeout_seconds = int(exchange_cfg.get("timeout_seconds", 30))
    market_data_limit = int(exchange_cfg.get("market_data_limit", 500))
    poll_interval_seconds = int(runtime_cfg.get("poll_interval_seconds", 15))
    paper_risk_bucket = str(runtime_cfg.get("paper_risk_bucket", "normal")).strip().lower()
    refresh_from_binance_rest = bool(data_cfg.get("refresh_from_binance_rest", False))
    candle_close_grace_seconds = int(data_cfg.get("candle_close_grace_seconds", 3))

    if recv_window_ms <= 0:
        raise RuntimeConfigError("binance.recv_window_ms debe ser mayor a 0.")
    if timeout_seconds <= 0:
        raise RuntimeConfigError("binance.timeout_seconds debe ser mayor a 0.")
    if market_data_limit <= 0 or market_data_limit > 1500:
        raise RuntimeConfigError("binance.market_data_limit debe estar entre 1 y 1500.")
    if poll_interval_seconds <= 0:
        raise RuntimeConfigError("runtime.poll_interval_seconds debe ser mayor a 0.")
    if candle_close_grace_seconds < 0:
        raise RuntimeConfigError("data.candle_close_grace_seconds no puede ser negativo.")
    if paper_risk_bucket not in {"small", "normal", "strong", "exceptional"}:
        raise RuntimeConfigError(
            "runtime.paper_risk_bucket debe ser uno de: small, normal, strong, exceptional."
        )

    return RuntimeConfig(
        mode=mode,  # type: ignore[arg-type]
        exchange=exchange,
        use_testnet=use_testnet,
        recv_window_ms=recv_window_ms,
        timeout_seconds=timeout_seconds,
        market_data_limit=market_data_limit,
        poll_interval_seconds=poll_interval_seconds,
        paper_risk_bucket=paper_risk_bucket,
        refresh_from_binance_rest=refresh_from_binance_rest,
        candle_close_grace_seconds=candle_close_grace_seconds,
    )
