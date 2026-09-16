from __future__ import annotations

import asyncio
import csv
import io
import re
from typing import Any, Dict

from tradingapi_a.mconnect import MConnect


_CATALOG_TTL_SECONDS = 4 * 3600  # script master is stable intraday


class MstockClient:
    def __init__(self):
        self._instrument_cache: dict[str, list[dict[str, Any]]] = {}
        self._catalog_ttl: dict[str, float] = {}
        self._catalog_locks: dict[str, asyncio.Lock] = {}

    def _new_client(self, api_key: str | None = None, access_token: str | None = None) -> MConnect:
        return MConnect(api_key=api_key, access_Token=access_token, debug=False)

    @staticmethod
    def _extract_payload(response) -> Dict[str, Any]:
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Mstock returned an unexpected response.")
        if str(payload.get("status") or "").lower() == "error":
            raise RuntimeError(str(payload.get("message") or "Mstock request failed"))
        return payload

    def _extract_dict_data(self, response, *, empty_ok: bool = False) -> Dict[str, Any]:
        payload = self._extract_payload(response)
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        if data is None and empty_ok:
            return {}
        message = payload.get("message")
        if message:
            return {"message": str(message)}
        raise RuntimeError("Mstock response did not include account data")

    def _extract_list_data(self, response) -> list[Dict[str, Any]]:
        payload = self._extract_payload(response)
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        raise RuntimeError("Mstock response did not include account data")

    def _extract_any_data(self, response) -> Any:
        payload = self._extract_payload(response)
        return payload.get("data")

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            text = str(value or "").replace(",", "").strip()
            if not text:
                return None
            return float(text)
        except Exception:
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        parsed = MstockClient._to_float(value)
        if parsed is None:
            return None
        try:
            return int(parsed)
        except Exception:
            return None

    @staticmethod
    def _parse_expiry(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return text.upper()

    @staticmethod
    def _detect_option_type(symbol: str, row: dict[str, Any]) -> str | None:
        for key in ("optiontype", "option_type", "opttype", "right", "cp_type"):
            text = str(row.get(key) or "").strip().upper()
            if text in {"CE", "CALL"}:
                return "CE"
            if text in {"PE", "PUT"}:
                return "PE"
        symbol_upper = symbol.upper()
        if symbol_upper.endswith("CE"):
            return "CE"
        if symbol_upper.endswith("PE"):
            return "PE"
        return None

    @staticmethod
    def _detect_instrument_type(symbol: str, exchange: str, row: dict[str, Any]) -> str:
        for key in ("instrumenttype", "instrument_type", "segment", "series", "type", "scrip_type"):
            text = str(row.get(key) or "").strip().upper()
            if text:
                if "OPT" in text:
                    return "OPTION"
                if "FUT" in text:
                    return "FUTURE"
                if text in {"EQ", "EQUITY", "CASH"}:
                    return "EQUITY"
                if "INDEX" in text:
                    return "INDEX"
        option_type = MstockClient._detect_option_type(symbol, row)
        symbol_upper = symbol.upper()
        if option_type:
            return "OPTION"
        if symbol_upper.endswith("FUT"):
            return "FUTURE"
        if exchange.upper() in {"NFO", "BFO", "MCX"}:
            return "DERIVATIVE"
        if exchange.upper() in {"NSE", "BSE"}:
            return "EQUITY"
        return "INSTRUMENT"

    @staticmethod
    def _extract_underlying(symbol: str, display_name: str, row: dict[str, Any]) -> str:
        # Prefer explicit underlying-symbol fields before falling back to name/company.
        # The mStock script master uses "name" for company name on equity rows,
        # so checking it first causes NFO options to get the company name as underlying.
        for key in ("underlying", "underlyingsymbol", "underlying_symbol", "symbolname"):
            text = str(row.get(key) or "").strip()
            if text:
                return text.upper()
        # For NFO options the trading symbol encodes the underlying as leading alpha chars
        # e.g. RELIANCE29AUG2026900PE → RELIANCE, M&M29AUG2026800PE → M&M
        opt_type = MstockClient._detect_option_type(symbol, row)
        if opt_type:
            match = re.match(r"^([A-Z&]+)", symbol.upper())
            if match:
                return match.group(1)
        # Fallback: name / company name
        for key in ("name", "companyname"):
            text = str(row.get(key) or "").strip()
            if text:
                return text.upper()
        match = re.match(r"^([A-Z]+)", symbol.upper())
        if match:
            return match.group(1)
        return display_name.upper()

    @staticmethod
    def _extract_strike(symbol: str, row: dict[str, Any]) -> float | None:
        for key in ("strikeprice", "strike_price", "strike", "exerciseprice", "exercise_price"):
            parsed = MstockClient._to_float(row.get(key))
            if parsed is not None:
                return parsed
        match = re.search(r"(\d{4,7})(?:CE|PE)$", symbol.upper())
        if match:
            return MstockClient._to_float(match.group(1))
        return None

    @staticmethod
    def _build_search_text(item: dict[str, Any]) -> str:
        parts = [
            item.get("symbol"),
            item.get("display_name"),
            item.get("exchange"),
            item.get("underlying"),
            item.get("instrument_type"),
            item.get("option_type"),
            item.get("expiry"),
            item.get("strike"),
            item.get("lot_size"),
        ]
        return " ".join(str(part or "").upper() for part in parts if part not in (None, ""))

    async def request_otp(self, username: str, password: str) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            client = self._new_client()
            response = client.login(username, password)
            return self._extract_dict_data(response, empty_ok=True)

        return await asyncio.to_thread(run)

    async def create_session_token(self, api_key: str, otp: str) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            client = self._new_client(api_key=api_key)
            response = client.generate_session(api_key, otp, "L")
            data = self._extract_dict_data(response)
            if not data.get("access_token"):
                raise RuntimeError("Mstock session response did not include an access token")
            return data

        return await asyncio.to_thread(run)

    async def validate_credentials(self, api_key: str, access_token: str) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            client = self._new_client(api_key=api_key, access_token=access_token)
            response = client.get_fund_summary()
            rows = self._extract_list_data(response)
            if rows:
                return rows[0]
            return {}

        return await asyncio.to_thread(run)

    async def fetch_script_master(self, api_key: str, access_token: str) -> str:
        def run() -> str:
            client = self._new_client(api_key=api_key, access_token=access_token)
            response = client.get_instruments()
            if isinstance(response, bytes):
                return response.decode("utf-8", "ignore")
            return str(response)

        return await asyncio.to_thread(run)

    async def fetch_ltp(self, api_key: str, access_token: str, instruments: list[str]) -> Any:
        def run() -> Any:
            client = self._new_client(api_key=api_key, access_token=access_token)
            response = client.get_ltp(instruments)
            return self._extract_any_data(response)

        return await asyncio.to_thread(run)

    async def get_historical_candles(
        self,
        api_key: str,
        access_token: str,
        *,
        segment: str,
        security_token: str | int,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLC candles via TypeA historical chart API.

        TypeA example: get_historical_chart("NSE", "11536", "day", "2025-01-05", "2025-01-10")
        """

        def run() -> list[dict[str, Any]]:
            client = self._new_client(api_key=api_key, access_token=access_token)
            response = client.get_historical_chart(
                str(segment),
                str(security_token),
                str(interval),
                str(from_date),
                str(to_date),
            )
            try:
                payload = self._extract_payload(response) if hasattr(response, "json") else response
            except Exception:
                payload = response
            return self._normalize_historical_candles(payload)

        return await asyncio.to_thread(run)

    @staticmethod
    def _normalize_historical_candles(payload: Any) -> list[dict[str, Any]]:
        rows: list[Any] = []
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("candles", "ohlc", "data", "values"):
                    if isinstance(data.get(key), list):
                        rows = data[key]
                        break
                else:
                    rows = []
            elif isinstance(data, list):
                rows = data
            else:
                for key in ("candles", "ohlc"):
                    if isinstance(payload.get(key), list):
                        rows = payload[key]
                        break
        elif isinstance(payload, list):
            rows = payload

        candles: list[dict[str, Any]] = []
        for row in rows:
            parsed = MstockClient._normalize_candle_row(row)
            if parsed:
                candles.append(parsed)
        candles.sort(key=lambda item: str(item.get("time") or ""))
        return candles

    @staticmethod
    def _normalize_candle_row(row: Any) -> dict[str, Any] | None:
        if isinstance(row, dict):
            time_value = (
                row.get("time")
                or row.get("datetime")
                or row.get("date")
                or row.get("timestamp")
                or row.get("t")
            )
            open_price = MstockClient._to_float(row.get("open") or row.get("o"))
            high_price = MstockClient._to_float(row.get("high") or row.get("h"))
            low_price = MstockClient._to_float(row.get("low") or row.get("l"))
            close_price = MstockClient._to_float(row.get("close") or row.get("c") or row.get("ltp"))
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            time_value, open_price, high_price, low_price, close_price = (
                row[0],
                MstockClient._to_float(row[1]),
                MstockClient._to_float(row[2]),
                MstockClient._to_float(row[3]),
                MstockClient._to_float(row[4]),
            )
        else:
            return None
        if open_price is None or high_price is None or low_price is None or close_price is None:
            return None
        return {
            "time": str(time_value),
            "open": float(open_price),
            "high": float(high_price),
            "low": float(low_price),
            "close": float(close_price),
        }

    def segment_for_instrument(self, item: dict[str, Any]) -> str:
        exchange = str(item.get("exchange") or "").upper()
        if exchange in {"NSE", "BSE", "NFO", "BFO", "MCX", "CDS"}:
            return exchange
        instrument_type = str(item.get("instrument_type") or "").upper()
        if instrument_type in {"OPTION", "FUTURE", "DERIVATIVE"}:
            return "NFO"
        return "NSE"

    async def get_instrument_catalog(self, api_key: str, access_token: str, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        import time

        lock = self._catalog_locks.setdefault(api_key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            age = now - self._catalog_ttl.get(api_key, 0)
            if not force_refresh and api_key in self._instrument_cache and age < _CATALOG_TTL_SECONDS:
                return self._instrument_cache[api_key]

            raw_csv = await self.fetch_script_master(api_key, access_token)
            catalog = self._parse_script_master(raw_csv)
            self._instrument_cache[api_key] = catalog
            self._catalog_ttl[api_key] = time.monotonic()
            return catalog

    def _parse_script_master(self, raw_csv: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        reader = csv.DictReader(io.StringIO(raw_csv))
        for row in reader:
            normalized = {str(key or "").strip().lower(): (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
            symbol = (
                normalized.get("tradingsymbol")
                or normalized.get("trading_symbol")
                or normalized.get("symbol")
                or normalized.get("name")
                or ""
            )
            exchange = (
                normalized.get("exchange")
                or normalized.get("exchange_segment")
                or normalized.get("exchange name")
                or normalized.get("exch")
                or ""
            )
            display_name = (
                normalized.get("companyname")
                or normalized.get("company name")
                or normalized.get("description")
                or normalized.get("name")
                or symbol
            )
            token_value = (
                normalized.get("token")
                or normalized.get("instrument_token")
                or normalized.get("securityid")
                or normalized.get("security_id")
                or normalized.get("tokenid")
                or ""
            )
            if not symbol or not token_value:
                continue
            try:
                instrument_token = int(float(str(token_value)))
            except Exception:
                continue
            symbol_upper = str(symbol).upper()
            exchange_upper = str(exchange).upper() or "INDIA"
            instrument_type = self._detect_instrument_type(symbol_upper, exchange_upper, normalized)
            option_type = self._detect_option_type(symbol_upper, normalized)
            strike = self._extract_strike(symbol_upper, normalized)
            expiry = self._parse_expiry(
                normalized.get("expiry")
                or normalized.get("expirydate")
                or normalized.get("expiry_date")
                or normalized.get("expirydt")
            )
            lot_size = self._to_int(
                normalized.get("lotsize")
                or normalized.get("lot_size")
                or normalized.get("boardlotsize")
                or normalized.get("board_lot_size")
                or normalized.get("qtymultiplier")
                or normalized.get("qty_multiplier")
            )
            underlying = self._extract_underlying(symbol_upper, str(display_name).strip() or symbol_upper, normalized)
            parsed = {
                "symbol": symbol_upper,
                "display_name": str(display_name).strip() or symbol_upper,
                "exchange": exchange_upper,
                "instrument_token": instrument_token,
                "instrument_type": instrument_type,
                "option_type": option_type,
                "strike": strike,
                "expiry": expiry,
                "lot_size": lot_size,
                "underlying": underlying,
                "raw": normalized,
            }
            parsed["search_text"] = self._build_search_text(parsed)
            rows.append(
                parsed
            )
        unique: dict[tuple[str, str, int], dict[str, Any]] = {}
        for item in rows:
            unique[(item["symbol"], item["exchange"], item["instrument_token"])] = item
        return list(unique.values())

    async def calculate_margin_for_leg(
        self,
        api_key: str,
        access_token: str,
        *,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        price: float,
        product: str,
        order_type: str = "LIMIT",
        variety: str = "regular",
        trigger_price: float = 0,
    ) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            client = self._new_client(api_key=api_key, access_token=access_token)
            response = client.calculate_order_margin(
                exchange,
                tradingsymbol,
                transaction_type,
                variety,
                product,
                order_type,
                quantity,
                price,
                trigger_price,
            )
            return self._extract_dict_data(response)

        return await asyncio.to_thread(run)


mstock_client = MstockClient()
