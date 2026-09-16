from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

PLATFORM_USERS_COLLECTION = "platform_users"
LEGACY_USERS_COLLECTION = "users"


def _normalize_email(value: Optional[str]) -> Optional[str]:
    email = str(value or "").strip().lower()
    return email or None


def mirror_legacy_user(db, user: dict) -> dict:
    if not user or not user.get("_id"):
        return user
    email = _normalize_email(user.get("email"))
    payload = {
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "email": email,
        "password_hash": user.get("password_hash"),
        "selected_market": user.get("selected_market", "INTERNATIONAL"),
        "selected_international_account_id": user.get("selected_international_account_id"),
        "selected_indian_account_id": user.get("selected_indian_account_id"),
        "selected_indian_crypto_account_id": user.get("selected_indian_crypto_account_id"),
        "selected_account_id": user.get("selected_account_id"),
        "ui_settings": user.get("ui_settings") or {},
        "current_session_id": user.get("current_session_id"),
        "active_session_ids": list(user.get("active_session_ids") or []),
        "is_admin": bool(user.get("is_admin", False)),
        "is_active": bool(user.get("is_active", True)),
        "created_at": user.get("created_at") or datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    db[PLATFORM_USERS_COLLECTION].update_one({"_id": user["_id"]}, {"$set": payload}, upsert=True)
    db[LEGACY_USERS_COLLECTION].update_one({"_id": user["_id"]}, {"$set": payload}, upsert=True)
    return {**user, **payload}


async def mirror_legacy_user_async(db, user: dict) -> dict:
    if not user or not user.get("_id"):
        return user
    email = _normalize_email(user.get("email"))
    payload = {
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "email": email,
        "password_hash": user.get("password_hash"),
        "selected_market": user.get("selected_market", "INTERNATIONAL"),
        "selected_international_account_id": user.get("selected_international_account_id"),
        "selected_indian_account_id": user.get("selected_indian_account_id"),
        "selected_indian_crypto_account_id": user.get("selected_indian_crypto_account_id"),
        "selected_account_id": user.get("selected_account_id"),
        "ui_settings": user.get("ui_settings") or {},
        "current_session_id": user.get("current_session_id"),
        "active_session_ids": list(user.get("active_session_ids") or []),
        "is_admin": bool(user.get("is_admin", False)),
        "is_active": bool(user.get("is_active", True)),
        "created_at": user.get("created_at") or datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db[PLATFORM_USERS_COLLECTION].update_one_async({"_id": user["_id"]}, {"$set": payload}, upsert=True)
    await db[LEGACY_USERS_COLLECTION].update_one_async({"_id": user["_id"]}, {"$set": payload}, upsert=True)
    return {**user, **payload}


def find_user_by_id(db, user_id: ObjectId) -> Optional[dict]:
    user = db[PLATFORM_USERS_COLLECTION].find_one({"_id": user_id})
    if user:
        return user
    legacy = db[LEGACY_USERS_COLLECTION].find_one({"_id": user_id})
    if legacy:
        return mirror_legacy_user(db, legacy)
    return None


async def find_user_by_id_async(db, user_id: ObjectId) -> Optional[dict]:
    user = await db[PLATFORM_USERS_COLLECTION].find_one_async({"_id": user_id})
    if user:
        return user
    legacy = await db[LEGACY_USERS_COLLECTION].find_one_async({"_id": user_id})
    if legacy:
        return await mirror_legacy_user_async(db, legacy)
    return None


def find_user_for_login(db, identifier: str) -> Optional[dict]:
    normalized = str(identifier or "").strip()
    if not normalized:
        return None
    if "@" in normalized:
        email = _normalize_email(normalized)
        user = db[PLATFORM_USERS_COLLECTION].find_one({"email": email})
        if user:
            return user
        return db[LEGACY_USERS_COLLECTION].find_one({"email": email})
    user = db[PLATFORM_USERS_COLLECTION].find_one({"username": normalized})
    if user:
        return user
    return db[LEGACY_USERS_COLLECTION].find_one({"username": normalized})


async def find_user_for_login_async(db, identifier: str) -> Optional[dict]:
    normalized = str(identifier or "").strip()
    if not normalized:
        return None
    if "@" in normalized:
        email = _normalize_email(normalized)
        user = await db[PLATFORM_USERS_COLLECTION].find_one_async({"email": email})
        if user:
            return user
        return await db[LEGACY_USERS_COLLECTION].find_one_async({"email": email})
    user = await db[PLATFORM_USERS_COLLECTION].find_one_async({"username": normalized})
    if user:
        return user
    return await db[LEGACY_USERS_COLLECTION].find_one_async({"username": normalized})


def persist_user_document(db, user_id: ObjectId, payload: dict[str, Any]) -> None:
    db[PLATFORM_USERS_COLLECTION].update_one({"_id": user_id}, {"$set": payload}, upsert=True)
    db[LEGACY_USERS_COLLECTION].update_one({"_id": user_id}, {"$set": payload}, upsert=True)


async def resolve_user_for_session_async(db, user_id: ObjectId, session_id: str) -> Optional[dict]:
    sid = str(session_id or "")
    platform_user = await db[PLATFORM_USERS_COLLECTION].find_one_async({"_id": user_id})
    legacy_user = await db[LEGACY_USERS_COLLECTION].find_one_async({"_id": user_id})

    def _session_matches(user: Optional[dict]) -> bool:
        if not user or not sid:
            return False
        if str(user.get("current_session_id") or "") == sid:
            return True
        active_session_ids = user.get("active_session_ids")
        if isinstance(active_session_ids, list):
            return sid in {str(item) for item in active_session_ids if item}
        return False

    if platform_user and _session_matches(platform_user):
        return platform_user
    if legacy_user and _session_matches(legacy_user):
        return await mirror_legacy_user_async(db, legacy_user)
    return platform_user or legacy_user


async def persist_user_document_async(db, user_id: ObjectId, payload: dict[str, Any]) -> None:
    await db[PLATFORM_USERS_COLLECTION].update_one_async({"_id": user_id}, {"$set": payload}, upsert=True)
    await db[LEGACY_USERS_COLLECTION].update_one_async({"_id": user_id}, {"$set": payload}, upsert=True)
