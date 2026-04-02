from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.baseline_diagnostics import (  # noqa: E402
    build_portfolio_diagnostic,
    build_symbol_diagnostic,
    load_trades_by_symbol,
    save_diagnostic_artifacts,
)
from src.core.config_loader import get_default_config_path, load_config, resolve_project_paths  # noqa: E402


def main() -> None:
    config = load_config(get_default_config_path())
    paths = resolve_project_paths(config)
    output_dir = paths["outputs_path"] / "backtests"
    baseline_summary_path = output_dir / "baseline_summary.json"

    if not baseline_summary_path.exists():
        raise FileNotFoundError(
            f"No existe baseline_summary.json en {baseline_summary_path}. Ejecuta primero el backtest."
        )

    baseline_summary = json.loads(baseline_summary_path.read_text(encoding="utf-8"))
    symbols = [str(item["symbol"]) for item in baseline_summary.get("symbols", [])]
    baseline_records_by_symbol = {
        str(item["symbol"]): item for item in baseline_summary.get("symbols", [])
    }
    trades_by_symbol = load_trades_by_symbol(output_dir, symbols)
    symbol_diagnostics = [
        build_symbol_diagnostic(
            symbol,
            trades_by_symbol[symbol],
            baseline_record=baseline_records_by_symbol.get(symbol),
        )
        for symbol in symbols
    ]
    portfolio_diagnostic = build_portfolio_diagnostic(symbol_diagnostics)
    artifact_paths = save_diagnostic_artifacts(
        output_dir=output_dir,
        baseline_summary=baseline_summary,
        symbol_diagnostics=symbol_diagnostics,
        portfolio_diagnostic=portfolio_diagnostic,
    )

    print("Diagnostico de baseline generado.")
    print(f"JSON -> {artifact_paths['json_path']}")
    print(f"Markdown -> {artifact_paths['md_path']}")
    print(
        "Resumen -> "
        f"worst_expectancy={portfolio_diagnostic['worst_expectancy_symbol']} | "
        f"highest_timeout={portfolio_diagnostic['highest_timeout_share_symbol']} | "
        f"highest_notional_cap={portfolio_diagnostic['highest_notional_capped_share_symbol']}"
    )


if __name__ == "__main__":
    main()
