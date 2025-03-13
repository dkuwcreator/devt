#!/usr/bin/env python3
"""
devt/logger_manager.py

Logger Manager

Provides a class to manage the application's logging configuration.
"""
import logging
from devt.config_manager import USER_APP_DIR

class SafeFileHandler(logging.FileHandler):
    """A FileHandler that gracefully handles OSError exceptions."""
    def emit(self, record):
        try:
            super().emit(record)
        except OSError:
            # Ignore the error silently.
            pass

class LoggerManager:
    LOG_LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    @classmethod
    def from_dict(cls, config: dict) -> "LoggerManager":
        return cls(
            log_level=config.get("log_level", "WARNING"),
            format_type=config.get("log_format", "default"),
        )
    
    def __init__(self, log_level="WARNING", format_type="default"):
        self.logs_dir = USER_APP_DIR / "logs"
        self.log_file = self.logs_dir / "devt.log"
        
        # Ensure the logs directory exists.
        self.logs_dir.mkdir(exist_ok=True)
        
        # Configure the root logger.
        self.configure_logging(log_level)
        self.configure_formatter(format_type)
        
        # Use the root logger for initialization messages.
        root_logger = logging.getLogger()
        root_logger.debug("Logger initialized with log level '%s'.", log_level)
        root_logger.debug("Logging to file: %s", self.log_file)
        root_logger.debug("Logs directory: %s", self.logs_dir)
        
    def configure_logging(self, log_level: str) -> None:
        level = self.LOG_LEVELS.get(log_level.upper(), logging.WARNING)
        if log_level.upper() not in self.LOG_LEVELS:
            logging.getLogger().warning(
                "Log level '%s' is not recognized. Defaulting to WARNING.", log_level
            )
        # Set the root logger's level so all child loggers inherit it.
        logging.getLogger().setLevel(level)
        
    def configure_formatter(self, format_type: str = "default") -> None:
        if format_type == "detailed":
            # Detailed format includes an absolute file path for clickable links.
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        elif format_type == "verbose":
            # Verbose format: using module name instead.
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(module)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        else:
            # Minimal/default format: log level and message.
            formatter = logging.Formatter("%(levelname)s: %(message)s")
        
        file_handler = SafeFileHandler(self.log_file)
        stream_handler = logging.StreamHandler()
        
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)
        
        # Clear existing handlers on the root logger to avoid duplicates.
        root_logger = logging.getLogger()
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
            
        root_logger.addHandler(file_handler)
        root_logger.addHandler(stream_handler)
