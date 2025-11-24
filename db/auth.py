# ---------------------------------------------------
# db/auth.py
# ---------------------------------------------------
from typing import Optional, Tuple
from db.postgres import get_connection
from Services.logger_config import logger  # Import the logger

def authenticate_staff(username: str, password: str) -> Optional[Tuple[str, str, str, str]]:
    """
    Authenticate a staff member using their username and password.

    Returns:
        Tuple[staff_id, outlet_id, username, role] if valid credentials
        None if authentication fails
    """
    query = """
        SELECT
            staff_id,
            outlet_id,
            username,
            role
        FROM staff_schema.staff
        WHERE username = %s
          AND password_hash = crypt(%s, password_hash)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (username, password))
                result = cur.fetchone()
                if result:
                    logger.info(f"Staff authenticated successfully: {username}")
                else:
                    logger.warning(f"Failed authentication attempt for username: {username}")
                return result
    except Exception as e:
        logger.error(f"Error during staff authentication for username '{username}': {e}", exc_info=True)
        return None
