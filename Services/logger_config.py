import logging
import os

LOG_DIR = "Logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Paths for the two log files
ALL_LOG_FILE = os.path.join(LOG_DIR, "app.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "app_error.log")

# Setup formatting
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 1. Setup General Handler (app.log)
# This will capture EVERYTHING (INFO, WARNING, ERROR, CRITICAL)
all_handler = logging.FileHandler(ALL_LOG_FILE)
all_handler.setLevel(logging.INFO)
all_handler.setFormatter(log_format)

# 2. Setup Error Handler (app_error.log)
# This will ONLY capture ERROR and CRITICAL levels
error_handler = logging.FileHandler(ERROR_LOG_FILE)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(log_format)

# Create the logger instance
logger = logging.getLogger("app_logger")
logger.setLevel(logging.INFO) # Set base level to INFO to allow info logs to flow

# Add both handlers to the logger
logger.addHandler(all_handler)
logger.addHandler(error_handler)
