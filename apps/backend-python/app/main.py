import hashlib
import hmac
import asyncio
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pymongo import UpdateOne
from starlette.websockets import WebSocketState

from .auth import create_access_token, decode_platform_token, get_admin_user, get_current_user, hash_password, is_session_active, new_session_id, verify_password
from .config import settings
from .db import get_db, parse_object_id
from .logging_config import configure_application_logging
from .platform_audit import new_request_id, set_request_context, write_audit
from .platform_users import find_user_for_login_async, mirror_legacy_user_async, persist_user_document_async, resolve_user_for_session_async
from .schemas import (
    AccountOut,
    AccountEquityOut,
    AccountRiskUpdateIn,
    AdminUserCreateIn,
    AdminUserOut,
    AdminUserUpdateIn,
    CandleDetectorPreviewIn,
    CandleDetectorPreviewOut,
    ClosePositionIn,
    LoginIn,
    MetaAccountIn,
    MarketSelectIn,
    MultiRiskPreviewOut,
    IndianOtpVerifyIn,
    NotificationOut,
    OrderCreateIn,
    OrderEventOut,
    OrderPlacementOut,
    OrderPlacementResultOut,
    OrderRowOut,
    OrderModifyIn,
    OrderTargetIn,
    QuickOrderIn,
    QuickOrderPreviewOut,
    OrderHistoryPageOut,
    PaginatedBrokerTradeHistoryOut,
    RegisterIn,
    RiskPreviewOut,
    RiskPreviewTargetOut,
    SelectAccountIn,
    SymbolAliasesUpdateIn,
    SymbolResolveOut,
    TradePlannerAccountTargetOut,
    TradePlannerPlanCreateIn,
    TradePlannerPlanOut,
    TradePlannerPlanUpdateIn,
    TradePlannerTargetOut,
    TokenOut,
    UserUiSettingsUpdateIn,
    UserSnapshotOut,
    WatchlistItemOut,
    WatchlistUpsertIn,
)
from .services.metaapi_client import LocalMT5Error, is_missing_broker_order_error, merge_realized_pl_on_close, metaapi_service
from .services.manual_order_runtime import RETRYABLE_ORDER_TYPES, manual_order_runtime_manager
from .services.market_data_stream import market_data_stream
from .services.indian_market_stream import indian_market_stream_manager, INDIAN_WATCHLIST_COLLECTION
from .services.indian_fno_contracts import fno_equity_underlyings
from .services.mstock_client import mstock_client
from .services.secret_store import decrypt_secret, encrypt_secret
from .services.async_runtime import run_coro_in_thread, run_sync
from .services.risk import (
    calc_quantity,
    calc_quantity_from_live_pip_value,
    calc_risk_amount_from_quantity,
    calc_rr,
    calc_sl_pips,
    digits_from_symbol_spec,
    normalize_price_to_symbol,
    pip_size_for_symbol,
    point_size_from_symbol_spec,
)
from .services.order_logging import append_order_log_prices, merge_order_log_payload
from .services.order_placement import (
    DEFERRED_MARKET_OPEN_STATUS,
    is_market_closed_error,
    next_monday_0430_ist,
    order_placement_fallback_fields,
    place_pending_order_with_limit_fallback,
    sl_limit_fallback_event_message,
)
from .services.deferred_market_open import process_due_deferred_orders
from .services.symbol_resolver import (
    detect_account_symbol_aliases,
    display_symbol,
    infer_canonical,
    is_gold_request,
    lookup_live_price,
    normalize_symbol,
    resolve_broker_symbol_for_account,
    suggest_symbols,
)
from .services.candle_history import (
    get_chart_candles,
    parse_chart_datetime,
    timeframe_seconds,
)
from .services.candle_patterns import _has_min_candle_range, _is_hammer, _is_shooting_star
from .services.quick_order import build_quick_order_quote
from .services.state_manager import live_state_hub
from .services.feed_broker_consent import (
    build_consent_record,
    build_mismatch_warning,
    brokers_match,
    collect_mismatch_accounts,
)
from .services.ws_live import run_live_socket_loop
from .services.trade_planner import (
    derive_trade_plan,
    resolve_trade_plan_swing_type,
)
from .mt5.terminal_detection import find_running_terminal_paths, find_running_terminal_processes

logger = logging.getLogger(__name__)
TRADE_PLAN_COLLECTION = "trade_plans"
INDIAN_SESSION_COLLECTION = "indian_broker_sessions"
_STREAM_REFRESH_INFLIGHT: set[str] = set()
MARKET_INTERNATIONAL = "INTERNATIONAL"
MARKET_INDIAN = "INDIAN"
MARKET_INDIAN_CRYPTO = "INDIAN_CRYPTO"
SUPPORTED_MARKETS = (MARKET_INTERNATIONAL, MARKET_INDIAN, MARKET_INDIAN_CRYPTO)
HEADER_NAV_PAGE_ORDER = (
    "trading",
    "positions",
    "trade-planner",
    "admin",
)
DEFAULT_HEADER_PRIMARY_TABS = ("trading", "positions")

