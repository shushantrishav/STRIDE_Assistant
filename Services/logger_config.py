# logger_config.py
import logging
import os

LOG_DIR = "Logs"
LOG_FILE = os.path.join(LOG_DIR, "error.log")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Setup formatting
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Configure File Handler
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(log_format)

# Create the logger instance
logger = logging.getLogger("app_logger")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

# Optional: Add a StreamHandler to see logs in the terminal too
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_format)
logger.addHandler(console_handler)