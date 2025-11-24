# db/sales.py
# ---------------------------------------------------
# sales database controller
# ---------------------------------------------------
from db.postgres import get_connection
from Services.logger_config import logger  # Import logger

def get_order_by_id(order_id: str):
    """
    Fetch order details along with customer contact info.
    Used for complaint session validation and RAG context.
    """
    query = """
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
        WHERE o.order_id = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (order_id,))
                result = cur.fetchone()
                if result:
                    logger.info(f"Order fetched successfully: {order_id}")
                else:
                    logger.warning(f"No order found with ID: {order_id}")
                return result
    except Exception as e:
        logger.error(f"Error fetching order {order_id}: {e}", exc_info=True)
        return None
