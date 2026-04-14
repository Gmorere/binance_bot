from __future__ import annotations

import argparse

from src.core.config_loader import get_default_config_path, load_config
from src.live.live_runtime import run_live_runtime_loop
from src.live.runtime_config import load_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live runtime (modo seguro v0.1)")
    parser.add_argument("--once", action="store_true", help="Ejecuta un solo ciclo y termina")
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Cantidad maxima de ciclos antes de salir",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(get_default_config_path())
    runtime = load_runtime_config(config)
    if runtime.mode != "live":
        raise SystemExit("run_live.py requiere runtime.mode='live' en la configuracion activa")

    summary = run_live_runtime_loop(
        config=config,
        once=bool(args.once),
        max_cycles=args.max_cycles,
    )
    print(
        "summary "
        f"cycles_executed={summary.cycles_executed} "
        f"account_checks={summary.account_checks} "
        f"reconciliations_ok={summary.reconciliations_ok} "
        f"orders_submitted={summary.orders_submitted} "
        f"orders_blocked={summary.orders_blocked} "
        f"cycle_errors={summary.cycle_errors} "
        f"live_execution_enabled={summary.live_execution_enabled}"
    )


if __name__ == "__main__":
    main()
