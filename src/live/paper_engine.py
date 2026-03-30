from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from src.live.candidate_scanner import scan_trade_candidates
from src.live.runtime_config import RuntimeConfig, load_runtime_config
from src.risk.risk_engine import (
    portfolio_allows_new_trade,
    system_loss_limits_allow_trade,
)
from src.risk.sizing_engine import PositionSizingResult, calculate_position_size


class PaperEngineError(Exception):
    """Error relacionado con ejecución local de paper trading."""


@dataclass
class PaperPosition:
    symbol: str
    side: str
    entry_time: str
    last_update_time: str
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    leverage: float
    risk_pct: float
    current_risk_pct: float
    initial_quantity: float
    remaining_quantity: float
    notional_value_usdt: float
    fee_entry_usdt: float
    fee_exit_usdt: float = 0.0
    realized_pnl_gross_usdt: float = 0.0
    realized_pnl_net_usdt: float = 0.0
    tp1_hit: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class PaperState:
    initial_capital: float
    equity: float
    balance: float
    realized_pnl_net_usdt: float = 0.0
    open_risk_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    current_day: str | None = None
    current_week: str | None = None
    day_start_balance: float = 0.0
    week_start_balance: float = 0.0
    realized_pnl_today: float = 0.0
    realized_pnl_week: float = 0.0
    processed_candle_timestamps: dict[str, str] = field(default_factory=dict)
    open_positions: dict[str, PaperPosition] = field(default_factory=dict)
    event_log: list[str] = field(default_factory=list)


@dataclass
class PaperCycleResult:
    state: PaperState
    opened_symbols: list[str]
    closed_symbols: list[str]
    updated_symbols: list[str]
    events: list[str]


TP1_FRACTION = 0.40
TP2_FRACTION = 0.60
MAX_EVENT_LOG = 200


def create_initial_paper_state(initial_capital: float) -> PaperState:
    if initial_capital <= 0:
        raise PaperEngineError("initial_capital debe ser mayor a 0.")

    return PaperState(
        initial_capital=float(initial_capital),
        equity=float(initial_capital),
        balance=float(initial_capital),
        day_start_balance=float(initial_capital),
        week_start_balance=float(initial_capital),
    )


def _paper_position_from_dict(payload: Mapping[str, Any]) -> PaperPosition:
    return PaperPosition(
        symbol=str(payload["symbol"]),
        side=str(payload["side"]),
        entry_time=str(payload["entry_time"]),
        last_update_time=str(payload["last_update_time"]),
        entry_price=float(payload["entry_price"]),
        stop_price=float(payload["stop_price"]),
        tp1_price=float(payload["tp1_price"]),
        tp2_price=float(payload["tp2_price"]),
        leverage=float(payload["leverage"]),
        risk_pct=float(payload["risk_pct"]),
        current_risk_pct=float(payload["current_risk_pct"]),
        initial_quantity=float(payload["initial_quantity"]),
        remaining_quantity=float(payload["remaining_quantity"]),
        notional_value_usdt=float(payload["notional_value_usdt"]),
        fee_entry_usdt=float(payload.get("fee_entry_usdt", 0.0)),
        fee_exit_usdt=float(payload.get("fee_exit_usdt", 0.0)),
        realized_pnl_gross_usdt=float(payload.get("realized_pnl_gross_usdt", 0.0)),
        realized_pnl_net_usdt=float(payload.get("realized_pnl_net_usdt", 0.0)),
        tp1_hit=bool(payload.get("tp1_hit", False)),
        notes=[str(note) for note in payload.get("notes", [])],
    )


