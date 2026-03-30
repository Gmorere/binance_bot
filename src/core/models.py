from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


Side = Literal["LONG", "SHORT"]
SetupType = Literal["BREAKOUT", "PULLBACK"]
BotMode = Literal["DEFENSIVE", "NORMAL", "OFFENSIVE"]
ExitReason = Literal["STOP_LOSS", "TP1", "TP2", "TRAILING", "INVALIDATION", "FORCED_EXIT"]


@dataclass
class Candle:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class ScoreBreakdown:
    mtf_alignment: float = 0.0
    structure: float = 0.0
    momentum: float = 0.0
    rr_quality: float = 0.0
    regime: float = 0.0
    volume: float = 0.0
    liquidity: float = 0.0
    correlation: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.mtf_alignment
            + self.structure
            + self.momentum
            + self.rr_quality
            + self.regime
            + self.volume
            + self.liquidity
            + self.correlation
        )


@dataclass
class ScoreResult:
    total: float
    breakdown: ScoreBreakdown
    trade_allowed: bool
    aggressive_allowed: bool
    exceptional_allowed: bool


@dataclass
class SetupSignal:
    symbol: str
    side: Side
    setup_type: SetupType
    detected_at: datetime
    entry_timeframe: str

    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float

    rr_net: float
    breakout_level: Optional[float] = None
    invalidation_price: Optional[float] = None

    volume_ratio: float = 0.0
    atr_value: float = 0.0

    notes: list[str] = field(default_factory=list)


@dataclass
class Trade:
    symbol: str
    side: Side
    setup_type: SetupType

    entry_time: datetime
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float

    score_total: float
    risk_pct: float
    leverage: float

    position_size: float
    notional_value: float

    fee_entry: float = 0.0
    fee_exit: float = 0.0
    slippage_cost: float = 0.0

    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[ExitReason] = None

    pnl_gross: float = 0.0
    pnl_net: float = 0.0

    tp1_hit: bool = False
    tp2_hit: bool = False
    is_open: bool = True


@dataclass
class PortfolioState:
    equity: float
    balance: float
    mode: BotMode = "NORMAL"

    open_positions: int = 0
    open_risk_pct: float = 0.0

    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0

    consecutive_losses: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


@dataclass
class BacktestResult:
    variant_name: str
    initial_capital: float
    final_equity: float
    net_return_pct: float
    max_drawdown_pct: float
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy: float