from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import pandas as pd

from src.live.candidate_scanner import scan_trade_candidates
from src.live.runtime_config import RuntimeConfig, load_runtime_config
from src.execution.slippage import apply_adverse_entry_slippage, apply_adverse_exit_slippage
from src.risk.risk_engine import (
    get_risk_pct_for_bucket,
    portfolio_allows_new_trade,
    system_loss_limits_allow_trade,
)
from src.risk.sizing_engine import PositionSizingResult, calculate_position_size
from src.strategy.scoring_policy import (
    CandidateRiskResolution,
    ScoringPolicyError,
    resolve_candidate_risk_from_score,
)
from src.strategy.context_policy import ContextPolicyError, evaluate_trade_candidate_policy
from src.strategy.runtime_policy import (
    load_backtest_strategy_policy,
    load_dynamic_risk_policy,
    resolve_pullback_settings,
    resolve_symbol_allowed_setups,
    resolve_symbol_backtest_risk,
    resolve_symbol_filters,
)
from src.strategy.setup_detector import detect_breakout_setup, detect_pullback_setup
from src.strategy.signal_service import detect_trade_candidate


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
    risk_bucket: str
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
    decision_counts: dict[str, int] = field(default_factory=dict)
    symbol_decisions: dict[str, str] = field(default_factory=dict)


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
        risk_bucket=str(payload.get("risk_bucket", "normal")),
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
    payload = json.dumps(serialized, ensure_ascii=False, indent=2)
    temp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(path)
    return path


def _week_id(timestamp: pd.Timestamp) -> str:
    iso = timestamp.isocalendar()
    return f"{int(iso.year):04d}-W{int(iso.week):02d}"


def _append_event(state: PaperState, events: list[str], message: str) -> None:
    state.event_log.append(message)
    if len(state.event_log) > MAX_EVENT_LOG:
        state.event_log = state.event_log[-MAX_EVENT_LOG:]
    events.append(message)


def _record_symbol_decision(
    *,
    symbol: str,
    decision: str,
    decision_counts: dict[str, int],
    symbol_decisions: dict[str, str],
) -> None:
    decision_counts[decision] = decision_counts.get(decision, 0) + 1
    symbol_decisions[symbol] = decision


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
    try:
        risk_pct, _risk_notes = get_risk_pct_for_bucket(
            risk_by_score=dict(config["risk"]["risk_by_score"]),
            risk_bucket=runtime.paper_risk_bucket,
        )
    except Exception as exc:
        raise PaperEngineError(f"No se pudo resolver risk bucket de paper: {exc}") from exc

    return risk_pct


