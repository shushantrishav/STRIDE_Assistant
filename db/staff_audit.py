import uuid
from db.postgres import get_connection
from Services.logger_config import logger  # Import logger


def log_staff_action(staff_id: str, action: str, target_id: str | None = None):
    """
    Writes an immutable audit record for any staff action.
    This should be called ONLY after authentication (JWT-resolved staff_id).
    """
    query = """
        INSERT INTO staff_schema.staff_action_log (
            log_id,
            staff_id,
            action,
            target_id
        )
        VALUES (%s, %s, %s, %s)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(uuid.uuid4()), staff_id, action, target_id))
                conn.commit()
        logger.info(
            f"Staff action logged: staff_id={staff_id}, action={action}, target_id={target_id}"
        )
    except Exception as e:
        logger.error(
            f"Error logging staff action: staff_id={staff_id}, action={action}, target_id={target_id} - {e}",
            exc_info=True,
        )


def get_outlet_staff_logs(outlet_id: str, limit: int = 100):
    """
    Fetch staff action logs scoped to a specific outlet.
    Used ONLY by ADMIN routes.
    """
    query = """
        SELECT
            l.log_id,
            l.staff_id,
            s.username,
            s.role,
            s.outlet_id,
            l.action,
            l.target_id,
            l.created_at
        FROM staff_schema.staff_action_log l
        JOIN staff_schema.staff s
          ON l.staff_id = s.staff_id
        WHERE s.outlet_id = %s
        ORDER BY l.created_at DESC
        LIMIT %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (outlet_id, limit))
                rows = cur.fetchall()

        logs = [
            {
                "log_id": r[0],
                "staff_id": r[1],
                "username": r[2],
                "role": r[3],
                "outlet_id": r[4],
                "action": r[5],
                "target_id": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]
        logger.info(f"Fetched {len(logs)} staff action logs for outlet {outlet_id}")
        return logs
    except Exception as e:
        logger.error(
            f"Error fetching staff action logs for outlet {outlet_id}: {e}",
            exc_info=True,
        )
        return []
