from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from datetime import datetime


class RegisterIn(BaseModel):
    username: str
    password: str
    full_name: str
    email: Optional[str] = None


class LoginIn(BaseModel):
    username: str
    password: str


class SsoExchangeIn(BaseModel):
    code: str


class SsoHandoffOut(BaseModel):
    code: str
    expires_in: int = 60


class PlatformAuditLogOut(BaseModel):
    id: str
    ts: datetime
    app: str
    level: str
    category: str
    event: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PaginatedPlatformAuditLogsOut(BaseModel):
    records: List[PlatformAuditLogOut]
    total: int
    page: int
    page_size: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    full_name: str
    username: str
    is_admin: bool = False


class MetaAccountIn(BaseModel):
    market_type: str = "INTERNATIONAL"
    broker_type: str = "METAAPI"
    account_name: str
    account_id: Optional[str] = None
    api_token: Optional[str] = None
    credentials: Dict[str, Any] = Field(default_factory=dict)
    risk_amount: float


class SelectAccountIn(BaseModel):
    account_db_id: str


class MarketSelectIn(BaseModel):
    market_type: str


class IndianOtpVerifyIn(BaseModel):
    otp: str


class AccountRiskUpdateIn(BaseModel):
    risk_amount: float


class SymbolAliasesUpdateIn(BaseModel):
    aliases: Dict[str, str] = Field(default_factory=dict)


class SymbolResolveOut(BaseModel):
    requested: str
    canonical: Optional[str] = None
    broker_symbol: str
    display_symbol: str
    price_digits: int = 5
    point: float = 0.0
    tick_size: float = 0.0


class WatchlistUpsertIn(BaseModel):
    symbol: Any


class IndianStrategyLegIn(BaseModel):
    symbol: str
    exchange: str
    instrument_token: Optional[int] = None
    instrument_type: Optional[str] = None
    option_type: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[str] = None
    lot_size: Optional[int] = None
    action: str = "BUY"
    lots: int = 1
    price: float = 0


class IndianStrategyPreviewIn(BaseModel):
    legs: List[IndianStrategyLegIn] = Field(default_factory=list)


class IndianPeCycleBacktestIn(BaseModel):
    underlying: str
    from_date: str
    to_date: str


class IndianPeCycleBacktestListOut(BaseModel):
    results: List[dict] = Field(default_factory=list)


class OrderTargetIn(BaseModel):
    account_db_id: str
    risk_amount: float


class OrderCreateIn(BaseModel):
    symbol: str
    order_type: str
    side: str
    entry: float
    stop_loss: float
    target: Optional[float] = None
    comment: Optional[str] = None
    quantity: Optional[float] = None
    targets: List[OrderTargetIn] = Field(default_factory=list)
    retryable_order: bool = True
    automatic_trade_management: bool = True
    cancel_at: Optional[float] = None
    conditional_order: bool = False
    trigger_price: Optional[float] = None


class QuickOrderIn(BaseModel):
    symbol: str
    timeframe: str = "M1"
    side: str
    comment: Optional[str] = None
    targets: List[OrderTargetIn] = Field(default_factory=list)
    automatic_trade_management: bool = True


class QuickOrderPreviewOut(BaseModel):
    symbol: str
    timeframe: str
    side: str
    entry: float
    stop_loss: float
    candle_high: float
    candle_low: float
    candle_time: datetime
    tick_size: float
    price_digits: int = 5


class OrderEventOut(BaseModel):
    id: str
    order_id: str
    event_type: str
    status: str
    message: str
    event_ts_ist: str
    payload_json: Optional[str] = None
    failure_reason: Optional[str] = None
    broker_info: Optional[Dict[str, str]] = None


class OrderModifyIn(BaseModel):
    entry: float
    stop_loss: float
    target: Optional[float] = None
    quantity: float
    trigger_price: Optional[float] = None


