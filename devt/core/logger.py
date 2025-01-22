import logging
from .env import APP_DATA_DIR, LOGS_DIR, LOG_FILE

# Ensure directories exist
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Create a logger
logger = logging.getLogger("devt")

# Set the logging level
logger.setLevel(logging.INFO)

# Create a file handler and a stream handler
file_handler = logging.FileHandler(LOG_FILE)
stream_handler = logging.StreamHandler()

# Create a formatter and attach it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# To set the log level dynamically, you can use the following function
def set_log_level(level: str):
    """
    Set the log level dynamically.
    Args:
        level (str): The log level to set. Can be 'DEBUG', 'INFO', 'WARNING', 'ERROR', or 'CRITICAL'.
    """
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    if level in levels:
        logger.setLevel(levels[level])
    else:
        logger.error(f"Invalid log level: {level}")