from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TradeRecord:
    symbol: str
    side: str

    entry_time: str
    exit_time: Optional[str]

    entry_price: float
    exit_price: Optional[float]

    stop_loss: float
    tp1: float
    tp2: float

    size_qty: float
    leverage: float

    pnl_gross_usdt: float
    fee_entry_usdt: float
    fee_exit_usdt: float
    pnl_net_usdt: float

    exit_reason: str
    exit_index: Optional[int]
    trade_closed: bool

    setup_type: str
    rr_1: float
    rr_2: float
    breakout_level: Optional[float]

    notes: Optional[str] = None