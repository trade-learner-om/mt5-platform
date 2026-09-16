"""Feed vs execution broker mismatch detection and audited consent helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def account_broker_label(account: dict) -> str:
    meta = account.get("meta_profile") or {}
    server = str(meta.get("server") or "").strip()
    if server:
        return server
    company = str(meta.get("company") or "").strip()
    if company:
        return company
    broker_type = str(account.get("broker_type") or "").strip()
    if broker_type:
        return broker_type
    return "Unknown broker"


def account_broker_scope_key(account: dict) -> str:
    meta = account.get("meta_profile") or {}
    server = str(meta.get("server") or "").strip().upper()
    company = str(meta.get("company") or "").strip().upper()
    broker_type = str(account.get("broker_type") or "").strip().upper()
    market = str(account.get("market_type") or "INTERNATIONAL").strip().upper()
    if server:
        return f"{market}|{broker_type}|{server}"
    if company:
        return f"{market}|{broker_type}|{company}"
    return f"{market}|{broker_type}"


def brokers_match(feed_account: dict, execution_account: dict) -> bool:
    return account_broker_scope_key(feed_account) == account_broker_scope_key(execution_account)


def build_mismatch_warning(*, feed_account: dict, execution_account: dict) -> str:
    feed_name = str(feed_account.get("account_name") or feed_account.get("login") or feed_account.get("_id") or "feed")
    exec_name = str(
        execution_account.get("account_name") or execution_account.get("login") or execution_account.get("_id") or "execution"
    )
    feed_broker = account_broker_label(feed_account)
    exec_broker = account_broker_label(execution_account)
    return (
        f"Account {exec_name} executes on {exec_broker}, but prices come from feed account "
        f"{feed_name} ({feed_broker}). Prices and fills may differ."
    )


def build_consent_record(
    *,
    feed_account: dict,
    execution_account: dict,
    warning_text: str,
    agreed_at: Optional[datetime] = None,
) -> dict[str, Any]:
    when = agreed_at or datetime.now(timezone.utc)
    return {
        "agreed": True,
        "agreed_at": when.isoformat().replace("+00:00", "Z"),
        "feed_account_id": str(feed_account.get("_id") or ""),
        "feed_broker": account_broker_label(feed_account),
        "execution_account_id": str(execution_account.get("_id") or ""),
        "execution_broker": account_broker_label(execution_account),
        "warning_text": warning_text,
    }


def collect_mismatch_accounts(*, feed_account: dict, execution_accounts: list[dict]) -> list[dict]:
    mismatches = []
    for account in execution_accounts:
        if brokers_match(feed_account, account):
            continue
        warning = build_mismatch_warning(feed_account=feed_account, execution_account=account)
        mismatches.append(
            {
                "account_id": str(account.get("_id") or ""),
                "account_name": str(account.get("account_name") or account.get("login") or ""),
                "feed_account_id": str(feed_account.get("_id") or ""),
                "feed_broker": account_broker_label(feed_account),
                "execution_broker": account_broker_label(account),
                "warning": warning,
            }
        )
    return mismatches
