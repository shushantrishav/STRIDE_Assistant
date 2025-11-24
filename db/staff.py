from typing import Optional, List, Tuple
from db.postgres import get_connection
from Services.logger_config import logger  # Import logger

# ---------------------------------------------------
# Fetch a single staff member by username
# ---------------------------------------------------
def get_staff_by_username(username: str) -> Optional[Tuple[str, str, str, str]]:
    """
    Returns:
        (staff_id, outlet_id, username, role) if found
        None if no staff matches
    """
    query = """
        SELECT
            staff_id,
            outlet_id,
            username,
            role
        FROM staff_schema.staff
        WHERE username = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (username,))
                result = cur.fetchone()
                if result:
                    logger.info(f"Staff found by username: {username}")
                else:
                    logger.warning(f"No staff found with username: {username}")
                return result
    except Exception as e:
        logger.error(f"Error fetching staff by username '{username}': {e}", exc_info=True)
        return None


# ---------------------------------------------------
# Fetch all staff for a specific outlet
# ---------------------------------------------------
def get_staff_by_outlet(outlet_id: str) -> List[Tuple[str, str, str]]:
    """
    Returns:
        List of (staff_id, username, role) tuples for the outlet
    """
    query = """
        SELECT
            staff_id,
            username,
            role
        FROM staff_schema.staff
        WHERE outlet_id = %s
        ORDER BY role
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (outlet_id,))
                rows = cur.fetchall()
                logger.info(f"Fetched {len(rows)} staff members for outlet {outlet_id}")
                return rows
    except Exception as e:
        logger.error(f"Error fetching staff for outlet '{outlet_id}': {e}", exc_info=True)
        return []
