from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable, Mapping

from src.exchange.binance_usdm_client import BinanceUsdmClient, BinanceUsdmClientError
from src.live.runtime_config import load_runtime_config


class LiveRuntimeLoopError(Exception):
    """Error relacionado con runtime live."""


OutputFn = Callable[[str], None]
SleepFn = Callable[[float], None]


def _env_flag_true(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LiveRuntimeSummary:
    cycles_executed: int
    account_checks: int
    reconciliations_ok: int
    orders_submitted: int
    orders_blocked: int
    cycle_errors: int
    live_execution_enabled: bool


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _count_open_positions(account_payload: Mapping[str, object]) -> int:
    raw_positions = account_payload.get("positions", [])
    if not isinstance(raw_positions, list):
        return 0

    open_positions = 0
    for item in raw_positions:
        if not isinstance(item, Mapping):
            continue
        if abs(_safe_float(item.get("positionAmt", 0.0))) > 0:
            open_positions += 1
    return open_positions


def _build_client_from_env_or_none(
    *,
    config: Mapping[str, object],
    output_fn: OutputFn,
    env: Mapping[str, str] | None = None,
) -> BinanceUsdmClient | None:
    runtime = load_runtime_config(config)
    try:
        return BinanceUsdmClient.from_env(
            use_testnet=runtime.use_testnet,
            recv_window_ms=runtime.recv_window_ms,
            timeout_seconds=runtime.timeout_seconds,
            env=env,
        )
    except BinanceUsdmClientError as exc:
        output_fn(
            "live_startup credentials_unavailable "
            f"error={exc} continuing_safe_mode=true"
        )
        return None


def run_live_runtime_loop(
    *,
    config: Mapping[str, object],
    once: bool = False,
    max_cycles: int | None = None,
    output_fn: OutputFn = print,
    sleep_fn: SleepFn = time.sleep,
    env: Mapping[str, str] | None = None,
    client: BinanceUsdmClient | None = None,
) -> LiveRuntimeSummary:
    runtime = load_runtime_config(config)
    if runtime.mode != "live":
        raise LiveRuntimeLoopError(
            f"run_live_runtime_loop requiere runtime.mode='live', actual: {runtime.mode}"
        )

    source_env = env or os.environ
    live_execution_enabled = _env_flag_true(source_env.get("LIVE_ENABLED"))
    exchange_client = client or _build_client_from_env_or_none(
        config=config,
        output_fn=output_fn,
        env=source_env,
    )
    if exchange_client is None and live_execution_enabled:
        raise LiveRuntimeLoopError(
            "LIVE_ENABLED=true requiere BINANCE_API_KEY y BINANCE_API_SECRET disponibles."
        )

    output_fn(
        "live_startup "
        f"mode={runtime.mode} exchange={runtime.exchange} "
        f"use_testnet={runtime.use_testnet} live_execution_enabled={live_execution_enabled}"
    )

    cycles_executed = 0
    account_checks = 0
    reconciliations_ok = 0
    orders_submitted = 0
    orders_blocked = 0
    cycle_errors = 0

    while True:
        cycle_number = cycles_executed + 1
        try:
            if exchange_client is None:
                output_fn(
                    f"live_cycle cycle={cycle_number} safe_mode_no_client=true"
                )
            else:
                account_checks += 1
                account_info = exchange_client.get_account_info()
                if not isinstance(account_info, Mapping):
                    raise LiveRuntimeLoopError("Respuesta de cuenta inválida (no mapping).")

                wallet_balance = _safe_float(account_info.get("totalWalletBalance"))
                available_balance = _safe_float(account_info.get("availableBalance"))
                open_positions = _count_open_positions(account_info)
                reconciliations_ok += 1
                output_fn(
                    "live_reconciliation "
                    f"cycle={cycle_number} wallet_balance={wallet_balance:.4f} "
                    f"available_balance={available_balance:.4f} "
                    f"open_positions={open_positions}"
                )

            if live_execution_enabled:
                output_fn(
                    "live_guard execution_enabled_but_order_routing_not_implemented_v0_1 "
                    f"cycle={cycle_number} orders_submitted=0"
                )
            else:
                orders_blocked += 1
                output_fn(
                    "live_guard execution_disabled "
                    f"cycle={cycle_number} orders_blocked_total={orders_blocked}"
                )

        except Exception as exc:
            cycle_errors += 1
            output_fn(
                "live_cycle_error "
                f"cycle={cycle_number} error_type={type(exc).__name__} error={exc}"
            )

        cycles_executed += 1
        output_fn(
            "live_status "
            f"cycles={cycles_executed} account_checks={account_checks} "
            f"reconciliations_ok={reconciliations_ok} orders_submitted={orders_submitted} "
            f"orders_blocked={orders_blocked} cycle_errors={cycle_errors}"
        )

        if once:
            break
        if max_cycles is not None and cycles_executed >= max_cycles:
            break

        sleep_seconds = float(runtime.poll_interval_seconds)
        output_fn(f"sleep_seconds={sleep_seconds:.3f}")
        sleep_fn(sleep_seconds)

    return LiveRuntimeSummary(
        cycles_executed=cycles_executed,
        account_checks=account_checks,
        reconciliations_ok=reconciliations_ok,
        orders_submitted=orders_submitted,
        orders_blocked=orders_blocked,
        cycle_errors=cycle_errors,
        live_execution_enabled=live_execution_enabled,
    )