def _resolve_candidate_paper_risk(
    *,
    config: Mapping[str, Any],
    runtime: RuntimeConfig,
    dynamic_risk_policy: Mapping[str, object],
    symbol: str,
    candidate: Any,
    df_1h: pd.DataFrame | None,
    df_4h: pd.DataFrame | None,
) -> CandidateRiskResolution:
    default_risk_pct, default_risk_bucket = resolve_symbol_backtest_risk(
        dict(config),
        symbol,
        _risk_pct_for_paper(config, runtime),
        runtime.paper_risk_bucket,
    )

    if not bool(dynamic_risk_policy.get("enabled", False)):
        return CandidateRiskResolution(
            trade_allowed=True,
            risk_pct=float(default_risk_pct),
            risk_bucket=str(default_risk_bucket),
            score_total=0.0,
            notes=["Dynamic risk deshabilitado en paper."],
        )

    if df_1h is None or df_4h is None:
        return CandidateRiskResolution(
            trade_allowed=True,
            risk_pct=float(default_risk_pct),
            risk_bucket=str(default_risk_bucket),
            score_total=0.0,
            notes=["Dynamic risk en paper sin contexto 1h/4h. Se usa riesgo base."],
        )

    try:
        risk_resolution = resolve_candidate_risk_from_score(
            symbol=symbol,
            candidate=candidate,
            df_1h=df_1h,
            df_4h=df_4h,
            score_thresholds={
                "min_trade": float(config["score_thresholds"]["min_trade"]),
                "aggressive": float(config["score_thresholds"]["aggressive"]),
                "exceptional": float(config["score_thresholds"]["exceptional"]),
            },
            risk_by_score={
                str(key): float(value)
                for key, value in dict(config["risk"]["risk_by_score"]).items()
            },
            open_positions=0,
            same_side_exposure_count=0,
        )
    except (ScoringPolicyError, KeyError, TypeError, ValueError) as exc:
        raise PaperEngineError(f"No se pudo resolver dynamic risk en paper: {exc}") from exc

    if (
        bool(dynamic_risk_policy.get("preserve_symbol_base_risk", True))
        and risk_resolution.trade_allowed
        and float(risk_resolution.risk_pct) < float(default_risk_pct)
    ):
        updated_notes = list(risk_resolution.notes)
        updated_notes.append(
            "Dynamic risk preserva riesgo base del simbolo en paper: "
            f"{risk_resolution.risk_pct:.4f} -> {float(default_risk_pct):.4f}"
        )
        return CandidateRiskResolution(
            trade_allowed=True,
            risk_pct=float(default_risk_pct),
            risk_bucket=str(risk_resolution.risk_bucket),
            score_total=float(risk_resolution.score_total),
            notes=updated_notes,
        )

    return risk_resolution


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
    risk_bucket: str,
    fee_rate_entry: float,
    slippage_pct: float,
    events: list[str],
) -> None:
    entry_price = apply_adverse_entry_slippage(
        side=str(order_plan.side),
        price=float(order_plan.entry_price),
        slippage_pct=slippage_pct,
    )
    fee_entry = _compute_entry_fee(
        entry_price,
        float(sizing.position_size_units),
        fee_rate_entry,
    )

    position = PaperPosition(
        symbol=symbol,
        side=str(order_plan.side),
        entry_time=str(timestamp),
        last_update_time=str(timestamp),
        entry_price=entry_price,
        stop_price=float(order_plan.stop_price),
        tp1_price=float(order_plan.tp1_price),
        tp2_price=float(order_plan.tp2_price),
        leverage=float(sizing.leverage),
        risk_pct=float(sizing.risk_pct),
        risk_bucket=str(risk_bucket),
        current_risk_pct=float(sizing.risk_pct),
        initial_quantity=float(sizing.position_size_units),
        remaining_quantity=float(sizing.position_size_units),
        notional_value_usdt=entry_price * float(sizing.position_size_units),
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
            f"risk_bucket={position.risk_bucket} "
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
    slippage_pct: float,
    note: str,
    events: list[str],
    apply_slippage: bool = True,
) -> None:
    filled_exit_price = (
        apply_adverse_exit_slippage(position.side, exit_price, slippage_pct)
        if apply_slippage
        else exit_price
    )
    pnl_gross = _compute_pnl_gross(position.side, position.entry_price, filled_exit_price, size_units)
    fee_exit = _compute_exit_fee(filled_exit_price, size_units, fee_rate_exit)
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
            f"EXIT {position.symbol} {note} qty={size_units:.6f} price={filled_exit_price:.4f} "
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
    slippage_pct: float,
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
                    slippage_pct=slippage_pct,
                    note="STOP_LOSS antes de TP1",
                    events=events,
                    apply_slippage=exit_price == position.stop_price,
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
                    slippage_pct=slippage_pct,
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
                    slippage_pct=slippage_pct,
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
                    slippage_pct=slippage_pct,
                    note="STOP remanente despues de TP1",
                    events=events,
                    apply_slippage=exit_price == position.stop_price,
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
                    slippage_pct=slippage_pct,
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
                    slippage_pct=slippage_pct,
                    note="STOP_LOSS antes de TP1",
                    events=events,
                    apply_slippage=exit_price == position.stop_price,
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
                    slippage_pct=slippage_pct,
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
                    slippage_pct=slippage_pct,
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
                    slippage_pct=slippage_pct,
                    note="STOP remanente despues de TP1",
                    events=events,
                    apply_slippage=exit_price == position.stop_price,
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
                    slippage_pct=slippage_pct,
                    note="TP2 remanente",
                    events=events,
                )
                return True

    else:
        raise PaperEngineError(f"Side invalido en posicion paper: {position.side}")

    position.last_update_time = str(candle_time)
    return False


