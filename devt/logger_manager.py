# devt/logger_manager.py
import logging
from devt.config_manager import USER_APP_DIR

# Create a logger instance for the application.
logger = logging.getLogger("devt")

# Define log directory and file.
LOGS_DIR = USER_APP_DIR / "logs"
LOG_FILE = LOGS_DIR / "devt.log"

# Ensure the logs directory exists.
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Mapping of log level names to logging constants.
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def configure_logging(log_level: str) -> None:
    """
    Configure the logging level based on the provided log level string.
    """
    level = LOG_LEVELS.get(log_level.upper(), logging.WARNING)
    if level == logging.WARNING and log_level.upper() not in LOG_LEVELS:
        logger.warning("Log level '%s' is not recognized. Defaulting to WARNING.", log_level)
    logger.setLevel(level)


def configure_formatter(format_type: str = "default") -> None:
    """
    Configures the logging formatter for both file and stream handlers.
    """
    if format_type == "detailed":
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    else:
        formatter = logging.Formatter("%(levelname)s: %(message)s")
    
    file_handler = logging.FileHandler(LOG_FILE)
    stream_handler = logging.StreamHandler()
    
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    
    # Clear existing handlers to avoid duplicate log messages.
    if logger.hasHandlers():
        logger.handlers.clear()
    
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
