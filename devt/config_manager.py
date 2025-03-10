import logging
import typer

from devt.constants import USER_APP_DIR, WORKSPACE_APP_DIR
from devt.utils import (
    load_json,
    load_manifest,
    merge_configs,
    find_file_type,
    save_json,
)

logger = logging.getLogger(__name__)

class ConfigManager:
    CONFIG_FILE = USER_APP_DIR / "config.json"
    DEFAULT_CONFIG = {
        "scope": "user",
        "log_level": "WARNING",
        "log_format": "default",
        "auto_sync": True,
    }

    def to_dict(self) -> dict:
        return self.effective_config

    def __init__(self, runtime_options: dict = None):
        self.runtime_options = runtime_options or {}
        self.user_config = self.load_user_config()
        self.workspace_config = self.load_workspace_config()
        self.effective_config = merge_configs(self.user_config, self.workspace_config, self.runtime_options)

    def load_user_config(self) -> dict:
        """
        Creates or updates the persistent user configuration file.
        """
        if not self.CONFIG_FILE.exists():
            save_json(self.CONFIG_FILE, self.DEFAULT_CONFIG)
            logger.debug("Created configuration file at %s", self.CONFIG_FILE)
        else:
            config = load_json(self.CONFIG_FILE)
            updated = merge_configs(self.DEFAULT_CONFIG, config)
            save_json(self.CONFIG_FILE, updated)
            logger.debug("Updated configuration file at %s", self.CONFIG_FILE)
        return load_json(self.CONFIG_FILE)

    def load_workspace_config(self) -> dict:
        """
        Loads workspace configuration from a manifest file.
        """
        workspace_config = {}
        workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
        if workspace_file:
            try:
                workspace_data = load_manifest(workspace_file)
                workspace_config = workspace_data.get("config", {})
                logger.debug("Loaded workspace configuration: %s", workspace_config)
            except Exception as e:
                typer.echo(f"Error loading workspace config: {e}")
                logger.error("Error loading workspace config from %s: %s", workspace_file, e)
        else:
            logger.debug("No workspace manifest found; using empty workspace configuration.")
        return workspace_config

    def set_config_value(self, key: str, value) -> None:
        """
        Sets a configuration value and updates the persistent user config file.
        """
        self.user_config[key] = value
        save_json(self.CONFIG_FILE, self.user_config)
        self.effective_config = merge_configs(self.user_config, self.workspace_config, self.runtime_options)
        logger.debug("Set config key '%s' to '%s'.", key, value)

    def remove_config_key(self, key: str) -> None:
        """
        Removes a configuration key from the persistent user config file.
        """
        if key in self.user_config:
            del self.user_config[key]
            save_json(self.CONFIG_FILE, self.user_config)
            self.effective_config = merge_configs(self.user_config, self.workspace_config, self.runtime_options)
            logger.debug("Removed config key '%s'.", key)
        else:
            logger.debug("Config key '%s' not found; no changes made.", key)
