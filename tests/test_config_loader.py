from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.core.config_loader import get_default_config_path, load_config, resolve_project_paths


CONFIG_BODY = """
project:
  name: test_bot
  version: \"0.1.0\"
  mode: backtest
capital:
  initial_capital: 10000.0
symbols:
  enabled:
    - BTCUSDT
timeframes:
  context: \"4h\"
  bias: \"1h\"
  entry: \"15m\"
strategy:
  name: test_strategy
score_thresholds:
  min_trade: 70
  aggressive: 85
  exceptional: 93
risk:
  risk_by_score:
    small: 0.004
    normal: 0.006
    strong: 0.0085
    exceptional: 0.011
  max_open_positions: 3
  max_open_risk:
    normal: 0.0225
    offensive: 0.03
    absolute: 0.035
  loss_limits:
    daily: 0.02
    weekly: 0.05
leverage:
  BTCUSDT: 8
position_limits:
  max_notional_pct:
    BTCUSDT: 0.60
execution:
  fee_rate_entry: 0.0004
  fee_rate_exit: 0.0004
  slippage:
    BTCUSDT: 0.0002
filters:
  min_rr_net: 1.8
  min_breakout_volume_multiple: 1.0
  max_consolidation_range_atr_multiple: 1.2
  max_trigger_candle_atr_multiple: 1.8
data:
  raw_data_path: data/raw
  processed_data_path: data/processed
  outputs_path: outputs
reporting:
  save_trades_csv: true
  save_metrics_json: true
  save_equity_chart: false
""".strip()


class ConfigLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path("tests") / "_tmp_config_loader" / uuid.uuid4().hex
        (self.base / "config").mkdir(parents=True, exist_ok=True)
        self.config_path = self.base / "config" / "base.yaml"
        self.config_path.write_text(CONFIG_BODY, encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)

    def test_load_config_resolves_relative_paths_from_project_root(self) -> None:
        config = load_config(self.config_path)
        paths = resolve_project_paths(config)

        self.assertEqual(paths["raw_data_path"], (self.base / "data" / "raw").resolve())
        self.assertEqual(paths["processed_data_path"], (self.base / "data" / "processed").resolve())
        self.assertEqual(paths["outputs_path"], (self.base / "outputs").resolve())

    def test_load_config_applies_env_path_overrides(self) -> None:
        raw_override = (self.base / "raw_override").resolve()
        processed_override = (self.base / "processed_override").resolve()
        outputs_override = (self.base / "outputs_override").resolve()
        config = load_config(
            self.config_path,
            env={
                "BOT_BASE_DIR": str(self.base),
                "BOT_RAW_DATA_PATH": str(raw_override),
                "BOT_PROCESSED_DATA_PATH": str(processed_override),
                "BOT_OUTPUTS_PATH": str(outputs_override),
            },
        )
        paths = resolve_project_paths(config)

        self.assertEqual(paths["raw_data_path"], raw_override)
        self.assertEqual(paths["processed_data_path"], processed_override)
        self.assertEqual(paths["outputs_path"], outputs_override)

    def test_get_default_config_path_uses_env_when_present(self) -> None:
        path = get_default_config_path({"BOT_CONFIG_PATH": str(self.config_path)})
        self.assertEqual(path, self.config_path)


if __name__ == "__main__":
    unittest.main()
