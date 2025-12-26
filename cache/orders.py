# ==========================================
# STRIDE – SALES PREFETCH SCRIPT (ORDERS)
# ==========================================

import json
from datetime import date, datetime
from db.postgres import get_connection, dict_row
from Services.logger_config import logger
from cache.redis_client import client as redis
from typing import Optional, Dict
from decimal import Decimal

# ------------------------------------------
# Cache Configuration
# ------------------------------------------
ORDER_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
ORDER_CACHE_PREFIX = "order"

# ------------------------------------------
# Cache Key Builder
# ------------------------------------------
def _order_cache_key(order_id: str) -> str:
    return f"{ORDER_CACHE_PREFIX}:{order_id}"

# ------------------------------------------
# JSON serializer for date/datetime
# ------------------------------------------
def json_serializer(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)  # convert Decimal to float
    raise TypeError(f"Type {type(obj)} not serializable")

# ------------------------------------------
# Search Redis cache
# ------------------------------------------
def get_order_from_cache(order_id: str) -> Optional[Dict]:
    """
    Search Redis cache for a given order_id and return the order data as a dict.
    Returns None if not found in cache.
    """
    cache_key = _order_cache_key(order_id)
    try:
        cached = redis.get(cache_key)
        if cached:
            return json.loads(cached)
        else:
            logger.warning(f"Order {order_id} not found in Redis cache")
            return None
    except Exception as e:
        logger.error(f"Error fetching order {order_id} from Redis: {e}", exc_info=True)
        return None

# ------------------------------------------
# Fetch all recent orders from Postgres
# ------------------------------------------
def fetch_all_orders(days_back: int = 7) -> list[dict]:
    """
    Fetch all orders from the last N days.
    Adjust query if you want full table fetch (remove WHERE clause).
    """
    query = f"""
        SELECT
            o.order_id,
            o.product_id,
            o.size,
            o.customer_id,
            o.outlet_id,
            o.purchase_date,
            o.price,
            p.category,
            c.full_name,
            c.email,
            c.phone AS customer_phone
        FROM sales_schema.orders o
        JOIN sales_schema.products p
            ON o.product_id = p.product_id
        JOIN sales_schema.customers c
            ON o.customer_id = c.customer_id
        WHERE o.purchase_date >= current_date - interval '{days_back} days'
    """
    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query)
                results = cur.fetchall()
                logger.info(f"Fetched {len(results)} orders from Postgres (last {days_back} days)")
                return results
    except Exception as e:
        logger.error(f"Error fetching orders from Postgres: {e}", exc_info=True)
        return []

# ------------------------------------------
# Prefetch orders into Redis
# ------------------------------------------
def prefetch_orders(days_back: int = 7):
    orders = fetch_all_orders(days_back)
    if not orders:
        logger.warning("No orders fetched, skipping Redis cache prefill")
        return

    for order in orders:
        cache_key = _order_cache_key(order["order_id"])
        try:
            redis.set(cache_key, json.dumps(order, default=json_serializer), ex=ORDER_CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning(f"Failed to cache order {order['order_id']}: {e}")

    logger.info(f"Prefetched {len(orders)} orders into Redis with TTL {ORDER_CACHE_TTL_SECONDS} sec")

# ------------------------------------------
# Optional: Run script standalone
# ------------------------------------------
if __name__ == "__main__":
    prefetch_orders(days_back=7)
