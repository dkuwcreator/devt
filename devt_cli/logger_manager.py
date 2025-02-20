# ./devt/logger.py
import logging

from devt_cli.config import USER_APP_DIR

LOGS_DIR = USER_APP_DIR / "logs"
LOG_FILE = LOGS_DIR / "devt.log"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Convert the string (e.g., "DEBUG") to a numeric level (e.g., logging.DEBUG).
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
    level = LOG_LEVELS.get(log_level.upper())
    if level is None:
        logger.warning(
            "Log level '%s' is not recognized. Defaulting to WARNING.", log_level
        )
        level = logging.WARNING
    logger.setLevel(level)


def configure_formatter(format_type: str = "default"):
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    if format_type == "detailed":
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    file_handler = logging.FileHandler(LOG_FILE)
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


# Logger setup
logger = logging.getLogger("devt")
