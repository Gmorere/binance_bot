from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.exchange.binance_usdm_client import BinanceCredentials, BinanceUsdmClient
from src.live.runtime_config import load_runtime_config


class BinanceUsdmClientTests(unittest.TestCase):
    def test_build_signature_matches_known_hmac(self) -> None:
        params = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": 1,
            "price": 9000,
            "timeInForce": "GTC",
            "recvWindow": 5000,
            "timestamp": 1591702613943,
        }

        signature = BinanceUsdmClient.build_signature(
            "2b5eb11e18796d12d88f13dc27dbbd02c2cc51ff7059765ed9821957d82bb4d9",
            params,
        )

        self.assertEqual(
            signature,
            "3c661234138461fcc7a7d8746c6558c9842d4e10870d2ecbedf7777cad694af9",
        )

    def test_client_uses_testnet_base_url(self) -> None:
        client = BinanceUsdmClient(
            credentials=BinanceCredentials(api_key="key", api_secret="secret"),
            use_testnet=True,
        )
        self.assertEqual(client.base_url, BinanceUsdmClient.TESTNET_BASE_URL)

    def test_signed_request_adds_signature_and_timestamp(self) -> None:
        session = Mock()
        response = Mock()
        response.json.return_value = {"ok": True}
        response.raise_for_status.return_value = None
        session.request.return_value = response

        client = BinanceUsdmClient(
            credentials=BinanceCredentials(api_key="key", api_secret="secret"),
            use_testnet=True,
            session=session,
        )

        client._request(method="GET", path="/fapi/v2/account", signed=True)

        kwargs = session.request.call_args.kwargs
        params = kwargs["params"]
        self.assertIn("timestamp", params)
        self.assertIn("recvWindow", params)
        self.assertIn("signature", params)
        self.assertEqual(kwargs["headers"]["X-MBX-APIKEY"], "key")


class RuntimeConfigTests(unittest.TestCase):
    def test_load_runtime_config_defaults_to_backtest(self) -> None:
        runtime = load_runtime_config({"project": {"mode": "backtest"}})
        self.assertEqual(runtime.mode, "backtest")
        self.assertTrue(runtime.use_testnet)
        self.assertFalse(runtime.use_testnet_market_data)
        self.assertEqual(runtime.exchange, "binance_usdm")
        self.assertEqual(runtime.backtest_risk_bucket, "normal")
        self.assertEqual(runtime.paper_risk_bucket, "normal")
        self.assertEqual(runtime.candle_close_grace_seconds, 3)


if __name__ == "__main__":
    unittest.main()
