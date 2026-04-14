from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.exchange.binance_usdm_client import (
    BinanceCredentials,
    BinanceUsdmClient,
    BinanceUsdmClientError,
)
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

    def test_get_open_orders_calls_signed_endpoint(self) -> None:
        session = Mock()
        response = Mock()
        response.json.return_value = []
        response.raise_for_status.return_value = None
        session.request.return_value = response

        client = BinanceUsdmClient(
            credentials=BinanceCredentials(api_key="key", api_secret="secret"),
            use_testnet=True,
            session=session,
        )

        client.get_open_orders(symbol="BTCUSDT")

        kwargs = session.request.call_args.kwargs
        self.assertEqual(kwargs["method"], "GET")
        self.assertTrue(kwargs["url"].endswith("/fapi/v1/openOrders"))
        self.assertEqual(kwargs["params"]["symbol"], "BTCUSDT")
        self.assertIn("signature", kwargs["params"])

    def test_cancel_order_requires_identifier(self) -> None:
        client = BinanceUsdmClient(
            credentials=BinanceCredentials(api_key="key", api_secret="secret"),
            use_testnet=True,
        )

        with self.assertRaises(BinanceUsdmClientError):
            client.cancel_order(symbol="BTCUSDT")

    def test_cancel_order_uses_delete_endpoint(self) -> None:
        session = Mock()
        response = Mock()
        response.json.return_value = {"status": "CANCELED"}
        response.raise_for_status.return_value = None
        session.request.return_value = response

        client = BinanceUsdmClient(
            credentials=BinanceCredentials(api_key="key", api_secret="secret"),
            use_testnet=True,
            session=session,
        )

        client.cancel_order(symbol="BTCUSDT", order_id=12345)

        kwargs = session.request.call_args.kwargs
        self.assertEqual(kwargs["method"], "DELETE")
        self.assertTrue(kwargs["url"].endswith("/fapi/v1/order"))
        self.assertEqual(kwargs["params"]["symbol"], "BTCUSDT")
        self.assertEqual(kwargs["params"]["orderId"], 12345)
        self.assertIn("signature", kwargs["params"])


class RuntimeConfigTests(unittest.TestCase):
    def test_load_runtime_config_defaults_to_backtest(self) -> None:
        runtime = load_runtime_config({"project": {"mode": "backtest"}})
        self.assertEqual(runtime.mode, "backtest")
        self.assertTrue(runtime.use_testnet)
        self.assertFalse(runtime.use_testnet_market_data)
        self.assertEqual(runtime.exchange, "binance_usdm")
        self.assertEqual(runtime.rest_max_retries, 2)
        self.assertEqual(runtime.rest_retry_backoff_ms, 1000)
        self.assertEqual(runtime.backtest_risk_bucket, "normal")
        self.assertEqual(runtime.paper_risk_bucket, "normal")
        self.assertEqual(runtime.candle_close_grace_seconds, 3)
        self.assertEqual(runtime.refresh_error_backoff_seconds, 120)


if __name__ == "__main__":
    unittest.main()
