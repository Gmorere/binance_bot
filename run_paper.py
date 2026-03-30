from __future__ import annotations

import argparse

from src.core.config_loader import get_default_config_path, load_config
from src.live.paper_runtime import run_paper_runtime_loop
from src.live.runtime_config import load_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paper trading runtime local/cloud")
    parser.add_argument("--once", action="store_true", help="Ejecuta un solo ciclo y termina")
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Cantidad maxima de ciclos a ejecutar antes de salir",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(get_default_config_path())
    runtime = load_runtime_config(config)

    if runtime.mode != "paper":
        raise SystemExit("run_paper.py requiere runtime.mode='paper' en la configuracion activa")

    summary = run_paper_runtime_loop(
        config=config,
        once=bool(args.once),
        max_cycles=args.max_cycles,
    )
    print(
        f"summary cycles_executed={summary.cycles_executed} cycles_with_new_candles={summary.cycles_with_new_candles} state_path={summary.last_state_path}"
    )


if __name__ == "__main__":
    main()