app = FastAPI(title=settings.app_name)
configure_application_logging()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def platform_request_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    set_request_context(request_id=request_id)
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "HTTP request | method=%s path=%s status=%s duration_ms=%s request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        int((time.perf_counter() - started) * 1000),
        request_id,
    )
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(
        "FastAPI request validation failed | method=%s path=%s errors=%s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(ResponseValidationError)
async def response_validation_exception_handler(request: Request, exc: ResponseValidationError):
    logger.error(
        "FastAPI response validation failed | method=%s path=%s errors=%s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(status_code=500, content={"detail": "Response validation failed."})


@app.exception_handler(LocalMT5Error)
async def local_mt5_error_handler(request: Request, exc: LocalMT5Error):
    logger.warning(
        "Local MT5 error | method=%s path=%s detail=%s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _mask_secret(secret: Optional[str]) -> Optional[str]:
    if not secret:
        return None
    text = str(secret)
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _as_utc_datetime(value):
    if not isinstance(value, datetime):
        return value
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _serialize_admin_user(doc: dict, account_count: int = 0) -> AdminUserOut:
    return AdminUserOut(
        id=str(doc["_id"]),
        username=doc.get("username", ""),
        full_name=doc.get("full_name", ""),
        is_admin=bool(doc.get("is_admin", False)),
        is_active=bool(doc.get("is_active", True)),
        selected_account_id=str(doc.get("selected_account_id")) if doc.get("selected_account_id") else None,
        account_count=account_count,
        created_at=_as_utc_datetime(doc.get("created_at")),
        updated_at=_as_utc_datetime(doc.get("updated_at")),
    )


def _assert_not_last_active_admin(db, target_user: dict, incoming_is_admin: Optional[bool], incoming_is_active: Optional[bool]):
    currently_admin = bool(target_user.get("is_admin", False))
    currently_active = bool(target_user.get("is_active", True))
    next_admin = currently_admin if incoming_is_admin is None else bool(incoming_is_admin)
    next_active = currently_active if incoming_is_active is None else bool(incoming_is_active)
    if not currently_admin or not currently_active or (next_admin and next_active):
        return
    active_admin_count = db.users.count_documents({"is_admin": True, "is_active": True})
    if active_admin_count <= 1:
        raise HTTPException(status_code=400, detail="At least one active admin user is required.")


async def _assert_not_last_active_admin_async(db, target_user: dict, incoming_is_admin: Optional[bool], incoming_is_active: Optional[bool]):
    currently_admin = bool(target_user.get("is_admin", False))
    currently_active = bool(target_user.get("is_active", True))
    next_admin = currently_admin if incoming_is_admin is None else bool(incoming_is_admin)
    next_active = currently_active if incoming_is_active is None else bool(incoming_is_active)
    if not currently_admin or not currently_active or (next_admin and next_active):
        return
    active_admin_count = await db.users.count_documents_async({"is_admin": True, "is_active": True})
    if active_admin_count <= 1:
        raise HTTPException(status_code=400, detail="At least one active admin user is required.")


def _seed_default_admin_user(db):
    username = settings.admin_username.strip()
    password = settings.admin_password
    if not username or not password:
        logger.warning("Admin seed skipped because ADMIN_USERNAME or ADMIN_PASSWORD is missing.")
        return

    now = datetime.utcnow()
    full_name = settings.admin_full_name or "Administrator"
    existing = db.users.find_one({"username": username})
    if existing:
        updates = {
            "full_name": full_name,
            "is_admin": True,
            "is_active": True,
            "updated_at": now,
        }
        if not verify_password(password, existing.get("password_hash", "")):
            updates["password_hash"] = hash_password(password)
        db.users.update_one({"_id": existing["_id"]}, {"$set": updates})
        return

    db.users.insert_one(
        {
            "username": username,
            "full_name": full_name,
            "password_hash": hash_password(password),
            "selected_account_id": None,
            "ui_settings": {},
            "current_session_id": None,
            "active_session_ids": [],
            "is_admin": True,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
    )


async def _restore_market_data_runtime(db):
    loop = asyncio.get_running_loop()
    await market_data_stream._run_on_tick_loop(
        market_data_stream.restore_running_streams,
        db,
        _threadsafe_push_snapshot(loop),
    )


async def _ensure_market_data_stream(db, user_id: str, *, force: bool = False):
    loop = asyncio.get_running_loop()
    if force:
        await market_data_stream._run_on_tick_loop(
            market_data_stream.refresh_live_stream,
            db,
            user_id,
            _threadsafe_push_snapshot(loop),
            force=True,
        )
        return
    await market_data_stream._run_on_tick_loop(
        market_data_stream.ensure_user_stream,
        db,
        user_id,
        _threadsafe_push_snapshot(loop),
    )


async def _reconcile_market_data_orders(db, user_id: str, *, force: bool = False, include_all_accounts: bool = False):
    await market_data_stream._run_on_tick_loop(
        market_data_stream.reconcile_active_orders,
        db,
        user_id,
        force=force,
        include_all_accounts=include_all_accounts,
    )


async def _handle_market_data_ticks(db, ingest_account_db_id: str, ticks: list[dict]):
    loop = asyncio.get_running_loop()
    return await market_data_stream._run_on_tick_loop(
        market_data_stream.handle_pushed_ticks,
        db,
        ingest_account_db_id,
        ticks,
        _threadsafe_push_snapshot(loop),
    )


async def _restore_runtime_state():
    db = next(get_db())
    try:
        logger.info("Background runtime restore started")
        await _restore_market_data_runtime(db)
        logger.info("Background runtime restore finished")
    except Exception:
        logger.exception("Background runtime restore failed")


async def _refresh_user_streams(user_id: str, include_indian: bool = True, force: bool = False):
    if user_id in _STREAM_REFRESH_INFLIGHT:
        return
    if not force and market_data_stream.stream_refresh_is_debounced(user_id):
        logger.debug("Skipping debounced user stream refresh | user_id=%s", user_id)
        return
    _STREAM_REFRESH_INFLIGHT.add(user_id)
    db = next(get_db())
    try:
        loop = asyncio.get_running_loop()
        push_snapshot = _threadsafe_push_snapshot(loop)
        await market_data_stream._run_on_tick_loop(
            market_data_stream.refresh_live_stream, db, user_id, push_snapshot, force=force
        )
        if include_indian:
            await run_coro_in_thread(indian_market_stream_manager.ensure_user_stream, db, user_id, push_snapshot)
        await live_state_hub.push_snapshot(db, user_id)
    except Exception:
        logger.exception(
            "Background stream refresh failed | user_id=%s include_indian=%s",
            user_id,
            include_indian,
        )
    finally:
        _STREAM_REFRESH_INFLIGHT.discard(user_id)


def _threadsafe_push_snapshot(loop: asyncio.AbstractEventLoop):
    async def _push_snapshot(db, user_id: str):
        current_loop = asyncio.get_running_loop()
        if current_loop is loop:
            await live_state_hub.push_snapshot(db, user_id)
            return
        future = asyncio.run_coroutine_threadsafe(live_state_hub.push_snapshot(db, user_id), loop)
        await asyncio.wrap_future(future)

    return _push_snapshot


@app.on_event("startup")
async def startup_restore_automations():
    db = next(get_db())
    await asyncio.to_thread(_seed_default_admin_user, db)
    asyncio.create_task(_restore_runtime_state())


@app.get("/health")
async def health_check(db=Depends(get_db)):
    try:
        await db.command_async("ping")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
    return {"status": "ok"}


@app.get("/mt5/terminals")
async def list_mt5_terminals(user=Depends(get_current_user)):
    processes = await asyncio.to_thread(find_running_terminal_processes)
    path_counts: dict[str, int] = {}
    for process in processes:
        path = str(process.get("path") or "")
        if path:
            path_counts[path] = path_counts.get(path, 0) + 1
    return {
        "terminals": [
            {
                "pid": process.get("pid"),
                "path": process.get("path"),
                "same_path_instance_count": path_counts.get(str(process.get("path") or ""), 0),
            }
            for process in processes
        ],
        "unique_paths": await asyncio.to_thread(find_running_terminal_paths),
        "requires_unique_install_paths": any(count > 1 for count in path_counts.values()),
    }


@app.post("/mt5/browse-terminal")
async def browse_mt5_terminal(user=Depends(get_current_user)):
    def pick_terminal_path() -> str:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askopenfilename(
                title="Select MetaTrader 5 terminal64.exe",
                filetypes=[
                    ("MetaTrader terminal", "terminal64.exe terminal.exe"),
                    ("Executable files", "*.exe"),
                    ("All files", "*.*"),
                ],
            )
        finally:
            root.destroy()

    try:
        selected_path = await asyncio.to_thread(pick_terminal_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to open file picker: {exc}")

    if not selected_path:
        return {"path": ""}

    executable_name = os.path.basename(selected_path).lower()
    if executable_name not in {"terminal.exe", "terminal64.exe"}:
        raise HTTPException(status_code=400, detail="Select terminal.exe or terminal64.exe.")

    return {"path": selected_path}


def _format_equity_value(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):,.2f}"


def _format_account_label(doc: dict) -> str:
    if _normalize_market_type(doc.get("market_type")) in {MARKET_INDIAN, MARKET_INDIAN_CRYPTO}:
        return str(doc.get("account_name") or "Account")
    return f"{doc.get('account_name', 'Account')} ({_format_equity_value(doc.get('equity_balance'))})"


def _normalize_market_type(value: Optional[str]) -> str:
    normalized = str(value or MARKET_INTERNATIONAL).strip().upper()
    if normalized in SUPPORTED_MARKETS:
        return normalized
    return MARKET_INTERNATIONAL


def _header_nav_candidates_for_user(user: Optional[dict]) -> List[str]:
    candidates = list(HEADER_NAV_PAGE_ORDER)
    if not bool((user or {}).get("is_admin", False)):
        candidates = [item for item in candidates if item != "admin"]
    return candidates


def _normalize_nav_usage_map(raw_value: object, user: Optional[dict]) -> Dict[str, int]:
    allowed = set(_header_nav_candidates_for_user(user))
    normalized: Dict[str, int] = {}
    if isinstance(raw_value, dict):
        for key, value in raw_value.items():
            page_id = str(key or "").strip()
            if page_id not in allowed:
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count > 0:
                normalized[page_id] = count
    return normalized


def _resolve_header_primary_tabs(user: Optional[dict]) -> List[str]:
    allowed = _header_nav_candidates_for_user(user)
    usage = _normalize_nav_usage_map(((user or {}).get("ui_settings") or {}).get("page_usage"), user)
    ranked = sorted(
        allowed,
        key=lambda page_id: (-usage.get(page_id, 0), allowed.index(page_id)),
    )
    top_two = [page_id for page_id in ranked[:2] if page_id in allowed]
    if len(top_two) < 2:
        for page_id in DEFAULT_HEADER_PRIMARY_TABS:
            if page_id in allowed and page_id not in top_two:
                top_two.append(page_id)
            if len(top_two) >= 2:
                break
    return top_two[:2]


def _serialize_user_ui_settings(user: Optional[dict]) -> Dict[str, object]:
    usage = _normalize_nav_usage_map(((user or {}).get("ui_settings") or {}).get("page_usage"), user)
    raw_order_defaults = ((user or {}).get("ui_settings") or {}).get("order_defaults")
    order_defaults = raw_order_defaults if isinstance(raw_order_defaults, dict) else {}
    return {
        "page_usage": usage,
        "header_primary_tabs": _resolve_header_primary_tabs(user),
        "order_defaults": {
            "automatic_trade_management": bool(
                order_defaults.get("automatic_trade_management")
                if order_defaults.get("automatic_trade_management") is not None
                else True
            ),
            "retryable_order": bool(
                order_defaults.get("retryable_order") if order_defaults.get("retryable_order") is not None else True
            ),
        },
    }



def _normalize_broker_type(value: Optional[str], market_type: str) -> str:
    normalized = str(value or "").strip().upper()
    if market_type == MARKET_INDIAN:
        return normalized or "MSTOCK"
    if market_type == MARKET_INDIAN_CRYPTO:
        return normalized or "DELTA_EXCHANGE_INDIA"
    return normalized or "METAAPI"


def _extract_indian_available_margin(session_payload: dict) -> Optional[float]:
    fund_summary = session_payload.get("fund_summary") or {}
    if not isinstance(fund_summary, dict):
        return None
    preferred_keys = (
        "available_margin",
        "availablemargin",
        "available_funds",
        "availablefunds",
        "available_cash",
        "availablecash",
        "clear_cash",
        "clearcash",
        "net",
        "net_cash",
        "netcash",
        "cash",
    )
    normalized = {str(key).strip().lower(): value for key, value in fund_summary.items()}
    for key in preferred_keys:
        value = normalized.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            continue
    for key, value in normalized.items():
        if "available" not in key and "cash" not in key and "margin" not in key and key != "net":
            continue
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            continue
    return None


def _to_account_out(doc: dict) -> AccountOut:
    market_type = _normalize_market_type(doc.get("market_type"))
    credentials = doc.get("credentials") or {}
    session_payload = doc.get("session_payload") or {}
    meta_profile = doc.get("meta_profile") or {}
    broker_server = str(meta_profile.get("server") or "").strip() or None
    return AccountOut(
        id=str(doc["_id"]),
        account_name=_format_account_label(doc),
        account_id=str(doc.get("account_id") or ""),
        market_type=market_type,
        broker_type=_normalize_broker_type(doc.get("broker_type"), market_type),
        currency_code="INR" if market_type == "INDIAN" else str(doc.get("account_currency") or "USD").upper(),
        risk_amount=doc["risk_amount"],
        session_status=doc.get("session_status"),
        session_expires_at=doc.get("session_expires_at"),
        broker_user_id=str(session_payload.get("user_name") or credentials.get("username") or "") or None,
        broker_email=str(session_payload.get("email") or "") or None,
        broker_exchanges=[str(item) for item in (session_payload.get("exchanges") or []) if str(item).strip()],
        broker_server=broker_server,
        broker_scope_key=_account_broker_scope_key(doc),
        mt5_tick_ingest_secret=doc.get("mt5_tick_ingest_secret") if market_type == "INTERNATIONAL" else None,
        available_margin=_extract_indian_available_margin(session_payload) if market_type == "INDIAN" else None,
        equity_balance=(
            _extract_indian_available_margin(session_payload)
            if market_type == "INDIAN"
            else (float(doc["equity_balance"]) if doc.get("equity_balance") is not None else None)
        ),
        broker_utc_offset=doc.get("broker_utc_offset"),
        broker_time_region=doc.get("broker_time_region"),
        symbol_aliases={str(key).upper(): str(value).upper() for key, value in (doc.get("symbol_aliases") or {}).items()},
    )


def _new_mt5_tick_ingest_secret() -> str:
    return secrets.token_urlsafe(32)


def _ensure_account_tick_secret(db, account: dict) -> dict:
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        return account
    if account.get("mt5_tick_ingest_secret"):
        return account
    secret = _new_mt5_tick_ingest_secret()
    db.meta_accounts.update_one({"_id": account["_id"]}, {"$set": {"mt5_tick_ingest_secret": secret, "updated_at": datetime.utcnow()}})
    account["mt5_tick_ingest_secret"] = secret
    return account


async def _ensure_account_tick_secret_async(db, account: dict) -> dict:
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        return account
    if account.get("mt5_tick_ingest_secret"):
        return account
    secret = _new_mt5_tick_ingest_secret()
    await db.meta_accounts.update_one_async(
        {"_id": account["_id"]},
        {"$set": {"mt5_tick_ingest_secret": secret, "updated_at": datetime.utcnow()}},
    )
    account["mt5_tick_ingest_secret"] = secret
    return account


def _account_broker_scope_key(account: dict) -> str:
    market_type = _normalize_market_type(account.get("market_type"))
    broker_type = _normalize_broker_type(account.get("broker_type"), market_type)
    meta_profile = account.get("meta_profile") or {}
    server = str(meta_profile.get("server") or "").strip().upper()
    if server:
        return f"{market_type}|{broker_type}|{server}"
    return f"{market_type}|{broker_type}"


def _require_feed_account(user: dict, db) -> dict:
    """Selected account is the datafeed source of truth for strategy prices."""
    try:
        return _assert_account(user, db)
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail="No usable feed account selected. Select a deployed international MT5 account before starting strategies.",
        ) from exc


def _enforce_feed_broker_consent(*, feed_account: dict, execution_accounts: list[dict], consented: bool) -> None:
    mismatches = collect_mismatch_accounts(feed_account=feed_account, execution_accounts=execution_accounts)
    if not mismatches:
        return
    if consented:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "FEED_BROKER_MISMATCH_CONSENT_REQUIRED",
            "message": "Feed account broker differs from one or more execution accounts. Confirm I Agree to continue.",
            "mismatches": mismatches,
        },
    )



def _consent_for_execution_account(*, feed_account: dict, execution_account: dict, consented: bool) -> tuple[bool, Optional[dict]]:
    if brokers_match(feed_account, execution_account):
        return False, None
    if not consented:
        return True, None
    warning = build_mismatch_warning(feed_account=feed_account, execution_account=execution_account)
    return True, build_consent_record(
        feed_account=feed_account,
        execution_account=execution_account,
        warning_text=warning,
    )


def _validate_execution_account_selection(accounts: list[dict], feed_account: dict):
    unique_accounts = []
    seen = set()
    for account in accounts:
        account_id = str(account.get("_id"))
        if account_id in seen:
            continue
        seen.add(account_id)
        unique_accounts.append(account)
    if not unique_accounts:
        raise HTTPException(status_code=400, detail="Select at least one execution account.")
    if len(unique_accounts) > 2:
        raise HTTPException(status_code=400, detail="Select at most two execution accounts.")
    # Prices come from the header feed account; execution targets may omit it.
    feed_scope = _account_broker_scope_key(feed_account)
    if feed_scope:
        for account in unique_accounts:
            if _account_broker_scope_key(account) != feed_scope:
                raise HTTPException(
                    status_code=400,
                    detail="Selected execution accounts must belong to the same broker/server as the feed account.",
                )
    scope_keys = {_account_broker_scope_key(account) for account in unique_accounts}
    if len(scope_keys) > 1:
        raise HTTPException(status_code=400, detail="Selected execution accounts must belong to the same broker/server.")
    return unique_accounts


def _coerce_account_oid(value) -> Optional[ObjectId]:
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return parse_object_id(str(value))
    except ValueError:
        return None


def _selected_account_candidate_ids(user: dict) -> List[ObjectId]:
    keys = (
        "selected_account_id",
        "selected_international_account_id",
        "selected_indian_account_id",
        "selected_indian_crypto_account_id",
    )
    candidates: List[ObjectId] = []
    seen = set()
    for key in keys:
        account_oid = _coerce_account_oid(user.get(key))
        if account_oid and account_oid not in seen:
            seen.add(account_oid)
            candidates.append(account_oid)
    return candidates


def _lookup_international_account(user_id: ObjectId, account_oid: ObjectId, db):
    account = db.meta_accounts.find_one({"_id": account_oid, "user_id": user_id})
    if not account:
        return None
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        return None
    return account


async def _lookup_international_account_async(user_id: ObjectId, account_oid: ObjectId, db):
    account = await db.meta_accounts.find_one_async({"_id": account_oid, "user_id": user_id})
    if not account:
        return None
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        return None
    return account


def _assert_account(user: dict, db):
    user_id = user["_id"]
    candidates = _selected_account_candidate_ids(user)
    if not candidates:
        raise HTTPException(status_code=400, detail="No selected broker account")
    for account_oid in candidates:
        account = _lookup_international_account(user_id, account_oid, db)
        if account:
            return account
    raise HTTPException(status_code=404, detail="Selected account not found")


async def _assert_account_async(user: dict, db):
    user_id = user["_id"]
    candidates = _selected_account_candidate_ids(user)
    if not candidates:
        raise HTTPException(status_code=400, detail="No selected broker account")
    for account_oid in candidates:
        account = await _lookup_international_account_async(user_id, account_oid, db)
        if account:
            if _coerce_account_oid(user.get("selected_account_id")) != account["_id"]:
                await persist_user_document_async(db, user_id, {"selected_account_id": account["_id"]})
                user["selected_account_id"] = account["_id"]
            return account
    raise HTTPException(status_code=404, detail="Selected account not found")


async def _resolve_execution_feed_account_async(user: dict, db, target_accounts: Optional[list] = None) -> dict:
    """Resolve the price-feed account from the user's header selection.

    Execution targets may omit the feed account; do not rewrite selected_account_id
    just because orders are placed on a different same-broker account.
    """
    try:
        return await _assert_account_async(user, db)
    except HTTPException:
        if not target_accounts:
            raise
        for _, account in target_accounts:
            if _normalize_market_type(account.get("market_type")) == "INTERNATIONAL":
                return account
        raise


def _get_account_by_db_id(user_id: ObjectId, account_db_id: str, db):
    try:
        account_oid = parse_object_id(account_db_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid account id: {account_db_id}")
    account = db.meta_accounts.find_one({"_id": account_oid, "user_id": user_id})
    if not account:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_db_id}")
    return account


async def _get_account_by_db_id_async(user_id: ObjectId, account_db_id: str, db):
    try:
        account_oid = parse_object_id(account_db_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid account id: {account_db_id}")
    account = await db.meta_accounts.find_one_async({"_id": account_oid, "user_id": user_id})
    if not account:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_db_id}")
    return account


async def _resolve_symbol_for_account(account: dict, symbol: str) -> str:
    return await resolve_broker_symbol_for_account(account, symbol)


def _serialize_symbol_resolve(requested: str, broker_symbol: str, symbol_spec: Optional[dict] = None) -> SymbolResolveOut:
    canonical = infer_canonical(requested) or normalize_symbol(requested)
    spec = symbol_spec or {}
    tick_size = float(spec.get("tickSize") or spec.get("point") or 0.0)
    return SymbolResolveOut(
        requested=normalize_symbol(requested),
        canonical=canonical,
        broker_symbol=str(broker_symbol).strip(),
        display_symbol=display_symbol(requested, broker_symbol),
        price_digits=digits_from_symbol_spec(spec),
        point=float(spec.get("point") or 0.0),
        tick_size=tick_size,
    )


async def _symbol_spec_for_account(account: dict, symbol: str) -> dict:
    return await metaapi_service.get_symbol_specification(account["api_token"], account["account_id"], str(symbol).strip())


async def _normalize_price_for_account(account: dict, symbol: str, value: Optional[float]) -> float:
    if value is None:
        return 0.0
    symbol_spec = await _symbol_spec_for_account(account, symbol)
    return normalize_price_to_symbol(value, symbol_spec)


def _normalize_trade_plan_input_targets(user: dict, db, raw_targets: List[OrderTargetIn], fallback_account: Optional[dict], fallback_risk_amount: Optional[float]) -> List[dict]:
    selected_targets = []
    seen_account_ids = set()
    for target in raw_targets or []:
        if target.risk_amount <= 0:
            raise HTTPException(status_code=400, detail="Each selected account needs a valid positive risk amount.")
        account = _get_account_by_db_id(user["_id"], target.account_db_id, db)
        if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
            raise HTTPException(status_code=400, detail="Trade Planner supports international accounts only.")
        account_key = str(account["_id"])
        if account_key in seen_account_ids:
            continue
        seen_account_ids.add(account_key)
        selected_targets.append(
            {
                "account": account,
                "account_id": account["_id"],
                "risk_amount": float(target.risk_amount),
            }
        )
    if selected_targets:
        return selected_targets
    if fallback_account:
        fallback_value = float(fallback_risk_amount if fallback_risk_amount is not None else fallback_account.get("risk_amount") or settings.default_risk_amount)
        if fallback_value <= 0:
            raise HTTPException(status_code=400, detail="Each selected account needs a valid positive risk amount.")
        return [
            {
                "account": fallback_account,
                "account_id": fallback_account["_id"],
                "risk_amount": fallback_value,
            }
        ]
    raise HTTPException(status_code=400, detail="Select at least one account for this plan.")


async def _normalize_trade_plan_input_targets_async(
    user: dict,
    db,
    raw_targets: List[OrderTargetIn],
    fallback_account: Optional[dict],
    fallback_risk_amount: Optional[float],
) -> List[dict]:
    selected_targets = []
    seen_account_ids = set()
    for target in raw_targets or []:
        if target.risk_amount <= 0:
            raise HTTPException(status_code=400, detail="Each selected account needs a valid positive risk amount.")
        account = await _get_account_by_db_id_async(user["_id"], target.account_db_id, db)
        if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
            raise HTTPException(status_code=400, detail="Trade Planner supports international accounts only.")
        account_key = str(account["_id"])
        if account_key in seen_account_ids:
            continue
        seen_account_ids.add(account_key)
        selected_targets.append(
            {
                "account": account,
                "account_id": account["_id"],
                "risk_amount": float(target.risk_amount),
            }
        )
    if selected_targets:
        return selected_targets
    if fallback_account:
        fallback_value = float(fallback_risk_amount if fallback_risk_amount is not None else fallback_account.get("risk_amount") or settings.default_risk_amount)
        if fallback_value <= 0:
            raise HTTPException(status_code=400, detail="Each selected account needs a valid positive risk amount.")
        return [
            {
                "account": fallback_account,
                "account_id": fallback_account["_id"],
                "risk_amount": fallback_value,
            }
        ]
    raise HTTPException(status_code=400, detail="Select at least one account for this plan.")


def _indian_session_expiry():
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    next_midnight_ist = (now_ist + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return next_midnight_ist.astimezone(timezone.utc).replace(tzinfo=None)


def _get_order_account(order: dict, user_id: ObjectId, db):
    account = db.meta_accounts.find_one({"_id": order.get("account_id"), "user_id": user_id})
    if not account:
        raise HTTPException(status_code=404, detail="Linked broker account not found")
    return account


def _normalize_historical_candle(candle: dict) -> dict:
    candle_time = candle.get("time")
    if hasattr(candle_time, "tzinfo"):
        dt_value = candle_time if candle_time.tzinfo else candle_time.replace(tzinfo=timezone.utc)
    else:
        dt_value = datetime.fromisoformat(str(candle_time).replace("Z", "+00:00"))
    return {
        "time": dt_value.astimezone(timezone.utc),
        "open": float(candle.get("open") or 0),
        "high": float(candle.get("high") or 0),
        "low": float(candle.get("low") or 0),
        "close": float(candle.get("close") or 0),
    }


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _broker_cache_key(account: dict) -> str:
    meta_profile = account.get("meta_profile") or {}
    server = str(meta_profile.get("server") or "").strip().upper()
    broker_type = str(meta_profile.get("type") or "").strip().upper()
    account_currency = str(account.get("account_currency") or meta_profile.get("currency") or "").strip().upper()
    if server:
        return "|".join(part for part in [server, broker_type, account_currency] if part)
    return f"METAACCOUNT|{str(account.get('account_id') or '').upper()}"


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_broker_time_string(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _to_ist_iso(dt_value: Optional[datetime]) -> Optional[str]:
    if not dt_value:
        return None
    if not dt_value.tzinfo:
        dt_value = dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(ZoneInfo(settings.timezone)).isoformat()


def _convert_server_time_payload_to_ist(payload: dict) -> dict:
    utc_time = _parse_iso_timestamp(payload.get("time"))
    broker_time_naive = _parse_broker_time_string(payload.get("brokerTime"))
    last_quote_utc = _parse_iso_timestamp(payload.get("lastQuoteTime"))
    last_quote_broker_naive = _parse_broker_time_string(payload.get("lastQuoteBrokerTime"))

    broker_offset = None
    broker_time_aware = None
    if utc_time and broker_time_naive:
        broker_offset = broker_time_naive - utc_time.replace(tzinfo=None)
        broker_time_aware = broker_time_naive.replace(tzinfo=timezone(broker_offset))

    last_quote_broker_aware = None
    if last_quote_utc and last_quote_broker_naive:
        offset = broker_offset if broker_offset is not None else (last_quote_broker_naive - last_quote_utc.replace(tzinfo=None))
        last_quote_broker_aware = last_quote_broker_naive.replace(tzinfo=timezone(offset))

    return {
        "region": payload.get("region"),
        "server_time_utc": payload.get("time"),
        "server_time_ist": _to_ist_iso(utc_time),
        "broker_time_raw": payload.get("brokerTime"),
        "broker_time_ist": _to_ist_iso(broker_time_aware),
        "last_quote_time_utc": payload.get("lastQuoteTime"),
        "last_quote_time_ist": _to_ist_iso(last_quote_utc),
        "last_quote_broker_time_raw": payload.get("lastQuoteBrokerTime"),
        "last_quote_broker_time_ist": _to_ist_iso(last_quote_broker_aware),
        "inferred_broker_utc_offset": str(broker_offset) if broker_offset is not None else None,
    }


def _account_server_time_fields(payload: dict) -> dict:
    converted = _convert_server_time_payload_to_ist(payload)
    return {
        "broker_utc_offset": converted.get("inferred_broker_utc_offset"),
        "broker_time_region": converted.get("region"),
        "broker_server_time_utc": converted.get("server_time_utc"),
        "broker_server_time_ist": converted.get("server_time_ist"),
        "last_quote_time_utc": converted.get("last_quote_time_utc"),
        "last_quote_time_ist": converted.get("last_quote_time_ist"),
        "broker_last_time_sync_at": datetime.utcnow(),
    }


def _broker_info_from_account(account: Optional[dict]) -> dict:
    if not account:
        return {}

    meta_profile = account.get("meta_profile") or {}
    broker_info = {
        "account_name": str(account.get("account_name") or meta_profile.get("account_name") or ""),
        "account_id": str(account.get("account_id") or ""),
        "login": str(meta_profile.get("login") or ""),
        "server": str(meta_profile.get("server") or ""),
        "type": str(meta_profile.get("type") or ""),
    }
    return {key: value for key, value in broker_info.items() if value}


def _build_manual_context(
    data: OrderCreateIn,
    order_type: str,
    *,
    is_retry_child: bool = False,
    parent_order_id: Optional[str] = None,
    automatic_trade_management: Optional[bool] = None,
) -> dict:
    normalized_type = str(order_type or "").upper()
    retryable = bool(data.retryable_order) and normalized_type in RETRYABLE_ORDER_TYPES and not is_retry_child
    auto_mgmt = bool(data.automatic_trade_management) if automatic_trade_management is None else bool(automatic_trade_management)
    context = {
        "retryable_order": retryable,
        "automatic_trade_management": auto_mgmt,
        "retry_used": False,
        "partial_booked_4r": False,
        "target_booked": False,
        "position_was_open": False,
        "parent_order_id": parent_order_id,
        "is_retry_child": is_retry_child,
        "conditional_order": False,
        "conditional_triggered": False,
        "trigger_price": None,
    }
    if normalized_type == "LIMIT" and data.cancel_at is not None:
        context["cancel_at"] = float(data.cancel_at)
    if normalized_type == "SL" and bool(getattr(data, "conditional_order", False)):
        context["conditional_order"] = True
        context["trigger_price"] = float(data.trigger_price) if data.trigger_price is not None else None
        context["conditional_triggered"] = False
    return context


def _pick_active_account_id(accounts: List[dict], selected_account_id) -> Optional[ObjectId]:
    if not accounts:
        return None

    selected_oid = selected_account_id if isinstance(selected_account_id, ObjectId) else None
    by_id = {account["_id"]: account for account in accounts}
    selected_account = by_id.get(selected_oid)

    if selected_account and str(selected_account.get("deployment_state") or "").upper() != "UNDEPLOYED":
        return selected_account["_id"]

    for account in accounts:
        if str(account.get("deployment_state") or "").upper() != "UNDEPLOYED":
            return account["_id"]

    return None


def _pick_active_account_id_for_market(accounts: List[dict], selected_account_id, selected_market: str) -> Optional[ObjectId]:
    market_accounts = [
        account for account in accounts
        if _normalize_market_type(account.get("market_type")) == selected_market
    ]
    if not market_accounts:
        return None
    if selected_market in {MARKET_INDIAN, MARKET_INDIAN_CRYPTO}:
        selected_oid = selected_account_id if isinstance(selected_account_id, ObjectId) else None
        selected_account = next((account for account in market_accounts if account["_id"] == selected_oid), None)
        return selected_account["_id"] if selected_account else market_accounts[0]["_id"]
    return _pick_active_account_id(market_accounts, selected_account_id)


def _market_selection_field(market_type: str) -> str:
    if market_type == MARKET_INDIAN:
        return "selected_indian_account_id"
    if market_type == MARKET_INDIAN_CRYPTO:
        return "selected_indian_crypto_account_id"
    return "selected_international_account_id"


def _fallback_markets(selected_market: str) -> List[str]:
    ordered = [selected_market, *SUPPORTED_MARKETS]
    seen = []
    for market in ordered:
        if market not in seen:
            seen.append(market)
    return [market for market in seen if market != selected_market]


def _to_notification_out(doc: dict) -> NotificationOut:
    return NotificationOut(
        id=str(doc["_id"]),
        order_id=str(doc["order_id"]) if doc.get("order_id") else None,
        symbol=doc.get("symbol"),
        category=doc.get("category", "orders"),
        event_type=doc.get("event_type"),
        status=doc.get("status"),
        activity=doc.get("activity", ""),
        failure_reason=doc.get("failure_reason"),
        placement_fallback_reason=doc.get("placement_fallback_reason"),
        timestamp=_as_utc_datetime(doc["created_at"]),
        broker_info=doc.get("broker_info"),
    )


def _order_row_out(doc: dict) -> OrderRowOut:
    return OrderRowOut(
        id=str(doc["_id"]),
        symbol=doc.get("symbol"),
        order_type=doc.get("order_type"),
        side=doc.get("side"),
        status=doc.get("status"),
        manual_context=doc.get("manual_context"),
        quantity=doc.get("quantity"),
        entry=doc.get("entry"),
        stop_loss=doc.get("stop_loss"),
        target=doc.get("target"),
        rr_ratio=doc.get("rr_ratio"),
        is_open_position=doc.get("is_open_position"),
        position_quantity=doc.get("position_quantity"),
        realized_pl=doc.get("realized_pl"),
        unrealized_pl=doc.get("unrealized_pl"),
        failure_reason=doc.get("failure_reason"),
        placement_fallback_reason=doc.get("placement_fallback_reason"),
        comment=doc.get("comment"),
        broker_info=doc.get("broker_info"),
        account_id=str(doc.get("account_id") or "") or None,
        copy_group_id=doc.get("copy_group_id"),
        meta_order_id=str(doc.get("meta_order_id")) if doc.get("meta_order_id") else None,
        meta_position_id=str(doc.get("meta_position_id")) if doc.get("meta_position_id") else None,
        external_source=doc.get("external_source"),
        opened_at=_as_utc_datetime(doc.get("opened_at")),
        closed_at=_as_utc_datetime(doc.get("closed_at")),
        last_broker_seen_at=_as_utc_datetime(doc.get("last_broker_seen_at")),
        created_at=_as_utc_datetime(doc.get("created_at")),
        updated_at=_as_utc_datetime(doc.get("updated_at")),
    )


def _broker_position_side(position: dict) -> str:
    raw_type = str(position.get("type") or "").upper()
    if raw_type == "1" or "SELL" in raw_type:
        return "SELL"
    return "BUY"


def _float_or_none(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _position_matches_local_order(order: dict, position: dict) -> bool:
    if str(order.get("symbol") or "").upper() != str(position.get("symbol") or "").upper():
        return False
    side = str(order.get("side") or "").upper()
    position_side = _broker_position_side(position)
    if side in {"BUY", "SELL"} and side != position_side:
        return False
    order_qty = _float_or_none(order.get("quantity"))
    position_qty = _float_or_none(position.get("volume"))
    if order_qty is not None and position_qty is not None and abs(order_qty - position_qty) > 1e-8:
        return False
    order_entry = _float_or_none(order.get("entry"))
    position_entry = _float_or_none(position.get("openPrice"))
    if order_entry is not None and position_entry is not None:
        # Broker execution can have slight price variance, but a different entry
        # by more than a small fraction usually means this is not the same trade.
        return abs(order_entry - position_entry) <= max(abs(order_entry) * 0.0005, 0.0001)
    return True


def _broker_position_order_values(user_oid, account: dict, position: dict, existing: Optional[dict] = None) -> dict:
    now = datetime.utcnow()
    volume = _float_or_none(position.get("volume"))
    open_price = _float_or_none(position.get("openPrice"))
    stop_loss = _float_or_none(position.get("stopLoss"))
    take_profit = _float_or_none(position.get("takeProfit"))
    unrealized = _float_or_none(position.get("unrealizedProfit"))
    total_profit = _float_or_none(position.get("profit"))
    realized = existing.get("realized_pl") if existing else None
    if total_profit is not None and unrealized is not None and abs(total_profit - unrealized) > 1e-9:
        realized = round(total_profit - unrealized, 2)
    last_broker_profit = existing.get("last_broker_profit") if existing else None
    if total_profit is not None:
        last_broker_profit = round(total_profit, 2)
    elif unrealized is not None:
        last_broker_profit = round(unrealized, 2)

    base = {
        "user_id": user_oid,
        "account_id": account["_id"],
        "symbol": str(position.get("symbol") or "").upper(),
        "order_type": existing.get("order_type") if existing else "MARKET",
        "side": existing.get("side") if existing else _broker_position_side(position),
        "entry": open_price,
        "stop_loss": stop_loss,
        "target": take_profit,
        "comment": existing.get("comment") if existing else "Imported from broker",
        "quantity": volume if volume is not None else (existing.get("quantity") if existing else None),
        "risk_amount": existing.get("risk_amount") if existing else None,
        "sl_pips": existing.get("sl_pips") if existing else None,
        "rr_ratio": existing.get("rr_ratio") if existing else None,
        "meta_order_id": existing.get("meta_order_id") if existing else None,
        "meta_position_id": str(position.get("id")) if position.get("id") is not None else (existing.get("meta_position_id") if existing else None),
        "status": "POSITION_OPEN",
        "failure_reason": None,
        "copy_group_id": existing.get("copy_group_id") if existing else None,
        "broker_missing_since": None,
        "last_broker_seen_at": now,
        "is_open_position": True,
        "position_quantity": volume,
        "realized_pl": realized,
        "unrealized_pl": unrealized if unrealized is not None else total_profit,
        "last_broker_profit": last_broker_profit,
        "broker_info": _broker_info_from_account(account),
        "external_source": existing.get("external_source") if existing else "BROKER_IMPORT",
        "opened_at": existing.get("opened_at") if existing and existing.get("opened_at") else now,
        "closed_at": None,
        "updated_at": now,
    }
    if not existing:
        base["created_at"] = now
    return base


def _close_duplicate_position_rows(db, user_oid, account_id, position_id: str, keep_order_id) -> None:
    if not position_id:
        return
    now = datetime.utcnow()
    duplicate_query = {
        "user_id": user_oid,
        "account_id": account_id,
        "meta_position_id": position_id,
        "_id": {"$ne": keep_order_id},
        "dry_run": {"$ne": True},
        "status": {"$in": ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]},
    }
    for duplicate in db.orders.find(duplicate_query, {"realized_pl": 1, "unrealized_pl": 1}):
        update_doc = {
            "status": "CLOSED",
            "is_open_position": False,
            "position_quantity": 0.0,
            "unrealized_pl": None,
            "closed_at": now,
            "updated_at": now,
            "failure_reason": "Duplicate local row for broker position",
        }
        realized = merge_realized_pl_on_close(duplicate)
        if realized is not None:
            update_doc["realized_pl"] = realized
        db.orders.update_one({"_id": duplicate["_id"]}, {"$set": update_doc})


async def _sync_live_broker_positions_for_user(db, user: dict) -> None:
    user_oid = user["_id"]
    accounts = list(db.meta_accounts.find({"user_id": user_oid}))
    for account in accounts:
        if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
            continue
        connection = None
        try:
            connection = await metaapi_service.connect_streaming_account(account["api_token"], account["account_id"])
            terminal_state = await connection.get_terminal_state()
            if getattr(terminal_state, "read_ok", True) is False:
                logger.warning("Skipping direct broker position sync after failed terminal-state read | user=%s account=%s", user_oid, account.get("account_id"))
                continue
            broker_positions = list(getattr(terminal_state, "positions", []) or [])
            logger.info(
                "Direct broker position sync | user=%s account=%s broker_positions=%s",
                user_oid,
                account.get("account_id"),
                len(broker_positions),
            )
            for position in broker_positions:
                position_id = str(position.get("id") or "")
                if not position_id:
                    continue
                existing = db.orders.find_one({"user_id": user_oid, "account_id": account["_id"], "meta_position_id": position_id, "dry_run": {"$ne": True}})
                if not existing:
                    candidates = list(
                        db.orders.find(
                            {
                                "user_id": user_oid,
                                "account_id": account["_id"],
                                "dry_run": {"$ne": True},
                                "status": {"$in": ["PLACEMENT_PENDING", "PENDING", "CANCELLED", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]},
                                "symbol": str(position.get("symbol") or "").upper(),
                            }
                        ).sort("updated_at", -1).limit(25)
                    )
                    existing = next((order for order in candidates if _position_matches_local_order(order, position)), None)
                values = _broker_position_order_values(user_oid, account, position, existing)
                if existing:
                    db.orders.update_one({"_id": existing["_id"]}, {"$set": values})
                    _close_duplicate_position_rows(db, user_oid, account["_id"], position_id, existing["_id"])
                else:
                    inserted = db.orders.insert_one(values)
                    _close_duplicate_position_rows(db, user_oid, account["_id"], position_id, inserted.inserted_id)
        except Exception:
            logger.exception("Direct broker position sync failed | user=%s account=%s", user_oid, account.get("account_id"))
        finally:
            if connection:
                try:
                    await connection.close()
                except Exception:
                    pass


def _today_utc_range():
    now_local = datetime.now(ZoneInfo(settings.timezone))
    local_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _save_event(
    db,
    user_id: ObjectId,
    order_id: ObjectId,
    event_type: str,
    status: str,
    message: str,
    payload: Optional[dict] = None,
    notify_user: bool = True,
    symbol: Optional[str] = None,
    broker_info: Optional[dict] = None,
    failure_reason: Optional[str] = None,
    placement_fallback_reason: Optional[str] = None,
):
    db.order_events.insert_one(
        {
            "order_id": order_id,
            "event_type": event_type,
            "status": status,
            "message": message,
            "event_ts_ist": metaapi_service.now_ist(),
            "payload_json": metaapi_service.serialize_payload(payload or {}),
            "failure_reason": failure_reason,
            "broker_info": broker_info or {},
        }
    )
    if notify_user:
        db.notifications.insert_one(
            {
                "user_id": user_id,
                "order_id": order_id,
                "symbol": symbol,
                "category": "orders",
                "event_type": event_type,
                "status": status,
                "activity": message,
                "failure_reason": failure_reason,
                "placement_fallback_reason": placement_fallback_reason,
                "created_at": datetime.utcnow(),
                "broker_info": broker_info or {},
            }
        )


def _build_order_quantity(account: dict, symbol: str, entry: float, stop_loss: float, risk_amount: float, risk_ctx: Optional[dict] = None) -> float:
    qty = 0.0
    if risk_ctx:
        qty = calc_quantity_from_live_pip_value(
            symbol.upper(),
            risk_amount,
            entry,
            stop_loss,
            risk_ctx["pip_value_per_standard_lot"],
            volume_step=float(risk_ctx.get("volume_step") or 0.01),
            volume_min=float(risk_ctx.get("volume_min") or 0.01),
            volume_max=float(risk_ctx.get("volume_max") or 0),
            tick_size=float(risk_ctx.get("tick_size") or 0.0),
            tick_value=float(risk_ctx.get("tick_value") or 0.0),
            contract_size=float(risk_ctx.get("contract_size") or 0.0),
            account_currency=str(risk_ctx.get("account_currency") or account.get("account_currency") or "USD"),
        )
    if qty <= 0:
        qty = calc_quantity(
            symbol,
            risk_amount,
            entry,
            stop_loss,
            account_currency=str(account.get("account_currency") or "USD"),
        )
    return qty


def _build_order_risk_amount(
    account: dict,
    symbol: str,
    entry: float,
    stop_loss: float,
    quantity: float,
    risk_ctx: Optional[dict] = None,
) -> float:
    if risk_ctx:
        return calc_risk_amount_from_quantity(
            symbol.upper(),
            quantity,
            entry,
            stop_loss,
            pip_value_per_standard_lot=float(risk_ctx.get("pip_value_per_standard_lot") or 0),
            tick_size=float(risk_ctx.get("tick_size") or 0.0),
            tick_value=float(risk_ctx.get("tick_value") or 0.0),
            contract_size=float(risk_ctx.get("contract_size") or 0.0),
            account_currency=str(risk_ctx.get("account_currency") or account.get("account_currency") or "USD"),
        )
    return calc_risk_amount_from_quantity(
        symbol.upper(),
        quantity,
        entry,
        stop_loss,
        account_currency=str(account.get("account_currency") or "USD"),
    )


async def _modify_deferred_local_order(db, user, account: dict, order: dict, order_oid, data: OrderModifyIn, broker_info: dict):
    await _validate_order_payload(
        account,
        order["symbol"],
        order["order_type"],
        order["side"],
        data.entry,
        data.stop_loss,
        data.target,
    )
    new_entry, new_stop, new_target = await _normalize_order_prices(
        account,
        order["symbol"],
        float(data.entry),
        float(data.stop_loss),
        data.target,
    )
    try:
        risk_ctx = await metaapi_service.get_risk_context(account["api_token"], account["account_id"], order["symbol"])
    except Exception:
        risk_ctx = None

    risk_provided = data.risk_amount is not None
    qty_provided = data.quantity is not None
    if risk_provided:
        risk_amount = float(data.risk_amount)
        if risk_amount <= 0:
            raise HTTPException(status_code=400, detail="risk_amount must be positive")
        new_qty = _build_order_quantity(account, order["symbol"], new_entry, new_stop, risk_amount, risk_ctx)
        if new_qty <= 0:
            raise HTTPException(status_code=400, detail="Risk amount is too small for broker minimum volume.")
    elif qty_provided:
        new_qty = float(data.quantity)
        if new_qty <= 0:
            raise HTTPException(status_code=400, detail="quantity must be positive")
        risk_amount = _build_order_risk_amount(account, order["symbol"], new_entry, new_stop, new_qty, risk_ctx)
    else:
        new_qty = float(order.get("quantity") or 0)
        risk_amount = _build_order_risk_amount(account, order["symbol"], new_entry, new_stop, new_qty, risk_ctx)

    update_fields = {
        "entry": new_entry,
        "stop_loss": new_stop,
        "target": new_target,
        "quantity": new_qty,
        "risk_amount": risk_amount,
        "sl_pips": calc_sl_pips(order["symbol"], new_entry, new_stop),
        "rr_ratio": calc_rr(order["side"], new_entry, new_stop, new_target),
        "updated_at": datetime.utcnow(),
        "broker_info": broker_info,
    }
    await db.orders.update_one_async({"_id": order_oid}, {"$set": update_fields})
    updated = {**order, **update_fields}
    _save_event(
        db,
        user["_id"],
        order_oid,
        "ORDER_MODIFIED",
        str(order.get("status") or DEFERRED_MARKET_OPEN_STATUS),
        append_order_log_prices(
            f"{order['symbol']} deferred pending order updated locally (not yet at broker)",
            updated,
        ),
        merge_order_log_payload(update_fields, source=updated),
        symbol=order["symbol"],
        broker_info=broker_info,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {
        "ok": True,
        "entry": new_entry,
        "stop_loss": new_stop,
        "target": new_target,
        "quantity": new_qty,
        "risk_amount": risk_amount,
        "status": order.get("status"),
    }


def _normalize_trade_plan_account_targets(doc: dict) -> List[dict]:
    raw_targets = doc.get("account_targets") or []
    normalized = []
    seen = set()
    for raw in raw_targets:
        account_id = raw.get("account_id")
        if not account_id:
            continue
        account_key = str(account_id)
        if account_key in seen:
            continue
        seen.add(account_key)
        normalized.append(
            {
                "account_id": account_id,
                "risk_amount": float(raw.get("risk_amount") or 0),
            }
        )
    if normalized:
        return normalized
    legacy_account_id = doc.get("account_id")
    legacy_risk_amount = doc.get("risk_amount")
    if legacy_account_id and legacy_risk_amount:
        return [{"account_id": legacy_account_id, "risk_amount": float(legacy_risk_amount)}]
    return []


def _resolve_trade_plan_account_targets(user_id: ObjectId, db, targets: List[dict]) -> List[dict]:
    resolved = []
    for target in targets:
        account = db.meta_accounts.find_one({"_id": target["account_id"], "user_id": user_id})
        if not account or _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
            continue
        resolved.append(
            {
                "account": account,
                "account_id": target["account_id"],
                "risk_amount": float(target["risk_amount"]),
            }
        )
    return resolved


def _collect_trade_plan_orders(db, user_id: ObjectId, plan_id: ObjectId) -> Dict[str, dict]:
    orders = list(
        db.orders.find(
            {
                "user_id": user_id,
                "planner_context.plan_id": str(plan_id),
            }
        ).sort([("updated_at", -1), ("created_at", -1)])
    )
    grouped: Dict[str, dict] = {}
    for order in orders:
        account_key = str((order.get("planner_context") or {}).get("plan_account_id") or order.get("account_id") or "")
        if not account_key or account_key in grouped:
            continue
        grouped[account_key] = order
    return grouped


def _trade_planner_runtime_from_order_status(status: Optional[str], fallback: Optional[str] = None) -> str:
    mapping = {
        "PLACEMENT_PENDING": "PLACING_ORDER",
        "PENDING": "ORDER_PLACED",
        "FILLED": "POSITION_OPEN",
        "POSITION_OPEN": "POSITION_OPEN",
        "PARTIALLY_CLOSED": "PARTIALLY_CLOSED",
        "CLOSED": "CLOSED",
        "CANCELLED": "CANCELLED",
        "FAILED": "FAILED",
    }
    upper = str(status or "").upper().strip()
    if upper:
        return mapping.get(upper, upper)
    return str(fallback or "IDLE").upper()


def _summarize_trade_plan_account_states(doc: dict, account_targets: List[TradePlannerAccountTargetOut]) -> tuple[str, str, Optional[str]]:
    if str(doc.get("status") or "").upper() == "INACTIVE":
        return "INACTIVE", "INACTIVE", None
    active_statuses = [str(item.linked_order_status or "").upper() for item in account_targets if item.linked_order_status]
    if any(status in {"PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"} for status in active_statuses):
        winning_status = next(
            (
                status
                for status in ["POSITION_OPEN", "PARTIALLY_CLOSED", "FILLED", "PENDING", "PLACEMENT_PENDING"]
                if status in active_statuses
            ),
            "PENDING",
        )
        return "RUNNING", _trade_planner_runtime_from_order_status(winning_status, doc.get("runtime_status")), winning_status
    if any(status == "CLOSED" for status in active_statuses):
        return "INACTIVE", "CLOSED", "CLOSED"
    if any(status in {"FAILED", "CANCELLED"} for status in active_statuses):
        return str(doc.get("status") or "ACTIVE").upper(), _trade_planner_runtime_from_order_status(active_statuses[0], doc.get("runtime_status")), active_statuses[0]
    if bool(doc.get("auto_execution_enabled")):
        return "RUNNING", str(doc.get("runtime_status") or "WAITING_ENTRY_ZONE").upper(), None
    return str(doc.get("status") or "ACTIVE").upper(), str(doc.get("runtime_status") or "IDLE").upper(), None


def _trade_plan_has_entry_order(order_statuses: List[str]) -> bool:
    active_statuses = {"PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"}
    return any(str(status or "").upper() in active_statuses for status in order_statuses)


async def _sync_trade_plan_targets_with_orders(db, user_id: ObjectId, plan_id: ObjectId, resolved_targets: List[dict], doc_payload: dict):
    order_map = _collect_trade_plan_orders(db, user_id, plan_id)
    if not order_map:
        return
    for resolved_target in resolved_targets:
        account = resolved_target["account"]
        account_id = str(account["_id"])
        order = order_map.get(account_id)
        if not order:
            continue
        derived = derive_trade_plan(
            account,
            doc_payload.get("symbol"),
            doc_payload.get("strong_swing_type"),
            doc_payload.get("strong_swing_price"),
            doc_payload.get("reversal_points") or [],
            doc_payload.get("unmitigated_targets") or [],
            doc_payload.get("target_allocations") or [],
            bool(doc_payload.get("breakeven_at_t1", False)),
            doc_payload.get("point_size"),
            resolved_target["risk_amount"],
        )
        next_targets_payload = derived.get("targets") or []
        next_target = next_targets_payload[-1]["price"] if next_targets_payload else None
        next_rr = calc_rr(order.get("side"), order.get("entry"), order.get("stop_loss"), next_target)
        status = str(order.get("status") or "").upper()
        if status == "PENDING" and order.get("meta_order_id"):
            try:
                await metaapi_service.cancel_order(account["api_token"], account["account_id"], order["meta_order_id"])
                result = await metaapi_service.place_pending_order(
                    account["api_token"],
                    account["account_id"],
                    {
                        "symbol": order["symbol"],
                        "order_type": order["order_type"],
                        "side": order["side"],
                        "entry": order["entry"],
                        "stop_loss": order["stop_loss"],
                        "target": next_target,
                        "quantity": order["quantity"],
                    },
                )
                db.orders.update_one(
                    {"_id": order["_id"]},
                    {
                        "$set": {
                            "target": next_target,
                            "rr_ratio": next_rr,
                            "meta_order_id": str(result.get("orderId", "")),
                            "updated_at": datetime.utcnow(),
                            "planner_context.targets": next_targets_payload,
                        }
                    },
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Could not update pending planner target for {account.get('account_name')}: {exc}") from exc
        elif status in {"FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"} and order.get("meta_position_id"):
            try:
                await metaapi_service.modify_position(
                    account["api_token"],
                    account["account_id"],
                    str(order["meta_position_id"]),
                    stop_loss=order.get("stop_loss"),
                    take_profit=next_target,
                )
                db.orders.update_one(
                    {"_id": order["_id"]},
                    {
                        "$set": {
                            "target": next_target,
                            "rr_ratio": next_rr,
                            "updated_at": datetime.utcnow(),
                            "planner_context.targets": next_targets_payload,
                        }
                    },
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Could not update open planner target for {account.get('account_name')}: {exc}") from exc
        else:
            db.orders.update_one(
                {"_id": order["_id"]},
                {
                    "$set": {
                        "target": next_target,
                        "rr_ratio": next_rr,
                        "updated_at": datetime.utcnow(),
                        "planner_context.targets": next_targets_payload,
                    }
                },
            )


async def _cancel_trade_plan_pending_orders(db, user: dict, plan_id: ObjectId, reason: str) -> int:
    pending_orders = list(
        db.orders.find(
            {
                "user_id": user["_id"],
                "planner_context.plan_id": str(plan_id),
                "status": {"$in": ["PLACEMENT_PENDING", "PENDING"]},
            }
        )
    )
    cancelled_count = 0
    for order in pending_orders:
        account = _get_order_account(order, user["_id"], db)
        broker_info = order.get("broker_info") or _broker_info_from_account(account)
        meta_order_id = order.get("meta_order_id")
        now = datetime.utcnow()
        if not meta_order_id:
            db.orders.update_one(
                {"_id": order["_id"]},
                {
                    "$set": {
                        "status": "CANCELLED",
                        "updated_at": now,
                        "closed_at": now,
                        "broker_info": broker_info,
                        "comment": reason,
                    }
                },
            )
            _save_event(
                db,
                user["_id"],
                order["_id"],
                "PLANNER_ORDER_CANCELLED",
                "CANCELLED",
                f"{order['symbol']} planner order cancelled locally: {reason}",
                symbol=order["symbol"],
                broker_info=broker_info,
            )
            cancelled_count += 1
            continue
        try:
            result = await metaapi_service.cancel_order(account["api_token"], account["account_id"], meta_order_id)
        except Exception as exc:
            failure_reason = str(exc)
            if not _is_missing_broker_order_error(exc):
                _save_event(
                    db,
                    user["_id"],
                    order["_id"],
                    "PLANNER_ORDER_CANCEL_FAILED",
                    order.get("status", "PENDING"),
                    append_order_log_prices(
                        f"{order['symbol']} planner order cancel failed on {broker_info.get('account_name', 'broker account')}: {failure_reason}",
                        order,
                    ),
                    merge_order_log_payload({"error": failure_reason}, source=order),
                    symbol=order["symbol"],
                    broker_info=broker_info,
                    failure_reason=failure_reason,
                )
                raise HTTPException(status_code=502, detail=f"Could not cancel planner order for {order['symbol']}: {failure_reason}") from exc
            result = {"already_cancelled": True, "reason": failure_reason}
        db.orders.update_one(
            {"_id": order["_id"]},
            {
                "$set": {
                    "status": "CANCELLED",
                    "updated_at": datetime.utcnow(),
                    "closed_at": datetime.utcnow(),
                    "broker_info": broker_info,
                    "comment": reason,
                }
            },
        )
        _save_event(
            db,
            user["_id"],
            order["_id"],
            "PLANNER_ORDER_CANCELLED",
            "CANCELLED",
            f"{order['symbol']} planner pending order cancelled on {broker_info.get('account_name', 'broker account')}: {reason}",
            result,
            symbol=order["symbol"],
            broker_info=broker_info,
        )
        cancelled_count += 1
    return cancelled_count


def _serialize_trade_plan(doc: dict, db) -> TradePlannerPlanOut:
    normalized_targets = _normalize_trade_plan_account_targets(doc)
    resolved_targets = _resolve_trade_plan_account_targets(doc["user_id"], db, normalized_targets)
    if not resolved_targets:
        raise HTTPException(status_code=404, detail="Trade plan accounts not found")
    primary_target = resolved_targets[0]
    derived = derive_trade_plan(
        primary_target["account"],
        doc.get("symbol"),
        doc.get("strong_swing_type"),
        doc.get("strong_swing_price"),
        doc.get("reversal_points") or [],
        doc.get("unmitigated_targets") or [],
        doc.get("target_allocations") or [],
        bool(doc.get("breakeven_at_t1", False)),
        doc.get("point_size"),
        primary_target["risk_amount"],
    )
    base_payload = {key: value for key, value in derived.items() if key not in {"risk_amount", "quantity"}}
    order_map = _collect_trade_plan_orders(db, doc["user_id"], doc["_id"])
    account_target_rows: List[TradePlannerAccountTargetOut] = []
    total_risk = 0.0
    total_quantity = 0.0
    any_breakeven_at = _as_utc_datetime(doc.get("breakeven_activated_at"))
    for resolved_target in resolved_targets:
        account = resolved_target["account"]
        risk_amount = resolved_target["risk_amount"]
        target_derived = derive_trade_plan(
            account,
            doc.get("symbol"),
            doc.get("strong_swing_type"),
            doc.get("strong_swing_price"),
            doc.get("reversal_points") or [],
            doc.get("unmitigated_targets") or [],
            doc.get("target_allocations") or [],
            bool(doc.get("breakeven_at_t1", False)),
            doc.get("point_size"),
            risk_amount,
        )
        total_risk += risk_amount
        total_quantity += float(target_derived["quantity"])
        order = order_map.get(str(account["_id"]))
        linked_order_status = str(order.get("status") or "").upper() if order else None
        runtime_status = _trade_planner_runtime_from_order_status(linked_order_status, doc.get("runtime_status"))
        if order and order.get("stop_loss") is not None:
            try:
                if round(float(order.get("stop_loss")), 10) == round(float(target_derived["entry_price"]), 10):
                    any_breakeven_at = any_breakeven_at or _as_utc_datetime(order.get("updated_at"))
            except Exception:
                pass
        account_target_rows.append(
            TradePlannerAccountTargetOut(
                account_db_id=str(account["_id"]),
                account_name=_format_account_label(account),
                risk_amount=risk_amount,
                quantity=float(target_derived["quantity"]),
                runtime_status=runtime_status,
                linked_order_id=str(order["_id"]) if order else None,
                linked_order_status=linked_order_status,
                last_execution_at=_as_utc_datetime(order.get("updated_at")) if order else None,
                running_pl=float(order.get("unrealized_pl")) if order and order.get("unrealized_pl") is not None else None,
            )
        )
    effective_status, effective_runtime, effective_linked_status = _summarize_trade_plan_account_states(doc, account_target_rows)
    return TradePlannerPlanOut(
        id=str(doc["_id"]),
        account_id=str(primary_target["account_id"]),
        status=effective_status,
        auto_execution_enabled=bool(doc.get("auto_execution_enabled", False)),
        runtime_status=effective_runtime,
        linked_order_id=str(doc.get("linked_order_id")) if doc.get("linked_order_id") else None,
        linked_order_status=effective_linked_status,
        last_execution_at=_as_utc_datetime(doc.get("last_execution_at")),
        breakeven_activated_at=any_breakeven_at,
        created_at=_as_utc_datetime(doc.get("created_at")),
        updated_at=_as_utc_datetime(doc.get("updated_at")),
        risk_amount=round(total_risk, 2),
        quantity=round(total_quantity, 4),
        account_targets=account_target_rows,
        **base_payload,
    )


def _is_missing_broker_order_error(exc: Exception) -> bool:
    return is_missing_broker_order_error(exc)


def _mid_price(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None and ask is None:
        return None
    if bid is None:
        return ask
    if ask is None:
        return bid
    bid_decimal = Decimal(str(bid))
    ask_decimal = Decimal(str(ask))
    precision = max(-bid_decimal.as_tuple().exponent, -ask_decimal.as_tuple().exponent, 0)
    midpoint = (bid_decimal + ask_decimal) / Decimal("2")
    return float(midpoint.quantize(Decimal(1).scaleb(-precision)))


async def _resolve_entry_for_order(account: dict, symbol: str, order_type: str, side: str, requested_entry: Optional[float]) -> float:
    order_type_u = order_type.upper()
    side_u = side.upper()
    if order_type_u != "MARKET":
        if requested_entry is None or requested_entry <= 0:
            raise HTTPException(status_code=400, detail="Entry must be a valid positive number")
        return requested_entry

    price = await metaapi_service.get_symbol_price(account["api_token"], account["account_id"], symbol.upper())
    bid = price.get("bid")
    ask = price.get("ask")
    resolved_entry = ask if side_u == "BUY" else bid
    if resolved_entry is None:
        resolved_entry = _mid_price(bid, ask)
    if resolved_entry is None:
        raise HTTPException(status_code=400, detail="Current market price is unavailable for this symbol")
    return resolved_entry


async def _validate_order_payload(
    account: dict,
    symbol: str,
    order_type: str,
    side: str,
    entry: float,
    stop_loss: float,
    target: Optional[float],
    cancel_at: Optional[float] = None,
    *,
    conditional_order: bool = False,
    trigger_price: Optional[float] = None,
):
    symbol_u = symbol.upper()
    order_type_u = order_type.upper()
    side_u = side.upper()
    is_conditional = bool(conditional_order)

    if stop_loss <= 0:
        raise HTTPException(status_code=400, detail="Stop loss must be a positive number")

    if side_u not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="Side must be BUY or SELL")

    if order_type_u not in {"SL", "LIMIT", "MARKET"}:
        raise HTTPException(status_code=400, detail="Order type must be SL, LIMIT, or MARKET")

    if is_conditional and order_type_u != "SL":
        raise HTTPException(status_code=400, detail="Conditional order is only supported for SL orders")

    if side_u == "BUY" and stop_loss >= entry:
        raise HTTPException(status_code=400, detail="For BUY, stop loss must be below entry")
    if side_u == "SELL" and stop_loss <= entry:
        raise HTTPException(status_code=400, detail="For SELL, stop loss must be above entry")

    if target is not None:
        if side_u == "BUY" and target <= entry:
            raise HTTPException(status_code=400, detail="For BUY, target must be above entry")
        if side_u == "SELL" and target >= entry:
            raise HTTPException(status_code=400, detail="For SELL, target must be below entry")

    if cancel_at is not None:
        if order_type_u != "LIMIT":
            raise HTTPException(status_code=400, detail="Cancel At is only supported for LIMIT orders")
        if side_u == "BUY" and float(cancel_at) <= entry:
            raise HTTPException(status_code=400, detail="For BUY, Cancel At must be above entry")
        if side_u == "SELL" and float(cancel_at) >= entry:
            raise HTTPException(status_code=400, detail="For SELL, Cancel At must be below entry")

    if order_type_u == "MARKET":
        return

    price = await metaapi_service.get_symbol_price(account["api_token"], account["account_id"], symbol_u)
    bid = price.get("bid")
    ask = price.get("ask")
    market_price = _mid_price(bid, ask)
    if market_price is None:
        return

    if is_conditional:
        # Conditional SL: never enforce entry-vs-market. Trigger rules apply once provided.
        if trigger_price is None:
            return
        try:
            trigger = float(trigger_price)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Trigger price must be a valid number")
        if trigger <= 0:
            raise HTTPException(status_code=400, detail="Trigger price must be a positive number")
        if side_u == "SELL":
            if trigger <= market_price:
                raise HTTPException(status_code=400, detail="Conditional SELL trigger must be above current price")
            if entry >= trigger:
                raise HTTPException(status_code=400, detail="Conditional SELL entry must be below trigger price")
        else:
            if trigger >= market_price:
                raise HTTPException(status_code=400, detail="Conditional BUY trigger must be below current price")
            if entry <= trigger:
                raise HTTPException(status_code=400, detail="Conditional BUY entry must be above trigger price")
        return

    if order_type_u == "SL" and side_u == "BUY" and entry <= market_price:
        raise HTTPException(status_code=400, detail="SL BUY entry must be above current price")
    if order_type_u == "SL" and side_u == "SELL" and entry >= market_price:
        raise HTTPException(status_code=400, detail="SL SELL entry must be below current price")
    if order_type_u == "LIMIT" and side_u == "BUY" and entry >= market_price:
        raise HTTPException(status_code=400, detail="LIMIT BUY entry must be below current price")
    if order_type_u == "LIMIT" and side_u == "SELL" and entry <= market_price:
        raise HTTPException(status_code=400, detail="LIMIT SELL entry must be above current price")

    if cancel_at is not None and order_type_u == "LIMIT":
        high = ask if ask is not None else market_price
        low = bid if bid is not None else market_price
        if side_u == "BUY" and high is not None and float(high) >= float(cancel_at):
            raise HTTPException(status_code=400, detail="Cancel At already tapped")
        if side_u == "SELL" and low is not None and float(low) <= float(cancel_at):
            raise HTTPException(status_code=400, detail="Cancel At already tapped")


DETECTOR_TIMEFRAME_ALIASES = {
    "1M": "M1",
    "1MIN": "M1",
    "1MINUTE": "M1",
    "M1": "M1",
    "5M": "M5",
    "5MIN": "M5",
    "5MINUTES": "M5",
    "M5": "M5",
    "15M": "M15",
    "15MIN": "M15",
    "15MINUTES": "M15",
    "M15": "M15",
}

def _normalize_detector_timeframe(value: str) -> str:
    normalized = str(value or "").strip().replace(" ", "").replace("-", "").upper()
    if normalized not in DETECTOR_TIMEFRAME_ALIASES:
        raise HTTPException(status_code=400, detail="Timeframe must be 1 minute, 5 minutes, or 15 minutes.")
    return DETECTOR_TIMEFRAME_ALIASES[normalized]


def _normalize_detector_candle_type(value: str) -> str:
    normalized = str(value or "").strip().replace(" ", "_").replace("-", "_").upper()
    if normalized not in {"HAMMER", "SHOOTING_STAR"}:
        raise HTTPException(status_code=400, detail="Candle type must be Hammer or Shooting Star.")
    return normalized


def _normalize_detector_candle(candle: dict) -> dict:
    raw_time = candle.get("time")
    if hasattr(raw_time, "tzinfo"):
        candle_time = raw_time if raw_time.tzinfo else raw_time.replace(tzinfo=timezone.utc)
    else:
        candle_time = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
    return {
        "time": candle_time.astimezone(timezone.utc),
        "open": float(candle.get("open") or 0.0),
        "high": float(candle.get("high") or 0.0),
        "low": float(candle.get("low") or 0.0),
        "close": float(candle.get("close") or 0.0),
    }


def _completed_detector_candles(candles: list[dict]) -> list[dict]:
    normalized = sorted((_normalize_detector_candle(item) for item in candles), key=lambda item: item["time"])
    if len(normalized) <= 1:
        return []
    # MT5 can return broker-time candles ahead of workstation UTC. Since
    # copy_rates_from_pos(..., 0, count) returns the current bar last in this
    # adapter, drop the latest returned candle and scan the previous five.
    return normalized[:-1][-5:]


def _serialize_detector_candle(candle: dict, matched: bool = False) -> dict:
    return {
        "time": candle["time"],
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "matched": matched,
    }


def _round_to_symbol_digits(value: float, symbol_spec: dict) -> float:
    return normalize_price_to_symbol(value, symbol_spec)


async def _normalize_order_prices(account: dict, symbol: str, entry: float, stop_loss: float, target: Optional[float]):
    symbol_spec = await metaapi_service.get_symbol_specification(account["api_token"], account["account_id"], symbol.upper())
    normalized_entry = normalize_price_to_symbol(entry, symbol_spec)
    normalized_stop = normalize_price_to_symbol(stop_loss, symbol_spec)
    normalized_target = None if target is None else normalize_price_to_symbol(target, symbol_spec)
    return normalized_entry, normalized_stop, normalized_target


@app.post("/auth/register", response_model=TokenOut)
async def register(data: RegisterIn, request: Request, db=Depends(get_db)):
    existing = await db.users.find_one_async({"username": data.username})
    if existing:
        raise HTTPException(status_code=409, detail="Username exists")
    email = str(data.email or "").strip().lower() or None
    if email:
        existing_email = await db.platform_users.find_one_async({"email": email})
        if not existing_email:
            existing_email = await db.users.find_one_async({"email": email})
        if existing_email:
            raise HTTPException(status_code=409, detail="Email exists")

    session_id = new_session_id()
    now = datetime.utcnow()
    doc = {
        "username": data.username,
        "full_name": data.full_name,
        "email": email,
        "password_hash": hash_password(data.password),
        "selected_market": "INTERNATIONAL",
        "selected_international_account_id": None,
        "selected_indian_account_id": None,
        "selected_indian_crypto_account_id": None,
        "selected_account_id": None,
        "ui_settings": {},
        "current_session_id": session_id,
        "active_session_ids": [session_id],
        "is_admin": False,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.users.insert_one_async(doc)
    doc["_id"] = result.inserted_id
    await mirror_legacy_user_async(db, doc)
    write_audit(
        db,
        level="INFO",
        category="auth",
        event="REGISTER_SUCCESS",
        message="User registered.",
        user_id=str(result.inserted_id),
        session_id=session_id,
        metadata={"ip": request.client.host if request.client else None},
    )
    return TokenOut(
        access_token=create_access_token(str(result.inserted_id), session_id),
        full_name=data.full_name,
        username=data.username,
        is_admin=False,
    )


@app.post("/auth/login", response_model=TokenOut)
async def login(data: LoginIn, request: Request, db=Depends(get_db)):
    user = await find_user_for_login_async(db, data.username)
    if not user or not verify_password(data.password, user["password_hash"]):
        write_audit(
            db,
            level="WARN",
            category="auth",
            event="LOGIN_FAILED",
            message="Invalid credentials.",
            metadata={"identifier": data.username, "ip": request.client.host if request.client else None},
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get("is_active", True) is False:
        raise HTTPException(status_code=403, detail="User is inactive")
    session_id = new_session_id()
    existing_sessions = [str(item) for item in (user.get("active_session_ids") or []) if item]
    if user.get("current_session_id"):
        existing_sessions.append(str(user["current_session_id"]))
    active_session_ids = list(dict.fromkeys([session_id, *existing_sessions]))
    merged_user = {
        **user,
        "current_session_id": session_id,
        "active_session_ids": active_session_ids,
        "updated_at": datetime.utcnow(),
    }
    await mirror_legacy_user_async(db, merged_user)
    set_request_context(user_id=str(user["_id"]), session_id=session_id)
    write_audit(
        db,
        level="INFO",
        category="auth",
        event="LOGIN_SUCCESS",
        message="User logged in.",
        user_id=str(user["_id"]),
        session_id=session_id,
        metadata={"ip": request.client.host if request.client else None},
    )
    return TokenOut(
        access_token=create_access_token(str(user["_id"]), session_id),
        full_name=user["full_name"],
        username=user["username"],
        is_admin=bool(user.get("is_admin", False)),
    )


@app.get("/auth/me", response_model=UserSnapshotOut)
async def me(user=Depends(get_current_user), db=Depends(get_db)):
    accounts = await db.meta_accounts.find_async({"user_id": user["_id"]})
    selected_market = _normalize_market_type(user.get("selected_market"))
    selected_international_account_id = user.get("selected_international_account_id")
    selected_indian_account_id = user.get("selected_indian_account_id")
    selected_indian_crypto_account_id = user.get("selected_indian_crypto_account_id")
    refreshed_accounts = []
    for account in accounts:
        market_type = _normalize_market_type(account.get("market_type"))
        if market_type != "INTERNATIONAL":
            account.setdefault("market_type", market_type)
            account.setdefault("broker_type", _normalize_broker_type(account.get("broker_type"), market_type))
            session_doc = await db[INDIAN_SESSION_COLLECTION].find_one_async({"user_id": user["_id"], "account_id": account["_id"]})
            account["session_status"] = (session_doc or {}).get("session_status") or account.get("session_status") or "DISCONNECTED"
            account["session_expires_at"] = (session_doc or {}).get("expires_at") or account.get("session_expires_at")
            refreshed_accounts.append(account)
            continue
        account = await _ensure_account_tick_secret_async(db, account)
        try:
            account_state = await metaapi_service.get_account_connection_state(account["api_token"], account["account_id"])
            deployment_state = str(account_state.get("state") or "")
            connection_status = str(account_state.get("connection_status") or "")
            profile = await metaapi_service.get_account_profile(account["api_token"], account["account_id"])
            account_update = {
                "account_name": profile["account_name"],
                "meta_profile": {
                    **profile,
                    "deployment_state": deployment_state,
                    "connection_status": connection_status,
                },
                "deployment_state": deployment_state,
                "connection_status": connection_status,
                "last_meta_sync_at": datetime.utcnow(),
            }

            try:
                server_time_payload = await metaapi_service.get_server_time(account["api_token"], account["account_id"])
                server_time_fields = _account_server_time_fields(server_time_payload)
                account_update.update(server_time_fields)
                account_update["meta_profile"] = {
                    **account_update["meta_profile"],
                    "broker_utc_offset": server_time_fields.get("broker_utc_offset"),
                    "broker_time_region": server_time_fields.get("broker_time_region"),
                }
            except Exception:
                pass

            if deployment_state == "DEPLOYED" and connection_status == "CONNECTED":
                equity_profile = await metaapi_service.get_account_profile_with_equity(account["api_token"], account["account_id"])
                account_update.update(
                    {
                        "account_name": equity_profile["account_name"],
                        "equity_balance": equity_profile["equity"],
                        "balance": equity_profile["balance"],
                        "account_currency": equity_profile["currency"],
                        "meta_profile": {
                            **equity_profile,
                            "deployment_state": deployment_state,
                            "connection_status": connection_status,
                        },
                    }
                )

            await db.meta_accounts.update_one_async(
                {"_id": account["_id"]},
                {"$set": account_update},
            )
            account.update(account_update)
        except Exception:
            pass
        refreshed_accounts.append(account)

    preferred_selected_id = {
        MARKET_INTERNATIONAL: selected_international_account_id,
        MARKET_INDIAN: selected_indian_account_id,
        MARKET_INDIAN_CRYPTO: selected_indian_crypto_account_id,
    }.get(selected_market)
    active_account_id = _pick_active_account_id_for_market(refreshed_accounts, preferred_selected_id, selected_market)
    updates = {}
    active_field = _market_selection_field(selected_market)
    if active_account_id != preferred_selected_id:
        updates[active_field] = active_account_id
        if selected_market == MARKET_INDIAN:
            selected_indian_account_id = active_account_id
        elif selected_market == MARKET_INDIAN_CRYPTO:
            selected_indian_crypto_account_id = active_account_id
        else:
            selected_international_account_id = active_account_id
    if active_account_id != user.get("selected_account_id"):
        updates["selected_account_id"] = active_account_id
        user["selected_account_id"] = active_account_id
    if updates:
        await persist_user_document_async(db, user["_id"], updates)

    return UserSnapshotOut(
        full_name=user["full_name"],
        username=user["username"],
        is_admin=bool(user.get("is_admin", False)),
        is_active=bool(user.get("is_active", True)),
        selected_market=selected_market,
        selected_international_account_id=str(selected_international_account_id) if selected_international_account_id else None,
        selected_indian_account_id=str(selected_indian_account_id) if selected_indian_account_id else None,
        selected_indian_crypto_account_id=str(selected_indian_crypto_account_id) if selected_indian_crypto_account_id else None,
        selected_account_id=str(active_account_id) if active_account_id else None,
        ui_settings=_serialize_user_ui_settings(user),
        accounts=[_to_account_out(a) for a in refreshed_accounts],
    )


@app.post("/auth/ui-settings", response_model=UserSnapshotOut)
async def update_user_ui_settings(data: UserUiSettingsUpdateIn, user=Depends(get_current_user), db=Depends(get_db)):
    page_id = str(data.page_id or "").strip()
    allowed_pages = set(_header_nav_candidates_for_user(user))
    if page_id and page_id not in allowed_pages:
        raise HTTPException(status_code=400, detail="Unsupported page id")

    ui_settings = dict(user.get("ui_settings") or {})
    usage = _normalize_nav_usage_map(ui_settings.get("page_usage"), user)
    if page_id:
        usage[page_id] = int(usage.get(page_id, 0)) + 1
    ui_settings["page_usage"] = usage

    if data.order_defaults is not None:
        current_defaults = ui_settings.get("order_defaults") if isinstance(ui_settings.get("order_defaults"), dict) else {}
        next_defaults = {
            "automatic_trade_management": bool(
                data.order_defaults.automatic_trade_management
                if data.order_defaults.automatic_trade_management is not None
                else current_defaults.get("automatic_trade_management", True)
            ),
            "retryable_order": bool(
                data.order_defaults.retryable_order
                if data.order_defaults.retryable_order is not None
                else current_defaults.get("retryable_order", True)
            ),
        }
        ui_settings["order_defaults"] = next_defaults

    user["ui_settings"] = ui_settings

    await persist_user_document_async(db, user["_id"], {"ui_settings": ui_settings})
    return await me(user=user, db=db)


@app.get("/admin/users", response_model=List[AdminUserOut])
async def admin_list_users(admin_user=Depends(get_admin_user), db=Depends(get_db)):
    users = await db.users.find_async({})
    users.sort(key=lambda item: str(item.get("username") or ""))
    account_counts = {
        item["_id"]: item.get("count", 0)
        for item in await db.meta_accounts.aggregate_async([
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        ])
    }
    return [_serialize_admin_user(user, account_counts.get(user["_id"], 0)) for user in users]


@app.post("/admin/users", response_model=AdminUserOut)
async def admin_create_user(data: AdminUserCreateIn, admin_user=Depends(get_admin_user), db=Depends(get_db)):
    username = data.username.strip()
    full_name = data.full_name.strip()
    password = data.password
    if not username or not full_name or not password:
        raise HTTPException(status_code=400, detail="Username, full name, and password are required.")
    if await db.users.find_one_async({"username": username}):
        raise HTTPException(status_code=409, detail="Username exists")
    now = datetime.utcnow()
    result = await db.users.insert_one_async(
        {
            "username": username,
            "full_name": full_name,
            "password_hash": hash_password(password),
            "selected_market": "INTERNATIONAL",
            "selected_international_account_id": None,
            "selected_indian_account_id": None,
            "selected_indian_crypto_account_id": None,
            "selected_account_id": None,
            "ui_settings": {},
            "current_session_id": None,
            "active_session_ids": [],
            "is_admin": bool(data.is_admin),
            "is_active": bool(data.is_active),
            "created_at": now,
            "updated_at": now,
            "created_by": admin_user["_id"],
        }
    )
    created = await db.users.find_one_async({"_id": result.inserted_id})
    return _serialize_admin_user(created, 0)


@app.patch("/admin/users/{target_user_id}", response_model=AdminUserOut)
async def admin_update_user(target_user_id: str, data: AdminUserUpdateIn, admin_user=Depends(get_admin_user), db=Depends(get_db)):
    target_oid = parse_object_id(target_user_id)
    target_user = await db.users.find_one_async({"_id": target_oid})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    await _assert_not_last_active_admin_async(db, target_user, data.is_admin, data.is_active)

    updates = {"updated_at": datetime.utcnow()}
    if data.username is not None:
        username = data.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        existing = await db.users.find_one_async({"username": username, "_id": {"$ne": target_oid}})
        if existing:
            raise HTTPException(status_code=409, detail="Username exists")
        updates["username"] = username
    if data.full_name is not None:
        full_name = data.full_name.strip()
        if not full_name:
            raise HTTPException(status_code=400, detail="Full name is required")
        updates["full_name"] = full_name
    if data.password:
        updates["password_hash"] = hash_password(data.password)
    if data.is_admin is not None:
        updates["is_admin"] = bool(data.is_admin)
    if data.is_active is not None:
        updates["is_active"] = bool(data.is_active)
        if not bool(data.is_active):
            updates["current_session_id"] = None
            updates["active_session_ids"] = []
    await db.users.update_one_async({"_id": target_oid}, {"$set": updates})
    updated = await db.users.find_one_async({"_id": target_oid})
    if updates.get("current_session_id") is None and updated.get("is_active", True) is False:
        await live_state_hub.force_logout_user_sessions(str(updated["_id"]), "__inactive__")
    account_count = await db.meta_accounts.count_documents_async({"user_id": target_oid})
    return _serialize_admin_user(updated, account_count)


@app.post("/accounts", response_model=AccountOut)
async def add_account(data: MetaAccountIn, user=Depends(get_current_user), db=Depends(get_db)):
    market_type = _normalize_market_type(data.market_type)
    broker_type = _normalize_broker_type(data.broker_type, market_type)
    profile = {}
    server_time_fields = {}
    account_id = str(data.account_id or "").strip()
    api_token = str(data.api_token or "").strip()
    if market_type == "INTERNATIONAL":
        broker_type = "MT5"
        credentials = data.credentials or {}
        mt5_login = str(credentials.get("mt5_login") or credentials.get("login") or account_id).strip()
        mt5_password = str(credentials.get("mt5_password") or credentials.get("password") or api_token).strip()
        mt5_server = str(credentials.get("mt5_server") or credentials.get("server") or "").strip()
        mt5_path = str(credentials.get("mt5_terminal_path") or credentials.get("terminal_path") or "").strip().strip('"')
        if not mt5_login or not mt5_password or not mt5_server:
            raise HTTPException(status_code=400, detail="MT5 account number, password, and server are required.")
        if not mt5_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "MT5 terminal path is required for local multi-account use. "
                    "Use Detect running during account creation on the machine where MT5 is running, "
                    "or provide that account's terminal64.exe path."
                ),
            )
        if not os.path.isfile(mt5_path):
            raise HTTPException(status_code=400, detail=f"MT5 terminal path does not exist: {mt5_path}")
        terminal_processes = await asyncio.to_thread(find_running_terminal_processes)
        matching_processes = [
            process for process in terminal_processes
            if os.path.normcase(str(process.get("path") or "")) == os.path.normcase(mt5_path)
        ]
        if len(matching_processes) > 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Multiple MT5 processes are running from the same terminal path. "
                    "The MetaTrader5 Python API cannot reliably choose between them. "
                    "Use a separate copied MT5 folder per account so each account has a unique terminal64.exe path."
                ),
            )
        account_id = mt5_login
        local_mt5_token = json.dumps({"password": mt5_password, "server": mt5_server, "path": mt5_path})
        try:
            profile = await metaapi_service.get_account_profile_with_equity(local_mt5_token, account_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to fetch account details from local MT5: {exc}")
        try:
            server_time_payload = await metaapi_service.get_server_time(local_mt5_token, account_id)
            server_time_fields = _account_server_time_fields(server_time_payload)
            profile = {
                **profile,
                "broker_utc_offset": server_time_fields.get("broker_utc_offset"),
                "broker_time_region": server_time_fields.get("broker_time_region"),
            }
        except Exception:
            pass
        api_token = encrypt_secret(local_mt5_token)
    else:
        credentials = data.credentials or {}
        api_key = str(credentials.get("api_key") or "").strip()
        username = str(credentials.get("username") or "").strip()
        password = str(credentials.get("password") or "").strip()
        if broker_type != "MSTOCK":
            raise HTTPException(status_code=400, detail="Only Mstock is supported for Indian Market right now.")
        if not api_key or not username or not password:
            raise HTTPException(status_code=400, detail="Mstock API key, user ID, and password are required.")
        profile = {
            "user_name": username,
            "account_name": data.account_name.strip() or username,
            "broker_type": broker_type,
        }
        account_id = account_id or username
        api_token = None
    doc = {
        "user_id": user["_id"],
        "market_type": market_type,
        "broker_type": broker_type,
        "account_name": data.account_name.strip() or profile["account_name"],
        "account_id": account_id,
        "api_token": api_token or None,
        "credentials": {
            "api_key": api_key,
            "username": username,
            "password_encrypted": encrypt_secret(password),
        } if market_type == "INDIAN" else {
            "mt5_login": account_id,
            "mt5_server": profile.get("server") or mt5_server,
            "mt5_password_encrypted": api_token,
        },
        "risk_amount": data.risk_amount,
        "equity_balance": profile.get("equity"),
        "balance": profile.get("balance"),
        "account_currency": profile.get("currency"),
        "meta_profile": profile,
        "mt5_tick_ingest_secret": _new_mt5_tick_ingest_secret() if market_type == "INTERNATIONAL" else None,
        **server_time_fields,
        "last_meta_sync_at": datetime.utcnow(),
        "session_status": "DISCONNECTED" if market_type == "INDIAN" else None,
        "session_expires_at": None,
        "created_at": datetime.utcnow(),
    }
    result = await db.meta_accounts.insert_one_async(doc)
    doc["_id"] = result.inserted_id

    if market_type == "INTERNATIONAL":
        try:
            aliases = await detect_account_symbol_aliases(doc)
            if aliases:
                now = datetime.utcnow()
                await db.meta_accounts.update_one_async(
                    {"_id": doc["_id"]},
                    {"$set": {"symbol_aliases": aliases, "symbol_aliases_updated_at": now}},
                )
                doc["symbol_aliases"] = aliases
                doc["symbol_aliases_updated_at"] = now
        except Exception as exc:
            logger.warning("Auto-detect symbol aliases failed | account=%s error=%s", account_id, exc)

    selection_updates = {}
    market_selection_field = _market_selection_field(market_type)
    if not user.get(market_selection_field):
        selection_updates[market_selection_field] = result.inserted_id
    if _normalize_market_type(user.get("selected_market")) == market_type or not user.get("selected_account_id"):
        selection_updates["selected_account_id"] = result.inserted_id
        selection_updates["selected_market"] = market_type
    if selection_updates:
        await persist_user_document_async(db, user["_id"], selection_updates)
    if market_type == "INDIAN":
        await run_coro_in_thread(indian_market_stream_manager.ensure_user_stream, db, str(user["_id"]), live_state_hub.push_snapshot)
        await live_state_hub.push_snapshot(db, str(user["_id"]))
    return _to_account_out(doc)


@app.post("/accounts/select")
async def select_account(data: SelectAccountIn, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        account_oid = parse_object_id(data.account_db_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account id")

    account = await db.meta_accounts.find_one_async({"_id": account_oid, "user_id": user["_id"]})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    selected_market = _normalize_market_type(account.get("market_type"))
    await persist_user_document_async(
        db,
        user["_id"],
        {
            "selected_account_id": account_oid,
            "selected_market": selected_market,
            _market_selection_field(selected_market): account_oid,
        },
    )
    if selected_market == "INTERNATIONAL":
        await _ensure_market_data_stream(db, str(user["_id"]))
        await run_coro_in_thread(indian_market_stream_manager.stop_user_stream, str(user["_id"]))
    else:
        await _ensure_market_data_stream(db, str(user["_id"]))
        await run_coro_in_thread(indian_market_stream_manager.ensure_user_stream, db, str(user["_id"]), live_state_hub.push_snapshot)
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True}


@app.delete("/accounts/{account_db_id}")
async def delete_account(account_db_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    account = await _get_account_by_db_id_async(user["_id"], account_db_id, db)
    active_order_statuses = [
        "WAITING_TRIGGER",
        "PLACEMENT_PENDING",
        "PENDING",
        DEFERRED_MARKET_OPEN_STATUS,
        "FILLED",
        "POSITION_OPEN",
        "PARTIALLY_CLOSED",
    ]
    active_order = await db.orders.find_one_async(
        {
            "user_id": user["_id"],
            "account_id": account["_id"],
            "dry_run": {"$ne": True},
            "status": {"$in": active_order_statuses},
        }
    )
    if active_order:
        raise HTTPException(status_code=400, detail="Close or cancel active orders before deleting this account.")

    active_plan = await db[TRADE_PLAN_COLLECTION].find_one_async(
        {
            "user_id": user["_id"],
            "$or": [
                {"account_id": account["_id"]},
                {"account_targets.account_id": account["_id"]},
            ],
            "status": {"$nin": ["inactive", "deactivated", "completed", "cancelled"]},
        }
    )
    if active_plan:
        raise HTTPException(status_code=400, detail="Deactivate active Trade Planner plans before deleting this account.")

    market_type = _normalize_market_type(account.get("market_type"))
    selected_market = _normalize_market_type(user.get("selected_market"))
    remaining_accounts = await db.meta_accounts.find_async({"user_id": user["_id"], "_id": {"$ne": account["_id"]}})
    deleted_market_field = _market_selection_field(market_type)
    selected_market_field = _market_selection_field(selected_market)
    next_deleted_market_account_id = _pick_active_account_id_for_market(remaining_accounts, None, market_type)
    updates = {}

    if user.get(deleted_market_field) == account["_id"]:
        updates[deleted_market_field] = next_deleted_market_account_id

    preferred_selected_account_id = updates.get(selected_market_field, user.get(selected_market_field))
    next_selected_account_id = _pick_active_account_id_for_market(remaining_accounts, preferred_selected_account_id, selected_market)
    next_selected_market = selected_market
    if not next_selected_account_id:
        for fallback_market in _fallback_markets(selected_market):
            fallback_market_field = _market_selection_field(fallback_market)
            preferred_fallback_account_id = updates.get(fallback_market_field, user.get(fallback_market_field))
            fallback_account_id = _pick_active_account_id_for_market(remaining_accounts, preferred_fallback_account_id, fallback_market)
            if fallback_account_id:
                next_selected_market = fallback_market
                next_selected_account_id = fallback_account_id
                break
    if user.get("selected_account_id") != next_selected_account_id:
        updates["selected_account_id"] = next_selected_account_id
    if selected_market != next_selected_market:
        updates["selected_market"] = next_selected_market

    await db.meta_accounts.delete_one_async({"_id": account["_id"], "user_id": user["_id"]})
    await db[INDIAN_SESSION_COLLECTION].delete_many_async({"user_id": user["_id"], "account_id": account["_id"]})
    await db[INDIAN_WATCHLIST_COLLECTION].delete_many_async({"user_id": user["_id"], "account_id": account["_id"]})
    if updates:
        await persist_user_document_async(db, user["_id"], updates)

    try:
        if next_selected_market == "INTERNATIONAL":
            await _ensure_market_data_stream(db, str(user["_id"]))
            await run_coro_in_thread(indian_market_stream_manager.stop_user_stream, str(user["_id"]))
        else:
            await _ensure_market_data_stream(db, str(user["_id"]))
            if next_selected_account_id:
                await run_coro_in_thread(indian_market_stream_manager.ensure_user_stream, db, str(user["_id"]), live_state_hub.push_snapshot)
            else:
                await run_coro_in_thread(indian_market_stream_manager.stop_user_stream, str(user["_id"]))
        await live_state_hub.push_snapshot(db, str(user["_id"]))
    except Exception:
        logger.exception("Post-delete stream refresh failed | user=%s account=%s", str(user["_id"]), account_db_id)
        asyncio.create_task(_refresh_user_streams(str(user["_id"]), include_indian=True))
    return {"ok": True, "deleted_account_id": account_db_id}


@app.post("/indian/accounts/{account_db_id}/request-otp")
async def request_indian_account_otp(account_db_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    account = await _get_account_by_db_id_async(user["_id"], account_db_id, db)
    if _normalize_market_type(account.get("market_type")) != "INDIAN":
        raise HTTPException(status_code=400, detail="OTP flow is available only for Indian broker accounts.")
    credentials = account.get("credentials") or {}
    api_key = str(credentials.get("api_key") or "").strip()
    username = str(credentials.get("username") or "").strip()
    password_encrypted = str(credentials.get("password_encrypted") or "").strip()
    if not api_key or not username or not password_encrypted:
        raise HTTPException(status_code=400, detail="Indian broker credentials are incomplete.")
    logger.info("Indian OTP request started | user=%s account=%s username=%s", str(user["_id"]), account_db_id, username)
    try:
        await mstock_client.request_otp(username, decrypt_secret(password_encrypted))
    except Exception as exc:
        logger.exception("Indian OTP request failed | user=%s account=%s", str(user["_id"]), account_db_id)
        raise HTTPException(status_code=400, detail=str(exc))
    await db[INDIAN_SESSION_COLLECTION].update_one_async(
        {"user_id": user["_id"], "account_id": account["_id"]},
        {
            "$set": {
                "user_id": user["_id"],
                "account_id": account["_id"],
                "otp_requested_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "session_status": "OTP_PENDING",
            }
        },
        upsert=True,
    )
    await db.meta_accounts.update_one_async({"_id": account["_id"]}, {"$set": {"session_status": "OTP_PENDING", "session_expires_at": None}})
    logger.info("Indian OTP request succeeded | user=%s account=%s", str(user["_id"]), account_db_id)
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True, "message": "OTP requested from Mstock."}


@app.post("/indian/accounts/{account_db_id}/verify-otp")
async def verify_indian_account_otp(account_db_id: str, data: IndianOtpVerifyIn, user=Depends(get_current_user), db=Depends(get_db)):
    account = await _get_account_by_db_id_async(user["_id"], account_db_id, db)
    if _normalize_market_type(account.get("market_type")) != "INDIAN":
        raise HTTPException(status_code=400, detail="OTP verification is available only for Indian broker accounts.")
    credentials = account.get("credentials") or {}
    api_key = str(credentials.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Indian broker API key is missing.")
    otp = str(data.otp or "").strip()
    if not otp:
        raise HTTPException(status_code=400, detail="OTP is required.")
    logger.info("Indian OTP verify started | user=%s account=%s", str(user["_id"]), account_db_id)
    try:
        session_data = await mstock_client.create_session_token(api_key, otp)
        logger.info(
            "Indian OTP verify session created | user=%s account=%s user_name=%s exchanges=%s",
            str(user["_id"]),
            account_db_id,
            session_data.get("user_name"),
            session_data.get("exchanges"),
        )
        account_profile = await mstock_client.validate_credentials(api_key, str(session_data.get("access_token") or ""))
    except Exception as exc:
        logger.exception("Indian OTP verify failed | user=%s account=%s", str(user["_id"]), account_db_id)
        raise HTTPException(status_code=400, detail=str(exc))

    expires_at = _indian_session_expiry()
    await db[INDIAN_SESSION_COLLECTION].update_one_async(
        {"user_id": user["_id"], "account_id": account["_id"]},
        {
            "$set": {
                "user_id": user["_id"],
                "account_id": account["_id"],
                "access_token_encrypted": encrypt_secret(str(session_data.get("access_token"))),
                "session_payload": {
                    "user_name": session_data.get("user_name"),
                    "email": session_data.get("email"),
                    "login_time": session_data.get("login_time"),
                    "exchanges": session_data.get("exchanges"),
                    "fund_summary": account_profile,
                },
                "session_status": "CONNECTED",
                "expires_at": expires_at,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    await db.meta_accounts.update_one_async(
        {"_id": account["_id"]},
        {
            "$set": {
                "session_status": "CONNECTED",
                "session_expires_at": expires_at,
                "session_payload": {
                    "user_name": session_data.get("user_name"),
                    "email": session_data.get("email"),
                    "login_time": session_data.get("login_time"),
                    "exchanges": session_data.get("exchanges"),
                    "fund_summary": account_profile,
                },
            }
        },
    )
    if account["_id"] == user.get("selected_indian_account_id"):
        logger.info("Indian OTP verify ensuring live stream | user=%s account=%s", str(user["_id"]), account_db_id)
        await run_coro_in_thread(indian_market_stream_manager.ensure_account_stream, db, str(user["_id"]), account["_id"], live_state_hub.push_snapshot)
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    logger.info("Indian OTP verify completed | user=%s account=%s", str(user["_id"]), account_db_id)
    return {"ok": True, "message": "Indian broker session connected."}


@app.post("/market/select")
async def select_market(data: MarketSelectIn, user=Depends(get_current_user), db=Depends(get_db)):
    selected_market = _normalize_market_type(data.market_type)
    accounts = await db.meta_accounts.find_async({"user_id": user["_id"]})
    preferred_account_id = user.get(_market_selection_field(selected_market))
    next_account_id = _pick_active_account_id_for_market(accounts, preferred_account_id, selected_market)
    await persist_user_document_async(
        db,
        user["_id"],
        {"selected_market": selected_market, "selected_account_id": next_account_id},
    )
    if selected_market == MARKET_INTERNATIONAL and next_account_id:
        await _ensure_market_data_stream(db, str(user["_id"]))
        await run_coro_in_thread(indian_market_stream_manager.stop_user_stream, str(user["_id"]))
    else:
        await _ensure_market_data_stream(db, str(user["_id"]))
        if selected_market == MARKET_INDIAN and next_account_id:
            await run_coro_in_thread(indian_market_stream_manager.ensure_user_stream, db, str(user["_id"]), live_state_hub.push_snapshot)
        else:
            await run_coro_in_thread(indian_market_stream_manager.stop_user_stream, str(user["_id"]))
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True, "selected_market": selected_market, "selected_account_id": str(next_account_id) if next_account_id else None}


@app.patch("/accounts/{account_db_id}/risk", response_model=AccountOut)
async def update_account_risk(account_db_id: str, data: AccountRiskUpdateIn, user=Depends(get_current_user), db=Depends(get_db)):
    if data.risk_amount <= 0:
        raise HTTPException(status_code=400, detail="Risk amount must be a positive number")

    account = await _get_account_by_db_id_async(user["_id"], account_db_id, db)
    await db.meta_accounts.update_one_async({"_id": account["_id"]}, {"$set": {"risk_amount": data.risk_amount}})
    account["risk_amount"] = data.risk_amount
    return _to_account_out(account)


@app.get("/accounts/{account_db_id}/equity", response_model=AccountEquityOut)
async def get_account_equity(account_db_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    """Fetch live equity/balance from the local MT5 terminal for the selected account."""
    account = await _get_account_by_db_id_async(user["_id"], account_db_id, db)
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        raise HTTPException(status_code=400, detail="Live equity is available for international MT5 accounts only.")
    if not account.get("api_token") or not account.get("account_id"):
        raise HTTPException(status_code=400, detail="Account is missing MT5 credentials.")
    try:
        equity_profile = await metaapi_service.get_account_profile_with_equity(account["api_token"], account["account_id"])
    except LocalMT5Error as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to fetch equity from MT5: {exc}") from exc

    equity = float(equity_profile.get("equity") or 0)
    balance = float(equity_profile.get("balance") or 0)
    currency = str(equity_profile.get("currency") or account.get("account_currency") or "USD").upper()
    await db.meta_accounts.update_one_async(
        {"_id": account["_id"]},
        {
            "$set": {
                "equity_balance": equity,
                "balance": balance,
                "account_currency": currency,
                "last_equity_sync_at": datetime.utcnow(),
            }
        },
    )
    return AccountEquityOut(
        account_id=str(account["_id"]),
        equity=equity,
        balance=balance,
        currency=currency,
        equity_balance=equity,
    )


@app.get("/accounts/{account_db_id}/symbols/resolve", response_model=SymbolResolveOut)
async def resolve_account_symbol(account_db_id: str, symbol: str = Query(...), user=Depends(get_current_user), db=Depends(get_db)):
    account = await _get_account_by_db_id_async(user["_id"], account_db_id, db)
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        raise HTTPException(status_code=400, detail="Symbol resolution is available for international MT5 accounts.")
    try:
        broker_symbol = await _resolve_symbol_for_account(account, symbol)
        symbol_spec = await _symbol_spec_for_account(account, broker_symbol)
    except LocalMT5Error as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_symbol_resolve(symbol, broker_symbol, symbol_spec)


@app.patch("/accounts/{account_db_id}/symbol-aliases", response_model=AccountOut)
async def update_account_symbol_aliases(account_db_id: str, data: SymbolAliasesUpdateIn, user=Depends(get_current_user), db=Depends(get_db)):
    account = _get_account_by_db_id(user["_id"], account_db_id, db)
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        raise HTTPException(status_code=400, detail="Symbol aliases are available for international MT5 accounts.")
    available = await metaapi_service.get_symbols(account["api_token"], account["account_id"])
    original_by_normalized = {}
    for item in available:
        normalized = normalize_symbol(item)
        if normalized and normalized not in original_by_normalized:
            original_by_normalized[normalized] = str(item)
    available_set = set(original_by_normalized.keys())
    normalized_aliases = {}
    for key, value in (data.aliases or {}).items():
        canonical = normalize_symbol(key)
        broker_symbol = normalize_symbol(value)
        if not canonical or not broker_symbol:
            continue
        if broker_symbol not in available_set:
            raise HTTPException(status_code=400, detail=f"{broker_symbol} is not available on this broker account.")
        normalized_aliases[canonical] = original_by_normalized[broker_symbol]
    now = datetime.utcnow()
    await db.meta_accounts.update_one_async(
        {"_id": account["_id"]},
        {"$set": {"symbol_aliases": normalized_aliases, "symbol_aliases_updated_at": now}},
    )
    account["symbol_aliases"] = normalized_aliases
    account["symbol_aliases_updated_at"] = now
    await _ensure_market_data_stream(db, str(user["_id"]))
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return _to_account_out(account)


@app.get("/watchlist", response_model=List[WatchlistItemOut])
async def get_watchlist(user=Depends(get_current_user), db=Depends(get_db)):
    if _normalize_market_type(user.get("selected_market")) != "INTERNATIONAL":
        return []
    items = await db.watchlist_items.find_async({"user_id": user["_id"]})
    live_prices = market_data_stream.get_prices(str(user["_id"]))
    invalid_symbols = market_data_stream.get_invalid_watchlist_symbols(str(user["_id"]))
    return [
        WatchlistItemOut(
            symbol=item["symbol"],
            bid=lookup_live_price(live_prices, item["symbol"]).get("bid"),
            ask=lookup_live_price(live_prices, item["symbol"]).get("ask"),
            price=_mid_price(
                lookup_live_price(live_prices, item["symbol"]).get("bid"),
                lookup_live_price(live_prices, item["symbol"]).get("ask"),
            ),
            price_digits=lookup_live_price(live_prices, item["symbol"]).get("price_digits"),
        )
        for item in items
        if item["symbol"] not in invalid_symbols
    ]


@app.get("/market-price")
async def market_price(symbol: str, user=Depends(get_current_user), db=Depends(get_db)):
    account = _assert_account(user, db)
    broker_symbol = await _resolve_symbol_for_account(account, symbol)
    symbol_spec = await _symbol_spec_for_account(account, broker_symbol)
    price = await metaapi_service.get_symbol_price(account["api_token"], account["account_id"], broker_symbol)
    bid = normalize_price_to_symbol(price.get("bid"), symbol_spec) if price.get("bid") is not None else None
    ask = normalize_price_to_symbol(price.get("ask"), symbol_spec) if price.get("ask") is not None else None
    return {
        "symbol": broker_symbol,
        "requested_symbol": normalize_symbol(symbol),
        "display_symbol": display_symbol(symbol, broker_symbol),
        "bid": bid,
        "ask": ask,
        "price": _mid_price(bid, ask),
        "price_digits": digits_from_symbol_spec(symbol_spec),
    }


@app.get("/chart/candles")
async def chart_candles(
    account_id: str = Query(...),
    symbol: str = Query(...),
    timeframe: str = Query(...),
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    limit: int = Query(default=300, ge=1, le=5000),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        account_oid = parse_object_id(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account id")
    account = await db.meta_accounts.find_one_async({"_id": account_oid, "user_id": user["_id"]})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if str(account.get("market_type") or "INTERNATIONAL").upper() != "INTERNATIONAL":
        raise HTTPException(status_code=400, detail="Chart candles are available for international MT5 accounts.")
    normalized_symbol = str(symbol or "").upper().strip()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    try:
        broker_symbol = await _resolve_symbol_for_account(account, normalized_symbol)
        seconds = timeframe_seconds(timeframe)
        to_time = parse_chart_datetime(to, datetime.now(timezone.utc))
        from_time = parse_chart_datetime(from_, to_time - timedelta(seconds=seconds * limit))
        if from_time >= to_time:
            raise ValueError("from must be earlier than to")
        candles = await get_chart_candles(db, account, broker_symbol, timeframe, from_time, to_time, limit)
    except LocalMT5Error:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception(
            "Chart candle fetch failed | user=%s account=%s symbol=%s timeframe=%s",
            user["_id"],
            account_id,
            normalized_symbol,
            timeframe,
        )
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "symbol": broker_symbol,
        "requested_symbol": normalized_symbol,
        "display_symbol": display_symbol(normalized_symbol, broker_symbol),
        "timeframe": timeframe,
        "candles": candles,
    }


@app.get("/account/server-time")
async def account_server_time(user=Depends(get_current_user), db=Depends(get_db)):
    account = _assert_account(user, db)
    try:
        payload = await metaapi_service.get_server_time(account["api_token"], account["account_id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to fetch broker server time: {exc}")
    return _convert_server_time_payload_to_ist(payload)


@app.get("/instruments/suggest")
async def instrument_suggest(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=12, ge=1, le=50),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    account = _assert_account(user, db)
    symbols = await metaapi_service.get_symbols(account["api_token"], account["account_id"])
    return {"symbols": suggest_symbols(q, symbols, limit)}


@app.post("/watchlist", response_model=SymbolResolveOut)
async def add_watchlist(data: WatchlistUpsertIn, user=Depends(get_current_user), db=Depends(get_db)):
    if _normalize_market_type(user.get("selected_market")) != "INTERNATIONAL":
        raise HTTPException(status_code=400, detail="International watchlist is available only in International Market.")
    account = _assert_account(user, db)
    broker_symbol = await _resolve_symbol_for_account(account, str(data.symbol))
    await db.watchlist_items.update_one_async(
        {"user_id": user["_id"], "symbol": broker_symbol},
        {"$setOnInsert": {"user_id": user["_id"], "symbol": broker_symbol}},
        upsert=True,
    )
    await _ensure_market_data_stream(db, str(user["_id"]))
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    symbol_spec = await _symbol_spec_for_account(account, broker_symbol)
    return _serialize_symbol_resolve(data.symbol, broker_symbol, symbol_spec)


@app.delete("/watchlist")
async def remove_watchlist(symbol: str = Query(...), user=Depends(get_current_user), db=Depends(get_db)):
    if _normalize_market_type(user.get("selected_market")) != "INTERNATIONAL":
        raise HTTPException(status_code=400, detail="International watchlist is available only in International Market.")
    await db.watchlist_items.delete_one_async({"user_id": user["_id"], "symbol": symbol.upper()})
    await _ensure_market_data_stream(db, str(user["_id"]))
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True}


@app.get("/indian/watchlist")
async def get_indian_watchlist(user=Depends(get_current_user), db=Depends(get_db)):
    account = await db.meta_accounts.find_one_async({"_id": user.get("selected_indian_account_id"), "user_id": user["_id"]}) if user.get("selected_indian_account_id") else None
    if not account or _normalize_market_type(account.get("market_type")) != "INDIAN":
        return []
    items = await db[INDIAN_WATCHLIST_COLLECTION].find_async({"user_id": user["_id"], "account_id": account["_id"]})
    live_prices = indian_market_stream_manager.get_prices(str(user["_id"]))
    response = []
    for item in items:
        live = live_prices.get(item["symbol"], {})
        response.append(
            {
                "symbol": item["symbol"],
                "display_name": item.get("display_name") or item["symbol"],
                "exchange": item.get("exchange"),
                "instrument_token": item.get("instrument_token"),
                "price": live.get("price"),
                "change": live.get("change"),
                "time": live.get("time"),
            }
        )
    return response


@app.get("/indian/instruments/suggest")
async def suggest_indian_instruments(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=12, ge=1, le=25),
    kind: Optional[str] = Query(default=None),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    account = await db.meta_accounts.find_one_async({"_id": user.get("selected_indian_account_id"), "user_id": user["_id"]}) if user.get("selected_indian_account_id") else None
    if not account or _normalize_market_type(account.get("market_type")) != "INDIAN":
        return {"items": []}
    session_doc = await db[INDIAN_SESSION_COLLECTION].find_one_async({"user_id": user["_id"], "account_id": account["_id"]})
    access_token_encrypted = str((session_doc or {}).get("access_token_encrypted") or "").strip()
    if not access_token_encrypted:
        return {"items": []}
    try:
        access_token = decrypt_secret(access_token_encrypted)
    except Exception:
        return {"items": []}
    api_key = str((account.get("credentials") or {}).get("api_key") or "").strip()
    if not api_key:
        return {"items": []}
    catalog = await mstock_client.get_instrument_catalog(api_key, access_token)
    needle = q.strip().upper()
    query_tokens = [token for token in "".join(ch if ch.isalnum() else " " for ch in needle).split() if token]
    prefers_derivatives = any(token.isdigit() for token in query_tokens) or any(token in {"CE", "PE", "CALL", "PUT", "FUT"} for token in query_tokens)
    kind_normalized = str(kind or "").strip().lower()
    fno_underlyings = fno_equity_underlyings(catalog) if kind_normalized == "fno_equity" else set()
    matches = []
    for item in catalog:
        search_text = str(item.get("search_text") or "").upper()
        if not search_text:
            continue
        instrument_type = str(item.get("instrument_type") or "").upper()
        underlying = str(item.get("underlying") or "").upper()
        if kind_normalized == "fno_equity":
            if instrument_type != "EQUITY":
                continue
            symbol_key = str(item.get("symbol") or "").upper()
            if symbol_key not in fno_underlyings and underlying not in fno_underlyings:
                continue
        if query_tokens and not all(token in search_text for token in query_tokens):
            continue
        symbol = item["symbol"]
        display_name = str(item["display_name"]).upper()
        option_type = str(item.get("option_type") or "").upper()
        score = 0
        if symbol.startswith(needle):
            score += 140
        if display_name.startswith(needle):
            score += 120
        if underlying.startswith(query_tokens[0]) if query_tokens else False:
            score += 80
        score += sum(18 for token in query_tokens if token in symbol)
        score += sum(12 for token in query_tokens if token in display_name)
        if prefers_derivatives and instrument_type in {"OPTION", "FUTURE", "DERIVATIVE"}:
            score += 40
        if option_type in {"CE", "PE"}:
            score += 12
        if kind_normalized == "fno_equity" and instrument_type == "EQUITY":
            score += 50
        matches.append((score, item))
    matches.sort(
        key=lambda pair: (
            -pair[0],
            0 if str(pair[1].get("instrument_type") or "").upper() in {"OPTION", "FUTURE", "DERIVATIVE"} else 1,
            str(pair[1].get("expiry") or ""),
            str(pair[1]["symbol"]),
        )
    )
    ordered: list[dict] = []
    seen = set()
    for _, item in matches:
        key = (item["symbol"], item["exchange"], item["instrument_token"])
        if kind_normalized == "fno_equity":
            key = (str(item.get("underlying") or item["symbol"]).upper(), "EQUITY")
        if key in seen:
            continue
        seen.add(key)
        ordered.append({
            "symbol": item["symbol"],
            "display_name": item["display_name"],
            "exchange": item["exchange"],
            "instrument_token": item["instrument_token"],
            "instrument_type": item.get("instrument_type"),
            "option_type": item.get("option_type"),
            "strike": item.get("strike"),
            "expiry": item.get("expiry"),
            "lot_size": item.get("lot_size"),
            "underlying": item.get("underlying") or item["symbol"],
        })
        if len(ordered) >= limit:
            break
    return {"items": ordered}


def _indian_margin_product(instrument_type: Optional[str], exchange: str) -> str:
    instrument = str(instrument_type or "").upper()
    exch = str(exchange or "").upper()
    if instrument in {"OPTION", "FUTURE", "DERIVATIVE"} or exch in {"NFO", "BFO", "MCX"}:
        return "NRML"
    return "CNC"


async def _require_indian_session(user: dict, db) -> tuple[dict, str, str]:
    account = (
        await db.meta_accounts.find_one_async({"_id": user.get("selected_indian_account_id"), "user_id": user["_id"]})
        if user.get("selected_indian_account_id")
        else None
    )
    if not account or _normalize_market_type(account.get("market_type")) != "INDIAN":
        raise HTTPException(status_code=400, detail="Select a connected Indian broker account first.")
    session_doc = await db[INDIAN_SESSION_COLLECTION].find_one_async({"user_id": user["_id"], "account_id": account["_id"]})
    access_token_encrypted = str((session_doc or {}).get("access_token_encrypted") or "").strip()
    if not access_token_encrypted:
        raise HTTPException(status_code=400, detail="Connect the Indian broker session first.")
    try:
        access_token = decrypt_secret(access_token_encrypted)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to read the Indian broker session.") from exc
    api_key = str((account.get("credentials") or {}).get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Indian broker API key is missing.")
    return account, api_key, access_token


@app.post("/indian/watchlist")
async def add_indian_watchlist(data: WatchlistUpsertIn, user=Depends(get_current_user), db=Depends(get_db)):
    account = await db.meta_accounts.find_one_async({"_id": user.get("selected_indian_account_id"), "user_id": user["_id"]}) if user.get("selected_indian_account_id") else None
    if not account or _normalize_market_type(account.get("market_type")) != "INDIAN":
        raise HTTPException(status_code=400, detail="Indian watchlist is available only in Indian Market.")
    payload = data.symbol if isinstance(data.symbol, dict) else None
    symbol = str((payload or {}).get("symbol") or data.symbol or "").strip().upper()
    display_name = str((payload or {}).get("display_name") or symbol).strip() or symbol
    exchange = str((payload or {}).get("exchange") or "INDIA").strip().upper()
    instrument_token = (payload or {}).get("instrument_token")
    if not symbol or instrument_token in (None, ""):
        raise HTTPException(status_code=400, detail="Instrument symbol and token are required.")
    try:
        instrument_token = int(instrument_token)
    except Exception:
        raise HTTPException(status_code=400, detail="Instrument token is invalid.")
    await db[INDIAN_WATCHLIST_COLLECTION].update_one_async(
        {"user_id": user["_id"], "account_id": account["_id"], "symbol": symbol, "instrument_token": instrument_token},
        {
            "$setOnInsert": {
                "user_id": user["_id"],
                "account_id": account["_id"],
                "symbol": symbol,
                "display_name": display_name,
                "exchange": exchange,
                "instrument_token": instrument_token,
            }
        },
        upsert=True,
    )
    await run_coro_in_thread(indian_market_stream_manager.ensure_account_stream, db, str(user["_id"]), account["_id"], live_state_hub.push_snapshot)
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True}


@app.delete("/indian/watchlist")
async def remove_indian_watchlist(symbol: str = Query(...), instrument_token: Optional[int] = Query(default=None), user=Depends(get_current_user), db=Depends(get_db)):
    account = await db.meta_accounts.find_one_async({"_id": user.get("selected_indian_account_id"), "user_id": user["_id"]}) if user.get("selected_indian_account_id") else None
    if not account or _normalize_market_type(account.get("market_type")) != "INDIAN":
        raise HTTPException(status_code=400, detail="Indian watchlist is available only in Indian Market.")
    query = {"user_id": user["_id"], "account_id": account["_id"], "symbol": symbol.upper()}
    if instrument_token is not None:
        query["instrument_token"] = instrument_token
    await db[INDIAN_WATCHLIST_COLLECTION].delete_one_async(query)
    await run_coro_in_thread(indian_market_stream_manager.ensure_account_stream, db, str(user["_id"]), account["_id"], live_state_hub.push_snapshot)
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True}


@app.get("/risk-preview", response_model=RiskPreviewOut)
async def risk_preview(
    symbol: str,
    entry: float,
    stop_loss: float,
    target: Optional[float] = None,
    side: str = Query(default="BUY"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    account = _assert_account(user, db)
    broker_symbol = await _resolve_symbol_for_account(account, symbol)
    symbol_spec = await _symbol_spec_for_account(account, broker_symbol)
    resolved_entry = await _resolve_entry_for_order(account, broker_symbol, "LIMIT", side, entry)
    normalized_entry, normalized_stop, normalized_target = await _normalize_order_prices(
        account,
        broker_symbol,
        resolved_entry,
        stop_loss,
        target,
    )
    risk_ctx = await metaapi_service.get_risk_context(account["api_token"], account["account_id"], broker_symbol)
    qty = calc_quantity_from_live_pip_value(
        broker_symbol,
        account["risk_amount"],
        normalized_entry,
        normalized_stop,
        risk_ctx["pip_value_per_standard_lot"],
        volume_step=float(risk_ctx.get("volume_step") or 0.01),
        volume_min=float(risk_ctx.get("volume_min") or 0.01),
        volume_max=float(risk_ctx.get("volume_max") or 0),
        tick_size=float(risk_ctx.get("tick_size") or 0.0),
        tick_value=float(risk_ctx.get("tick_value") or 0.0),
        contract_size=float(risk_ctx.get("contract_size") or 0.0),
        account_currency=str(risk_ctx.get("account_currency") or account.get("account_currency") or "USD"),
    )
    if qty <= 0:
        qty = calc_quantity(broker_symbol, account["risk_amount"], normalized_entry, normalized_stop, account_currency=str(account.get("account_currency") or "USD"))
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Risk amount is too small for this symbol's minimum tradable volume.")
    sl_pips = calc_sl_pips(broker_symbol, normalized_entry, normalized_stop)
    rr = calc_rr(side.upper(), normalized_entry, normalized_stop, normalized_target)
    return RiskPreviewOut(
        symbol=broker_symbol,
        entry=normalized_entry,
        stop_loss=normalized_stop,
        risk_amount=account["risk_amount"],
        sl_pips=sl_pips,
        quantity=qty,
        rr_ratio=rr,
        price_digits=digits_from_symbol_spec(symbol_spec),
    )


@app.post("/orders/candle-detector/preview", response_model=CandleDetectorPreviewOut)
async def candle_detector_preview(data: CandleDetectorPreviewIn, user=Depends(get_current_user), db=Depends(get_db)):
    requested_symbol = str(data.symbol or "").upper().strip()
    if not requested_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required.")
    timeframe = _normalize_detector_timeframe(data.timeframe)
    candle_type = _normalize_detector_candle_type(data.candle_type)

    account = None
    if data.account_id:
        account = _get_account_by_db_id(user["_id"], data.account_id, db)
    else:
        account = _assert_account(user, db)
    if _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        raise HTTPException(status_code=400, detail="Candle detector is available for international MT5 accounts.")

    symbol = await _resolve_symbol_for_account(account, requested_symbol)
    symbol_spec = await metaapi_service.get_symbol_specification(account["api_token"], account["account_id"], symbol)
    point = float(symbol_spec.get("point") or 0.0)
    if point <= 0:
        raise HTTPException(status_code=400, detail="Symbol point size is unavailable.")

    candles = await metaapi_service.get_historical_candles(
        account["api_token"],
        account["account_id"],
        symbol,
        timeframe,
        limit=8,
    )
    completed = _completed_detector_candles(candles)
    scanned = [_serialize_detector_candle(candle) for candle in completed]
    if not completed:
        return CandleDetectorPreviewOut(
            symbol=symbol,
            timeframe=timeframe,
            candle_type=candle_type,
            found=False,
            message="No completed candles are available for this symbol/timeframe.",
            point=point,
            scanned_candles=scanned,
        )

    matched_candle = None
    for candle in reversed(completed):
        has_range = _has_min_candle_range(candle, symbol_spec)
        if candle_type == "HAMMER" and has_range and _is_hammer(candle):
            matched_candle = candle
            break
        if candle_type == "SHOOTING_STAR" and has_range and _is_shooting_star(candle):
            matched_candle = candle
            break

    if not matched_candle:
        return CandleDetectorPreviewOut(
            symbol=symbol,
            timeframe=timeframe,
            candle_type=candle_type,
            found=False,
            message="No matching completed candle found in the last 5 completed candles.",
            point=point,
            scanned_candles=scanned,
        )

    side = "BUY" if candle_type == "HAMMER" else "SELL"
    if side == "BUY":
        entry = matched_candle["high"] + point
        stop_loss = matched_candle["low"] - point
    else:
        entry = matched_candle["low"] - point
        stop_loss = matched_candle["high"] + point
    entry = _round_to_symbol_digits(entry, symbol_spec)
    stop_loss = _round_to_symbol_digits(stop_loss, symbol_spec)
    return CandleDetectorPreviewOut(
        symbol=symbol,
        timeframe=timeframe,
        candle_type=candle_type,
        found=True,
        side=side,
        order_type="SL",
        entry=entry,
        stop_loss=stop_loss,
        point=point,
        sl_pips=calc_sl_pips(symbol, entry, stop_loss),
        candle=_serialize_detector_candle(matched_candle, matched=True),
        scanned_candles=[_serialize_detector_candle(candle, candle["time"] == matched_candle["time"]) for candle in completed],
    )


async def _quick_order_feed_account(data: QuickOrderIn, user: dict, db) -> tuple[dict, str]:
    selected_accounts = []
    for target in data.targets:
        if target.risk_amount <= 0:
            raise HTTPException(status_code=400, detail="Risk amount must be a positive number for each selected account")
        selected_accounts.append((target, await _get_account_by_db_id_async(user["_id"], target.account_db_id, db)))
    account = await _resolve_execution_feed_account_async(user, db, selected_accounts or None)
    if selected_accounts:
        _validate_execution_account_selection([item for _, item in selected_accounts], account)
    if _normalize_market_type(account.get("market_type")) != MARKET_INTERNATIONAL:
        raise HTTPException(status_code=400, detail="Quick Order is available for international MT5 accounts only.")
    return account, await _resolve_symbol_for_account(account, data.symbol)


@app.post("/orders/quick/preview", response_model=QuickOrderPreviewOut)
async def quick_order_preview(data: QuickOrderIn, user=Depends(get_current_user), db=Depends(get_db)):
    account, symbol = await _quick_order_feed_account(data, user, db)
    try:
        return await build_quick_order_quote(account, symbol, data.timeframe, data.side)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/risk-preview/multi", response_model=MultiRiskPreviewOut)
async def risk_preview_multi(data: OrderCreateIn, user=Depends(get_current_user), db=Depends(get_db)):
    if not data.targets:
        raise HTTPException(status_code=400, detail="Select at least one account for copy trading")

    selected_accounts = []
    for target in data.targets:
        if target.risk_amount <= 0:
            raise HTTPException(status_code=400, detail="Risk amount must be a positive number for each selected account")
        selected_accounts.append((target, await _get_account_by_db_id_async(user["_id"], target.account_db_id, db)))

    validation_account = await _resolve_execution_feed_account_async(user, db, selected_accounts)
    _validate_execution_account_selection([account for _, account in selected_accounts], validation_account)
    broker_symbol = await _resolve_symbol_for_account(validation_account, data.symbol)
    symbol_spec = await _symbol_spec_for_account(validation_account, broker_symbol)
    validation_entry = await _resolve_entry_for_order(validation_account, broker_symbol, data.order_type, data.side, data.entry)
    normalized_entry, normalized_stop, normalized_target = await _normalize_order_prices(
        validation_account,
        broker_symbol,
        validation_entry,
        data.stop_loss,
        data.target,
    )
    await _validate_order_payload(
        validation_account,
        broker_symbol,
        data.order_type,
        data.side,
        normalized_entry,
        normalized_stop,
        normalized_target,
        data.cancel_at,
        conditional_order=bool(data.conditional_order) and str(data.order_type or "").upper() == "SL",
        trigger_price=data.trigger_price,
    )

    preview_targets = []
    for target, account in selected_accounts:
        account_symbol = await _resolve_symbol_for_account(account, data.symbol)
        resolved_entry = await _resolve_entry_for_order(account, account_symbol, data.order_type, data.side, data.entry)
        _, account_stop, _ = await _normalize_order_prices(
            account,
            account_symbol,
            resolved_entry,
            data.stop_loss,
            data.target,
        )
        try:
            risk_ctx = await metaapi_service.get_risk_context(account["api_token"], account["account_id"], account_symbol)
        except Exception:
            risk_ctx = None
        quantity = _build_order_quantity(account, account_symbol, resolved_entry, account_stop, target.risk_amount, risk_ctx)
        if quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Risk amount is too small for {account.get('account_name') or account.get('account_id')}.")
        preview_targets.append(
            RiskPreviewTargetOut(
                account_db_id=str(account["_id"]),
                account_name=_format_account_label(account),
                risk_amount=target.risk_amount,
                quantity=quantity,
            )
        )

    return MultiRiskPreviewOut(
        symbol=broker_symbol,
        entry=normalized_entry,
        stop_loss=normalized_stop,
        side=data.side.upper(),
        sl_pips=calc_sl_pips(broker_symbol, normalized_entry, normalized_stop),
        rr_ratio=calc_rr(data.side, normalized_entry, normalized_stop, normalized_target),
        price_digits=digits_from_symbol_spec(symbol_spec),
        targets=preview_targets,
    )


@app.get("/notifications", response_model=List[NotificationOut])
async def get_notifications(
    category: Optional[str] = None,
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    query = {"user_id": user["_id"]}
    if category:
        query["category"] = category
    if status:
        query["status"] = status.upper()
    if event_type:
        query["event_type"] = event_type.upper()
    if symbol:
        query["symbol"] = symbol.upper()

    docs = await db.notifications.find_async(query)
    docs.sort(key=lambda doc: doc.get("created_at") or datetime.min, reverse=True)
    docs = docs[:limit]
    return [_to_notification_out(doc) for doc in docs]


@app.get("/orders/active", response_model=List[OrderRowOut])
async def get_active_orders(user=Depends(get_current_user), db=Depends(get_db)):
    await _reconcile_market_data_orders(db, str(user["_id"]), force=True, include_all_accounts=True)
    await _sync_live_broker_positions_for_user(db, user)
    today_start_utc, today_end_utc = _today_utc_range()
    docs = await db.orders.find_async(
        {
            "user_id": user["_id"],
            "dry_run": {"$ne": True},
            "$or": [
                {"status": {"$in": ["WAITING_TRIGGER", "PLACEMENT_PENDING", "PENDING", DEFERRED_MARKET_OPEN_STATUS, "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]}},
                {
                    "created_at": {
                        "$gte": today_start_utc,
                        "$lt": today_end_utc,
                    },
                },
            ],
        }
    )
    docs.sort(key=lambda doc: doc.get("updated_at") or datetime.min, reverse=True)
    docs = docs[:100]
    docs = await market_data_stream.enrich_orders_pl(db, user["_id"], docs)
    return [_order_row_out(doc) for doc in docs]


@app.get("/broker/trade-history", response_model=PaginatedBrokerTradeHistoryOut)
async def get_broker_trade_history(
    account_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    trade_type: str = Query(default="all", alias="type"),
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    today: bool = Query(default=False),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    account_query = {"user_id": user["_id"]}
    if account_id:
        try:
            account_query["_id"] = ObjectId(account_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid account_id.")
    elif user.get("selected_account_id"):
        account_query["_id"] = user["selected_account_id"]

    account = await db.meta_accounts.find_one_async(account_query)
    if account and _normalize_market_type(account.get("market_type")) != "INTERNATIONAL":
        account = None
    if not account and user.get("selected_account_id") and not account_id:
        account = next(
            (item for item in await db.meta_accounts.find_async({"user_id": user["_id"]}) if _normalize_market_type(item.get("market_type")) == "INTERNATIONAL"),
            None,
        )
    if not account:
        raise HTTPException(status_code=404, detail="International MT5 account not found.")

    if today:
        today_start_utc, today_end_utc = _today_utc_range()
        from_time = today_start_utc.replace(tzinfo=timezone.utc)
        to_time = today_end_utc.replace(tzinfo=timezone.utc)
    else:
        to_time = _parse_iso_timestamp(to) if to else datetime.now(timezone.utc)
        from_time = _parse_iso_timestamp(from_) if from_ else to_time - timedelta(days=90)
        if not isinstance(to_time, datetime) or not isinstance(from_time, datetime):
            raise HTTPException(status_code=400, detail="Invalid from/to date.")
        if to_time.tzinfo is None:
            to_time = to_time.replace(tzinfo=timezone.utc)
        if from_time.tzinfo is None:
            from_time = from_time.replace(tzinfo=timezone.utc)
        if from_time > to_time:
            raise HTTPException(status_code=400, detail="from must be before to.")

    rows = await metaapi_service.get_trade_history(account["api_token"], account["account_id"], from_time, to_time)
    normalized_type = str(trade_type or "all").strip().upper()
    if normalized_type in {"BUY", "SELL"}:
        rows = [row for row in rows if str(row.get("type") or "").upper() == normalized_type]
    elif normalized_type == "RUNNING":
        rows = [row for row in rows if row.get("is_running")]
    elif normalized_type == "CLOSED":
        rows = [row for row in rows if not row.get("is_running")]

    account_name = _format_account_label(account)
    output_rows = [
        {
            **row,
            "account_id": str(account["_id"]),
            "account_name": account_name,
        }
        for row in rows
    ]
    total = len(output_rows)
    skip = (page - 1) * page_size
    return PaginatedBrokerTradeHistoryOut(
        records=output_rows[skip:skip + page_size],
        page=page,
        page_size=page_size,
        total=total,
    )


def _order_history_sort_key(doc: dict):
    created = doc.get("created_at") or datetime.min
    return (created, str(doc.get("_id") or ""))


def _order_history_cursor(doc: dict) -> str:
    created = doc.get("created_at") or datetime.min
    stamp = created.isoformat() if isinstance(created, datetime) else str(created)
    return f"{stamp}|{doc.get('_id')}"


@app.get("/orders/history", response_model=OrderHistoryPageOut)
async def get_order_history(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    today_start_utc, _ = _today_utc_range()
    docs = await db.orders.find_async({"user_id": user["_id"], "created_at": {"$lt": today_start_utc}})
    docs.sort(key=_order_history_sort_key, reverse=True)
    if cursor:
        cursor_id = cursor.split("|", 1)[-1]
        start = 0
        for index, doc in enumerate(docs):
            if str(doc.get("_id")) == cursor_id:
                start = index + 1
                break
        else:
            raise HTTPException(status_code=400, detail="History cursor is not valid.")
        docs = docs[start:]
    page = docs[:limit]
    next_cursor = _order_history_cursor(page[-1]) if len(docs) > limit and page else None
    return OrderHistoryPageOut(
        records=[_order_row_out(doc) for doc in page],
        next_cursor=next_cursor,
    )


@app.post("/trade-planner/preview", response_model=TradePlannerPlanOut)
async def preview_trade_plan(data: TradePlannerPlanCreateIn, user=Depends(get_current_user), db=Depends(get_db)):
    fallback_account = await _assert_account_async(user, db)
    selected_targets = await _normalize_trade_plan_input_targets_async(user, db, data.account_targets, fallback_account, data.risk_amount)
    reference_account = selected_targets[0]["account"]
    resolved_swing_type = await resolve_trade_plan_swing_type(reference_account, data.symbol, data.strong_swing_price, data.strong_swing_type)
    symbol_spec = await metaapi_service.get_symbol_specification(reference_account["api_token"], reference_account["account_id"], str(data.symbol or "").upper().strip())
    preview_doc = {
        "_id": "preview",
        "user_id": user["_id"],
        "account_id": selected_targets[0]["account_id"],
        "account_targets": [{"account_id": target["account_id"], "risk_amount": target["risk_amount"]} for target in selected_targets],
        "symbol": str(data.symbol or "").upper().strip(),
        "strong_swing_type": resolved_swing_type,
        "strong_swing_price": data.strong_swing_price,
        "reversal_points": data.reversal_points,
        "unmitigated_targets": data.unmitigated_targets,
        "target_allocations": data.target_allocations,
        "point_size": float(symbol_spec.get("point") or 0.0),
        "breakeven_at_t1": bool(data.breakeven_at_t1),
        "risk_amount": selected_targets[0]["risk_amount"],
        "auto_execution_enabled": bool(data.auto_execution_enabled),
        "status": "RUNNING" if data.auto_execution_enabled else "ACTIVE",
        "runtime_status": "WAITING_ENTRY_ZONE" if data.auto_execution_enabled else "IDLE",
        "linked_order_id": None,
        "linked_order_status": None,
        "last_execution_at": None,
        "breakeven_activated_at": None,
        "created_at": None,
        "updated_at": None,
    }
    derived = derive_trade_plan(
        reference_account,
        data.symbol,
        resolved_swing_type,
        data.strong_swing_price,
        data.reversal_points,
        data.unmitigated_targets,
        data.target_allocations,
        data.breakeven_at_t1,
        preview_doc["point_size"],
        selected_targets[0]["risk_amount"],
    )
    preview_doc["risk_amount"] = selected_targets[0]["risk_amount"]
    preview_doc["point_size"] = derived["point_size"]
    return _serialize_trade_plan(preview_doc, db)


@app.get("/trade-planner/plans", response_model=List[TradePlannerPlanOut])
async def list_trade_plans(symbol: Optional[str] = None, user=Depends(get_current_user), db=Depends(get_db)):
    query = {"user_id": user["_id"]}
    if symbol:
        query["symbol"] = str(symbol).upper().strip()
    docs = await db[TRADE_PLAN_COLLECTION].find_async(query)
    docs.sort(key=lambda doc: doc.get("updated_at") or datetime.min, reverse=True)
    return [_serialize_trade_plan(doc, db) for doc in docs]


@app.post("/trade-planner/plans", response_model=TradePlannerPlanOut)
async def create_trade_plan(data: TradePlannerPlanCreateIn, user=Depends(get_current_user), db=Depends(get_db)):
    fallback_account = await _assert_account_async(user, db)
    selected_targets = await _normalize_trade_plan_input_targets_async(user, db, data.account_targets, fallback_account, data.risk_amount)
    reference_account = selected_targets[0]["account"]
    broker_symbol = await _resolve_symbol_for_account(reference_account, data.symbol)
    resolved_swing_type = await resolve_trade_plan_swing_type(reference_account, broker_symbol, data.strong_swing_price, data.strong_swing_type)
    symbol_spec = await metaapi_service.get_symbol_specification(reference_account["api_token"], reference_account["account_id"], broker_symbol)
    derived = derive_trade_plan(
        reference_account,
        broker_symbol,
        resolved_swing_type,
        data.strong_swing_price,
        data.reversal_points,
        data.unmitigated_targets,
        data.target_allocations,
        data.breakeven_at_t1,
        float(symbol_spec.get("point") or 0.0),
        selected_targets[0]["risk_amount"],
    )
    now = datetime.utcnow()
    doc = {
        "user_id": user["_id"],
        "account_id": selected_targets[0]["account_id"],
        "account_targets": [{"account_id": target["account_id"], "risk_amount": target["risk_amount"]} for target in selected_targets],
        "symbol": derived["symbol"],
        "strong_swing_type": derived["strong_swing_type"],
        "strong_swing_price": derived["strong_swing_price"],
        "reversal_points": derived["reversal_points"],
        "unmitigated_targets": derived["unmitigated_targets"],
        "target_allocations": (
            [item["allocation_percent"] for item in derived["targets"][1:-1]]
            if bool(data.breakeven_at_t1)
            else [item["allocation_percent"] for item in derived["targets"][:-1]]
        ),
        "point_size": derived["point_size"],
        "breakeven_at_t1": bool(data.breakeven_at_t1),
        "risk_amount": selected_targets[0]["risk_amount"],
        "auto_execution_enabled": bool(data.auto_execution_enabled),
        "status": "RUNNING" if data.auto_execution_enabled else "ACTIVE",
        "runtime_status": "WAITING_ENTRY_ZONE" if data.auto_execution_enabled else "IDLE",
        "linked_order_id": None,
        "linked_order_status": None,
        "last_execution_at": None,
        "breakeven_activated_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[TRADE_PLAN_COLLECTION].insert_one_async(doc)
    asyncio.create_task(_refresh_user_streams(str(user["_id"]), include_indian=False))
    saved = await db[TRADE_PLAN_COLLECTION].find_one_async({"_id": result.inserted_id})
    return _serialize_trade_plan(saved, db)


@app.patch("/trade-planner/plans/{plan_id}", response_model=TradePlannerPlanOut)
async def update_trade_plan(plan_id: str, data: TradePlannerPlanUpdateIn, user=Depends(get_current_user), db=Depends(get_db)):
    fallback_account = await _assert_account_async(user, db)
    try:
        plan_oid = parse_object_id(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid trade plan id") from exc
    existing = await db[TRADE_PLAN_COLLECTION].find_one_async({"_id": plan_oid, "user_id": user["_id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Trade plan not found")

    order_map = _collect_trade_plan_orders(db, user["_id"], plan_oid)
    existing_order_statuses = [str(order.get("status") or "").upper() for order in order_map.values()]
    has_entry_order = _trade_plan_has_entry_order(existing_order_statuses)

    has_structural_edit = any(
        value is not None
        for value in [
            data.strong_swing_type,
            data.strong_swing_price,
            data.reversal_points,
            data.unmitigated_targets,
            data.target_allocations,
            data.breakeven_at_t1,
            data.account_targets,
        ]
    )
    has_target_only_edit = any(
        value is not None
        for value in [
            data.unmitigated_targets,
            data.target_allocations,
            data.breakeven_at_t1,
        ]
    )
    has_non_target_structural_edit = any(
        value is not None
        for value in [
            data.strong_swing_type,
            data.strong_swing_price,
            data.reversal_points,
            data.account_targets,
        ]
    )
    if has_entry_order and has_non_target_structural_edit:
        raise HTTPException(status_code=409, detail="Once the entry order is placed, only target prices and target strategy can be edited")

    existing_targets = [
        OrderTargetIn(account_db_id=str(target["account_id"]), risk_amount=float(target["risk_amount"]))
        for target in _normalize_trade_plan_account_targets(existing)
    ]
    next_input_targets = existing_targets if data.account_targets is None else data.account_targets
    selected_targets = await _normalize_trade_plan_input_targets_async(user, db, next_input_targets, fallback_account, data.risk_amount if data.account_targets is not None else existing.get("risk_amount"))
    reference_account = selected_targets[0]["account"]
    merged = {
        "symbol": existing.get("symbol"),
        "strong_swing_type": data.strong_swing_type or existing.get("strong_swing_type"),
        "strong_swing_price": data.strong_swing_price if data.strong_swing_price is not None else existing.get("strong_swing_price"),
        "reversal_points": data.reversal_points if data.reversal_points is not None else existing.get("reversal_points") or [],
        "unmitigated_targets": data.unmitigated_targets if data.unmitigated_targets is not None else existing.get("unmitigated_targets") or [],
        "target_allocations": data.target_allocations if data.target_allocations is not None else existing.get("target_allocations") or [],
        "breakeven_at_t1": bool(existing.get("breakeven_at_t1", False)) if data.breakeven_at_t1 is None else bool(data.breakeven_at_t1),
        "point_size": existing.get("point_size"),
        "risk_amount": selected_targets[0]["risk_amount"],
    }
    resolved_swing_type = await resolve_trade_plan_swing_type(reference_account, merged["symbol"], merged["strong_swing_price"], merged["strong_swing_type"])
    symbol_spec = await metaapi_service.get_symbol_specification(reference_account["api_token"], reference_account["account_id"], str(merged["symbol"] or "").upper().strip())
    derived = derive_trade_plan(
        reference_account,
        merged["symbol"],
        resolved_swing_type,
        merged["strong_swing_price"],
        merged["reversal_points"],
        merged["unmitigated_targets"],
        merged["target_allocations"],
        merged["breakeven_at_t1"],
        float(symbol_spec.get("point") or merged.get("point_size") or 0.0),
        merged["risk_amount"],
    )

    next_auto = bool(existing.get("auto_execution_enabled", False)) if data.auto_execution_enabled is None else bool(data.auto_execution_enabled)
    explicit_status = str(data.status or "").upper().strip() if data.status else ""
    if explicit_status == "INACTIVE":
        next_status = "INACTIVE"
        next_auto = False
    elif next_auto:
        next_status = "RUNNING"
    else:
        next_status = "ACTIVE"

    if not next_auto:
        await _cancel_trade_plan_pending_orders(db, user, plan_oid, "Trade plan execution deactivated")

    await db[TRADE_PLAN_COLLECTION].update_one_async(
        {"_id": plan_oid},
        {
            "$set": {
                "account_id": selected_targets[0]["account_id"],
                "account_targets": [{"account_id": target["account_id"], "risk_amount": target["risk_amount"]} for target in selected_targets],
                "strong_swing_type": derived["strong_swing_type"],
                "strong_swing_price": derived["strong_swing_price"],
                "reversal_points": derived["reversal_points"],
                "unmitigated_targets": derived["unmitigated_targets"],
                "target_allocations": (
                    [item["allocation_percent"] for item in derived["targets"][1:-1]]
                    if bool(merged["breakeven_at_t1"])
                    else [item["allocation_percent"] for item in derived["targets"][:-1]]
                ),
                "point_size": derived["point_size"],
                "breakeven_at_t1": bool(merged["breakeven_at_t1"]),
                "risk_amount": selected_targets[0]["risk_amount"],
                "auto_execution_enabled": next_auto,
                "status": next_status,
                "runtime_status": (
                    "INACTIVE"
                    if next_status == "INACTIVE"
                    else (existing.get("runtime_status") or "WAITING_ENTRY_ZONE") if next_auto
                    else "IDLE"
                ),
                "breakeven_activated_at": None if has_structural_edit or not bool(merged["breakeven_at_t1"]) or not next_auto else existing.get("breakeven_activated_at"),
                "updated_at": datetime.utcnow(),
            }
        },
    )
    if has_entry_order and has_target_only_edit:
        await _sync_trade_plan_targets_with_orders(
            db,
            user["_id"],
            plan_oid,
            selected_targets,
            {
                "symbol": merged["symbol"],
                "strong_swing_type": derived["strong_swing_type"],
                "strong_swing_price": derived["strong_swing_price"],
                "reversal_points": derived["reversal_points"],
                "unmitigated_targets": derived["unmitigated_targets"],
                "target_allocations": (
                    [item["allocation_percent"] for item in derived["targets"][1:-1]]
                    if bool(merged["breakeven_at_t1"])
                    else [item["allocation_percent"] for item in derived["targets"][:-1]]
                ),
                "breakeven_at_t1": bool(merged["breakeven_at_t1"]),
                "point_size": derived["point_size"],
            },
        )
    asyncio.create_task(_refresh_user_streams(str(user["_id"]), include_indian=False))
    saved = await db[TRADE_PLAN_COLLECTION].find_one_async({"_id": plan_oid})
    return _serialize_trade_plan(saved, db)


@app.post("/trade-planner/plans/{plan_id}/deactivate", response_model=TradePlannerPlanOut)
async def deactivate_trade_plan(plan_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    await _assert_account_async(user, db)
    try:
        plan_oid = parse_object_id(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid trade plan id") from exc
    existing = await db[TRADE_PLAN_COLLECTION].find_one_async({"_id": plan_oid, "user_id": user["_id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Trade plan not found")
    await _cancel_trade_plan_pending_orders(db, user, plan_oid, "Trade plan deactivated")
    await db[TRADE_PLAN_COLLECTION].update_one_async(
        {"_id": plan_oid},
        {"$set": {"status": "INACTIVE", "runtime_status": "INACTIVE", "auto_execution_enabled": False, "updated_at": datetime.utcnow()}},
    )
    asyncio.create_task(_refresh_user_streams(str(user["_id"]), include_indian=False))
    saved = await db[TRADE_PLAN_COLLECTION].find_one_async({"_id": plan_oid})
    return _serialize_trade_plan(saved, db)


@app.delete("/trade-planner/plans/{plan_id}")
async def delete_trade_plan(plan_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    await _assert_account_async(user, db)
    try:
        plan_oid = parse_object_id(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid trade plan id") from exc
    existing = await db[TRADE_PLAN_COLLECTION].find_one_async({"_id": plan_oid, "user_id": user["_id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Trade plan not found")
    await _cancel_trade_plan_pending_orders(db, user, plan_oid, "Trade plan deleted")
    await db[TRADE_PLAN_COLLECTION].delete_one_async({"_id": plan_oid})
    asyncio.create_task(_refresh_user_streams(str(user["_id"]), include_indian=False))
    return {"ok": True}


@app.post("/orders", response_model=OrderPlacementOut)
async def create_order(data: OrderCreateIn, user=Depends(get_current_user), db=Depends(get_db)):
    selected_targets = []
    if data.targets:
        seen_account_ids = set()
        for target in data.targets:
            if target.risk_amount <= 0:
                raise HTTPException(status_code=400, detail="Risk amount must be a positive number for each selected account")
            if target.account_db_id in seen_account_ids:
                continue
            seen_account_ids.add(target.account_db_id)
            selected_targets.append((target, await _get_account_by_db_id_async(user["_id"], target.account_db_id, db)))

    validation_account = await _resolve_execution_feed_account_async(user, db, selected_targets or None)
    if not selected_targets:
        selected_targets = [(None, validation_account)]
    _validate_execution_account_selection([account for _, account in selected_targets], validation_account)

    broker_symbol = await _resolve_symbol_for_account(validation_account, data.symbol)
    validation_entry = await _resolve_entry_for_order(validation_account, broker_symbol, data.order_type, data.side, data.entry)
    is_conditional = bool(data.conditional_order) and str(data.order_type or "").upper() == "SL"
    if is_conditional and data.trigger_price is None:
        raise HTTPException(status_code=400, detail="Trigger price is required for conditional SL orders")
    await _validate_order_payload(
        validation_account,
        broker_symbol,
        data.order_type,
        data.side,
        validation_entry,
        data.stop_loss,
        data.target,
        data.cancel_at,
        conditional_order=is_conditional,
        trigger_price=data.trigger_price if is_conditional else None,
    )
    copy_group_id = str(ObjectId())
    placement_results = []

    for target, account in selected_targets:
        broker_info = _broker_info_from_account(account)
        risk_amount = target.risk_amount if target else account["risk_amount"]
        account_symbol = await _resolve_symbol_for_account(account, data.symbol)
        resolved_entry = await _resolve_entry_for_order(account, account_symbol, data.order_type, data.side, data.entry)
        await _validate_order_payload(
            account,
            account_symbol,
            data.order_type,
            data.side,
            resolved_entry,
            data.stop_loss,
            data.target,
            data.cancel_at,
            conditional_order=is_conditional,
            trigger_price=data.trigger_price if is_conditional else None,
        )
        resolved_entry, normalized_stop_loss, normalized_target = await _normalize_order_prices(
            account,
            account_symbol,
            resolved_entry,
            data.stop_loss,
            data.target,
        )

        try:
            risk_ctx = await metaapi_service.get_risk_context(account["api_token"], account["account_id"], account_symbol)
        except Exception:
            risk_ctx = None
        quantity = _build_order_quantity(
            account,
            account_symbol,
            resolved_entry,
            normalized_stop_loss,
            risk_amount,
            risk_ctx,
        )
        if quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Risk amount is too small for {broker_info.get('account_name', 'broker account')}.")

        order_doc = {
            "user_id": user["_id"],
            "account_id": account["_id"],
            "symbol": account_symbol,
            "order_type": data.order_type.upper(),
            "side": data.side.upper(),
            "entry": resolved_entry,
            "stop_loss": normalized_stop_loss,
            "target": normalized_target,
            "comment": (data.comment or "").strip() or None,
            "quantity": quantity,
            "risk_amount": risk_amount,
            "sl_pips": calc_sl_pips(account_symbol, resolved_entry, normalized_stop_loss),
            "rr_ratio": calc_rr(data.side, resolved_entry, normalized_stop_loss, normalized_target),
            "meta_order_id": None,
            "status": "WAITING_TRIGGER" if is_conditional else "PLACEMENT_PENDING",
            "failure_reason": None,
            "copy_group_id": copy_group_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "opened_at": datetime.utcnow(),
            "closed_at": None,
            "last_broker_seen_at": None,
            "is_open_position": False,
            "position_quantity": None,
            "realized_pl": None,
            "unrealized_pl": None,
            "broker_info": broker_info,
            "manual_context": _build_manual_context(data, data.order_type),
        }
        insert_result = await db.orders.insert_one_async(order_doc)
        order_doc["_id"] = insert_result.inserted_id
        _save_event(
            db,
            user["_id"],
            order_doc["_id"],
            "ORDER_CREATE_REQUESTED",
            order_doc["status"],
            append_order_log_prices(
                f"{order_doc['symbol']} order create requested for {broker_info.get('account_name', 'broker account')}",
                order_doc,
            ),
            merge_order_log_payload(
                {
                    **data.model_dump(),
                    "risk_amount": risk_amount,
                    "quantity": quantity,
                },
                source=order_doc,
            ),
            notify_user=False,
            symbol=order_doc["symbol"],
            broker_info=broker_info,
        )

        if is_conditional:
            trigger_value = float(data.trigger_price)
            _save_event(
                db,
                user["_id"],
                order_doc["_id"],
                "CONDITIONAL_ORDER_ARMED",
                "WAITING_TRIGGER",
                append_order_log_prices(
                    f"{order_doc['symbol']} conditional SL armed; waiting for price to cross {trigger_value}",
                    order_doc,
                ),
                merge_order_log_payload(
                    {"trigger_price": trigger_value, "entry": order_doc["entry"], "side": order_doc["side"]},
                    source=order_doc,
                ),
                symbol=order_doc["symbol"],
                broker_info=broker_info,
            )
            placement_results.append(
                OrderPlacementResultOut(
                    account_db_id=str(account["_id"]),
                    account_name=_format_account_label(account),
                    order_id=str(order_doc["_id"]),
                    status="WAITING_TRIGGER",
                    quantity=quantity,
                )
            )
            continue

        try:
            placement = await place_pending_order_with_limit_fallback(
                metaapi_service,
                account["api_token"],
                account["account_id"],
                {
                    "symbol": order_doc["symbol"],
                    "order_type": order_doc["order_type"],
                    "side": order_doc["side"],
                    "entry": order_doc["entry"],
                    "stop_loss": order_doc["stop_loss"],
                    "target": order_doc["target"],
                    "quantity": order_doc["quantity"],
                },
            )
        except Exception as exc:
            failure_reason = str(exc)
            if is_market_closed_error(exc):
                context = dict(order_doc.get("manual_context") or {})
                context["market_closed_offer"] = True
                await db.orders.update_one_async(
                    {"_id": order_doc["_id"]},
                    {
                        "$set": {
                            "status": "PLACEMENT_PENDING",
                            "failure_reason": failure_reason,
                            "manual_context": context,
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                _save_event(
                    db,
                    user["_id"],
                    order_doc["_id"],
                    "ORDER_MARKET_CLOSED_OFFER",
                    "PLACEMENT_PENDING",
                    append_order_log_prices(
                        f"{order_doc['symbol']} market closed; awaiting defer confirmation on "
                        f"{broker_info.get('account_name', 'broker account')}: {failure_reason}",
                        order_doc,
                    ),
                    merge_order_log_payload({"error": failure_reason, "market_closed": True}, source=order_doc),
                    symbol=order_doc["symbol"],
                    broker_info=broker_info,
                    failure_reason=failure_reason,
                )
                placement_results.append(
                    OrderPlacementResultOut(
                        account_db_id=str(account["_id"]),
                        account_name=_format_account_label(account),
                        order_id=str(order_doc["_id"]),
                        status="PLACEMENT_PENDING",
                        quantity=quantity,
                        failure_reason=failure_reason,
                        market_closed=True,
                    )
                )
                continue

            await db.orders.update_one_async(
                {"_id": order_doc["_id"]},
                {"$set": {"status": "FAILED", "failure_reason": failure_reason, "updated_at": datetime.utcnow()}},
            )
            failure_message = append_order_log_prices(
                f"{order_doc['symbol']} order placement failed on {broker_info.get('account_name', 'broker account')}: {failure_reason}",
                order_doc,
            )
            _save_event(
                db,
                user["_id"],
                order_doc["_id"],
                "ORDER_PLACEMENT_FAILED",
                "FAILED",
                failure_message,
                merge_order_log_payload({"error": failure_reason}, source=order_doc),
                symbol=order_doc["symbol"],
                broker_info=broker_info,
                failure_reason=failure_reason,
            )
            placement_results.append(
                OrderPlacementResultOut(
                    account_db_id=str(account["_id"]),
                    account_name=_format_account_label(account),
                    order_id=str(order_doc["_id"]),
                    status="FAILED",
                    quantity=quantity,
                    failure_reason=failure_reason,
                )
            )
            continue

        result = placement["result"]
        fallback = placement.get("fallback")
        meta_order_id = str(result.get("orderId", ""))
        order_doc.update(
            {
                "meta_order_id": meta_order_id,
                "status": "PENDING",
                "failure_reason": None,
                **order_placement_fallback_fields(fallback),
            }
        )
        await db.orders.update_one_async(
            {"_id": order_doc["_id"]},
            {
                "$set": {
                    "meta_order_id": meta_order_id,
                    "status": "PENDING",
                    "failure_reason": None,
                    "updated_at": datetime.utcnow(),
                    **order_placement_fallback_fields(fallback),
                }
            },
        )
        if fallback:
            fallback_message = sl_limit_fallback_event_message(
                str(order_doc["symbol"] or ""),
                str(fallback.get("sl_placement_error") or ""),
                order_doc,
            )
            _save_event(
                db,
                user["_id"],
                order_doc["_id"],
                "ORDER_SL_FALLBACK_TO_LIMIT",
                "PENDING",
                fallback_message,
                merge_order_log_payload(fallback, source=order_doc),
                symbol=order_doc["symbol"],
                broker_info=broker_info,
                placement_fallback_reason=str(fallback.get("fallback_reason") or ""),
            )
        placed_label = str(placement.get("order_type") or order_doc["order_type"] or "").upper()
        _save_event(
            db,
            user["_id"],
            order_doc["_id"],
            "ORDER_PLACED",
            "PENDING",
            append_order_log_prices(
                f"{order_doc['symbol']} {placed_label} pending order placed on {broker_info.get('account_name', 'broker account')}"
                + (". SL Invalid price — placed LIMIT at same entry/SL/target instead." if fallback else ""),
                order_doc,
            ),
            merge_order_log_payload(result, source=order_doc),
            symbol=order_doc["symbol"],
            broker_info=broker_info,
            placement_fallback_reason=str(fallback.get("fallback_reason") or "") if fallback else None,
        )
        placement_results.append(
            OrderPlacementResultOut(
                account_db_id=str(account["_id"]),
                account_name=_format_account_label(account),
                order_id=str(order_doc["_id"]),
                meta_order_id=meta_order_id,
                status="PENDING",
                quantity=quantity,
            )
        )

    placement_out = OrderPlacementOut(
        copy_group_id=copy_group_id,
        success_count=sum(
            1
            for result in placement_results
            if result.status not in {"FAILED"} and not result.market_closed
        ),
        failed_count=sum(1 for result in placement_results if result.status == "FAILED"),
        results=placement_results,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return placement_out


@app.post("/orders/quick", response_model=OrderPlacementOut)
async def create_quick_order(data: QuickOrderIn, user=Depends(get_current_user), db=Depends(get_db)):
    """Place an SL order from the last completed candle. The desk sends edited prices via POST /orders."""
    if str(data.side or "").upper() not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="Direction must be BUY or SELL.")
    account, symbol = await _quick_order_feed_account(data, user, db)
    try:
        quote = await build_quick_order_quote(account, symbol, data.timeframe, data.side)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await create_order(
        OrderCreateIn(
            symbol=data.symbol,
            order_type="SL",
            side=str(data.side).upper(),
            entry=quote["entry"],
            stop_loss=quote["stop_loss"],
            comment=data.comment,
            targets=data.targets,
            retryable_order=False,
            automatic_trade_management=data.automatic_trade_management,
        ),
        user,
        db,
    )


def _event_failure_reason(doc: dict) -> Optional[str]:
    stored = doc.get("failure_reason")
    if stored:
        return str(stored)
    payload_json = doc.get("payload_json")
    if not payload_json:
        return None
    try:
        payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("error", "failure_reason", "reason"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


@app.get("/orders/{order_id}/events", response_model=List[OrderEventOut])
async def get_order_events(order_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        order_oid = parse_object_id(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order id")

    order = await db.orders.find_one_async({"_id": order_oid, "user_id": user["_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    related_ids = {order_oid}
    manual_context = order.get("manual_context") or {}
    parent_order_id = manual_context.get("parent_order_id")
    if parent_order_id:
        try:
            related_ids.add(parse_object_id(str(parent_order_id)))
        except ValueError:
            pass
    child_orders = await db.orders.find_async(
        {"user_id": user["_id"], "manual_context.parent_order_id": str(order_oid)},
        {"_id": 1},
    )
    for child in child_orders:
        related_ids.add(child["_id"])

    docs = await db.order_events.find_async({"order_id": {"$in": list(related_ids)}})
    docs.sort(key=lambda doc: str(doc.get("event_ts_ist") or ""))
    return [
        OrderEventOut(
            id=str(doc.get("_id")),
            order_id=str(doc.get("order_id")),
            event_type=str(doc.get("event_type") or ""),
            status=str(doc.get("status") or ""),
            message=str(doc.get("message") or ""),
            event_ts_ist=str(doc.get("event_ts_ist") or ""),
            payload_json=doc.get("payload_json"),
            failure_reason=_event_failure_reason(doc),
            broker_info=doc.get("broker_info") or {},
        )
        for doc in docs
    ]


@app.post("/orders/{order_id}/defer-market-open")
async def defer_order_market_open(order_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        order_oid = parse_object_id(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order id")
    order = await db.orders.find_one_async({"_id": order_oid, "user_id": user["_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status = str(order.get("status") or "").upper()
    context = dict(order.get("manual_context") or {})
    market_closed_offer = bool(context.get("market_closed_offer"))
    if status != "PLACEMENT_PENDING" or not market_closed_offer:
        if status == DEFERRED_MARKET_OPEN_STATUS:
            return {
                "ok": True,
                "order_id": str(order_oid),
                "status": DEFERRED_MARKET_OPEN_STATUS,
                "place_after": order.get("place_after"),
            }
        raise HTTPException(status_code=400, detail="Order is not awaiting market-closed defer confirmation")

    place_after = next_monday_0430_ist()
    context["market_closed_offer"] = False
    context["deferred_market_open"] = True
    place_after_naive = place_after.replace(tzinfo=None) if place_after.tzinfo else place_after
    updates = {
        "status": DEFERRED_MARKET_OPEN_STATUS,
        "place_after": place_after_naive,
        "failure_reason": None,
        "manual_context": context,
        "updated_at": datetime.utcnow(),
    }
    await db.orders.update_one_async({"_id": order_oid}, {"$set": updates})
    account = _get_order_account(order, user["_id"], db)
    broker_info = _broker_info_from_account(account)
    from zoneinfo import ZoneInfo

    place_after_ist = place_after.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M IST")
    _save_event(
        db,
        user["_id"],
        order_oid,
        "ORDER_DEFERRED_MARKET_OPEN",
        DEFERRED_MARKET_OPEN_STATUS,
        append_order_log_prices(
            f"{order.get('symbol')} deferred until Monday 04:30 IST ({place_after_ist})",
            {**order, **updates},
        ),
        merge_order_log_payload({"place_after": place_after.isoformat()}, source={**order, **updates}),
        symbol=order.get("symbol"),
        broker_info=order.get("broker_info") or broker_info,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {
        "ok": True,
        "order_id": str(order_oid),
        "status": DEFERRED_MARKET_OPEN_STATUS,
        "place_after": place_after.isoformat().replace("+00:00", "Z"),
    }


@app.post("/orders/{order_id}/decline-defer")
async def decline_order_market_open_defer(order_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        order_oid = parse_object_id(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order id")
    order = await db.orders.find_one_async({"_id": order_oid, "user_id": user["_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status = str(order.get("status") or "").upper()
    context = dict(order.get("manual_context") or {})
    if status != "PLACEMENT_PENDING" or not context.get("market_closed_offer"):
        if status == "FAILED":
            return {"ok": True, "order_id": str(order_oid), "status": "FAILED"}
        raise HTTPException(status_code=400, detail="Order is not awaiting market-closed defer confirmation")

    failure_reason = str(order.get("failure_reason") or "Market closed; defer declined")
    context["market_closed_offer"] = False
    await db.orders.update_one_async(
        {"_id": order_oid},
        {
            "$set": {
                "status": "FAILED",
                "failure_reason": failure_reason,
                "manual_context": context,
                "updated_at": datetime.utcnow(),
                "closed_at": datetime.utcnow(),
            }
        },
    )
    account = _get_order_account(order, user["_id"], db)
    broker_info = _broker_info_from_account(account)
    _save_event(
        db,
        user["_id"],
        order_oid,
        "ORDER_DEFER_DECLINED",
        "FAILED",
        append_order_log_prices(
            f"{order.get('symbol')} market-closed defer declined; order marked failed",
            order,
        ),
        merge_order_log_payload({"error": failure_reason}, source=order),
        symbol=order.get("symbol"),
        broker_info=order.get("broker_info") or broker_info,
        failure_reason=failure_reason,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True, "order_id": str(order_oid), "status": "FAILED"}


async def _modify_open_position_sltp(db, user: dict, order: dict, order_oid, data: OrderModifyIn):
    """Update stop and target on an open position. Quantity stays at the filled size."""
    existing_qty = round(float(order.get("position_quantity") or order.get("quantity") or 0), 2)
    if data.quantity is not None and round(float(data.quantity), 2) != existing_qty:
        raise HTTPException(status_code=400, detail="Quantity stays fixed while the position is open.")

    side = str(order.get("side") or "").upper()
    entry = float(order.get("entry") or 0)
    stop_loss = float(data.stop_loss)
    target = data.target
    if stop_loss <= 0:
        raise HTTPException(status_code=400, detail="Stop loss must be a positive number")
    if side == "BUY" and stop_loss >= entry:
        raise HTTPException(status_code=400, detail="For BUY, stop loss must be below entry")
    if side == "SELL" and stop_loss <= entry:
        raise HTTPException(status_code=400, detail="For SELL, stop loss must be above entry")
    if target is not None:
        if side == "BUY" and float(target) <= entry:
            raise HTTPException(status_code=400, detail="For BUY, target must be above entry")
        if side == "SELL" and float(target) >= entry:
            raise HTTPException(status_code=400, detail="For SELL, target must be below entry")

    position_id = str(order.get("meta_position_id") or "").strip()
    if not position_id:
        raise HTTPException(status_code=400, detail="Open position ticket is missing.")

    account = _get_order_account(order, user["_id"], db)
    broker_info = _broker_info_from_account(account)
    _, new_stop, new_target = await _normalize_order_prices(
        account,
        order["symbol"],
        entry,
        stop_loss,
        target,
    )
    await metaapi_service.modify_position(
        account["api_token"],
        account["account_id"],
        position_id,
        stop_loss=new_stop,
        take_profit=float(new_target) if new_target is not None else 0,
    )
    update_fields = {
        "stop_loss": new_stop,
        "target": new_target,
        "updated_at": datetime.utcnow(),
    }
    await db.orders.update_one_async({"_id": order_oid}, {"$set": update_fields})
    updated_order = {**order, **update_fields}
    _save_event(
        db,
        user["_id"],
        order_oid,
        "ORDER_MODIFIED",
        str(order.get("status") or ""),
        append_order_log_prices(f"{order['symbol']} open position stop and target updated", updated_order),
        merge_order_log_payload(source=updated_order),
        symbol=order["symbol"],
        broker_info=broker_info,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True}


@app.post("/orders/{order_id}/modify")
async def modify_order(order_id: str, data: OrderModifyIn, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        order_oid = parse_object_id(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order id")
    order = await db.orders.find_one_async({"_id": order_oid, "user_id": user["_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status = str(order.get("status") or "").upper()
    if status in {"FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"}:
        return await _modify_open_position_sltp(db, user, order, order_oid, data)
    if status not in {"PENDING", "PLACEMENT_PENDING", "WAITING_TRIGGER", DEFERRED_MARKET_OPEN_STATUS}:
        raise HTTPException(status_code=400, detail="Only pending orders or open positions can be modified")

    account = _get_order_account(order, user["_id"], db)
    broker_info = _broker_info_from_account(account)
    context = dict(order.get("manual_context") or {})
    if status == DEFERRED_MARKET_OPEN_STATUS or (
        status == "PLACEMENT_PENDING" and context.get("market_closed_offer")
    ):
        return await _modify_deferred_local_order(db, user, account, order, order_oid, data, broker_info)

    is_conditional_waiting = status == "WAITING_TRIGGER" or bool(context.get("conditional_order"))
    trigger_for_validation = data.trigger_price if data.trigger_price is not None else context.get("trigger_price")
    await _validate_order_payload(
        account,
        order["symbol"],
        order["order_type"],
        order["side"],
        data.entry,
        data.stop_loss,
        data.target,
        conditional_order=is_conditional_waiting and str(order.get("order_type") or "").upper() == "SL",
        trigger_price=float(trigger_for_validation) if trigger_for_validation is not None else None,
    )
    new_entry, new_stop, new_target = await _normalize_order_prices(
        account,
        order["symbol"],
        float(data.entry),
        float(data.stop_loss),
        data.target,
    )

    if data.quantity is None:
        raise HTTPException(status_code=400, detail="quantity is required")
    old_qty = round(float(order.get("quantity") or 0), 2)
    new_qty = round(float(data.quantity), 2)
    old_entry = float(order.get("entry") or 0)
    old_stop = float(order.get("stop_loss") or 0)
    old_target = order.get("target")
    old_target_value = float(old_target) if old_target is not None else None
    new_target_value = float(new_target) if new_target is not None else None

    qty_changed = old_qty != new_qty
    entry_changed = abs(old_entry - new_entry) > 1e-9
    stop_changed = abs(old_stop - new_stop) > 1e-9
    target_changed = (old_target_value is None) != (new_target_value is None) or (
        old_target_value is not None and new_target_value is not None and abs(old_target_value - new_target_value) > 1e-9
    )
    old_trigger = context.get("trigger_price")
    old_trigger_value = float(old_trigger) if old_trigger is not None else None
    new_trigger_value = float(data.trigger_price) if data.trigger_price is not None else old_trigger_value
    trigger_changed = status == "WAITING_TRIGGER" and (
        (old_trigger_value is None) != (new_trigger_value is None)
        or (
            old_trigger_value is not None
            and new_trigger_value is not None
            and abs(old_trigger_value - new_trigger_value) > 1e-9
        )
    )
    if not any([qty_changed, entry_changed, stop_changed, target_changed, trigger_changed]):
        raise HTTPException(status_code=400, detail="No changes to apply")

    update_fields = {
        "entry": new_entry,
        "stop_loss": new_stop,
        "target": new_target,
        "quantity": new_qty,
        "sl_pips": calc_sl_pips(order["symbol"], new_entry, new_stop),
        "rr_ratio": calc_rr(order["side"], new_entry, new_stop, new_target),
        "updated_at": datetime.utcnow(),
        "broker_info": broker_info,
    }
    if status == "WAITING_TRIGGER" and new_trigger_value is not None:
        update_fields["manual_context.trigger_price"] = new_trigger_value

    meta_order_id = order.get("meta_order_id")
    if status == "WAITING_TRIGGER":
        await db.orders.update_one_async({"_id": order_oid}, {"$set": update_fields})
        updated = await db.orders.find_one_async({"_id": order_oid})
        _save_event(
            db,
            user["_id"],
            order_oid,
            "ORDER_MODIFIED",
            "WAITING_TRIGGER",
            append_order_log_prices(
                f"{order['symbol']} conditional order updated while waiting for trigger",
                updated or order,
            ),
            merge_order_log_payload(update_fields, source=updated or order),
            symbol=order["symbol"],
            broker_info=broker_info,
        )
        await live_state_hub.push_snapshot(db, str(user["_id"]))
        return {"ok": True}

    if not meta_order_id:
        await db.orders.update_one_async({"_id": order_oid}, {"$set": {**update_fields, "status": "PLACEMENT_PENDING"}})
        updated = await db.orders.find_one_async({"_id": order_oid})
        placement = await place_pending_order_with_limit_fallback(
            metaapi_service,
            account["api_token"],
            account["account_id"],
            {
                "symbol": updated["symbol"],
                "order_type": updated["order_type"],
                "side": updated["side"],
                "entry": updated["entry"],
                "stop_loss": updated["stop_loss"],
                "target": updated.get("target"),
                "quantity": updated["quantity"],
            },
        )
        result = placement["result"]
        fallback = placement.get("fallback")
        updated = {**updated, **order_placement_fallback_fields(fallback)}
        await db.orders.update_one_async(
            {"_id": order_oid},
            {
                "$set": {
                    "meta_order_id": str(result.get("orderId", "")),
                    "status": "PENDING",
                    "updated_at": datetime.utcnow(),
                    **order_placement_fallback_fields(fallback),
                }
            },
        )
        if fallback:
            _save_event(
                db,
                user["_id"],
                order_oid,
                "ORDER_SL_FALLBACK_TO_LIMIT",
                "PENDING",
                sl_limit_fallback_event_message(str(updated["symbol"] or ""), str(fallback.get("sl_placement_error") or ""), updated),
                merge_order_log_payload(fallback, source=updated),
                symbol=updated["symbol"],
                broker_info=broker_info,
                placement_fallback_reason=str(fallback.get("fallback_reason") or ""),
            )
        _save_event(
            db,
            user["_id"],
            order_oid,
            "ORDER_UPDATED",
            "PENDING",
            append_order_log_prices(
                f"{updated['symbol']} pending order updated before broker placement"
                + (". SL Invalid price — placed LIMIT at same entry/SL/target instead." if fallback else ""),
                updated,
            ),
            merge_order_log_payload(result, source=updated),
            symbol=updated["symbol"],
            broker_info=broker_info,
            placement_fallback_reason=str(fallback.get("fallback_reason") or "") if fallback else None,
        )
        await live_state_hub.push_snapshot(db, str(user["_id"]))
        return {"ok": True}

    if qty_changed:
        await metaapi_service.cancel_order(account["api_token"], account["account_id"], meta_order_id)
        _save_event(
            db,
            user["_id"],
            order_oid,
            "ORDER_CANCELLED_FOR_MODIFY",
            "CANCELLED",
            append_order_log_prices(f"{order['symbol']} pending order cancelled for quantity change", order),
            merge_order_log_payload(source=order),
            symbol=order["symbol"],
            broker_info=order.get("broker_info") or broker_info,
        )
        await db.orders.update_one_async({"_id": order_oid}, {"$set": {**update_fields, "status": "PLACEMENT_PENDING"}})
        updated = await db.orders.find_one_async({"_id": order_oid})
        placement = await place_pending_order_with_limit_fallback(
            metaapi_service,
            account["api_token"],
            account["account_id"],
            {
                "symbol": updated["symbol"],
                "order_type": updated["order_type"],
                "side": updated["side"],
                "entry": updated["entry"],
                "stop_loss": updated["stop_loss"],
                "target": updated.get("target"),
                "quantity": updated["quantity"],
            },
        )
        result = placement["result"]
        fallback = placement.get("fallback")
        updated = {**updated, **order_placement_fallback_fields(fallback)}
        await db.orders.update_one_async(
            {"_id": order_oid},
            {
                "$set": {
                    "meta_order_id": str(result.get("orderId", "")),
                    "status": "PENDING",
                    "updated_at": datetime.utcnow(),
                    **order_placement_fallback_fields(fallback),
                }
            },
        )
        if fallback:
            _save_event(
                db,
                user["_id"],
                order_oid,
                "ORDER_SL_FALLBACK_TO_LIMIT",
                "PENDING",
                sl_limit_fallback_event_message(str(updated["symbol"] or ""), str(fallback.get("sl_placement_error") or ""), updated),
                merge_order_log_payload(fallback, source=updated),
                symbol=updated["symbol"],
                broker_info=broker_info,
                placement_fallback_reason=str(fallback.get("fallback_reason") or ""),
            )
        _save_event(
            db,
            user["_id"],
            order_oid,
            "ORDER_REPLACED",
            "PENDING",
            append_order_log_prices(
                f"{updated['symbol']} order re-created after quantity change"
                + (". SL Invalid price — placed LIMIT at same entry/SL/target instead." if fallback else ""),
                updated,
            ),
            merge_order_log_payload(result, source=updated),
            result,
            symbol=updated["symbol"],
            broker_info=broker_info,
            placement_fallback_reason=str(fallback.get("fallback_reason") or "") if fallback else None,
        )
        await live_state_hub.push_snapshot(db, str(user["_id"]))
        return {"ok": True}

    await metaapi_service.modify_pending_order(
        account["api_token"],
        account["account_id"],
        meta_order_id,
        price=new_entry if str(order.get("order_type") or "").upper() != "MARKET" else None,
        stop_loss=new_stop,
        target=new_target_value if new_target_value is not None else 0,
    )
    await db.orders.update_one_async({"_id": order_oid}, {"$set": update_fields})
    updated_order = {**order, **update_fields}
    _save_event(
        db,
        user["_id"],
        order_oid,
        "ORDER_MODIFIED",
        status,
        append_order_log_prices(f"{order['symbol']} pending order updated at broker", updated_order),
        merge_order_log_payload(source=updated_order),
        symbol=order["symbol"],
        broker_info=broker_info,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True}


@app.post("/orders/{order_id}/cancel")
async def cancel_pending_order(order_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        order_oid = parse_object_id(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order id")

    order = await db.orders.find_one_async({"_id": order_oid, "user_id": user["_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status = str(order.get("status") or "").upper()
    if status not in {"PENDING", "PLACEMENT_PENDING", "WAITING_TRIGGER", DEFERRED_MARKET_OPEN_STATUS}:
        raise HTTPException(status_code=400, detail="Only pending orders can be cancelled")

    account = _get_order_account(order, user["_id"], db)
    broker_info = _broker_info_from_account(account)

    if status == DEFERRED_MARKET_OPEN_STATUS or (
        status == "PLACEMENT_PENDING"
        and bool((order.get("manual_context") or {}).get("market_closed_offer"))
    ):
        await db.orders.update_one_async(
            {"_id": order_oid},
            {
                "$set": {
                    "status": "CANCELLED",
                    "updated_at": datetime.utcnow(),
                    "closed_at": datetime.utcnow(),
                    "broker_info": broker_info,
                    "failure_reason": "Deferred pending order cancelled before broker placement",
                }
            },
        )
        _save_event(
            db,
            user["_id"],
            order_oid,
            "ORDER_CANCELLED",
            "CANCELLED",
            append_order_log_prices(
                f"{order['symbol']} deferred pending order cancelled before broker placement",
                order,
            ),
            merge_order_log_payload(source=order),
            symbol=order["symbol"],
            broker_info=order.get("broker_info") or broker_info,
        )
        await live_state_hub.push_snapshot(db, str(user["_id"]))
        return {"ok": True, "cancelled_deferred": True}

    if status == "WAITING_TRIGGER" or not order.get("meta_order_id"):
        if status == "WAITING_TRIGGER" or (
            bool((order.get("manual_context") or {}).get("conditional_order")) and not order.get("meta_order_id")
        ):
            await db.orders.update_one_async(
                {"_id": order_oid},
                {
                    "$set": {
                        "status": "CANCELLED",
                        "updated_at": datetime.utcnow(),
                        "closed_at": datetime.utcnow(),
                        "broker_info": broker_info,
                        "failure_reason": "Conditional order cancelled before trigger",
                    }
                },
            )
            _save_event(
                db,
                user["_id"],
                order_oid,
                "CONDITIONAL_ORDER_CANCELLED",
                "CANCELLED",
                append_order_log_prices(
                    f"{order['symbol']} conditional order cancelled before trigger",
                    order,
                ),
                merge_order_log_payload(source=order),
                symbol=order["symbol"],
                broker_info=order.get("broker_info") or broker_info,
            )
            await live_state_hub.push_snapshot(db, str(user["_id"]))
            return {"ok": True, "cancelled_before_trigger": True}
        raise HTTPException(status_code=400, detail="No broker order found to cancel")

    try:
        result = await metaapi_service.cancel_order(account["api_token"], account["account_id"], order["meta_order_id"])
    except Exception as exc:
        failure_reason = str(exc)
        if _is_missing_broker_order_error(exc):
            await db.orders.update_one_async(
                {"_id": order_oid},
                {
                    "$set": {
                        "status": "CANCELLED",
                        "updated_at": datetime.utcnow(),
                        "closed_at": datetime.utcnow(),
                        "broker_info": broker_info,
                        "comment": "Order already cancelled at broker end",
                    }
                },
            )
            _save_event(
                db,
                user["_id"],
                order_oid,
                "ORDER_ALREADY_CANCELLED",
                "CANCELLED",
                f"{order['symbol']} was already cancelled on {broker_info.get('account_name', 'broker account')}",
                {"reason": failure_reason},
                symbol=order["symbol"],
                broker_info=order.get("broker_info") or broker_info,
            )
            await live_state_hub.push_snapshot(db, str(user["_id"]))
            return {"ok": True, "already_cancelled": True}
        _save_event(
            db,
            user["_id"],
            order_oid,
            "ORDER_CANCEL_FAILED",
            order.get("status", "PENDING"),
            append_order_log_prices(
                f"{order['symbol']} cancel failed on {broker_info.get('account_name', 'broker account')}: {failure_reason}",
                order,
            ),
            merge_order_log_payload({"error": failure_reason}, source=order),
            symbol=order["symbol"],
            broker_info=order.get("broker_info") or broker_info,
            failure_reason=failure_reason,
        )
        await live_state_hub.push_snapshot(db, str(user["_id"]))
        raise HTTPException(status_code=502, detail=f"MetaApi cancel failed: {failure_reason}")

    await db.orders.update_one_async(
        {"_id": order_oid},
        {"$set": {"status": "CANCELLED", "updated_at": datetime.utcnow(), "closed_at": datetime.utcnow(), "broker_info": broker_info}},
    )
    _save_event(
        db,
        user["_id"],
        order_oid,
        "ORDER_CANCELLED",
        "CANCELLED",
        append_order_log_prices(
            f"{order['symbol']} pending order cancelled on {broker_info.get('account_name', 'broker account')}",
            order,
        ),
        merge_order_log_payload(result, source=order),
        symbol=order["symbol"],
        broker_info=order.get("broker_info") or broker_info,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True}


@app.post("/orders/{order_id}/close")
async def close_position(order_id: str, data: ClosePositionIn, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        order_oid = parse_object_id(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order id")

    order = await db.orders.find_one_async({"_id": order_oid, "user_id": user["_id"]})
    position_id = (order or {}).get("meta_position_id") or (order or {}).get("meta_order_id")
    if not order or not position_id:
        raise HTTPException(status_code=404, detail="Position source order not found")
    account = _get_order_account(order, user["_id"], db)
    broker_info = _broker_info_from_account(account)

    close_type = str(data.order_type or "MARKET").strip().upper()
    if close_type not in {"MARKET", "LIMIT"}:
        raise HTTPException(status_code=400, detail="order_type must be MARKET or LIMIT")
    if close_type == "LIMIT" and (data.price is None or float(data.price) <= 0):
        raise HTTPException(status_code=400, detail="Limit close requires a positive price")

    if close_type == "LIMIT":
        result = await metaapi_service.close_position_limit(
            account["api_token"],
            account["account_id"],
            str(position_id),
            data.quantity,
            float(data.price),
        )
        await db.orders.update_one_async(
            {"_id": order_oid},
            {
                "$set": {
                    "manual_context.pending_close_order_id": result.get("orderId"),
                    "manual_context.pending_close_price": float(data.price),
                    "manual_context.pending_close_quantity": float(data.quantity),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        _save_event(
            db,
            user["_id"],
            order_oid,
            "POSITION_LIMIT_CLOSE_PLACED",
            str(order.get("status") or ""),
            f"{order['symbol']} limit close placed at {data.price} qty {data.quantity}",
            result,
            symbol=order["symbol"],
            broker_info=order.get("broker_info") or broker_info,
        )
        await live_state_hub.push_snapshot(db, str(user["_id"]))
        return {"ok": True, "order_type": "LIMIT", "broker_order_id": result.get("orderId")}

    result = await metaapi_service.close_position(account["api_token"], account["account_id"], str(position_id), data.quantity)
    status = "PARTIALLY_CLOSED" if data.quantity < (order.get("position_quantity") or order["quantity"]) else "CLOSED"
    update_doc = {"status": status, "updated_at": datetime.utcnow()}
    if status == "CLOSED":
        update_doc["closed_at"] = datetime.utcnow()
        update_doc["position_quantity"] = 0.0
        update_doc["unrealized_pl"] = None
        merged_order = {**order, **update_doc}
        realized = None
        try:
            resolved = await metaapi_service.resolve_closed_orders_realized_pl(
                account["api_token"],
                account["account_id"],
                [merged_order],
            )
            realized = resolved.get(str(order["_id"]))
        except Exception:
            logger.exception("Failed to resolve closed position P/L after close request | order=%s position=%s", order_oid, position_id)
        if realized is None:
            realized = merge_realized_pl_on_close(order)
        if realized is None and order.get("last_broker_profit") is not None:
            try:
                realized = round(float(order["last_broker_profit"]), 2)
            except (TypeError, ValueError):
                realized = None
        if realized is not None:
            update_doc["realized_pl"] = realized
    elif status == "PARTIALLY_CLOSED":
        try:
            resolved = await metaapi_service.resolve_active_orders_booked_pl(
                account["api_token"],
                account["account_id"],
                [{**order, **update_doc}],
            )
            booked = resolved.get(str(order["_id"]))
            if booked is not None:
                update_doc["realized_pl"] = booked
        except Exception:
            logger.exception("Failed to resolve partial booked P/L after close request | order=%s position=%s", order_oid, position_id)
    await db.orders.update_one_async({"_id": order_oid}, {"$set": update_doc})
    _save_event(
        db,
        user["_id"],
        order_oid,
        "POSITION_CLOSE_REQUESTED",
        status,
        f"{order['symbol']} close request sent",
        result,
        symbol=order["symbol"],
        broker_info=order.get("broker_info") or broker_info,
    )
    await live_state_hub.push_snapshot(db, str(user["_id"]))
    return {"ok": True, "order_type": "MARKET"}


@app.post("/hooks/metaapi")
async def metaapi_hook(
    request: Request,
    x_metaapi_signature: Optional[str] = Header(default=None),
    db=Depends(get_db),
):
    raw_body = await request.body()
    if settings.metaapi_webhook_secret:
        if not x_metaapi_signature:
            raise HTTPException(status_code=401, detail="Missing webhook signature")
        expected = hmac.new(settings.metaapi_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, x_metaapi_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    meta_order_id = str(payload.get("orderId", ""))
    if not meta_order_id:
        return {"ok": True}

    order = await db.orders.find_one_async({"meta_order_id": meta_order_id})
    if not order:
        return {"ok": True}

    status = str(payload.get("status", "UNKNOWN")).upper()
    position_volume = payload.get("positionVolume", payload.get("volume"))
    position_id = payload.get("positionId")
    is_open_position = status in {"FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"}
    if status in {"CLOSED", "CANCELLED", "FAILED"} and position_volume in (None, ""):
        position_volume = 0.0
    update_doc = {
        "status": status,
        "is_open_position": is_open_position,
        "position_quantity": position_volume if position_volume is not None else order.get("position_quantity"),
        "unrealized_pl": payload.get("unrealizedProfit", order.get("unrealized_pl")),
        "realized_pl": payload.get("realizedProfit", order.get("realized_pl")),
        "meta_position_id": str(position_id) if position_id is not None else order.get("meta_position_id"),
        "opened_at": order.get("opened_at") or datetime.utcnow(),
        "closed_at": datetime.utcnow() if status in {"CLOSED", "CANCELLED", "FAILED"} else order.get("closed_at"),
        "last_broker_seen_at": datetime.utcnow(),
        "broker_missing_since": None,
        "updated_at": datetime.utcnow(),
    }
    if status == "CLOSED":
        update_doc["unrealized_pl"] = None
        if update_doc.get("realized_pl") is None:
            update_doc["realized_pl"] = merge_realized_pl_on_close(order)
    await db.orders.update_one_async(
        {"_id": order["_id"]},
        {
            "$set": update_doc,
        },
    )
    _save_event(
        db,
        order["user_id"],
        order["_id"],
        "METAAPI_STATUS_UPDATE",
        status,
        f"{order['symbol']} status updated to {status}",
        payload,
        symbol=order.get("symbol"),
        broker_info=order.get("broker_info"),
    )
    await live_state_hub.push_snapshot(db, str(order["user_id"]))
    return {"ok": True}


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket, token: Optional[str] = Query(default=None), db=Depends(get_db)):
    async def _safe_close(code: int):
        try:
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=code)
        except (RuntimeError, WebSocketDisconnect):
            # Socket is already closing/closed.
            pass

    try:
        await websocket.accept()
    except RuntimeError:
        return

    if not token:
        try:
            await websocket.send_json({"error": "Missing token"})
        except (RuntimeError, WebSocketDisconnect):
            pass
        await _safe_close(1008)
        return

    try:
        payload = decode_platform_token(token)
        user_id = payload["sub"]
        session_id = str(payload.get("sid") or "")
        parse_object_id(user_id)
    except (JWTError, KeyError, ValueError, TypeError):
        try:
            await websocket.send_json({"error": "Invalid token"})
        except (RuntimeError, WebSocketDisconnect):
            pass
        await _safe_close(1008)
        return

    user = await resolve_user_for_session_async(db, parse_object_id(user_id), session_id)
    if not user or not is_session_active(user, session_id):
        try:
            await websocket.send_json({"error": "Session expired"})
        except (RuntimeError, WebSocketDisconnect):
            pass
        await _safe_close(1008)
        return

    try:
        await live_state_hub.connect(user_id, session_id, websocket)
        await live_state_hub.push_snapshot(db, user_id)
        asyncio.create_task(_refresh_user_streams(user_id, include_indian=True))
        await run_live_socket_loop(websocket, user_id, db, live_state_hub.push_snapshot)
    except (WebSocketDisconnect, RuntimeError):
        logger.info("WebSocket /ws/live disconnected | user_id=%s", user_id)
        await live_state_hub.disconnect(user_id, websocket)
    except Exception:
        logger.exception("WebSocket /ws/live failed for user_id=%s", user_id)
        await live_state_hub.disconnect(user_id, websocket)
        await _safe_close(1011)


@app.websocket("/ws/mt5/ticks")
async def ws_mt5_ticks(websocket: WebSocket, secret: Optional[str] = Query(default=None), account_id: Optional[str] = Query(default=None), db=Depends(get_db)):
    async def _safe_close(code: int):
        try:
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=code)
        except (RuntimeError, WebSocketDisconnect):
            pass

    try:
        await websocket.accept()
    except RuntimeError:
        return

    ingest_account = None
    if secret:
        account_query = {
            "$and": [
                {"$or": [{"market_type": "INTERNATIONAL"}, {"market_type": {"$exists": False}}, {"market_type": None}]},
            ],
            "mt5_tick_ingest_secret": str(secret),
        }
        if account_id:
            account_query["$and"].append(
                {"$or": [{"account_id": str(account_id)}, {"_id": ObjectId(account_id)}]}
                if ObjectId.is_valid(str(account_id))
                else {"account_id": str(account_id)}
            )
        ingest_account = await db.meta_accounts.find_one_async(account_query)
    if not ingest_account or not hmac.compare_digest(str(secret or ""), str(ingest_account.get("mt5_tick_ingest_secret") or "")):
        try:
            await websocket.send_json({"error": "Invalid MT5 account tick ingest secret"})
        except (RuntimeError, WebSocketDisconnect):
            pass
        await _safe_close(1008)
        return

    ingest_account_db_id = str(ingest_account.get("_id") or "")
    ingest_account_login = str(ingest_account.get("account_id") or "")
    logger.info("MT5 tick ingest websocket connected | account_id=%s", ingest_account_login)
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json({"ok": False, "error": "Invalid JSON"})
                continue
            ticks = payload.get("ticks") if isinstance(payload, dict) else None
            if ticks is None:
                ticks = [payload]
            if not isinstance(ticks, list):
                await websocket.send_json({"ok": False, "error": "ticks must be a list"})
                continue
            routed = await _handle_market_data_ticks(db, ingest_account_db_id, ticks)
            await websocket.send_json({"ok": True, "received": len(ticks), "routed": routed})
    except (WebSocketDisconnect, RuntimeError):
        logger.info("MT5 tick ingest websocket disconnected | account_id=%s", ingest_account_login)
    except Exception:
        logger.exception("WebSocket /ws/mt5/ticks failed | account_id=%s", ingest_account_login)
        await _safe_close(1011)