def _get_unprocessed_candles(
    market_df: pd.DataFrame,
    last_processed_timestamp: str | None,
) -> pd.DataFrame:
    if market_df.empty:
        return market_df.iloc[0:0].copy()

    if not last_processed_timestamp:
        return market_df.tail(1).copy().reset_index(drop=True)

    last_processed = pd.Timestamp(last_processed_timestamp)
    pending = market_df.loc[
        pd.to_datetime(market_df["timestamp"], utc=True) > last_processed
    ].copy()
    return pending.reset_index(drop=True)


def _diagnose_no_candidate(
    *,
    config: Mapping[str, Any],
    symbol: str,
    market_df: pd.DataFrame,
    trigger_index: int,
) -> str:
    history_df = market_df.iloc[: trigger_index + 1].copy().reset_index(drop=True)
    symbol_filters = resolve_symbol_filters(dict(config), symbol)
    symbol_allowed_setups = resolve_symbol_allowed_setups(dict(config), symbol)
    pullback_settings = resolve_pullback_settings(dict(config), symbol)
    min_candles = int(symbol_filters.get("min_candles", 6))
    max_candles = int(symbol_filters.get("max_candles", 12))
    if min_candles < 2:
        min_candles = 2
    if max_candles < min_candles:
        max_candles = min_candles
    reasons: list[str] = []

    if "BREAKOUT" in symbol_allowed_setups:
        breakout_setup = detect_breakout_setup(
            df_15m=history_df,
            min_candles=min_candles,
            max_candles=max_candles,
            max_range_atr_multiple=float(
                symbol_filters.get("max_consolidation_range_atr_multiple", 1.2)
            ),
            min_volume_ratio=float(symbol_filters.get("min_breakout_volume_multiple", 1.0)),
            max_trigger_candle_atr_multiple=float(
                symbol_filters.get("max_trigger_candle_atr_multiple", 1.8)
            ),
        )
        if not bool(breakout_setup.get("detected", False)):
            notes = list(breakout_setup.get("notes", []))
            reasons.append(f"BREAKOUT={str(notes[0]) if notes else 'sin_detalle'}")

    if "PULLBACK" in symbol_allowed_setups:
        pullback_setup = detect_pullback_setup(
            df_15m=history_df,
            impulse_lookback_candles=int(
                pullback_settings.get("impulse_lookback_candles", 6)
            ),
            min_pullback_candles=int(pullback_settings.get("min_pullback_candles", 2)),
            max_pullback_candles=int(pullback_settings.get("max_pullback_candles", 5)),
            min_impulse_atr_multiple=float(
                pullback_settings.get("min_impulse_atr_multiple", 1.8)
            ),
            min_retrace_ratio=float(pullback_settings.get("min_retrace_ratio", 0.25)),
            max_retrace_ratio=float(pullback_settings.get("max_retrace_ratio", 0.60)),
            min_volume_ratio=float(symbol_filters.get("min_breakout_volume_multiple", 1.0)),
            max_trigger_candle_atr_multiple=float(
                symbol_filters.get("max_trigger_candle_atr_multiple", 1.8)
            ),
            max_trigger_body_atr_multiple=(
                float(pullback_settings["max_trigger_body_atr_multiple"])
                if "max_trigger_body_atr_multiple" in pullback_settings
                else None
            ),
        )
        if not bool(pullback_setup.get("detected", False)):
            notes = list(pullback_setup.get("notes", []))
            reasons.append(f"PULLBACK={str(notes[0]) if notes else 'sin_detalle'}")

    return " | ".join(reasons) if reasons else "sin_detalle"


