from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from src.core.config_loader import get_default_config_path, load_config, resolve_project_paths


BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"
DEFAULT_START_YEAR = 2025
DEFAULT_START_MONTH = 1
DEFAULT_END_YEAR = 2026
DEFAULT_END_MONTH = 3


class DownloadError(Exception):
    """Error durante descarga o procesamiento de klines."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga historica mensual de Binance Data")
    parser.add_argument("--config", type=str, default=None, help="Ruta al YAML de configuracion")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--start-month", type=int, default=DEFAULT_START_MONTH)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--end-month", type=int, default=DEFAULT_END_MONTH)
    return parser.parse_args()


def month_range(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> Iterable[tuple[int, int]]:
    year = start_year
    month = start_month

    while (year < end_year) or (year == end_year and month <= end_month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def build_monthly_zip_url(symbol: str, interval: str, year: int, month: int) -> str:
    month_str = f"{month:02d}"
    filename = f"{symbol}-{interval}-{year}-{month_str}.zip"
    return f"{BASE_URL}/{symbol}/{interval}/{filename}"


def ensure_directories(output_dir: Path, temp_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)


def download_zip_bytes(url: str, timeout: int = 60) -> bytes:
    response = requests.get(url, timeout=timeout)
    if response.status_code == 404:
        raise FileNotFoundError(f"No existe archivo historico: {url}")
    response.raise_for_status()
    return response.content


def extract_csv_from_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_names = [name for name in zf.namelist() if name.endswith(".csv")]
        if not csv_names:
            raise DownloadError("El ZIP no contiene ningun archivo CSV.")

        csv_name = csv_names[0]
        with zf.open(csv_name) as csv_file:
            return pd.read_csv(csv_file, header=None)


def normalize_binance_kline_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    expected_min_cols = 6
    if df.shape[1] < expected_min_cols:
        raise DownloadError(
            f"El CSV tiene muy pocas columnas para ser un kline valido: {df.shape[1]}"
        )

    renamed = df.iloc[:, :12].copy()
    renamed.columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
        "ignore",
    ]

    normalized = renamed[["open_time", "open", "high", "low", "close", "volume"]].copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["open_time"], unit="ms", utc=True, errors="coerce"
    )

    for col in ["open", "high", "low", "close", "volume"]:
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized = normalized.drop(columns=["open_time"])
    normalized = normalized.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    normalized = normalized.drop_duplicates(subset=["timestamp"])
    normalized = normalized.sort_values("timestamp").reset_index(drop=True)

    return normalized[["timestamp", "open", "high", "low", "close", "volume"]]


def download_symbol_interval_history(
    symbol: str,
    interval: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for year, month in month_range(start_year, start_month, end_year, end_month):
        url = build_monthly_zip_url(symbol, interval, year, month)
        print(f"Descargando {symbol} {interval} {year}-{month:02d} ...")

        try:
            zip_bytes = download_zip_bytes(url)
            raw_df = extract_csv_from_zip(zip_bytes)
            normalized_df = normalize_binance_kline_dataframe(raw_df)
            frames.append(normalized_df)
        except FileNotFoundError:
            print(f"  - No disponible, se omite: {year}-{month:02d}")
        except Exception as exc:
            print(f"  - Error en {symbol} {interval} {year}-{month:02d}: {exc}")

    if not frames:
        raise DownloadError(f"No se descargaron datos para {symbol} {interval}")

    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def save_symbol_interval_csv(df: pd.DataFrame, symbol: str, interval: str, output_dir: Path) -> Path:
    output_path = output_dir / f"{symbol}_{interval}.csv"
    df.to_csv(output_path, index=False)
    return output_path


def main() -> None:
    args = parse_args()
    config_path = Path(args.config) if args.config else get_default_config_path()
    config = load_config(config_path)
    paths = resolve_project_paths(config)

    output_dir = paths["raw_data_path"]
    temp_dir = paths["processed_data_path"] / "temp_downloads"
    ensure_directories(output_dir, temp_dir)

    symbols = list(config["symbols"]["enabled"])
    intervals = list(dict.fromkeys([
        str(config["timeframes"]["entry"]),
        str(config["timeframes"]["bias"]),
        str(config["timeframes"]["context"]),
    ]))

    for symbol in symbols:
        for interval in intervals:
            try:
                df = download_symbol_interval_history(
                    symbol=symbol,
                    interval=interval,
                    start_year=args.start_year,
                    start_month=args.start_month,
                    end_year=args.end_year,
                    end_month=args.end_month,
                )
                saved_path = save_symbol_interval_csv(df, symbol, interval, output_dir)
                print(
                    f"OK -> {saved_path} | filas: {len(df)} | "
                    f"desde: {df['timestamp'].min()} | hasta: {df['timestamp'].max()}"
                )
            except Exception as exc:
                print(f"Fallo en {symbol} {interval}: {exc}")


if __name__ == "__main__":
    main()