def _paper_state_from_dict(payload: Mapping[str, Any], initial_capital: float) -> PaperState:
    state = create_initial_paper_state(initial_capital)
    state.equity = float(payload.get("equity", state.equity))
    state.balance = float(payload.get("balance", state.balance))
    state.realized_pnl_net_usdt = float(payload.get("realized_pnl_net_usdt", 0.0))
    state.open_risk_pct = float(payload.get("open_risk_pct", 0.0))
    state.total_trades = int(payload.get("total_trades", 0))
    state.winning_trades = int(payload.get("winning_trades", 0))
    state.losing_trades = int(payload.get("losing_trades", 0))
    state.current_day = payload.get("current_day")
    state.current_week = payload.get("current_week")
    state.day_start_balance = float(payload.get("day_start_balance", state.balance))
    state.week_start_balance = float(payload.get("week_start_balance", state.balance))
    state.realized_pnl_today = float(payload.get("realized_pnl_today", 0.0))
    state.realized_pnl_week = float(payload.get("realized_pnl_week", 0.0))
    state.processed_candle_timestamps = {
        str(symbol): str(ts)
        for symbol, ts in dict(payload.get("processed_candle_timestamps", {})).items()
    }
    state.open_positions = {
        str(symbol): _paper_position_from_dict(position_payload)
        for symbol, position_payload in dict(payload.get("open_positions", {})).items()
    }
    state.event_log = [str(event) for event in payload.get("event_log", [])][-MAX_EVENT_LOG:]
    return state


def load_paper_state(state_path: str | Path, *, initial_capital: float) -> PaperState:
    path = Path(state_path)
    if not path.exists():
        return create_initial_paper_state(initial_capital)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PaperEngineError(f"JSON inválido en paper state: {path}") from exc

    if not isinstance(payload, dict):
        raise PaperEngineError("paper state debe contener un objeto JSON raíz.")

    return _paper_state_from_dict(payload, initial_capital)


def save_paper_state(state: PaperState, state_path: str | Path) -> Path:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = asdict(state)
    path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _week_id(timestamp: pd.Timestamp) -> str:
    iso = timestamp.isocalendar()
    return f"{int(iso.year):04d}-W{int(iso.week):02d}"


def _append_event(state: PaperState, events: list[str], message: str) -> None:
    state.event_log.append(message)
    if len(state.event_log) > MAX_EVENT_LOG:
        state.event_log = state.event_log[-MAX_EVENT_LOG:]
    events.append(message)


def _apply_realized_delta(state: PaperState, delta_net_usdt: float) -> None:
    state.equity += delta_net_usdt
    state.balance += delta_net_usdt
    state.realized_pnl_net_usdt += delta_net_usdt
    state.realized_pnl_today += delta_net_usdt
    state.realized_pnl_week += delta_net_usdt


def _reset_period_trackers(state: PaperState, cycle_timestamp: pd.Timestamp) -> None:
    day_id = cycle_timestamp.date().isoformat()
    week_id = _week_id(cycle_timestamp)

    if state.current_day != day_id:
        state.current_day = day_id
        state.day_start_balance = state.balance
        state.realized_pnl_today = 0.0

    if state.current_week != week_id:
        state.current_week = week_id
        state.week_start_balance = state.balance
        state.realized_pnl_week = 0.0


def _compute_drawdown_pct(realized_pnl: float, reference_balance: float) -> float:
    if reference_balance <= 0:
        return 0.0
    return max(0.0, -realized_pnl / reference_balance)


def _risk_pct_for_paper(config: Mapping[str, Any], runtime: RuntimeConfig) -> float:
    risk_by_score = dict(config["risk"]["risk_by_score"])
    try:
        return float(risk_by_score[runtime.paper_risk_bucket])
    except KeyError as exc:
        raise PaperEngineError(
            f"No existe risk.risk_by_score.{runtime.paper_risk_bucket} en config."
        ) from exc


def _compute_entry_fee(entry_price: float, size_units: float, fee_rate: float) -> float:
    return entry_price * size_units * fee_rate


def _compute_exit_fee(exit_price: float, size_units: float, fee_rate: float) -> float:
    return exit_price * size_units * fee_rate


def _compute_pnl_gross(side: str, entry_price: float, exit_price: float, size_units: float) -> float:
    if side == "LONG":
        return (exit_price - entry_price) * size_units
    if side == "SHORT":
        return (entry_price - exit_price) * size_units
    raise PaperEngineError(f"Side inválido: {side}")


def _resolve_long_stop_exit_price(candle_open: float, stop_price: float) -> float:
    return candle_open if candle_open < stop_price else stop_price