class CandleDetectorPreviewIn(BaseModel):
    symbol: str
    timeframe: str = "M1"
    candle_type: str
    account_id: Optional[str] = None


class CandleDetectorCandleOut(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    matched: bool = False


class CandleDetectorPreviewOut(BaseModel):
    symbol: str
    timeframe: str
    candle_type: str
    found: bool
    message: Optional[str] = None
    side: Optional[str] = None
    order_type: str = "SL"
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    point: Optional[float] = None
    sl_pips: Optional[float] = None
    candle: Optional[CandleDetectorCandleOut] = None
    scanned_candles: List[CandleDetectorCandleOut] = Field(default_factory=list)


class ClosePositionIn(BaseModel):
    quantity: float
    order_type: str = "MARKET"
    price: Optional[float] = None


class OrderDefaultsIn(BaseModel):
    automatic_trade_management: Optional[bool] = None
    retryable_order: Optional[bool] = None


class OrderDefaultsOut(BaseModel):
    automatic_trade_management: bool = True
    retryable_order: bool = True


class RiskPreviewOut(BaseModel):
    symbol: str
    entry: float
    stop_loss: float
    risk_amount: float
    sl_pips: float
    quantity: float
    rr_ratio: Optional[float] = None
    price_digits: int = 5


class RiskPreviewTargetOut(BaseModel):
    account_db_id: str
    account_name: str
    risk_amount: float
    quantity: float


class MultiRiskPreviewOut(BaseModel):
    symbol: str
    entry: float
    stop_loss: float
    side: str
    sl_pips: float
    rr_ratio: Optional[float] = None
    price_digits: int = 5
    targets: List[RiskPreviewTargetOut]


class TradePlannerPlanCreateIn(BaseModel):
    symbol: str
    strong_swing_type: Optional[str] = None
    strong_swing_price: float
    reversal_points: List[float] = Field(default_factory=list)
    unmitigated_targets: List[float] = Field(default_factory=list)
    target_allocations: List[Optional[float]] = Field(default_factory=list)
    breakeven_at_t1: bool = False
    risk_amount: Optional[float] = None
    account_targets: List[OrderTargetIn] = Field(default_factory=list)
    auto_execution_enabled: bool = True


class TradePlannerPlanUpdateIn(BaseModel):
    strong_swing_type: Optional[str] = None
    strong_swing_price: Optional[float] = None
    reversal_points: Optional[List[float]] = None
    unmitigated_targets: Optional[List[float]] = None
    target_allocations: Optional[List[Optional[float]]] = None
    breakeven_at_t1: Optional[bool] = None
    risk_amount: Optional[float] = None
    account_targets: Optional[List[OrderTargetIn]] = None
    auto_execution_enabled: Optional[bool] = None
    status: Optional[str] = None


class TradePlannerTargetOut(BaseModel):
    target_index: int
    price: float
    rr_ratio: Optional[float] = None
    allocation_percent: float
    breakeven_trigger: bool = False


class TradePlannerAccountTargetOut(BaseModel):
    account_db_id: str
    account_name: str
    risk_amount: float
    quantity: float
    runtime_status: Optional[str] = None
    linked_order_id: Optional[str] = None
    linked_order_status: Optional[str] = None
    last_execution_at: Optional[datetime] = None
    running_pl: Optional[float] = None


class TradePlannerPlanOut(BaseModel):
    id: str
    symbol: str
    account_id: str
    status: str
    auto_execution_enabled: bool = False
    runtime_status: Optional[str] = None
    linked_order_id: Optional[str] = None
    linked_order_status: Optional[str] = None
    last_execution_at: Optional[datetime] = None
    breakeven_at_t1: bool = False
    breakeven_activated_at: Optional[datetime] = None
    direction: str
    strong_swing_type: str
    strong_swing_price: float
    reversal_points: List[float] = Field(default_factory=list)
    unmitigated_targets: List[float] = Field(default_factory=list)
    entry_price: float
    stop_loss: float
    risk_amount: float
    quantity: float
    sl_pips: float
    targets: List[TradePlannerTargetOut] = Field(default_factory=list)
    account_targets: List[TradePlannerAccountTargetOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AccountOut(BaseModel):
    id: str
    account_name: str
    account_id: str
    market_type: str = "INTERNATIONAL"
    broker_type: str = "METAAPI"
    currency_code: str = "USD"
    risk_amount: float
    session_status: Optional[str] = None
    session_expires_at: Optional[datetime] = None
    broker_user_id: Optional[str] = None
    broker_email: Optional[str] = None
    broker_exchanges: List[str] = Field(default_factory=list)
    broker_server: Optional[str] = None
    broker_scope_key: Optional[str] = None
    mt5_tick_ingest_secret: Optional[str] = None
    available_margin: Optional[float] = None
    equity_balance: Optional[float] = None
    broker_utc_offset: Optional[str] = None
    broker_time_region: Optional[str] = None
    symbol_aliases: Dict[str, str] = Field(default_factory=dict)


class AccountEquityOut(BaseModel):
    account_id: str
    equity: float
    balance: float
    currency: str = "USD"
    equity_balance: float


class WatchlistItemOut(BaseModel):
    symbol: str
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    price_digits: Optional[int] = None


class UserSnapshotOut(BaseModel):
    full_name: str
    username: str
    is_admin: bool = False
    is_active: bool = True
    selected_market: str = "INTERNATIONAL"
    selected_international_account_id: Optional[str] = None
    selected_indian_account_id: Optional[str] = None
    selected_indian_crypto_account_id: Optional[str] = None
    selected_account_id: Optional[str] = None
    ui_settings: Dict[str, object] = Field(default_factory=dict)
    accounts: List[AccountOut]


class UserUiSettingsUpdateIn(BaseModel):
    page_id: Optional[str] = None
    order_defaults: Optional[OrderDefaultsIn] = None


class AdminUserCreateIn(BaseModel):
    username: str
    password: str
    full_name: str
    is_admin: bool = False
    is_active: bool = True


class AdminUserUpdateIn(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    full_name: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class AdminUserOut(BaseModel):
    id: str
    username: str
    full_name: str
    is_admin: bool
    is_active: bool
    selected_account_id: Optional[str] = None
    account_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class NotificationOut(BaseModel):
    id: str
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    category: str
    event_type: Optional[str] = None
    status: Optional[str] = None
    activity: str
    failure_reason: Optional[str] = None
    placement_fallback_reason: Optional[str] = None
    timestamp: datetime
    broker_info: Optional[Dict[str, str]] = None


class OrderRowOut(BaseModel):
    id: str
    symbol: Optional[str] = None
    order_type: Optional[str] = None
    side: Optional[str] = None
    status: Optional[str] = None
    manual_context: Optional[Dict[str, object]] = None
    quantity: Optional[float] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    rr_ratio: Optional[float] = None
    is_open_position: Optional[bool] = None
    position_quantity: Optional[float] = None
    realized_pl: Optional[float] = None
    unrealized_pl: Optional[float] = None
    failure_reason: Optional[str] = None
    placement_fallback_reason: Optional[str] = None
    comment: Optional[str] = None
    broker_info: Optional[Dict[str, str]] = None
    account_id: Optional[str] = None
    copy_group_id: Optional[str] = None
    meta_order_id: Optional[str] = None
    meta_position_id: Optional[str] = None
    external_source: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    last_broker_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PaginatedOrdersOut(BaseModel):
    records: List[OrderRowOut]
    page: int
    page_size: int
    total: int


class BrokerTradeHistoryRowOut(BaseModel):
    id: str
    account_id: str
    account_name: Optional[str] = None
    position_id: Optional[str] = None
    order_id: Optional[str] = None
    deal_ids: List[str] = Field(default_factory=list)
    symbol: str
    type: str
    status: str
    open_time: Optional[datetime] = None
    open_price: Optional[float] = None
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    profit: float = 0.0
    lots: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    net_profit: float = 0.0
    is_running: bool = False


class PaginatedBrokerTradeHistoryOut(BaseModel):
    records: List[BrokerTradeHistoryRowOut]
    page: int
    page_size: int
    total: int


class OrderPlacementResultOut(BaseModel):
    account_db_id: str
    account_name: str
    order_id: Optional[str] = None
    meta_order_id: Optional[str] = None
    status: str
    quantity: Optional[float] = None
    failure_reason: Optional[str] = None


class OrderPlacementOut(BaseModel):
    copy_group_id: str
    success_count: int
    failed_count: int
    results: List[OrderPlacementResultOut]


class TrapReversalStartIn(BaseModel):
    symbol: str
    risk_amount: float


class TrapReversalStopIn(BaseModel):
    symbol: str


class MasterBreakTargetIn(BaseModel):
    r: float
    qty_pct: float


class MasterBreakSettingsIn(BaseModel):
    risk_amount: float = 100.0
    master_timeframe: str = "H6"
    exec_timeframe: str = "M5"
    breakeven_r: float = 1.0
    targets: List[MasterBreakTargetIn] = Field(
        default_factory=lambda: [
            MasterBreakTargetIn(r=2.0, qty_pct=50.0),
            MasterBreakTargetIn(r=4.0, qty_pct=50.0),
        ]
    )


class MasterBreakSettingsOut(BaseModel):
    risk_amount: float
    master_timeframe: str
    exec_timeframe: str
    breakeven_r: float
    targets: List[MasterBreakTargetIn]
    strategy_type: str = "master_break"


class MasterBreakStartIn(BaseModel):
    symbol: str = "XAUUSD"
    risk_amount: Optional[float] = None
    master_timeframe: Optional[str] = None
    exec_timeframe: Optional[str] = None
    breakeven_r: Optional[float] = None
    targets: Optional[List[MasterBreakTargetIn]] = None
    settings: Optional[MasterBreakSettingsIn] = None


class MasterBreakStopIn(BaseModel):
    symbol: str


class MasterBreakBacktestIn(BaseModel):
    from_date: str
    to_date: str
    symbol: str = "XAUUSD"
    risk_amount: Optional[float] = None
    master_timeframe: Optional[str] = None
    exec_timeframe: Optional[str] = None
    breakeven_r: Optional[float] = None
    targets: Optional[List[MasterBreakTargetIn]] = None


class ScheduledTradeCreateIn(BaseModel):
    symbol: str
    level: float
    timeframe: str = "M5"
    risk_amount: Optional[float] = None
    target: Optional[float] = None
    max_signal_candle_pips: Optional[float] = None
    retryable_order: bool = False


class ScheduledTradeOut(BaseModel):
    id: str
    account_id: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    level: Optional[float] = None
    side: Optional[str] = None
    risk_amount: Optional[float] = None
    target: Optional[float] = None
    max_signal_candle_pips: Optional[float] = None
    retryable_order: bool = False
    retry_used: bool = False
    status: Optional[str] = None
    point_size: Optional[float] = None
    pip_size: Optional[float] = None
    signal_candle: Optional[Dict[str, Any]] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    quantity: Optional[float] = None
    order_id: Optional[str] = None
    retry_order_id: Optional[str] = None
    meta_order_id: Optional[str] = None
    retry_meta_order_id: Optional[str] = None
    placement_fallback_reason: Optional[str] = None
    placement_order_type: Optional[str] = None
    last_error: Optional[str] = None
    broker_info: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    armed_at: Optional[str] = None
    placed_at: Optional[str] = None
    filled_at: Optional[str] = None
    exited_at: Optional[str] = None


class ScheduledTradeEventOut(BaseModel):
    id: str
    event_type: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None

