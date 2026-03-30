from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigError(Exception):
    """Error de configuracion del proyecto."""


DATA_PATH_ENV_OVERRIDES = {
    "raw_data_path": "BOT_RAW_DATA_PATH",
    "processed_data_path": "BOT_PROCESSED_DATA_PATH",
    "outputs_path": "BOT_OUTPUTS_PATH",
}
DEFAULT_CONFIG_PATH = Path("config/base.yaml")


def get_default_config_path(env: Mapping[str, str] | None = None) -> Path:
    source = env or os.environ
    raw_path = str(source.get("BOT_CONFIG_PATH", DEFAULT_CONFIG_PATH)).strip()
    if not raw_path:
        raise ConfigError("BOT_CONFIG_PATH no puede estar vacio.")
    return Path(raw_path).expanduser()


def _validate_required_sections(config: dict[str, Any]) -> None:
    required_sections = [
        "project",
        "capital",
        "symbols",
        "timeframes",
        "strategy",
        "score_thresholds",
        "risk",
        "leverage",
        "position_limits",
        "execution",
        "filters",
        "data",
        "reporting",
    ]

    missing = [section for section in required_sections if section not in config]
    if missing:
        raise ConfigError(
            f"Faltan secciones obligatorias en base.yaml: {', '.join(missing)}"
        )


def _validate_symbols(config: dict[str, Any]) -> None:
    enabled_symbols = config.get("symbols", {}).get("enabled", [])
    if not enabled_symbols:
        raise ConfigError("La lista symbols.enabled no puede estar vacia.")

    leverage_map = config.get("leverage", {})
    max_notional_pct_map = config.get("position_limits", {}).get("max_notional_pct", {})
    slippage_map = config.get("execution", {}).get("slippage", {})

    for symbol in enabled_symbols:
        if symbol not in leverage_map:
            raise ConfigError(f"Falta leverage configurado para el simbolo: {symbol}")
        if symbol not in max_notional_pct_map:
            raise ConfigError(
                f"Falta position_limits.max_notional_pct para el simbolo: {symbol}"
            )
        if symbol not in slippage_map:
            raise ConfigError(f"Falta execution.slippage para el simbolo: {symbol}")


def _validate_risk(config: dict[str, Any]) -> None:
    risk_cfg = config.get("risk", {})
    risk_by_score = risk_cfg.get("risk_by_score", {})
    max_open_risk = risk_cfg.get("max_open_risk", {})
    loss_limits = risk_cfg.get("loss_limits", {})

    required_risk_keys = ["small", "normal", "strong", "exceptional"]
    for key in required_risk_keys:
        if key not in risk_by_score:
            raise ConfigError(f"Falta risk.risk_by_score.{key}")

    required_open_risk_keys = ["normal", "offensive", "absolute"]
    for key in required_open_risk_keys:
        if key not in max_open_risk:
            raise ConfigError(f"Falta risk.max_open_risk.{key}")

    required_loss_limit_keys = ["daily", "weekly"]
    for key in required_loss_limit_keys:
        if key not in loss_limits:
            raise ConfigError(f"Falta risk.loss_limits.{key}")

    if risk_cfg.get("max_open_positions", 0) <= 0:
        raise ConfigError("risk.max_open_positions debe ser mayor a 0.")

    if max_open_risk["normal"] > max_open_risk["offensive"]:
        raise ConfigError(
            "risk.max_open_risk.normal no puede ser mayor que offensive."
        )

    if max_open_risk["offensive"] > max_open_risk["absolute"]:
        raise ConfigError(
            "risk.max_open_risk.offensive no puede ser mayor que absolute."
        )


def _validate_thresholds(config: dict[str, Any]) -> None:
    thresholds = config.get("score_thresholds", {})
    min_trade = thresholds.get("min_trade")
    aggressive = thresholds.get("aggressive")
    exceptional = thresholds.get("exceptional")

    if min_trade is None or aggressive is None or exceptional is None:
        raise ConfigError("Faltan valores en score_thresholds.")

    if not (0 <= min_trade <= aggressive <= exceptional <= 100):
        raise ConfigError(
            "Los score_thresholds deben cumplir: 0 <= min_trade <= aggressive <= exceptional <= 100."
        )


def _validate_paths(config: dict[str, Any]) -> None:
    data_cfg = config.get("data", {})
    required_paths = ["raw_data_path", "processed_data_path", "outputs_path"]

    for key in required_paths:
        path_value = data_cfg.get(key)
        if not path_value:
            raise ConfigError(f"Falta data.{key}")


def validate_config(config: dict[str, Any]) -> None:
    """Valida la estructura minima del archivo de configuracion."""
    _validate_required_sections(config)
    _validate_symbols(config)
    _validate_risk(config)
    _validate_thresholds(config)
    _validate_paths(config)


def _infer_base_dir(config_path: Path, env: Mapping[str, str] | None = None) -> Path:
    source = env or os.environ
    override = str(source.get("BOT_BASE_DIR", "")).strip()
    if override:
        return Path(override).expanduser().resolve()

    resolved_config = config_path.expanduser().resolve()
    if resolved_config.parent.name.lower() == "config":
        return resolved_config.parent.parent
    return resolved_config.parent


def _resolve_data_path(path_value: str | Path, base_dir: Path) -> Path:
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def _normalize_data_paths(
    config: dict[str, Any],
    *,
    config_path: Path,
    env: Mapping[str, str] | None = None,
) -> None:
    source = env or os.environ
    base_dir = _infer_base_dir(config_path, env=source)
    data_cfg = dict(config.get("data", {}))

    for key, env_var in DATA_PATH_ENV_OVERRIDES.items():
        raw_value = source.get(env_var, data_cfg[key])
        data_cfg[key] = str(_resolve_data_path(raw_value, base_dir))

    config["data"] = data_cfg
    config["_meta"] = {
        "config_path": str(config_path.expanduser().resolve()),
        "base_dir": str(base_dir),
    }


def load_config(
    config_path: str | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """
    Carga y valida un archivo YAML de configuracion.
    """
    path = Path(config_path).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de configuracion: {path}")

    if not path.is_file():
        raise ConfigError(f"La ruta no corresponde a un archivo valido: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Error leyendo YAML en {path}: {exc}") from exc

    if not isinstance(config, dict):
        raise ConfigError("El archivo YAML debe contener un diccionario raiz.")

    validate_config(config)
    _normalize_data_paths(config, config_path=path, env=env)
    return config


def resolve_project_paths(config: dict[str, Any]) -> dict[str, Path]:
    """Convierte las rutas del YAML a objetos Path absolutos."""
    data_cfg = config["data"]

    return {
        "raw_data_path": Path(data_cfg["raw_data_path"]).resolve(),
        "processed_data_path": Path(data_cfg["processed_data_path"]).resolve(),
        "outputs_path": Path(data_cfg["outputs_path"]).resolve(),
    }


def ensure_project_directories(config: dict[str, Any]) -> None:
    """Crea las carpetas clave del proyecto si no existen."""
    paths = resolve_project_paths(config)

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    default_config_path = get_default_config_path()

    try:
        loaded_config = load_config(default_config_path)
        ensure_project_directories(loaded_config)
        print("Configuracion cargada correctamente.")
        print(f"Proyecto: {loaded_config['project']['name']}")
        print(f"Simbolos habilitados: {loaded_config['symbols']['enabled']}")
        print(f"Base dir: {loaded_config['_meta']['base_dir']}")
    except Exception as exc:
        print(f"Error cargando configuracion: {exc}")