def _resolve_short_stop_exit_price(candle_open: float, stop_price: float) -> float:
    return candle_open if candle_open > stop_price else stop_price


def _open_position(
    state: PaperState,
    *,
    symbol: str,
    timestamp: pd.Timestamp,
    order_plan: Any,
    sizing: PositionSizingResult,
    fee_rate_entry: float,
    events: list[str],
) -> None:
    fee_entry = _compute_entry_fee(
        float(order_plan.entry_price),
        float(sizing.position_size_units),
        fee_rate_entry,
    )

    position = PaperPosition(
        symbol=symbol,
        side=str(order_plan.side),
        entry_time=str(timestamp),
        last_update_time=str(timestamp),
        entry_price=float(order_plan.entry_price),
        stop_price=float(order_plan.stop_price),
        tp1_price=float(order_plan.tp1_price),
        tp2_price=float(order_plan.tp2_price),
        leverage=float(sizing.leverage),
        risk_pct=float(sizing.risk_pct),
        current_risk_pct=float(sizing.risk_pct),
        initial_quantity=float(sizing.position_size_units),
        remaining_quantity=float(sizing.position_size_units),
        notional_value_usdt=float(sizing.notional_value_usdt),
        fee_entry_usdt=fee_entry,
        realized_pnl_net_usdt=-fee_entry,
        notes=list(order_plan.notes),
    )

    state.open_positions[symbol] = position
    state.open_risk_pct += position.current_risk_pct
    _apply_realized_delta(state, -fee_entry)
    _append_event(
        state,
        events,
        (
            f"OPEN {symbol} {position.side} qty={position.initial_quantity:.6f} "
            f"entry={position.entry_price:.4f} risk_pct={position.risk_pct:.4f} "
            f"fee_entry={fee_entry:.4f}"
        ),
    )


def _register_partial_exit(
    state: PaperState,
    position: PaperPosition,
    *,
    timestamp: pd.Timestamp,
    exit_price: float,
    size_units: float,
    fee_rate_exit: float,
    note: str,
    events: list[str],
) -> None:
    pnl_gross = _compute_pnl_gross(position.side, position.entry_price, exit_price, size_units)
    fee_exit = _compute_exit_fee(exit_price, size_units, fee_rate_exit)
    net_delta = pnl_gross - fee_exit

    previous_risk = position.current_risk_pct
    position.remaining_quantity -= size_units
    if position.remaining_quantity < -1e-12:
        raise PaperEngineError(f"remaining_quantity negativa en {position.symbol}.")
    if position.remaining_quantity <= 1e-12:
        position.remaining_quantity = 0.0
        position.current_risk_pct = 0.0
    else:
        remaining_ratio = position.remaining_quantity / position.initial_quantity
        position.current_risk_pct = position.risk_pct * remaining_ratio

    state.open_risk_pct += position.current_risk_pct - previous_risk
    position.last_update_time = str(timestamp)
    position.realized_pnl_gross_usdt += pnl_gross
    position.fee_exit_usdt += fee_exit
    position.realized_pnl_net_usdt += net_delta
    position.notes.append(note)
    _apply_realized_delta(state, net_delta)
    _append_event(
        state,
        events,
        (
            f"EXIT {position.symbol} {note} qty={size_units:.6f} price={exit_price:.4f} "
            f"gross={pnl_gross:.4f} fee_exit={fee_exit:.4f} net={net_delta:.4f}"
        ),
    )


def _close_position(state: PaperState, symbol: str, events: list[str]) -> None:
    position = state.open_positions.pop(symbol)
    state.total_trades += 1
    if position.realized_pnl_net_usdt > 0:
        state.winning_trades += 1
    elif position.realized_pnl_net_usdt < 0:
        state.losing_trades += 1

    _append_event(
        state,
        events,
        (
            f"CLOSE {symbol} net_total={position.realized_pnl_net_usdt:.4f} "
            f"tp1_hit={position.tp1_hit}"
        ),
    )


