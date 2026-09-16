from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bson import ObjectId
from .mstock_client import mstock_client
from .secret_store import decrypt_secret

logger = logging.getLogger(__name__)

MSTOCK_WS_URL = "wss://ws.mstock.trade"
INDIA_TZ = ZoneInfo("Asia/Kolkata")
DEFAULT_INDEXES = [
    {"symbol": "NIFTY50", "instrument_token": 26000, "exchange": "NSE", "display_name": "Nifty 50"},
    {"symbol": "SENSEX", "instrument_token": 51, "exchange": "BSE", "display_name": "Sensex"},
]
INDIAN_WATCHLIST_COLLECTION = "indian_watchlist_items"
INDIAN_SESSION_COLLECTION = "indian_broker_sessions"


@dataclass
class IndianSession:
    ticker: Any
    symbols: tuple[int, ...]
    account_db_id: ObjectId
    loop: asyncio.AbstractEventLoop
    connected: bool = False
    reconnecting: bool = False
    active: bool = True
    last_error: Optional[str] = None
    last_text_message: Optional[str] = None
    last_tick_at: Optional[str] = None


class IndianMarketStreamManager:
    def __init__(self):
        self._sessions: dict[str, IndianSession] = {}
        self._price_cache: dict[str, dict[str, dict]] = defaultdict(dict)

    def get_prices(self, user_id: str) -> dict[str, dict]:
        return self._price_cache.get(user_id, {})

    @staticmethod
    def _subscription_items(watchlist_items: list[dict]) -> list[dict]:
        combined: list[dict] = []
        seen: set[tuple[str, int]] = set()
        for item in [*DEFAULT_INDEXES, *watchlist_items]:
            token = item.get("instrument_token")
            symbol = str(item.get("symbol") or "").upper()
            if token is None or not symbol:
                continue
            key = (symbol, int(token))
            if key in seen:
                continue
            seen.add(key)
            combined.append(item)
        return combined

    def build_market_overview(self, user_id: str) -> dict:
        prices = self.get_prices(user_id)
        session = self._sessions.get(user_id)
        now_ist = datetime.now(INDIA_TZ)
        is_open = now_ist.weekday() < 5 and ((now_ist.hour, now_ist.minute) >= (9, 15)) and ((now_ist.hour, now_ist.minute) < (15, 30))
        indices = []
        for default in DEFAULT_INDEXES:
            item = prices.get(default["symbol"], {})
            indices.append(
                {
                    "symbol": default["symbol"],
                    "display_name": default["display_name"],
                    "price": item.get("price"),
                    "change": item.get("change"),
                    "time": item.get("time"),
                }
            )
        watchlist = [
            {
                "symbol": symbol,
                "display_name": tick.get("display_name") or symbol,
                "price": tick.get("price"),
                "change": tick.get("change"),
                "time": tick.get("time"),
                "exchange": tick.get("exchange"),
                "instrument_token": tick.get("instrument_token"),
            }
            for symbol, tick in prices.items()
        ]
        watchlist.sort(key=lambda item: (0 if item["symbol"] in {"NIFTY50", "SENSEX"} else 1, item["symbol"]))
        return {
            "status": "OPEN" if is_open else "CLOSED",
            "status_source": "schedule",
            "stream_connected": bool(session and session.connected),
            "stream_reconnecting": bool(session and session.reconnecting),
            "stream_error": session.last_error if session else None,
            "last_stream_message": session.last_text_message if session else None,
            "last_tick_at": session.last_tick_at if session else None,
            "indices": indices,
            "watchlist": watchlist,
            "updated_at": now_ist.isoformat(),
        }

    async def ensure_user_stream(self, db, user_id: str, on_update):
        user_oid = ObjectId(user_id)
        user = await db.users.find_one_async({"_id": user_oid})
        selected_indian_account_id = (user or {}).get("selected_indian_account_id")
        if not user or not selected_indian_account_id:
            logger.info("Indian stream skipped | user=%s reason=no_selected_indian_account", user_id)
            await self.stop_user_stream(user_id)
            return
        await self.ensure_account_stream(db, user_id, selected_indian_account_id, on_update)

    async def ensure_account_stream(self, db, user_id: str, account_db_id: ObjectId, on_update):
        user_oid = ObjectId(user_id)
        account = await db.meta_accounts.find_one_async({"_id": account_db_id, "user_id": user_oid})
        if not account or str(account.get("market_type") or "").upper() != "INDIAN":
            logger.info("Indian stream skipped | user=%s account=%s reason=account_not_indian_or_missing", user_id, str(account_db_id))
            await self.stop_user_stream(user_id)
            return
        credentials = account.get("credentials") or {}
        api_key = str(credentials.get("api_key") or "").strip()
        session_doc = await db[INDIAN_SESSION_COLLECTION].find_one_async({"user_id": user_oid, "account_id": account["_id"]})
        access_token_encrypted = str((session_doc or {}).get("access_token_encrypted") or "").strip()
        access_token = ""
        if access_token_encrypted:
            try:
                access_token = decrypt_secret(access_token_encrypted)
            except Exception:
                logger.exception("Indian stream access token decrypt failed | user=%s account=%s", user_id, str(account.get("_id")))
                access_token = ""
        if not api_key or not access_token:
            logger.info(
                "Indian stream skipped | user=%s account=%s reason=missing_api_key_or_access_token session_status=%s",
                user_id,
                str(account.get("_id")),
                (session_doc or {}).get("session_status"),
            )
            await self.stop_user_stream(user_id)
            return
        watchlist_items = await db[INDIAN_WATCHLIST_COLLECTION].find_async({"user_id": user_oid, "account_id": account["_id"]})
        subscription_items = self._subscription_items(watchlist_items)
        tokens = tuple(sorted({int(item["instrument_token"]) for item in subscription_items if item.get("instrument_token") is not None}))
        existing = self._sessions.get(user_id)
        if existing and existing.account_db_id == account["_id"] and existing.symbols == tokens and existing.ticker.is_connected():
            logger.info("Indian stream reused | user=%s account=%s tokens=%s", user_id, str(account["_id"]), list(tokens))
            return
        await self.stop_user_stream(user_id)
        if not tokens:
            logger.info("Indian stream skipped | user=%s account=%s reason=no_tokens", user_id, str(account["_id"]))
            self._price_cache[user_id] = {}
            await on_update(db, user_id)
            return
        logger.info("Indian stream creating session | user=%s account=%s tokens=%s", user_id, str(account["_id"]), list(tokens))
        loop = asyncio.get_running_loop()
        token_map = {int(item["instrument_token"]): item for item in subscription_items if item.get("instrument_token") is not None}
        from tradingapi_a.mticker import MTicker
        ticker = MTicker(api_key, access_token, MSTOCK_WS_URL, debug=False)
        session = IndianSession(ticker=ticker, symbols=tokens, account_db_id=account["_id"], loop=loop)
        self._sessions[user_id] = session
        self._wire_ticker(db, user_id, session, token_map, on_update)
        ticker.connect(threaded=True, disable_ssl_verification=True)
        asyncio.create_task(self._bootstrap_rest_prices(db, user_id, account["_id"], token_map, api_key, access_token, on_update))
        await on_update(db, user_id)

    def _wire_ticker(self, db, user_id: str, session: IndianSession, token_map: dict[int, dict], on_update):
        ticker = session.ticker

        def schedule_update():
            if not session.active:
                logger.debug("Indian stream session inactive, dropping update | user=%s", user_id)
                return
            if session.loop.is_closed():
                logger.debug("Indian stream loop closed, dropping update | user=%s", user_id)
                session.active = False
                return
            try:
                asyncio.run_coroutine_threadsafe(on_update(db, user_id), session.loop)
            except RuntimeError:
                # Loop was closed between the is_closed() check and the call — silence it.
                logger.debug("Indian stream loop closed during schedule | user=%s", user_id)
                session.active = False
            except Exception:
                logger.exception("Indian stream update scheduling failed | user=%s", user_id)

        def on_connect(ws, response):
            logger.info("Indian market websocket connected | user=%s response=%s", user_id, response)
            session.connected = True
            session.reconnecting = False
            session.last_error = None
            try:
                ticker.send_login_after_connect()
                ticker.subscribe(list(session.symbols))
                ticker.set_mode(ticker.MODE_LTP, list(session.symbols))
                logger.info("Indian market stream started | user=%s tokens=%s", user_id, list(session.symbols))
            except Exception as exc:
                session.connected = False
                session.last_error = str(exc)
                logger.exception("Indian market subscribe failed | user=%s", user_id)
            schedule_update()

        def on_ticks(ws, ticks):
            if not ticks:
                return
            session.connected = True
            session.reconnecting = False
            session.last_error = None
            session.last_tick_at = datetime.now(INDIA_TZ).isoformat()
            for tick in ticks:
                token = int(tick.get("instrument_token") or 0)
                meta = token_map.get(token)
                if not meta:
                    continue
                symbol = str(meta.get("symbol") or token)
                last_price = tick.get("last_price")
                change = tick.get("change")
                self._price_cache[user_id][symbol] = {
                    "symbol": symbol,
                    "display_name": meta.get("display_name") or symbol,
                    "instrument_token": token,
                    "exchange": meta.get("exchange"),
                    "price": float(last_price) if last_price is not None else None,
                    "change": round(float(change), 2) if change is not None else None,
                    "time": tick.get("exchange_timestamp") or tick.get("last_traded_timestamp") or session.last_tick_at,
                }
            schedule_update()

        def on_message(ws, payload, is_binary):
            if is_binary:
                return
            text = payload.decode("utf-8", "ignore") if isinstance(payload, (bytes, bytearray)) else str(payload)
            session.last_text_message = text[:500]
            logger.info("Indian market text message | user=%s payload=%s", user_id, session.last_text_message)
            schedule_update()

        def on_error(ws, code, reason):
            session.connected = False
            session.reconnecting = True
            session.last_error = f"{code}: {reason}"
            logger.error("Indian market stream error | user=%s code=%s reason=%s", user_id, code, reason)
            schedule_update()

        def on_close(ws, code, reason):
            session.connected = False
            session.reconnecting = True
            session.last_error = f"closed: {code} {reason}"
            logger.info("Indian market stream closed | user=%s code=%s reason=%s", user_id, code, reason)
            schedule_update()

        def on_reconnect(ws, attempts_count):
            session.connected = False
            session.reconnecting = True
            session.last_error = f"reconnecting: attempt {attempts_count}"
            logger.warning("Indian market stream reconnecting | user=%s attempts=%s", user_id, attempts_count)
            schedule_update()

        def on_noreconnect(ws):
            session.connected = False
            session.reconnecting = False
            session.last_error = "reconnect attempts exhausted"
            logger.error("Indian market stream reconnect exhausted | user=%s", user_id)
            schedule_update()

        ticker.on_connect = on_connect
        ticker.on_ticks = on_ticks
        ticker.on_message = on_message
        ticker.on_error = on_error
        ticker.on_close = on_close
        ticker.on_reconnect = on_reconnect
        ticker.on_noreconnect = on_noreconnect

    async def _bootstrap_rest_prices(self, db, user_id: str, account_id: ObjectId, token_map: dict[int, dict], api_key: str, access_token: str, on_update):
        await asyncio.sleep(2.5)
        session = self._sessions.get(user_id)
        if not session or session.account_db_id != account_id:
            return
        if self._price_cache.get(user_id):
            return
        instruments = []
        meta_by_key = {}
        for meta in token_map.values():
            exchange = str(meta.get("exchange") or "").upper().strip()
            symbol = str(meta.get("symbol") or "").upper().strip()
            if not exchange or not symbol:
                continue
            key = f"{exchange}:{symbol}"
            instruments.append(key)
            meta_by_key[key] = meta
        if not instruments:
            return
        try:
            logger.info("Indian market REST bootstrap started | user=%s instruments=%s", user_id, instruments)
            data = await mstock_client.fetch_ltp(api_key, access_token, instruments)
            parsed_any = False
            if isinstance(data, dict):
                for key, value in data.items():
                    if not isinstance(value, dict):
                        continue
                    meta = meta_by_key.get(str(key).upper())
                    if not meta:
                        continue
                    symbol = str(meta.get("symbol") or "")
                    price = value.get("last_price") or value.get("ltp") or value.get("lastPrice")
                    change = value.get("change")
                    if price is None:
                        continue
                    self._price_cache[user_id][symbol] = {
                        "symbol": symbol,
                        "display_name": meta.get("display_name") or symbol,
                        "instrument_token": meta.get("instrument_token"),
                        "exchange": meta.get("exchange"),
                        "price": float(price),
                        "change": round(float(change), 2) if change not in (None, "") else None,
                        "time": datetime.now(INDIA_TZ).isoformat(),
                    }
                    parsed_any = True
            if parsed_any:
                logger.info("Indian market REST bootstrap completed | user=%s count=%s", user_id, len(self._price_cache[user_id]))
                await on_update(db, user_id)
            else:
                logger.warning("Indian market REST bootstrap returned no parsable prices | user=%s data_type=%s", user_id, type(data).__name__)
        except Exception:
            logger.exception("Indian market REST bootstrap failed | user=%s", user_id)

    async def stop_user_stream(self, user_id: str):
        session = self._sessions.pop(user_id, None)
        self._price_cache[user_id] = {}
        if not session:
            return
        logger.info("Indian stream stopping | user=%s account=%s", user_id, str(session.account_db_id))
        session.active = False
        try:
            session.ticker.close()
        except Exception:
            logger.exception("Indian stream close failed | user=%s", user_id)


indian_market_stream_manager = IndianMarketStreamManager()
