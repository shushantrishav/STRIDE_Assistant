# ==========================================
# STRIDE – INVENTORY CACHE
# ==========================================

import json
from typing import Optional, Union

from Services.redis_client import client as redis
from Services.logger_config import logger
from db.inventory import get_inventory_for_product as db_get_inventory


# ------------------------------------------
# Cache Configuration
# ------------------------------------------
INVENTORY_CACHE_TTL_SECONDS = 5 * 60  # 5 minutes
INVENTORY_CACHE_PREFIX = "inventory"


# ------------------------------------------
# Cache Key Builder
# ------------------------------------------
def _inventory_cache_key(outlet_id: str, product_id: str, size: int) -> str:
    return f"{INVENTORY_CACHE_PREFIX}:{outlet_id}:{product_id}:{size}"


# ------------------------------------------
# Normalize DB row → dict (CRITICAL)
# ------------------------------------------
def _normalize_inventory(row: Union[dict, tuple, object]) -> dict:
    """
    Normalize inventory DB row (tuple / ORM / dict) into a clean dict.
    """

    # Dict from DB
    if isinstance(row, dict):
        return {
            "outlet_id": row.get("outlet_id"),
            "product_id": row.get("product_id"),
            "size": row.get("size"),
            "quantity": int(row.get("quantity", 0)),
        }

    # Tuple / list from cursor
    if isinstance(row, (tuple, list)):
        # EXPECTED ORDER: outlet_id, product_id, size, quantity
        outlet_id, product_id, size, quantity = row
        return {
            "outlet_id": outlet_id,
            "product_id": product_id,
            "size": size,
            "quantity": int(quantity),
        }

    # ORM object fallback
    return {
        "outlet_id": getattr(row, "outlet_id", None),
        "product_id": getattr(row, "product_id", None),
        "size": getattr(row, "size", None),
        "quantity": int(getattr(row, "quantity", 0)),
    }


# ------------------------------------------
# Public API: Read-through cache
# ------------------------------------------
def get_inventory_cached(outlet_id: str, product_id: str, size: int) -> Optional[dict]:
    """
    Fetch inventory row with Redis caching + Postgres fallback.

    Returns:
        {
            "outlet_id": str,
            "product_id": str,
            "size": int,
            "quantity": int
        } or None
    """

    cache_key = _inventory_cache_key(outlet_id, product_id, size)

    # 1️⃣ Try Redis
    try:
        cached = redis.get(cache_key)
        if cached:
            logger.info(f"[CACHE HIT] Inventory {cache_key}")
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"[CACHE ERROR] Redis read failed for {cache_key}: {e}")

    logger.info(f"[CACHE MISS] Inventory {cache_key}")

    # 2️⃣ Fallback to DB
    row = db_get_inventory(outlet_id, product_id, size)
    if not row:
        return None

    inventory = _normalize_inventory(row)

    # 3️⃣ Store normalized dict in Redis
    try:
        redis.set(
            cache_key,
            json.dumps(inventory),
            ex=INVENTORY_CACHE_TTL_SECONDS,
        )
        logger.info(f"[CACHE SET] Inventory {cache_key} cached for {INVENTORY_CACHE_TTL_SECONDS}s")
    except Exception as e:
        logger.warning(f"[CACHE ERROR] Redis write failed for {cache_key}: {e}")

    return inventory


# ------------------------------------------
# Public API: Check availability quickly
# ------------------------------------------
def is_inventory_available(outlet_id: str, product_id: str, size: int) -> bool:
    """
    Convenience wrapper for availability check with caching.
    """
    inv = get_inventory_cached(outlet_id, product_id, size)
    return bool(inv and inv["quantity"] > 0)


# ------------------------------------------
# Public API: Prefetch (fire-and-forget)
# ------------------------------------------
def prefetch_inventory(outlet_id: str, product_id: str, size: int) -> None:
    """
    Optional prefetch to warm Redis cache.
    """
    try:
        get_inventory_cached(outlet_id, product_id, size)
        logger.info(f"[CACHE PREFETCH] Inventory {outlet_id}:{product_id}:{size}")
    except Exception as e:
        logger.warning(
            f"[CACHE ERROR] Prefetch failed for {outlet_id}:{product_id}:{size}: {e}"
        )