def _manage_position_on_candle(
    state: PaperState,
    position: PaperPosition,
    *,
    candle: Mapping[str, Any],
    fee_rate_exit: float,
    events: list[str],
) -> bool:
    candle_time = pd.to_datetime(candle["timestamp"], utc=True)
    candle_open = float(candle["open"])
    candle_high = float(candle["high"])
    candle_low = float(candle["low"])

    if position.remaining_quantity <= 0:
        return True

    if position.side == "LONG":
        if not position.tp1_hit:
            if candle_low <= position.stop_price:
                exit_price = _resolve_long_stop_exit_price(candle_open, position.stop_price)
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=exit_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="STOP_LOSS antes de TP1",
                    events=events,
                )
                return True

            if candle_high >= position.tp2_price:
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=position.tp2_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="TP2 directo sin TP1",
                    events=events,
                )
                return True

            if candle_high >= position.tp1_price:
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=position.tp1_price,
                    size_units=position.initial_quantity * TP1_FRACTION,
                    fee_rate_exit=fee_rate_exit,
                    note="TP1 parcial",
                    events=events,
                )
                position.tp1_hit = True
                return False

        else:
            if candle_low <= position.stop_price:
                exit_price = _resolve_long_stop_exit_price(candle_open, position.stop_price)
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=exit_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="STOP remanente después de TP1",
                    events=events,
                )
                return True

            if candle_high >= position.tp2_price:
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=position.tp2_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="TP2 remanente",
                    events=events,
                )
                return True

    elif position.side == "SHORT":
        if not position.tp1_hit:
            if candle_high >= position.stop_price:
                exit_price = _resolve_short_stop_exit_price(candle_open, position.stop_price)
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=exit_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="STOP_LOSS antes de TP1",
                    events=events,
                )
                return True

            if candle_low <= position.tp2_price:
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=position.tp2_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="TP2 directo sin TP1",
                    events=events,
                )
                return True

            if candle_low <= position.tp1_price:
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=position.tp1_price,
                    size_units=position.initial_quantity * TP1_FRACTION,
                    fee_rate_exit=fee_rate_exit,
                    note="TP1 parcial",
                    events=events,
                )
                position.tp1_hit = True
                return False

        else:
            if candle_high >= position.stop_price:
                exit_price = _resolve_short_stop_exit_price(candle_open, position.stop_price)
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=exit_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="STOP remanente después de TP1",
                    events=events,
                )
                return True

            if candle_low <= position.tp2_price:
                _register_partial_exit(
                    state,
                    position,
                    timestamp=candle_time,
                    exit_price=position.tp2_price,
                    size_units=position.remaining_quantity,
                    fee_rate_exit=fee_rate_exit,
                    note="TP2 remanente",
                    events=events,
                )
                return True

    else:
        raise PaperEngineError(f"Side inválido en posición paper: {position.side}")

    position.last_update_time = str(candle_time)
    return False


