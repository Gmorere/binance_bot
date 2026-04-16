from __future__ import annotations

"""
notifier.py — Alertas por Telegram para el runtime de paper trading.

Configuracion via variables de entorno:
  TELEGRAM_BOT_TOKEN  — token del bot (de @BotFather)
  TELEGRAM_CHAT_ID    — chat ID del destinatario

Si alguna de las dos variables no esta presente, el notificador queda
deshabilitado silenciosamente: ninguna llamada genera error ni side-effect.
"""

import os
from dataclasses import dataclass
from typing import Any

import requests


_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_SEND_TIMEOUT_SECONDS = 10


class TelegramNotifier:
    """
    Envia mensajes de texto a un chat de Telegram.
    Si no esta configurado, todas las operaciones son no-op.
    """

    def __init__(self, *, token: str, chat_id: str) -> None:
        self._token = token.strip()
        self._chat_id = chat_id.strip()
        self._enabled = bool(self._token and self._chat_id)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def send(self, text: str) -> None:
        """Envia un mensaje. Silencia cualquier error para no romper el runtime."""
        if not self._enabled:
            return
        try:
            requests.post(
                _TELEGRAM_API.format(token=self._token),
                json={"chat_id": self._chat_id, "text": text},
                timeout=_SEND_TIMEOUT_SECONDS,
            )
        except Exception:
            pass

    # --- Mensajes de trading ---

    def notify_trade_opened(
        self,
        *,
        mode: str,
        symbol: str,
        side: str,
        entry_price: float,
        stop_price: float,
        tp1_price: float,
        tp2_price: float,
        risk_pct: float,
        risk_usdt: float,
        equity: float,
    ) -> None:
        direction = "LONG" if side.upper() == "LONG" else "SHORT"
        stop_dist_pct = abs(entry_price - stop_price) / entry_price * 100
        self.send(
            f"[{mode.upper()}] TRADE ABIERTO\n"
            f"{symbol} {direction}\n"
            f"Entry:  {entry_price:,.4f}\n"
            f"Stop:   {stop_price:,.4f}  (-{stop_dist_pct:.2f}%)\n"
            f"TP1:    {tp1_price:,.4f}\n"
            f"TP2:    {tp2_price:,.4f}\n"
            f"Riesgo: ${risk_usdt:.2f}  ({risk_pct*100:.2f}%)\n"
            f"Equity: ${equity:,.2f}"
        )

    def notify_trade_closed(
        self,
        *,
        mode: str,
        symbol: str,
        side: str,
        pnl_net_usdt: float,
        equity: float,
        total_trades: int,
        winning_trades: int,
        exit_notes: list[str],
    ) -> None:
        direction = "LONG" if side.upper() == "LONG" else "SHORT"
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0.0
        pnl_sign = "+" if pnl_net_usdt >= 0 else ""
        exit_summary = " / ".join(exit_notes) if exit_notes else "—"
        self.send(
            f"[{mode.upper()}] TRADE CERRADO\n"
            f"{symbol} {direction}  —  {exit_summary}\n"
            f"PnL:    {pnl_sign}${pnl_net_usdt:.2f}\n"
            f"Equity: ${equity:,.2f}\n"
            f"WR:     {winning_trades}/{total_trades}  ({win_rate:.0f}%)"
        )

    def notify_cycle_error(
        self,
        *,
        mode: str,
        cycle: int,
        total_errors: int,
        error_type: str,
        error_msg: str,
    ) -> None:
        self.send(
            f"[{mode.upper()}] ERROR DE CICLO\n"
            f"Ciclo: {cycle}  |  Errores totales: {total_errors}\n"
            f"Tipo:  {error_type}\n"
            f"Error: {error_msg[:200]}"
        )

    def notify_heartbeat(
        self,
        *,
        mode: str,
        date_utc: str,
        equity: float,
        initial_capital: float,
        pnl_today: float,
        pnl_week: float,
        open_positions: int,
        total_trades: int,
        cycle_errors: int,
    ) -> None:
        total_pnl = equity - initial_capital
        total_pnl_pct = total_pnl / initial_capital * 100
        today_sign = "+" if pnl_today >= 0 else ""
        week_sign = "+" if pnl_week >= 0 else ""
        total_sign = "+" if total_pnl >= 0 else ""
        self.send(
            f"[{mode.upper()}] HEARTBEAT  {date_utc}\n"
            f"Equity:    ${equity:,.2f}  ({total_sign}{total_pnl_pct:.2f}%)\n"
            f"Hoy:       {today_sign}${pnl_today:.2f}\n"
            f"Semana:    {week_sign}${pnl_week:.2f}\n"
            f"Posiciones abiertas: {open_positions}\n"
            f"Trades totales: {total_trades}\n"
            f"Errores de ciclo: {cycle_errors}"
        )


def build_notifier(env: dict[str, str] | None = None) -> TelegramNotifier:
    """
    Construye un TelegramNotifier leyendo TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
    del entorno. Si alguna variable falta, devuelve un notificador deshabilitado.
    """
    source: Any = env if env is not None else os.environ
    token = str(source.get("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(source.get("TELEGRAM_CHAT_ID", "")).strip()
    return TelegramNotifier(token=token, chat_id=chat_id)
