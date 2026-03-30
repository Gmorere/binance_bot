from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

import requests


class BinanceUsdmClientError(Exception):
    """Error relacionado con integración REST con Binance USD-M Futures."""


@dataclass(frozen=True)
class BinanceCredentials:
    api_key: str
    api_secret: str


class BinanceUsdmClient:
    PROD_BASE_URL = "https://fapi.binance.com"
    TESTNET_BASE_URL = "https://demo-fapi.binance.com"

    def __init__(
        self,
        *,
        credentials: BinanceCredentials,
        use_testnet: bool = True,
        recv_window_ms: int = 5000,
        timeout_seconds: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        if not credentials.api_key:
            raise BinanceUsdmClientError("api_key no puede venir vacío.")
        if not credentials.api_secret:
            raise BinanceUsdmClientError("api_secret no puede venir vacío.")
        if recv_window_ms <= 0:
            raise BinanceUsdmClientError("recv_window_ms debe ser mayor a 0.")
        if timeout_seconds <= 0:
            raise BinanceUsdmClientError("timeout_seconds debe ser mayor a 0.")

        self.credentials = credentials
        self.use_testnet = use_testnet
        self.recv_window_ms = int(recv_window_ms)
        self.timeout_seconds = int(timeout_seconds)
        self.session = session or requests.Session()
        self.base_url = (
            self.TESTNET_BASE_URL if use_testnet else self.PROD_BASE_URL
        )

    @classmethod
    def from_env(
        cls,
        *,
        use_testnet: bool = True,
        recv_window_ms: int = 5000,
        timeout_seconds: int = 30,
        env: Mapping[str, str] | None = None,
    ) -> "BinanceUsdmClient":
        source = env or os.environ
        api_key = source.get("BINANCE_API_KEY", "").strip()
        api_secret = source.get("BINANCE_API_SECRET", "").strip()

        if not api_key or not api_secret:
            raise BinanceUsdmClientError(
                "Faltan BINANCE_API_KEY o BINANCE_API_SECRET en el entorno."
            )

        return cls(
            credentials=BinanceCredentials(api_key=api_key, api_secret=api_secret),
            use_testnet=use_testnet,
            recv_window_ms=recv_window_ms,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def build_signature(secret: str, params: Mapping[str, Any]) -> str:
        query = urlencode(params, doseq=True)
        return hmac.new(
            secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def current_timestamp_ms() -> int:
        return int(time.time() * 1000)

    def _build_signed_params(self, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(params or {})
        payload["recvWindow"] = self.recv_window_ms
        payload["timestamp"] = self.current_timestamp_ms()
        payload["signature"] = self.build_signature(
            self.credentials.api_secret,
            payload,
        )
        return payload

    def _request(
        self,
        *,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"X-MBX-APIKEY": self.credentials.api_key}
        payload = self._build_signed_params(params) if signed else dict(params or {})

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise BinanceUsdmClientError(
                f"Error de red llamando a Binance: {exc}"
            ) from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text.strip()
            raise BinanceUsdmClientError(
                f"Binance respondió {response.status_code} en {path}: {body}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BinanceUsdmClientError(
                f"Respuesta no JSON desde Binance en {path}."
            ) from exc

    def get_exchange_info(self) -> Any:
        return self._request(method="GET", path="/fapi/v1/exchangeInfo")

    def get_account_info(self) -> Any:
        return self._request(method="GET", path="/fapi/v2/account", signed=True)

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        position_side: str | None = None,
        price: float | None = None,
        time_in_force: str | None = None,
        reduce_only: bool | None = None,
        new_client_order_id: str | None = None,
        response_type: str = "ACK",
    ) -> Any:
        if not symbol:
            raise BinanceUsdmClientError("symbol no puede venir vacío.")
        if quantity <= 0:
            raise BinanceUsdmClientError("quantity debe ser mayor a 0.")

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "newOrderRespType": response_type,
        }

        if position_side:
            params["positionSide"] = position_side
        if price is not None:
            params["price"] = price
        if time_in_force:
            params["timeInForce"] = time_in_force
        if reduce_only is not None:
            params["reduceOnly"] = "true" if reduce_only else "false"
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        return self._request(
            method="POST",
            path="/fapi/v1/order",
            params=params,
            signed=True,
        )
