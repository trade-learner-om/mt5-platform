from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from .metaapi_client import metaapi_service
from .risk import calc_rr, calc_sl_pips
from .trade_planner import derive_trade_plan, trigger_distance_pips

TRADE_PLAN_COLLECTION = "trade_plans"


def _plan_targets_for_account(plan: dict, account_db_id) -> list[dict]:
    raw_targets = plan.get("account_targets") or []
    if raw_targets:
        return [target for target in raw_targets if str(target.get("account_id")) == str(account_db_id)]
    if str(plan.get("account_id") or "") == str(account_db_id):
        return [{"account_id": account_db_id, "risk_amount": float(plan.get("risk_amount") or 0)}]
    return []


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


def _runtime_status_from_order_status(status: Optional[str]) -> str:
    upper = str(status or "").upper()
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
    return mapping.get(upper, upper or "WAITING_ENTRY_ZONE")


def _target_price_for_plan(derived: dict) -> Optional[float]:
    targets = derived.get("targets") or []
    if not targets:
        return None
    return targets[-1].get("price")


class TradePlannerRuntimeManager:
    async def handle_tick(self, db, user_id: str, account_db_id, account: dict, price_payload: dict):
        symbol = str(price_payload.get("symbol") or "").upper()
        if not symbol:
            return
        user_oid = ObjectId(user_id)
        plans = await db[TRADE_PLAN_COLLECTION].find_async(
            {
                "user_id": user_oid,
                "symbol": symbol,
                "auto_execution_enabled": True,
                "status": "RUNNING",
                "$or": [
                    {"account_targets.account_id": account_db_id},
                    {"account_id": account_db_id},
                ],
            }
        )
        if not plans:
            return

        current_price = self._current_price(price_payload)
        for plan in plans:
            matching_targets = _plan_targets_for_account(plan, account_db_id)
            for target in matching_targets:
                await self._sync_plan(db, user_oid, account_db_id, account, plan, target, current_price)

    async def _sync_plan(self, db, user_oid, account_db_id, account: dict, plan: dict, plan_target: dict, current_price: Optional[float]):
        derived = derive_trade_plan(
            account,
            plan.get("symbol"),
            plan.get("strong_swing_type"),
            plan.get("strong_swing_price"),
            plan.get("reversal_points") or [],
            plan.get("unmitigated_targets") or [],
            plan.get("target_allocations") or [],
            bool(plan.get("breakeven_at_t1", False)),
            plan.get("point_size"),
            plan_target.get("risk_amount") or plan.get("risk_amount"),
        )
        linked_order = None
        linked_order_id = plan.get("linked_order_id")
        if linked_order_id:
            try:
                linked_order = await db.orders.find_one_async(
                    {
                        "_id": ObjectId(str(linked_order_id)),
                        "user_id": user_oid,
                        "planner_context.plan_account_id": str(account_db_id),
                    }
                )
            except Exception:
                linked_order = None
        if not linked_order and plan.get("linked_meta_order_id"):
            linked_order = await db.orders.find_one_async(
                {
                    "user_id": user_oid,
                    "account_id": account_db_id,
                    "meta_order_id": plan.get("linked_meta_order_id"),
                    "planner_context.plan_account_id": str(account_db_id),
                }
            )
        if not linked_order:
            linked_order = await db.orders.find_one_async(
                {
                    "user_id": user_oid,
                    "account_id": account_db_id,
                    "planner_context.plan_id": str(plan["_id"]),
                    "planner_context.plan_account_id": str(account_db_id),
                    "status": {"$in": ["PLACEMENT_PENDING", "PENDING", "FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"]},
                },
                sort=[("created_at", -1)],
            )

        if linked_order:
            await self._maybe_activate_breakeven(db, account, plan, linked_order, derived, current_price)
            await self._update_plan_from_order(db, plan, linked_order)
            return

        distance = trigger_distance_pips(
            derived["symbol"],
            derived["direction"],
            current_price,
            derived["entry_price"],
        )
        if distance is None or distance > 10:
            runtime_status = plan.get("runtime_status") or "WAITING_ENTRY_ZONE"
            if runtime_status != "WAITING_ENTRY_ZONE":
                await db[TRADE_PLAN_COLLECTION].update_one_async(
                    {"_id": plan["_id"]},
                    {"$set": {"runtime_status": "WAITING_ENTRY_ZONE", "updated_at": datetime.utcnow()}},
                )
            return

        await self._place_limit_order(db, user_oid, account_db_id, account, plan, plan_target, derived)

    async def _place_limit_order(self, db, user_oid, account_db_id, account: dict, plan: dict, plan_target: dict, derived: dict):
        broker_info = _broker_info_from_account(account)
        side = "BUY" if str(derived["direction"]).upper() == "LONG" else "SELL"
        target_price = _target_price_for_plan(derived)
        now = datetime.utcnow()
        order_doc = {
            "user_id": user_oid,
            "account_id": account_db_id,
            "symbol": derived["symbol"],
            "order_type": "LIMIT",
            "side": side,
            "entry": derived["entry_price"],
            "stop_loss": derived["stop_loss"],
            "target": target_price,
            "comment": "Trade Planner auto order",
            "quantity": derived["quantity"],
            "risk_amount": derived["risk_amount"],
            "sl_pips": calc_sl_pips(derived["symbol"], derived["entry_price"], derived["stop_loss"]),
            "rr_ratio": calc_rr(side, derived["entry_price"], derived["stop_loss"], target_price),
            "meta_order_id": None,
            "status": "PLACEMENT_PENDING",
            "failure_reason": None,
            "copy_group_id": None,
            "created_at": now,
            "updated_at": now,
            "is_open_position": False,
            "position_quantity": None,
            "realized_pl": None,
            "unrealized_pl": None,
            "broker_info": broker_info,
            "planner_context": {
                "plan_id": str(plan["_id"]),
                "plan_account_id": str(account_db_id),
                "targets": derived.get("targets") or [],
            },
        }
        insert_result = await db.orders.insert_one_async(order_doc)
        order_doc["_id"] = insert_result.inserted_id

        try:
            result = await metaapi_service.place_pending_order(
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
            await db.orders.update_one_async(
                {"_id": order_doc["_id"]},
                {"$set": {"status": "FAILED", "failure_reason": failure_reason, "updated_at": datetime.utcnow()}},
            )
            await db[TRADE_PLAN_COLLECTION].update_one_async(
                {"_id": plan["_id"]},
                {
                    "$set": {
                        "auto_execution_enabled": False,
                        "status": "ACTIVE",
                        "runtime_status": "FAILED",
                        "linked_order_id": str(order_doc["_id"]),
                        "linked_order_status": "FAILED",
                        "last_execution_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            return

        meta_order_id = str(result.get("orderId", ""))
        await db.orders.update_one_async(
            {"_id": order_doc["_id"]},
            {"$set": {"meta_order_id": meta_order_id, "status": "PENDING", "updated_at": datetime.utcnow()}},
        )
        await db[TRADE_PLAN_COLLECTION].update_one_async(
            {"_id": plan["_id"]},
            {
                "$set": {
                    "runtime_status": "ORDER_PLACED",
                    "linked_order_id": str(order_doc["_id"]),
                    "linked_meta_order_id": meta_order_id,
                    "linked_order_status": "PENDING",
                    "last_execution_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    async def _update_plan_from_order(self, db, plan: dict, order: dict):
        status = str(order.get("status") or "").upper()
        runtime_status = _runtime_status_from_order_status(status)
        update_payload = {
            "runtime_status": runtime_status,
            "linked_order_id": str(order["_id"]),
            "linked_meta_order_id": order.get("meta_order_id"),
            "linked_order_status": status,
            "updated_at": datetime.utcnow(),
        }
        if status == "CLOSED":
            update_payload["auto_execution_enabled"] = False
            update_payload["status"] = "INACTIVE"
            update_payload["last_execution_at"] = datetime.utcnow()
        elif status in {"CANCELLED", "FAILED"}:
            update_payload["auto_execution_enabled"] = False
            update_payload["status"] = "ACTIVE"
            update_payload["last_execution_at"] = datetime.utcnow()
        else:
            update_payload["status"] = "RUNNING"
        await db[TRADE_PLAN_COLLECTION].update_one_async({"_id": plan["_id"]}, {"$set": update_payload})

    async def _maybe_activate_breakeven(self, db, account: dict, plan: dict, order: dict, derived: dict, current_price: Optional[float]):
        if not bool(plan.get("breakeven_at_t1")):
            return
        if plan.get("breakeven_activated_at"):
            return
        status = str(order.get("status") or "").upper()
        if status not in {"FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"}:
            return
        position_id = str(order.get("meta_position_id") or "")
        if not position_id:
            return
        targets = derived.get("targets") or []
        if len(targets) < 2:
            return
        first_target = targets[0].get("price")
        entry_price = derived.get("entry_price")
        if first_target is None or entry_price is None or current_price is None:
            return
        direction = str(derived.get("direction") or "").upper()
        triggered = current_price >= float(first_target) if direction == "LONG" else current_price <= float(first_target)
        if not triggered:
            return
        existing_stop = order.get("stop_loss")
        if existing_stop is not None:
            try:
                if round(float(existing_stop), 10) == round(float(entry_price), 10):
                    await db[TRADE_PLAN_COLLECTION].update_one_async(
                        {"_id": plan["_id"]},
                        {"$set": {"breakeven_activated_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
                    )
                    return
            except (TypeError, ValueError):
                pass
        try:
            await metaapi_service.modify_position(
                account["api_token"],
                account["account_id"],
                position_id,
                stop_loss=float(entry_price),
                take_profit=order.get("target"),
            )
        except Exception:
            return
        now = datetime.utcnow()
        await db.orders.update_one_async(
            {"_id": order["_id"]},
            {"$set": {"stop_loss": float(entry_price), "updated_at": now}},
        )
        await db[TRADE_PLAN_COLLECTION].update_one_async(
            {"_id": plan["_id"]},
            {"$set": {"breakeven_activated_at": now, "updated_at": now}},
        )

    def _current_price(self, price_payload: dict) -> Optional[float]:
        bid = price_payload.get("bid")
        ask = price_payload.get("ask")
        if bid is None and ask is None:
            return None
        if bid is None:
            return ask
        if ask is None:
            return bid
        return float((Decimal(str(bid)) + Decimal(str(ask))) / Decimal("2"))


trade_planner_runtime_manager = TradePlannerRuntimeManager()
