from pathlib import Path
import json
from .logger import logger

class Config:
    """
    A class to manage the configuration for the devt application.
    """

    CONFIG_FILE_NAME = "config.json"

    def __init__(self, app_dir: Path):
        self.app_dir = app_dir
        self.config_file = app_dir / self.CONFIG_FILE_NAME
        self.config = self.load_config()

    def load_config(self) -> dict:
        """
        Load the JSON configuration file. Create a default config if the file doesn't exist.

        Returns:
            dict: The loaded configuration data.
        """
        if not self.config_file.exists():
            logger.warning(f"Configuration file not found. Creating a default config at '{self.config_file}'.")
            self.create_default_config()

        try:
            with self.config_file.open("r") as config_file:
                config = json.load(config_file)
                logger.info(f"Configuration loaded from '{self.config_file}'.")
                return config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file '{self.config_file}': {e}")
        except Exception as e:
            logger.error(f"Failed to load configuration file '{self.config_file}': {e}")

        return {}

    def create_default_config(self):
        """
        Create a default configuration file.
        """
        default_config = {
            "app_data_dir": str(self.app_dir),
            "workspace_dir": str(Path.cwd()),
        }
        self.save_config(default_config)

    def save_config(self, config: dict) -> bool:
        """
        Save the configuration data to the JSON configuration file.

        Args:
            config (dict): The configuration data to save.

        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        try:
            self.app_dir.mkdir(parents=True, exist_ok=True)
            with self.config_file.open("w") as config_file:
                json.dump(config, config_file, indent=4)
                logger.info(f"Configuration saved to '{self.config_file}'.")
                return True
        except Exception as e:
            logger.error(f"Failed to save configuration to '{self.config_file}': {e}")
            return False

    def update_config(self, updates: dict) -> bool:
        """
        Update the configuration file with new data.

        Args:
            updates (dict): The updates to apply to the configuration.

        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        self.config.update(updates)
        return self.save_config(self.config)

    def reset_config(self) -> bool:
        """
        Reset the configuration file to its default state.

        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        logger.info("Resetting configuration file to the default state.")
        self.create_default_config()
        return True

    def get(self, key: str, default=None):
        """
        Get a configuration value by key.

        Args:
            key (str): The configuration key to retrieve.
            default: The default value to return if the key is not found.

        Returns:
            The value of the configuration key, or the default if the key does not exist.
        """
        return self.config.get(key, default)

    def set(self, key: str, value):
        """
        Set a configuration value and save it.

        Args:
            key (str): The configuration key to set.
            value: The value to set for the configuration key.
        """
        self.config[key] = value
        self.save_config(self.config)
        logger.info(f"Configuration updated: {key} = {value}")
