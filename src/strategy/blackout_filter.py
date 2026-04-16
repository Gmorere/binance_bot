from __future__ import annotations

"""
blackout_filter.py — Filtro de fechas donde el bot no debe abrir nuevas posiciones.

Ejemplos de uso en el config YAML:

    blackout_dates:
      enabled: true
      periods:
        - label: "FOMC Jan 2025"
          start: "2025-01-28"
          end: "2025-01-29"
        - label: "CPI Feb 2025"
          start: "2025-02-12"
          end: "2025-02-12"
        - label: "NFP Mar 2025"
          start: "2025-03-07 12:30"
          end: "2025-03-07 18:00"

Notas:
- start/end se interpretan como UTC.
- Una fecha sin hora (YYYY-MM-DD) cubre el día completo (00:00 a 23:59:59).
- El filtro bloquea ENTRADAS nuevas; los trades ya abiertos siguen corriendo.
- Si blackout_dates no existe en el config, o enabled=false, no se filtra nada.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd


class BlackoutFilterError(Exception):
    """Error de configuración del filtro de blackout."""


@dataclass
class BlackoutPeriod:
    label: str
    start: datetime   # UTC, inclusive
    end: datetime     # UTC, inclusive (fin de día si no se especificó hora)


def _parse_datetime_utc(raw: str, label: str, field: str) -> datetime:
    """
    Parsea una fecha o datetime en formato:
      - "YYYY-MM-DD"           → fecha completa, hora depende del contexto
      - "YYYY-MM-DD HH:MM"     → fecha + hora
      - "YYYY-MM-DD HH:MM:SS"  → fecha + hora + segundos
    Siempre retorna un datetime timezone-aware en UTC.
    """
    raw = str(raw).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise BlackoutFilterError(
        f"Blackout '{label}' — formato de fecha inválido en '{field}': '{raw}'. "
        "Use YYYY-MM-DD o YYYY-MM-DD HH:MM."
    )


def load_blackout_periods(config: dict[str, Any]) -> list[BlackoutPeriod]:
    """
    Extrae y parsea los períodos de blackout desde el config.
    Retorna lista vacía si la sección no existe o está deshabilitada.
    """
    blackout_cfg = config.get("blackout_dates", {})
    if not blackout_cfg:
        return []

    if not bool(blackout_cfg.get("enabled", True)):
        return []

    raw_periods = blackout_cfg.get("periods", [])
    if not raw_periods:
        return []

    periods: list[BlackoutPeriod] = []

    for i, raw in enumerate(raw_periods):
        label = str(raw.get("label", f"period_{i}")).strip()
        raw_start = raw.get("start")
        raw_end = raw.get("end")

        if raw_start is None or raw_end is None:
            raise BlackoutFilterError(
                f"Blackout '{label}' — faltan campos 'start' o 'end'."
            )

        start_dt = _parse_datetime_utc(str(raw_start), label, "start")
        end_raw = str(raw_end).strip()

        # Si end solo tiene fecha (sin hora), lo extendemos al final del día
        if len(end_raw) == 10:
            end_dt = _parse_datetime_utc(end_raw, label, "end")
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        else:
            end_dt = _parse_datetime_utc(end_raw, label, "end")

        if end_dt < start_dt:
            raise BlackoutFilterError(
                f"Blackout '{label}' — 'end' ({end_raw}) es anterior a 'start' ({raw_start})."
            )

        periods.append(BlackoutPeriod(label=label, start=start_dt, end=end_dt))

    return periods


def is_blackout(
    timestamp: pd.Timestamp | datetime,
    periods: list[BlackoutPeriod],
) -> bool:
    """
    Retorna True si el timestamp cae dentro de algún período de blackout.
    El timestamp debe ser UTC o timezone-aware.
    """
    if not periods:
        return False

    if isinstance(timestamp, pd.Timestamp):
        dt = timestamp.to_pydatetime()
    else:
        dt = timestamp

    # Normalizar a UTC si no tiene timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    for period in periods:
        if period.start <= dt <= period.end:
            return True

    return False


def describe_blackout_periods(periods: list[BlackoutPeriod]) -> str:
    """Resumen legible de los períodos configurados."""
    if not periods:
        return "Sin períodos de blackout configurados."
    lines = [
        f"  {p.label}: {p.start.strftime('%Y-%m-%d %H:%M')} UTC -> {p.end.strftime('%Y-%m-%d %H:%M')} UTC"
        for p in periods
    ]
    return "\n".join(lines)
