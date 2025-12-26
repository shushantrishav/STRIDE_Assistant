# ==========================================
# STRIDE – REDIS CLIENT
# ==========================================
import os
import redis
from Services.logger_config import logger

# ------------------------------------------
# Configuration (env-first)
# ------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_USER = os.getenv("REDIS_USER", "stride_admin")  # Added user
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "stride_password") 
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", 1.0))

# ------------------------------------------
# Client Initialization
# ------------------------------------------
try:
    # Note: Use 'username' for Redis 6.0+ ACL support
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        username=REDIS_USER,
        password=REDIS_PASSWORD,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
        decode_responses=True,
    )

    # Health check
    client.ping()
    logger.info(
        f"Redis connected successfully ({REDIS_HOST}:{REDIS_PORT}, db={REDIS_DB}, user={REDIS_USER})"
    )

except Exception as e:
    logger.error(f"Redis connection failed: {e}", exc_info=True)
    # Fail soft: ensuring the object is still defined
    client = None