def run_paper_cycle(
    *,
    config: Mapping[str, Any],
    market_data_by_symbol: Mapping[str, pd.DataFrame],
    state: PaperState,
    bias_market_data_by_symbol: Mapping[str, pd.DataFrame] | None = None,
    context_market_data_by_symbol: Mapping[str, pd.DataFrame] | None = None,
) -> PaperCycleResult:
    if not market_data_by_symbol:
        raise PaperEngineError("market_data_by_symbol no puede venir vacío.")

    runtime = load_runtime_config(config)
    if runtime.mode != "paper":
        raise PaperEngineError(
            f"run_paper_cycle requiere runtime.mode='paper', actual: {runtime.mode}"
        )

    backtest_policy = load_backtest_strategy_policy(dict(config))
    dynamic_risk_policy = load_dynamic_risk_policy(dict(config))
    bias_market_data_by_symbol = dict(bias_market_data_by_symbol or {})
    context_market_data_by_symbol = dict(context_market_data_by_symbol or {})
    non_empty_frames = [df for df in market_data_by_symbol.values() if not df.empty]
    if not non_empty_frames:
        raise PaperEngineError("No hay dataframes con datos para paper cycle.")

    cycle_timestamp = max(pd.to_datetime(df.iloc[-1]["timestamp"], utc=True) for df in non_empty_frames)

    fee_rate_entry = float(config["execution"]["fee_rate_entry"])
    fee_rate_exit = float(config["execution"]["fee_rate_exit"])
    symbol_slippage = dict(config["execution"].get("slippage", {}))
    max_open_positions = int(config["risk"]["max_open_positions"])
    max_open_risk_pct = float(config["risk"]["max_open_risk"]["normal"])
    daily_limit_pct = float(config["risk"]["loss_limits"]["daily"])
    weekly_limit_pct = float(config["risk"]["loss_limits"]["weekly"])

    opened_symbols: list[str] = []
    closed_symbols: list[str] = []
    updated_symbols: list[str] = []
    events: list[str] = []
    decision_counts: dict[str, int] = {}
    symbol_decisions: dict[str, str] = {}

    eligible_market_data: dict[str, pd.DataFrame] = {}
    eligible_trigger_indices: dict[str, int] = {}

    for symbol, market_df in market_data_by_symbol.items():
        pending_candles = _get_unprocessed_candles(
            market_df,
            state.processed_candle_timestamps.get(symbol),
        )
        if pending_candles.empty:
            continue

        had_position = symbol in state.open_positions
        if had_position:
            for pending_candle in pending_candles.to_dict("records"):
                _reset_period_trackers(
                    state,
                    pd.to_datetime(pending_candle["timestamp"], utc=True),
                )
                if symbol not in state.open_positions:
                    break
                position = state.open_positions[symbol]
                fully_closed = _manage_position_on_candle(
                    state,
                    position,
                    candle=pending_candle,
                    fee_rate_exit=fee_rate_exit,
                    slippage_pct=float(symbol_slippage.get(symbol, 0.0)),
                    events=events,
                )
                if fully_closed:
                    _close_position(state, symbol, events)
                    closed_symbols.append(symbol)
                    break
            updated_symbols.append(symbol)
            _record_symbol_decision(
                symbol=symbol,
                decision="managed_open_position",
                decision_counts=decision_counts,
                symbol_decisions=symbol_decisions,
            )

        latest_timestamp = str(pd.to_datetime(pending_candles.iloc[-1]["timestamp"], utc=True))
        state.processed_candle_timestamps[symbol] = latest_timestamp

        if had_position:
            continue

        if symbol in state.open_positions:
            _record_symbol_decision(
                symbol=symbol,
                decision="managed_open_position",
                decision_counts=decision_counts,
                symbol_decisions=symbol_decisions,
            )
            continue

        eligible_market_data[symbol] = market_df
        eligible_trigger_indices[symbol] = len(market_df) - 1

    _reset_period_trackers(state, cycle_timestamp)
    daily_drawdown_pct = _compute_drawdown_pct(state.realized_pnl_today, state.day_start_balance)
    weekly_drawdown_pct = _compute_drawdown_pct(state.realized_pnl_week, state.week_start_balance)

    if eligible_market_data:
        def _resolve_candidate(
            symbol_arg: str,
            market_df_arg: pd.DataFrame,
            trigger_index_arg: int,
            entry_reference_price: float,
        ):
            symbol_filters = resolve_symbol_filters(dict(config), symbol_arg)
            symbol_allowed_setups = resolve_symbol_allowed_setups(dict(config), symbol_arg)
            pullback_settings = resolve_pullback_settings(dict(config), symbol_arg)
            min_candles = int(symbol_filters.get("min_candles", 6))
            max_candles = int(symbol_filters.get("max_candles", 12))
            if min_candles < 2:
                min_candles = 2
            if max_candles < min_candles:
                max_candles = min_candles
            return detect_trade_candidate(
                symbol=symbol_arg,
                market_df=market_df_arg,
                trigger_index=trigger_index_arg,
                entry_reference_price=entry_reference_price,
                stop_buffer_atr_fraction=float(symbol_filters.get("stop_buffer_atr_fraction", 0.10)),
                min_candles=min_candles,
                max_candles=max_candles,
                max_range_atr_multiple=float(symbol_filters.get("max_consolidation_range_atr_multiple", 1.2)),
                min_volume_ratio=float(symbol_filters.get("min_breakout_volume_multiple", 1.0)),
                max_trigger_candle_atr_multiple=float(symbol_filters.get("max_trigger_candle_atr_multiple", 1.8)),
                allowed_setups=symbol_allowed_setups,
                impulse_lookback_candles=int(pullback_settings.get("impulse_lookback_candles", 6)),
                min_pullback_candles=int(pullback_settings.get("min_pullback_candles", 2)),
                max_pullback_candles=int(pullback_settings.get("max_pullback_candles", 5)),
                min_impulse_atr_multiple=float(pullback_settings.get("min_impulse_atr_multiple", 1.8)),
                min_retrace_ratio=float(pullback_settings.get("min_retrace_ratio", 0.25)),
                max_retrace_ratio=float(pullback_settings.get("max_retrace_ratio", 0.60)),
                max_trigger_body_atr_multiple=(
                    float(pullback_settings["max_trigger_body_atr_multiple"])
                    if "max_trigger_body_atr_multiple" in pullback_settings
                    else None
                ),
            )

        candidates = scan_trade_candidates(
            market_data_by_symbol=eligible_market_data,
            trigger_index_by_symbol=eligible_trigger_indices,
            entry_price_resolver=lambda _symbol, df, idx: float(df.iloc[idx]["close"]),
            trade_candidate_resolver=_resolve_candidate,
        )

        candidates_by_symbol = {item.symbol: item for item in candidates}
        for symbol in sorted(eligible_market_data.keys()):
            if symbol not in candidates_by_symbol:
                reason = _diagnose_no_candidate(
                    config=config,
                    symbol=symbol,
                    market_df=eligible_market_data[symbol],
                    trigger_index=eligible_trigger_indices[symbol],
                )
                _append_event(state, events, f"SKIP {symbol} no_candidate: {reason}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="no_candidate",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )

        for symbol_candidate in sorted(candidates_by_symbol.values(), key=lambda item: item.symbol):
            symbol = symbol_candidate.symbol
            candidate = symbol_candidate.candidate
            order_plan = candidate.order_plan

            try:
                candidate_allowed, candidate_notes = evaluate_trade_candidate_policy(
                    symbol=symbol,
                    candidate=candidate,
                    df_1h=bias_market_data_by_symbol.get(symbol),
                    df_4h=context_market_data_by_symbol.get(symbol),
                    allowed_sides_by_symbol=(
                        dict(backtest_policy["allowed_sides"])
                        if bool(backtest_policy["enabled"])
                        else None
                    ),
                    enforce_context_alignment=bool(
                        backtest_policy["enabled"]
                        and backtest_policy["enforce_context_alignment"]
                    ),
                )
            except ContextPolicyError as exc:
                _append_event(state, events, f"SKIP {symbol} context_policy_error: {exc}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="context_policy_error",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )
                continue

            if candidate_notes:
                order_plan.notes.extend(str(note) for note in candidate_notes)
            if not candidate_allowed:
                _append_event(state, events, f"SKIP {symbol} strategy_policy: {' | '.join(candidate_notes)}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="strategy_policy",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )
                continue

            allowed_by_limits, limit_notes = system_loss_limits_allow_trade(
                daily_drawdown_pct=daily_drawdown_pct,
                weekly_drawdown_pct=weekly_drawdown_pct,
                daily_limit_pct=daily_limit_pct,
                weekly_limit_pct=weekly_limit_pct,
            )
            if not allowed_by_limits:
                _append_event(state, events, f"SKIP {symbol} loss_limits: {' | '.join(limit_notes)}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="loss_limits",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )
                continue

            try:
                risk_resolution = _resolve_candidate_paper_risk(
                    config=config,
                    runtime=runtime,
                    dynamic_risk_policy=dynamic_risk_policy,
                    symbol=symbol,
                    candidate=candidate,
                    df_1h=bias_market_data_by_symbol.get(symbol),
                    df_4h=context_market_data_by_symbol.get(symbol),
                )
            except PaperEngineError as exc:
                _append_event(state, events, f"SKIP {symbol} dynamic_risk_error: {exc}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="dynamic_risk_error",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )
                continue

            if risk_resolution.notes:
                order_plan.notes.extend(str(note) for note in risk_resolution.notes)
            if not risk_resolution.trade_allowed:
                _append_event(state, events, f"SKIP {symbol} dynamic_risk: {' | '.join(risk_resolution.notes)}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="dynamic_risk",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )
                continue

            allowed_by_portfolio, portfolio_notes = portfolio_allows_new_trade(
                current_open_positions=len(state.open_positions),
                max_open_positions=max_open_positions,
                current_open_risk_pct=state.open_risk_pct,
                candidate_risk_pct=float(risk_resolution.risk_pct),
                max_open_risk_pct=max_open_risk_pct,
            )
            if not allowed_by_portfolio:
                _append_event(state, events, f"SKIP {symbol} portfolio_limits: {' | '.join(portfolio_notes)}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="portfolio_limits",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )
                continue

            sizing = calculate_position_size(
                equity=state.equity,
                risk_pct=float(risk_resolution.risk_pct),
                entry_price=float(order_plan.entry_price),
                stop_price=float(order_plan.stop_price),
                leverage=float(config["leverage"][symbol]),
                max_notional_pct=float(config["position_limits"]["max_notional_pct"][symbol]),
            )
            if not sizing.sizing_allowed:
                _append_event(state, events, f"SKIP {symbol} sizing: {' | '.join(sizing.notes)}")
                _record_symbol_decision(
                    symbol=symbol,
                    decision="sizing",
                    decision_counts=decision_counts,
                    symbol_decisions=symbol_decisions,
                )
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
                risk_bucket=str(risk_resolution.risk_bucket),
                fee_rate_entry=fee_rate_entry,
                slippage_pct=float(symbol_slippage.get(symbol, 0.0)),
                events=events,
            )
            opened_symbols.append(symbol)
            _record_symbol_decision(
                symbol=symbol,
                decision="opened",
                decision_counts=decision_counts,
                symbol_decisions=symbol_decisions,
            )

    return PaperCycleResult(
        state=state,
        opened_symbols=opened_symbols,
        closed_symbols=closed_symbols,
        updated_symbols=updated_symbols,
        events=events,
        decision_counts=decision_counts,
        symbol_decisions=symbol_decisions,
    )




















