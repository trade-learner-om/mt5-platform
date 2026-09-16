from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from fastapi import WebSocket


logger = logging.getLogger(__name__)

WS_LIVE_HEARTBEAT_SECONDS = 20
WS_LIVE_STREAM_REFRESH_SECONDS = 60


async def handle_live_socket_message(
    db,
    user_id: str,
    websocket: WebSocket,
    message: str,
    push_snapshot: Callable[..., Awaitable[None]],
) -> bool:
    stripped = str(message or "").strip()
    if not stripped:
        return True
    if stripped in {"ready", "pong"}:
        from .market_data_stream import market_data_stream

        try:
            await market_data_stream.refresh_live_stream(db, user_id, push_snapshot)
        except Exception:
            logger.exception("Live stream refresh failed on ready/pong | user=%s", user_id)
        return True
    if stripped == "ping":
        await websocket.send_json({"type": "pong"})
        return True

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return True

    msg_type = str(payload.get("type") or "").strip().lower()
    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})
        return True
    if msg_type == "pong":
        return True
    if msg_type == "subscribe_symbol":
        from .market_data_stream import market_data_stream

        symbol = str(payload.get("symbol") or "").strip().upper()
        await market_data_stream.set_extra_symbols(
            db,
            user_id,
            [symbol] if symbol else [],
            push_snapshot,
        )
        return True
    if msg_type == "subscribe_symbols":
        from .market_data_stream import market_data_stream

        symbols = [
            str(symbol or "").strip().upper()
            for symbol in (payload.get("symbols") or [])
            if str(symbol or "").strip()
        ]
        await market_data_stream.set_extra_symbols(
            db,
            user_id,
            symbols,
            push_snapshot,
        )
        return True
    return True


async def run_live_socket_loop(
    websocket: WebSocket,
    user_id: str,
    db,
    push_snapshot: Callable[..., Awaitable[None]],
) -> None:
    stop = asyncio.Event()
    last_stream_refresh_at = datetime.min.replace(tzinfo=timezone.utc)

    async def heartbeat() -> None:
        from .market_data_stream import market_data_stream

        nonlocal last_stream_refresh_at
        while not stop.is_set():
            try:
                await asyncio.sleep(WS_LIVE_HEARTBEAT_SECONDS)
            except asyncio.CancelledError:
                raise
            if stop.is_set():
                return
            try:
                now = datetime.now(timezone.utc)
                if (now - last_stream_refresh_at).total_seconds() >= WS_LIVE_STREAM_REFRESH_SECONDS:
                    await market_data_stream.refresh_live_stream(db, user_id, push_snapshot)
                    last_stream_refresh_at = now
                await websocket.send_json({"type": "ping"})
            except Exception:
                logger.warning("Live websocket heartbeat failed | user=%s", user_id, exc_info=True)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        while not stop.is_set():
            message = await websocket.receive_text()
            try:
                await handle_live_socket_message(db, user_id, websocket, message, push_snapshot)
            except Exception:
                logger.exception("Live websocket message handling failed | user=%s", user_id)
    finally:
        stop.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
