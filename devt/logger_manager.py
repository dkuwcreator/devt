import logging
from devt.config_manager import USER_APP_DIR

logger = logging.getLogger(__name__)

class LoggerManager:
    LOG_LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    def from_dict(cls, config: dict) -> "LoggerManager":
        return cls(
            log_level=config.get("log_level", "WARNING"),
            format_type=config.get("log_format", "default"),
        )
    
    def __init__(self, log_level="WARNING", format_type="default"):
        self.logs_dir = USER_APP_DIR / "logs"
        self.log_file = self.logs_dir / "devt.log"
        
        # Ensure the logs directory exists.
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure logger.
        self.configure_logging(log_level)
        self.configure_formatter(format_type)
        logger.debug("Logger initialized.")
        
    def configure_logging(self, log_level: str) -> None:
        level = self.LOG_LEVELS.get(log_level.upper(), logging.WARNING)
        if log_level.upper() not in self.LOG_LEVELS:
            logger.warning(
                "Log level '%s' is not recognized. Defaulting to WARNING.", log_level
            )
        logger.setLevel(level)
        
    def configure_formatter(self, format_type: str = "default") -> None:
        if format_type == "detailed":
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        else:
            formatter = logging.Formatter("%(levelname)s: %(message)s")
        
        file_handler = logging.FileHandler(self.log_file)
        stream_handler = logging.StreamHandler()
        
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)
        
        # Clear existing handlers to avoid duplicate log messages.
        if logger.hasHandlers():
            logger.handlers.clear()
            
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