def run_paper_cycle(
    *,
    config: Mapping[str, Any],
    market_data_by_symbol: Mapping[str, pd.DataFrame],
    state: PaperState,
) -> PaperCycleResult:
    if not market_data_by_symbol:
        raise PaperEngineError("market_data_by_symbol no puede venir vacío.")

    runtime = load_runtime_config(config)
    if runtime.mode != "paper":
        raise PaperEngineError(
            f"run_paper_cycle requiere runtime.mode='paper', actual: {runtime.mode}"
        )

    non_empty_frames = [df for df in market_data_by_symbol.values() if not df.empty]
    if not non_empty_frames:
        raise PaperEngineError("No hay dataframes con datos para paper cycle.")

    cycle_timestamp = max(pd.to_datetime(df.iloc[-1]["timestamp"], utc=True) for df in non_empty_frames)
    _reset_period_trackers(state, cycle_timestamp)

    fee_rate_entry = float(config["execution"]["fee_rate_entry"])
    fee_rate_exit = float(config["execution"]["fee_rate_exit"])
    max_open_positions = int(config["risk"]["max_open_positions"])
    max_open_risk_pct = float(config["risk"]["max_open_risk"]["normal"])
    daily_limit_pct = float(config["risk"]["loss_limits"]["daily"])
    weekly_limit_pct = float(config["risk"]["loss_limits"]["weekly"])
    paper_risk_pct = _risk_pct_for_paper(config, runtime)

    opened_symbols: list[str] = []
    closed_symbols: list[str] = []
    updated_symbols: list[str] = []
    events: list[str] = []

    eligible_market_data: dict[str, pd.DataFrame] = {}
    eligible_trigger_indices: dict[str, int] = {}

    for symbol, market_df in market_data_by_symbol.items():
        if market_df.empty:
            continue

        latest_candle = market_df.iloc[-1]
        latest_timestamp = str(pd.to_datetime(latest_candle["timestamp"], utc=True))
        if state.processed_candle_timestamps.get(symbol) == latest_timestamp:
            continue

        had_position = symbol in state.open_positions
        if had_position:
            position = state.open_positions[symbol]
            fully_closed = _manage_position_on_candle(
                state,
                position,
                candle=latest_candle,
                fee_rate_exit=fee_rate_exit,
                events=events,
            )
            updated_symbols.append(symbol)
            if fully_closed:
                _close_position(state, symbol, events)
                closed_symbols.append(symbol)

        state.processed_candle_timestamps[symbol] = latest_timestamp

        if had_position:
            continue

        if symbol in state.open_positions:
            continue

        eligible_market_data[symbol] = market_df
        eligible_trigger_indices[symbol] = len(market_df) - 1

    daily_drawdown_pct = _compute_drawdown_pct(state.realized_pnl_today, state.day_start_balance)
    weekly_drawdown_pct = _compute_drawdown_pct(state.realized_pnl_week, state.week_start_balance)

    if eligible_market_data:
        candidates = scan_trade_candidates(
            market_data_by_symbol=eligible_market_data,
            trigger_index_by_symbol=eligible_trigger_indices,
            entry_price_resolver=lambda _symbol, df, idx: float(df.iloc[idx]["close"]),
        )

        for symbol_candidate in sorted(candidates, key=lambda item: item.symbol):
            symbol = symbol_candidate.symbol
            order_plan = symbol_candidate.candidate.order_plan

            allowed_by_limits, limit_notes = system_loss_limits_allow_trade(
                daily_drawdown_pct=daily_drawdown_pct,
                weekly_drawdown_pct=weekly_drawdown_pct,
                daily_limit_pct=daily_limit_pct,
                weekly_limit_pct=weekly_limit_pct,
            )
            if not allowed_by_limits:
                _append_event(state, events, f"SKIP {symbol} loss_limits: {' | '.join(limit_notes)}")
                continue

            allowed_by_portfolio, portfolio_notes = portfolio_allows_new_trade(
                current_open_positions=len(state.open_positions),
                max_open_positions=max_open_positions,
                current_open_risk_pct=state.open_risk_pct,
                candidate_risk_pct=paper_risk_pct,
                max_open_risk_pct=max_open_risk_pct,
            )
            if not allowed_by_portfolio:
                _append_event(state, events, f"SKIP {symbol} portfolio_limits: {' | '.join(portfolio_notes)}")
                continue

            sizing = calculate_position_size(
                equity=state.equity,
                risk_pct=paper_risk_pct,
                entry_price=float(order_plan.entry_price),
                stop_price=float(order_plan.stop_price),
                leverage=float(config["leverage"][symbol]),
                max_notional_pct=float(config["position_limits"]["max_notional_pct"][symbol]),
            )
            if not sizing.sizing_allowed:
                _append_event(state, events, f"SKIP {symbol} sizing: {' | '.join(sizing.notes)}")
                continue

            timestamp = pd.to_datetime(
                eligible_market_data[symbol].iloc[eligible_trigger_indices[symbol]]["timestamp"],
                utc=True,
            )
            _open_position(
                state,
                symbol=symbol,
                timestamp=timestamp,
                order_plan=order_plan,
                sizing=sizing,
                fee_rate_entry=fee_rate_entry,
                events=events,
            )
            opened_symbols.append(symbol)

    return PaperCycleResult(
        state=state,
        opened_symbols=opened_symbols,
        closed_symbols=closed_symbols,
        updated_symbols=updated_symbols,
        events=events,
    )
