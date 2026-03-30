from __future__ import annotations

from pathlib import Path

from src.core.config_loader import load_config
from src.exchange.binance_usdm_client import BinanceUsdmClient, BinanceUsdmClientError
from src.live.runtime_config import load_runtime_config


def main() -> None:
    config = load_config(Path("config/base.yaml"))
    runtime = load_runtime_config(config)

    print(f"runtime.mode={runtime.mode}")
    print(f"runtime.exchange={runtime.exchange}")
    print(f"binance.use_testnet={runtime.use_testnet}")

    try:
        client = BinanceUsdmClient.from_env(
            use_testnet=runtime.use_testnet,
            recv_window_ms=runtime.recv_window_ms,
            timeout_seconds=runtime.timeout_seconds,
        )
    except BinanceUsdmClientError as exc:
        print(f"Credenciales/config Binance inválidas: {exc}")
        raise SystemExit(1) from exc

    exchange_info = client.get_exchange_info()
    symbols = {
        item["symbol"]: item
        for item in exchange_info.get("symbols", [])
        if isinstance(item, dict) and "symbol" in item
    }

    print(f"Base URL: {client.base_url}")
    print(f"Símbolos configurados: {config['symbols']['enabled']}")

    missing_symbols = [
        symbol for symbol in config["symbols"]["enabled"] if symbol not in symbols
    ]
    if missing_symbols:
        print(f"Símbolos no presentes en exchangeInfo: {missing_symbols}")
        raise SystemExit(2)

    print("exchangeInfo OK para todos los símbolos configurados.")

    if runtime.mode in {"paper", "live"}:
        account_info = client.get_account_info()
        can_trade = account_info.get("canTrade")
        total_wallet_balance = account_info.get("totalWalletBalance")
        print(f"canTrade={can_trade}")
        print(f"totalWalletBalance={total_wallet_balance}")


if __name__ == "__main__":
    main()
