from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from src.core.config_loader import ensure_project_directories, resolve_project_paths
from src.live.market_data_runtime import (
    MarketDataPollResult,
    build_market_data_service,
    detect_symbols_with_new_candles,
)
from src.live.notifier import TelegramNotifier, build_notifier
from src.live.paper_engine import load_paper_state, run_paper_cycle, save_paper_state
from src.live.runtime_config import load_runtime_config


class PaperRuntimeLoopError(Exception):
    """Error relacionado con el loop continuo de paper trading."""


class MarketDataService(Protocol):
    def poll(self, *, now_ms: int | None = None) -> MarketDataPollResult:
        ...


OutputFn = Callable[[str], None]
SleepFn = Callable[[float], None]
TimeFn = Callable[[], float]


@dataclass(frozen=True)
class PaperRuntimeSummary:
    cycles_executed: int
    cycles_with_new_candles: int
    cycle_errors: int
    last_state_path: Path


def run_paper_runtime_loop(
    *,
    config: Mapping[str, object],
    once: bool = False,
    max_cycles: int | None = None,
    output_fn: OutputFn = print,
    sleep_fn: SleepFn = time.sleep,
    time_fn: TimeFn = time.time,
    market_data_service: MarketDataService | None = None,
    notifier: TelegramNotifier | None = None,
) -> PaperRuntimeSummary:
    runtime = load_runtime_config(config)
    if runtime.mode != "paper":
        raise PaperRuntimeLoopError(
            f"run_paper_runtime_loop requiere runtime.mode='paper', actual: {runtime.mode}"
        )

    ensure_project_directories(config)  # type: ignore[arg-type]
    paths = resolve_project_paths(config)  # type: ignore[arg-type]
    state_path = Path(paths["outputs_path"]) / "paper" / "paper_state.json"
    state = load_paper_state(
        state_path,
        initial_capital=float(config["capital"]["initial_capital"]),  # type: ignore[index]
    )
    service = market_data_service or build_market_data_service(config, output_fn=output_fn)
    telegram = notifier if notifier is not None else build_notifier()

    cycles_executed = 0
    cycles_with_new_candles = 0
    cycle_errors = 0
    last_heartbeat_day: str | None = None

    while True:
        cycle_number = cycles_executed + 1
        try:
            poll_result = service.poll()
            snapshot = poll_result.snapshot
            new_symbols = detect_symbols_with_new_candles(
                snapshot.latest_timestamps,
                state.processed_candle_timestamps,
            )

            output_fn(
                f"cycle={cycle_number} symbols={sorted(snapshot.market_data_by_symbol.keys())} new_candles={new_symbols}"
            )

            if new_symbols:
                positions_before = dict(state.open_positions)
                result = run_paper_cycle(
                    config=config,
                    market_data_by_symbol=snapshot.market_data_by_symbol,
                    bias_market_data_by_symbol=snapshot.bias_market_data_by_symbol,
                    context_market_data_by_symbol=snapshot.context_market_data_by_symbol,
                    state=state,
                )
                state = result.state
                save_paper_state(state, state_path)
                cycles_with_new_candles += 1
                output_fn(
                    "opened="
                    f"{result.opened_symbols} closed={result.closed_symbols} "
                    f"updated={result.updated_symbols} equity={state.equity:.4f} "
                    f"decisions={result.decision_counts}"
                )
                for event in result.events[-10:]:
                    output_fn(f"event={event}")

                _notify_trade_events(
                    telegram=telegram,
                    mode=runtime.mode,
                    opened_symbols=result.opened_symbols,
                    closed_symbols=result.closed_symbols,
                    positions_before=positions_before,
                    state=state,
                    events=result.events,
                )
            else:
                output_fn("no_new_candles")
        except Exception as exc:
            if once:
                raise PaperRuntimeLoopError(
                    f"Error en ciclo paper {cycle_number}: {exc}"
                ) from exc

            cycle_errors += 1
            output_fn(
                "runtime_cycle_error "
                f"cycle={cycle_number} error_type={type(exc).__name__} error={exc}"
            )
            telegram.notify_cycle_error(
                mode=runtime.mode,
                cycle=cycle_number,
                total_errors=cycle_errors,
                error_type=type(exc).__name__,
                error_msg=str(exc),
            )
            cycles_executed += 1
            output_fn(
                "runtime_status "
                f"cycles={cycles_executed} cycles_with_new_candles={cycles_with_new_candles} "
                f"cycle_errors={cycle_errors} open_positions={len(state.open_positions)} "
                f"open_risk_pct={state.open_risk_pct:.4f} equity={state.equity:.4f}"
            )

            if max_cycles is not None and cycles_executed >= max_cycles:
                break

            sleep_seconds = float(runtime.refresh_error_backoff_seconds)
            output_fn(
                f"sleep_seconds={sleep_seconds:.3f} reason=runtime_cycle_error"
            )
            sleep_fn(sleep_seconds)
            continue

        cycles_executed += 1

        if once:
            break
        if max_cycles is not None and cycles_executed >= max_cycles:
            break

        output_fn(
            "runtime_status "
            f"cycles={cycles_executed} cycles_with_new_candles={cycles_with_new_candles} "
            f"cycle_errors={cycle_errors} open_positions={len(state.open_positions)} "
            f"open_risk_pct={state.open_risk_pct:.4f} equity={state.equity:.4f}"
        )

        today_utc = state.current_day
        if today_utc and today_utc != last_heartbeat_day:
            last_heartbeat_day = today_utc
            telegram.notify_heartbeat(
                mode=runtime.mode,
                date_utc=today_utc,
                equity=state.equity,
                initial_capital=state.initial_capital,
                pnl_today=state.realized_pnl_today,
                pnl_week=state.realized_pnl_week,
                open_positions=len(state.open_positions),
                total_trades=state.total_trades,
                cycle_errors=cycle_errors,
            )

        sleep_seconds = _resolve_sleep_seconds(
            poll_result.next_poll_after_ms,
            now_ms=int(time_fn() * 1000),
            fallback_seconds=float(runtime.poll_interval_seconds),
        )
        output_fn(f"sleep_seconds={sleep_seconds:.3f}")
        sleep_fn(sleep_seconds)

    return PaperRuntimeSummary(
        cycles_executed=cycles_executed,
        cycles_with_new_candles=cycles_with_new_candles,
        cycle_errors=cycle_errors,
        last_state_path=state_path,
    )


