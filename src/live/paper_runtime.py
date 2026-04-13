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

    cycles_executed = 0
    cycles_with_new_candles = 0

    while True:
        poll_result = service.poll()
        snapshot = poll_result.snapshot
        new_symbols = detect_symbols_with_new_candles(
            snapshot.latest_timestamps,
            state.processed_candle_timestamps,
        )

        output_fn(
            f"cycle={cycles_executed + 1} symbols={sorted(snapshot.market_data_by_symbol.keys())} new_candles={new_symbols}"
        )

        if new_symbols:
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
        else:
            output_fn("no_new_candles")

        cycles_executed += 1

        if once:
            break
        if max_cycles is not None and cycles_executed >= max_cycles:
            break

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
        last_state_path=state_path,
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
