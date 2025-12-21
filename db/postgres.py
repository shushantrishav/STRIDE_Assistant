# db/postgres.py
# ---------------------------------------------------
# DATABASE ENTRY POINT WITH CONNECTION POOL
# ---------------------------------------------------

import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from Services.logger_config import logger  # your logger

# ---------------------------------------------------
# Load environment variables
# ---------------------------------------------------
load_dotenv()
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

# ---------------------------------------------------
# Build connection URL
# ---------------------------------------------------
DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ---------------------------------------------------
# Initialize connection pool
# ---------------------------------------------------
try:
    pool = ConnectionPool(DB_URL)
    logger.info("PostgreSQL connection pool initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize connection pool: {e}", exc_info=True)
    raise

# ---------------------------------------------------
# Helper to get a connection
# ---------------------------------------------------
def get_connection():
    """
    Returns a connection from the pool.
    Usage:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(...)
    """
    try:
        conn = pool.connection()
        conn.row_factory = dict_row
        return conn
    except Exception as e:
        logger.error(f"Error acquiring connection from pool: {e}", exc_info=True)
        raise
