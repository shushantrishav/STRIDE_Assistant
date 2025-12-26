import logging
import os

LOG_DIR = os.getenv("LOG_DIR", "Logs")
os.makedirs(LOG_DIR, exist_ok=True)

ALL_LOG_FILE = os.path.join(LOG_DIR, "app.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "app_error.log")

log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger("app_logger")
logger.setLevel(logging.INFO)
logger.propagate = False

# Prevent duplicate handlers on re-import
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == ALL_LOG_FILE for h in logger.handlers):
    all_handler = logging.FileHandler(ALL_LOG_FILE)
    all_handler.setLevel(logging.INFO)
    all_handler.setFormatter(log_format)
    logger.addHandler(all_handler)

if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == ERROR_LOG_FILE for h in logger.handlers):
    error_handler = logging.FileHandler(ERROR_LOG_FILE)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(log_format)
    logger.addHandler(error_handler)
