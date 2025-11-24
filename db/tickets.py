import secrets
import string
from db.postgres import get_connection
import uuid
from Services.logger_config import logger  # Import logger

# -------------------------------
# Generate secure 8-char alphanumeric ticket ID
# -------------------------------
def generate_ticket_id(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


# -------------------------------
# Create ticket in DB
# -------------------------------
def create_ticket(
    order_id: str,
    ticket_type: str,
    status: str,
    outlet_id: str,
    notes: str | None = None
) -> str:
    ticket_id = generate_ticket_id()
    query = """
        INSERT INTO sales_schema.tickets (
            ticket_id,
            order_id,
            ticket_type,
            status,
            outlet_id,
            notes
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (ticket_id, order_id, ticket_type, status, outlet_id, notes)
                )
                conn.commit()
        logger.info(f"Ticket created: ticket_id={ticket_id}, order_id={order_id}, type={ticket_type}")
        return ticket_id
    except Exception as e:
        logger.error(f"Error creating ticket for order {order_id}: {e}", exc_info=True)
        return None


# -------------------------------
# Fetch ticket by order_id
# -------------------------------
def get_ticket_by_order(order_id: str):
    query = """
        SELECT *
        FROM sales_schema.tickets
        WHERE order_id = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (order_id,))
                result = cur.fetchone()
        if result:
            logger.info(f"Fetched ticket for order {order_id}")
        else:
            logger.warning(f"No ticket found for order {order_id}")
        return result
    except Exception as e:
        logger.error(f"Error fetching ticket for order {order_id}: {e}", exc_info=True)
        return None


# -------------------------------
# Check if an active ticket exists
# -------------------------------
def has_active_ticket(order_id: str) -> bool:
    query = """
        SELECT 1
        FROM sales_schema.tickets
        WHERE order_id = %s AND status IN ('OPEN', 'MANUAL_REVIEW')
        LIMIT 1
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (order_id,))
                exists = cur.fetchone() is not None
        logger.info(f"Active ticket check for order {order_id}: {exists}")
        return exists
    except Exception as e:
        logger.error(f"Error checking active ticket for order {order_id}: {e}", exc_info=True)
        return False


# -------------------------------
# Fetch ticket by outlet ID
# -------------------------------
def get_tickets_by_outlet(outlet_id: str):
    query = """
        SELECT
            ticket_id,
            order_id,
            ticket_type,
            status,
            generated_at,
            resolved_at,
            notes
        FROM sales_schema.tickets
        WHERE outlet_id = %s
        ORDER BY generated_at DESC
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (outlet_id,))
                rows = cur.fetchall()
        logger.info(f"Fetched {len(rows)} tickets for outlet {outlet_id}")
        return rows
    except Exception as e:
        logger.error(f"Error fetching tickets for outlet {outlet_id}: {e}", exc_info=True)
        return []


# -------------------------------
# Update ticket status
# -------------------------------
def update_ticket_status(
    ticket_id: str,
    new_status: str,
    staff_id: str,
    notes: str | None = None
):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # Update ticket
                cur.execute("""
                    UPDATE sales_schema.tickets
                    SET
                        status = %s,
                        resolved_at = CASE
                            WHEN %s IN ('RESOLVED','CLOSED') THEN now()
                            ELSE resolved_at
                        END,
                        notes = COALESCE(%s, notes)
                    WHERE ticket_id = %s
                """, (new_status, new_status, notes, ticket_id))

                # Audit log
                cur.execute("""
                    INSERT INTO staff_schema.staff_action_log (
                        log_id,
                        staff_id,
                        action,
                        target_id
                    )
                    VALUES (%s, %s, %s, %s)
                """, (
                    str(uuid.uuid4()),
                    staff_id,
                    f"TICKET_STATUS_CHANGED_TO_{new_status}",
                    ticket_id
                ))

                conn.commit()
        logger.info(f"Ticket {ticket_id} status updated to {new_status} by staff {staff_id}")
    except Exception as e:
        logger.error(f"Error updating ticket {ticket_id} status to {new_status} by staff {staff_id}: {e}", exc_info=True)
