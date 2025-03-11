#!/usr/bin/env python3
"""
devt/config_manager.py

Configuration Manager

Provides a class to manage user and workspace configuration settings.
"""

import logging
from typing import Any, Dict, List

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
    DEFAULT_CONFIG: Dict[str, Any] = {
        "scope": "user",
        "log_level": "WARNING",
        "log_format": "default",
        "auto_sync": True,
        "env_file": ".env",  # New configurable key for environment file name.
    }

    def __init__(self, runtime_options: Dict[str, Any] = None):
        self.runtime_options = runtime_options or {}
        self.workspace_config = self.load_workspace_config()
        self.user_config = self.load_user_config()
        self._update_effective_config()

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns the effective configuration dictionary.
        """
        return self.effective_config

    def load_user_config(self) -> Dict[str, Any]:
        """
        Loads the persistent user configuration.
        If the configuration file does not exist, creates it using DEFAULT_CONFIG.
        Also merges the loaded config with DEFAULT_CONFIG to ensure all keys exist.
        """
        if not self.CONFIG_FILE.exists():
            save_json(self.CONFIG_FILE, self.DEFAULT_CONFIG)
            logger.debug("Created configuration file at %s", self.CONFIG_FILE)
        else:
            config = load_json(self.CONFIG_FILE)
            merged = merge_configs(self.DEFAULT_CONFIG, config)
            save_json(self.CONFIG_FILE, merged)
            logger.debug("Updated configuration file at %s", self.CONFIG_FILE)
        return load_json(self.CONFIG_FILE)

    def load_workspace_config(self) -> Dict[str, Any]:
        """
        Loads workspace configuration from a manifest file.
        Returns an empty dictionary if no workspace manifest is found.
        """
        workspace_config = {}
        workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
        if workspace_file:
            try:
                workspace_data = load_manifest(workspace_file)
                workspace_config = workspace_data.get("config", {})
                logger.debug("Loaded workspace configuration: %s", workspace_config)
            except Exception as e:
                logger.error("Error loading workspace config from %s: %s", workspace_file, e)
        else:
            logger.debug("No workspace manifest found; using empty workspace configuration.")
        return workspace_config

    def _update_effective_config(self) -> None:
        """
        Updates the effective configuration by merging the user, workspace, and runtime options.
        """
        self.effective_config = merge_configs(self.user_config, self.workspace_config, self.runtime_options)

    def _save_user_config(self) -> None:
        """
        Saves the current user configuration to disk and updates the effective configuration.
        """
        save_json(self.CONFIG_FILE, self.user_config)
        self._update_effective_config()

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a configuration value by key, with an optional default if not set.
        """
        return self.effective_config.get(key, default)

    def set_config_value(self, key: str, value: Any) -> None:
        """
        Sets a single configuration value and persists the change.
        """
        self.user_config[key] = value
        self._save_user_config()
        logger.debug("Set config key '%s' to '%s'.", key, value)

    def update_config(self, **kwargs) -> None:
        """
        Updates multiple configuration keys at once.
        Only keys with non-None values are updated.
        """
        for key, value in kwargs.items():
            if value is not None:
                self.set_config_value(key, value)

    def update_config_from_list(self, options: List[str]) -> Dict[str, Any]:
        """
        Parses and updates configuration from a list of KEY=VALUE strings.
        Returns a dictionary of updated configuration options.
        Raises ValueError on parsing or validation errors.
        """
        updates = {}
        for option in options:
            if "=" not in option:
                raise ValueError(f"Invalid format: '{option}'. Expected KEY=VALUE.")
            key, value = option.split("=", 1)
            key = key.strip()
            value = value.strip()

            if key not in self.DEFAULT_CONFIG:
                valid_keys = ", ".join(f"'{k}'" for k in self.DEFAULT_CONFIG.keys())
                raise ValueError(f"Unknown configuration key: '{key}'. Valid keys are: {valid_keys}")

            default_val = self.DEFAULT_CONFIG[key]
            try:
                if isinstance(default_val, bool):
                    value_lower = value.lower()
                    if value_lower in ["true", "1", "yes"]:
                        value = True
                    elif value_lower in ["false", "0", "no"]:
                        value = False
                    else:
                        raise ValueError("Expected a boolean value (true/false).")
                elif isinstance(default_val, int):
                    value = int(value)
                # For strings (and other types), no conversion is needed.
            except Exception as e:
                raise ValueError(f"Error converting value for '{key}': {e}")

            updates[key] = value

        if updates:
            self.update_config(**updates)
        return updates

    def remove_config_key(self, key: str) -> None:
        """
        Removes a configuration key from the persistent user config file.
        """
        if key in self.user_config:
            del self.user_config[key]
            self._save_user_config()
            logger.debug("Removed config key '%s'.", key)
        else:
            logger.debug("Config key '%s' not found; no changes made.", key)

    def reset(self) -> None:
        """
        Resets the user configuration to its default values.
        """
        self.user_config = self.DEFAULT_CONFIG.copy()
        self._save_user_config()
        logger.debug("Configuration reset to default values: %s", self.DEFAULT_CONFIG)
