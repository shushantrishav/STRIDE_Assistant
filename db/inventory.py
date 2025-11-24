# db/inventory.py
# ==========================================
# STRIDE – INVENTORY CHECK (READ-ONLY)
# ==========================================

from db.postgres import get_connection
from Services.logger_config import logger  # Import logger

def get_inventory_for_product(
    outlet_id: str,
    product_id: str,
    size: int
):
    query = """
        SELECT
            outlet_id,
            product_id,
            size,
            quantity
        FROM inventory_schema.inventory
        WHERE outlet_id = %s
          AND product_id = %s
          AND size = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (outlet_id, product_id, size))
                result = cur.fetchone()
                logger.info(f"Fetched inventory for outlet {outlet_id}, product {product_id}, size {size}: {result}")
                return result
    except Exception as e:
        logger.error(f"Error fetching inventory for outlet {outlet_id}, product {product_id}, size {size}: {e}", exc_info=True)
        return None


# ------------------------------------------
# Check if inventory is available for a product at an outlet
# Returns True if quantity > 0, else False
# ------------------------------------------
def check_inventory(
    outlet_id: str,
    product_id: str,
    size: int
) -> bool:
    query = """
        SELECT quantity
        FROM inventory_schema.inventory
        WHERE outlet_id = %s
          AND product_id = %s
          AND size = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (outlet_id, product_id, size))
                row = cur.fetchone()
                available = bool(row and row.get("quantity", 0) > 0)
                logger.info(f"Inventory check for outlet {outlet_id}, product {product_id}, size {size}: {available}")
                return available
    except Exception as e:
        logger.error(f"Error checking inventory for outlet {outlet_id}, product {product_id}, size {size}: {e}", exc_info=True)
        return False