def _notify_trade_events(
    *,
    telegram: TelegramNotifier,
    mode: str,
    opened_symbols: list[str],
    closed_symbols: list[str],
    positions_before: dict,
    state: object,
    events: list[str],
) -> None:
    from src.live.paper_engine import PaperState  # local import to avoid circularity

    if not isinstance(state, PaperState):
        return

    for symbol in opened_symbols:
        pos = state.open_positions.get(symbol)
        if pos is None:
            continue
        risk_usdt = pos.risk_pct * state.equity
        telegram.notify_trade_opened(
            mode=mode,
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            stop_price=pos.stop_price,
            tp1_price=pos.tp1_price,
            tp2_price=pos.tp2_price,
            risk_pct=pos.risk_pct,
            risk_usdt=risk_usdt,
            equity=state.equity,
        )

    for symbol in closed_symbols:
        pos_before = positions_before.get(symbol)
        if pos_before is None:
            continue
        close_events = [e for e in events if e.startswith(f"CLOSE {symbol}")]
        pnl = float(close_events[0].split("net_total=")[1].split()[0]) if close_events else 0.0
        exit_notes = [
            e.split(f"EXIT {symbol} ")[1].split(" qty=")[0]
            for e in events
            if e.startswith(f"EXIT {symbol}")
        ]
        telegram.notify_trade_closed(
            mode=mode,
            symbol=symbol,
            side=pos_before.side,
            pnl_net_usdt=pnl,
            equity=state.equity,
            total_trades=state.total_trades,
            winning_trades=state.winning_trades,
            exit_notes=exit_notes,
        )


def _resolve_sleep_seconds(
    next_poll_after_ms: int | None,
    *,
    now_ms: int,
    fallback_seconds: float,
) -> float:
    if next_poll_after_ms is None:
        return max(0.0, float(fallback_seconds))

    delta_seconds = max(0.0, (int(next_poll_after_ms) - int(now_ms)) / 1000.0)
    return delta_seconds
