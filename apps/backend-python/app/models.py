from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    password_hash = Column(String(255), nullable=False)
    selected_account_id = Column(Integer, ForeignKey("meta_accounts.id"), nullable=True)

    accounts = relationship("MetaAccount", back_populates="user", foreign_keys="MetaAccount.user_id")


class MetaAccount(Base):
    __tablename__ = "meta_accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_name = Column(String(200), nullable=False)
    account_id = Column(String(200), nullable=False)
    api_token = Column(String(400), nullable=False)
    risk_amount = Column(Float, nullable=False, default=100.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="accounts", foreign_keys=[user_id])


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String(50), nullable=False, index=True)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("meta_accounts.id"), nullable=False)
    symbol = Column(String(50), nullable=False)
    order_type = Column(String(20), nullable=False)  # SL or LIMIT
    side = Column(String(10), nullable=False)  # BUY or SELL
    entry = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    target = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    risk_amount = Column(Float, nullable=False)
    sl_pips = Column(Float, nullable=False)
    rr_ratio = Column(Float, nullable=True)
    meta_order_id = Column(String(200), nullable=True)
    status = Column(String(50), nullable=False, default="CREATED")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_open_position = Column(Boolean, default=False, nullable=False)
    position_quantity = Column(Float, nullable=True)
    realized_pl = Column(Float, nullable=True)
    unrealized_pl = Column(Float, nullable=True)


class OrderEvent(Base):
    __tablename__ = "order_events"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(100), nullable=False)
    event_ts_ist = Column(String(40), nullable=False)
    payload_json = Column(Text, nullable=True)
