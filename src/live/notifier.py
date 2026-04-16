from __future__ import annotations

"""
notifier.py — Alertas y comandos por Telegram para el runtime de paper trading.

Configuracion via variables de entorno:
  TG_BOT_TOKEN  — token del bot (de @BotFather)
  TG_CHAT_ID    — chat ID del destinatario autorizado

Si alguna de las dos variables no esta presente, el notificador queda
deshabilitado silenciosamente: ninguna llamada genera error ni side-effect.

Comandos disponibles:
  /help    — lista de comandos
  /status  — estado del runtime (equity, ciclos, errores)
  /pos     — posiciones abiertas con entry/stop/TP
  /pnl     — resumen de PnL (hoy, semana, total)
"""

import os
from typing import Any

import requests


_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"
_SEND_TIMEOUT_SECONDS = 10
_POLL_TIMEOUT_SECONDS = 3

_HELP_TEXT = (
    "Comandos disponibles:\n"
    "/status  — equity, posiciones abiertas, ciclos\n"
    "/pos     — detalle de posiciones abiertas\n"
    "/pnl     — PnL de hoy, semana y total\n"
    "/pause   — pausar nuevas entradas\n"
    "/resume  — retomar operacion normal\n"
    "/help    — este mensaje"
)


class TelegramNotifier:
    """
    Envia alertas y responde comandos desde Telegram.
    Si no esta configurado, todas las operaciones son no-op.
    """

    def __init__(self, *, token: str, chat_id: str) -> None:
        self._token = token.strip()
        self._chat_id = chat_id.strip()
        self._enabled = bool(self._token and self._chat_id)
        self._last_update_id: int | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Envio de mensajes
    # ------------------------------------------------------------------

    def send(self, text: str) -> None:
        """Envia un mensaje al chat configurado. Silencia cualquier error."""
        if not self._enabled:
            return
        try:
            requests.post(
                f"{_TELEGRAM_API_BASE.format(token=self._token)}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
                timeout=_SEND_TIMEOUT_SECONDS,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Polling de comandos entrantes
    # ------------------------------------------------------------------

    def poll_commands(self) -> list[str]:
        """
        Consulta getUpdates y devuelve los comandos nuevos del chat autorizado.
        Actualiza el offset interno para no reprocesar mensajes.
        Solo acepta mensajes del chat_id configurado (seguridad).
        """
        if not self._enabled:
            return []
        try:
            params: dict[str, Any] = {"timeout": 1, "limit": 20}
            if self._last_update_id is not None:
                params["offset"] = self._last_update_id + 1

            resp = requests.get(
                f"{_TELEGRAM_API_BASE.format(token=self._token)}/getUpdates",
                params=params,
                timeout=_POLL_TIMEOUT_SECONDS,
            )
            data = resp.json()
            if not data.get("ok"):
                return []

            commands: list[str] = []
            for update in data.get("result", []):
                update_id = int(update["update_id"])
                self._last_update_id = max(self._last_update_id or 0, update_id)

                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = str(msg.get("text", "")).strip()

                # Solo aceptar mensajes del chat autorizado
                if chat_id != self._chat_id:
                    continue
                if text.startswith("/"):
                    commands.append(text.split()[0].lower())  # /status@botname → /status

            return commands
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Respuestas a comandos
    # ------------------------------------------------------------------

    def handle_commands(
        self,
        commands: list[str],
        *,
        mode: str,
        state: Any,
        cycles_executed: int,
        cycle_errors: int,
        trading_paused: bool = False,
    ) -> list[str]:
        """
        Procesa la lista de comandos y envia las respuestas correspondientes.
        Devuelve lista de acciones para el runtime: ["pause"] o ["resume"].
        """
        actions: list[str] = []
        for cmd in commands:
            if cmd == "/help":
                self.send(_HELP_TEXT)
            elif cmd == "/status":
                self._send_status(
                    mode=mode,
                    state=state,
                    cycles_executed=cycles_executed,
                    cycle_errors=cycle_errors,
                    trading_paused=trading_paused,
                )
            elif cmd == "/pos":
                self._send_positions(mode=mode, state=state)
            elif cmd == "/pnl":
                self._send_pnl(mode=mode, state=state)
            elif cmd == "/pause":
                if trading_paused:
                    self.send(f"[{mode.upper()}] El bot ya esta pausado. Usa /resume para retomar.")
                else:
                    actions.append("pause")
                    self.send(
                        f"[{mode.upper()}] PAUSADO\n"
                        "No se abriran nuevas entradas.\n"
                        "Las posiciones abiertas siguen siendo monitoreadas.\n"
                        "Usa /resume para retomar."
                    )
            elif cmd == "/resume":
                if not trading_paused:
                    self.send(f"[{mode.upper()}] El bot ya esta activo.")
                else:
                    actions.append("resume")
                    self.send(f"[{mode.upper()}] REANUDADO\nEl bot volvera a abrir entradas normalmente.")
            else:
                self.send(f"Comando no reconocido: {cmd}\n\n{_HELP_TEXT}")
        return actions

    def _send_status(
        self,
        *,
        mode: str,
        state: Any,
        cycles_executed: int,
        cycle_errors: int,
        trading_paused: bool = False,
    ) -> None:
        open_pos = len(state.open_positions)
        total_pnl = state.equity - state.initial_capital
        total_pnl_pct = total_pnl / state.initial_capital * 100
        total_sign = "+" if total_pnl >= 0 else ""
        paused_line = "\nESTADO: PAUSADO (usa /resume para retomar)" if trading_paused else ""
        self.send(
            f"[{mode.upper()}] STATUS{paused_line}\n"
            f"Equity:    ${state.equity:,.2f}  ({total_sign}{total_pnl_pct:.2f}%)\n"
            f"Posiciones abiertas: {open_pos}\n"
            f"Riesgo abierto: {state.open_risk_pct*100:.2f}%\n"
            f"Ciclos ejecutados: {cycles_executed}\n"
            f"Errores de ciclo: {cycle_errors}\n"
            f"Trades totales: {state.total_trades}\n"
            f"WR: {state.winning_trades}/{state.total_trades}"
            + (f"  ({state.winning_trades/state.total_trades*100:.0f}%)" if state.total_trades else "")
        )

    def _send_positions(self, *, mode: str, state: Any) -> None:
        if not state.open_positions:
            self.send(f"[{mode.upper()}] Sin posiciones abiertas.")
            return
        lines = [f"[{mode.upper()}] POSICIONES ABIERTAS ({len(state.open_positions)})"]
        for symbol, pos in state.open_positions.items():
            direction = "LONG" if pos.side.upper() == "LONG" else "SHORT"
            tp1_hit = "TP1 ✓" if pos.tp1_hit else "TP1 pendiente"
            lines.append(
                f"\n{symbol} {direction}\n"
                f"  Entry:  {pos.entry_price:,.4f}\n"
                f"  Stop:   {pos.stop_price:,.4f}\n"
                f"  TP1:    {pos.tp1_price:,.4f}  ({tp1_hit})\n"
                f"  TP2:    {pos.tp2_price:,.4f}\n"
                f"  Riesgo: {pos.current_risk_pct*100:.2f}%"
            )
        self.send("\n".join(lines))

    def _send_pnl(self, *, mode: str, state: Any) -> None:
        total_pnl = state.equity - state.initial_capital
        total_pnl_pct = total_pnl / state.initial_capital * 100
        today_sign = "+" if state.realized_pnl_today >= 0 else ""
        week_sign = "+" if state.realized_pnl_week >= 0 else ""
        total_sign = "+" if total_pnl >= 0 else ""
        self.send(
            f"[{mode.upper()}] PnL\n"
            f"Hoy:    {today_sign}${state.realized_pnl_today:.2f}\n"
            f"Semana: {week_sign}${state.realized_pnl_week:.2f}\n"
            f"Total:  {total_sign}${total_pnl:.2f}  ({total_sign}{total_pnl_pct:.2f}%)\n"
            f"Capital inicial: ${state.initial_capital:,.2f}\n"
            f"Equity actual:   ${state.equity:,.2f}"
        )

    # ------------------------------------------------------------------
    # Alertas de trading
    # ------------------------------------------------------------------

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
    Construye un TelegramNotifier leyendo TG_BOT_TOKEN y TG_CHAT_ID del entorno.
    Si alguna variable falta, devuelve un notificador deshabilitado.
    """
    source: Any = env if env is not None else os.environ
    token = str(source.get("TG_BOT_TOKEN", "")).strip()
    chat_id = str(source.get("TG_CHAT_ID", "")).strip()
    return TelegramNotifier(token=token, chat_id=chat_id)
