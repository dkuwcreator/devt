#!/usr/bin/env python3
"""
devt/cli/tool_service.py

Tool Service Commands

Provides commands to import, export, update, and remove tool packages.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from devt.constants import SCOPE_TO_REGISTRY_DIR
from devt.registry.manager import RegistryManager
from devt.package.manager import PackageManager
from devt.utils import scopes_to_registry_dirs

logger = logging.getLogger(__name__)


class ToolService:
    """
    Manages tool packages across different registries.
    """

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "ToolService":
        return cls(ctx.obj.get("registry_dir"))

    def __init__(self, registry_dir: Path) -> None:
        self.registry = RegistryManager(registry_dir)
        self.pkg_manager = PackageManager(registry_dir)

    # -------------------------------------------
    # Tool Import / Export / Update Operations
    # -------------------------------------------

    def import_tool(self, path: Path, group: str, force: bool) -> None:
        """Imports a tool package into the registry."""
        packages = self.pkg_manager.import_packages(path, group=group, force=force)
        for pkg in packages:
            if self.registry.retrieve_package(pkg.command):
                if force:
                    self.registry.unregister_package(pkg.command)
                    logger.debug(
                        "Force option enabled: Overwriting package '%s'.", pkg.command
                    )
                else:
                    logger.info(
                        "Package '%s' already exists; skipping registration.",
                        pkg.command,
                    )
                    continue
            self.registry.register_package(pkg.to_dict())
            logger.info("Registered package '%s' in group '%s'.", pkg.command, group)

    def overwrite_tool(self, path: Path, group: str, force: bool) -> None:
        """Overwrites an existing tool package with a new package."""
        packages = self.pkg_manager.overwrite_packages(path, group=group)
        for pkg in packages:
            if self.registry.retrieve_package(pkg.command):
                if force:
                    self.registry.unregister_package(pkg.command)
                    logger.debug(
                        "Force option enabled: Overwriting package '%s'.", pkg.command
                    )
                else:
                    logger.info(
                        "Package '%s' already exists; skipping registration.",
                        pkg.command,
                    )
                    continue
            self.registry.register_package(pkg.to_dict())
            logger.info("Registered package '%s' in group '%s'.", pkg.command, group)

    def update_tool(self, command: str) -> None:
        """Updates a single tool package."""
        existing_pkg = self.registry.retrieve_package(command)
        if not existing_pkg:
            logger.warning("Tool '%s' does not exist; skipping update.", command)
            raise ValueError(f"Tool '{command}' does not exist in the registry.")

        updated_pkg = self.pkg_manager.update_package(
            Path(existing_pkg["location"]), group=existing_pkg["group"]
        )
        if updated_pkg:
            self.registry.update_package(updated_pkg.to_dict())
            logger.info("Updated tool '%s'.", command)
        else:
            logger.error("Failed to update tool '%s'.", command)

    def update_group_tools(self, group: str) -> None:
        """Updates all tools in a given group."""
        packages = self.registry.package_registry.list_packages(group=group)
        if not packages:
            logger.info("No tools found in group '%s' to update.", group)
            raise ValueError(f"No tools found in group '{group}' to update.")

        for pkg_info in packages:
            self.update_tool(pkg_info["command"])

    def export_tool(
        self, command: str, output: Path, as_zip: bool, force: bool
    ) -> None:
        """Exports a tool package as a ZIP archive."""
        pkg_info = self.registry.package_registry.get_package(command)
        if not pkg_info:
            raise ValueError(f"Tool '{command}' not found in registry.")

        output_path = (Path.cwd() / output).resolve()
        self.pkg_manager.export_package(
            Path(pkg_info["location"]), output_path, as_zip, force
        )
        logger.info("Exported tool '%s' to %s.", command, output_path)

    # -------------------------------------------
    # Tool Removal Operations
    # -------------------------------------------

    def remove_tool(self, command: str) -> None:
        """Removes a tool package from the registry."""
        existing_pkg = self.registry.retrieve_package(command)
        if not existing_pkg:
            logger.warning("Attempted to remove non-existent tool '%s'.", command)
            raise ValueError(f"Tool '{command}' does not exist in the registry.")

        self.registry.unregister_package(command)
        self.pkg_manager.delete_package(Path(existing_pkg["location"]))
        logger.info("Removed tool '%s'.", command)

    def remove_group_tools(self, group: str) -> None:
        """Removes all tool packages in the specified group."""
        packages = self.registry.package_registry.list_packages(group=group)
        if not packages:
            logger.info("No tools found in group '%s' to remove.", group)
            return

        for pkg_info in packages:
            self.remove_tool(pkg_info["command"])

    # -------------------------------------------
    # Tool Listing / Querying
    # -------------------------------------------

    def list_tools(self, **filters: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
        """Returns a dictionary of tools matching the filters."""
        return self.registry.package_registry.list_packages(**filters)

    def get_tool_info(self, command: str) -> Optional[dict]:
        """Retrieves tool information by its unique command."""
        pkg_info = self.registry.retrieve_package(command)
        if not pkg_info:
            logger.warning("Tool '%s' not found in the registry.", command)
            raise ValueError(f"Tool '{command}' not found in the registry.")
        return pkg_info

    # -------------------------------------------
    # Tool Sync Operations
    # -------------------------------------------

    def sync_tools(self) -> None:
        """
        Synchronizes all active tool packages by re-importing them from disk.
        """
        count = 0
        active_packages = self.registry.package_registry.list_packages(active=True)
        for pkg in active_packages:
            pkg_location = Path(pkg["location"])
            new_pkg = self.registry.update_package(pkg_location, pkg["group"])
            self.registry.register_package(new_pkg.to_dict(), force=True)
            count += 1
            logger.info("Synced tool '%s' in group '%s'.", pkg["command"], pkg["group"])
        logger.info("Synced %d tools.", count)


class ToolServiceWrapper:
    """
    Wrapper class for ToolService to use in Typer commands.
    """

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "ToolServiceWrapper":
        return cls(ctx.obj.get("scope"))

    def __init__(self, scope: Optional[str] = None) -> None:
        self.scope = scope
        self.tool_services: Dict[str, ToolService] = self.get_scopes_to_query(scope)
        self.found_scope = None

    def get_scopes_to_query(
        self, scope: Optional[str] = None
    ) -> Dict[str, ToolService]:
        """
        Returns a dictionary mapping scope names to ToolService instances.

        :param scope: If 'user' or 'workspace', returns that single scope.
                      If 'both', 'all', or None, returns both scopes.
        :raises ValueError: If an invalid scope is provided.
        """
        registry_dirs = scopes_to_registry_dirs()

        normalized_scope = scope.lower() if scope else None

        if normalized_scope in (None, "both", "all"):
            logger.info("Querying both 'workspace' and 'user' scopes.")
            return {
                s: ToolService(registry_dir)
                for s, registry_dir in registry_dirs.items()
            }

        if normalized_scope in registry_dirs:
            logger.info("Querying single scope: %s", normalized_scope)
            return {normalized_scope: ToolService(SCOPE_TO_REGISTRY_DIR[normalized_scope])}

        logger.error(
            "Invalid scope provided: %s. Choose 'workspace', 'user', or 'both'.", scope
        )
        raise ValueError("Invalid scope provided. Choose 'workspace', 'user', or 'both'.")

    def import_tool(self, path: Path, group: str, force: bool) -> None:
        """Imports a tool package into the registry."""
        if not self.scope or self.scope == "both":
            raise ValueError("Cannot import tool without specifying a single scope.")
        self.tool_services[self.scope].import_tool(path, group, force)

    def overwrite_tool(self, path: Path, group: str, force: bool) -> None:
        """Overwrites an existing tool package with a new package."""
        if not self.scope or self.scope == "both":
            raise ValueError("Cannot overwrite tool without specifying a single scope.")
        self.tool_services[self.scope].overwrite_tool(path, group, force)

    def update_tool(self, command: str) -> None:
        """Updates a single tool package."""
        for scope, tool_service in self.tool_services.items():
            self.found_scope = scope
            try:
                tool_service.update_tool(command)
                return
            except ValueError:
                continue
        raise ValueError(f"Tool '{command}' not found in any scope.")

    def update_group_tools(self, group: str) -> None:
        """Updates all tools in a given group."""
        for scope, tool_service in self.tool_services.items():
            self.found_scope = scope
            try:
                tool_service.update_group_tools(group)
                return
            except ValueError:
                continue
        raise ValueError(f"No tools found in group '{group}' to update.")

    def export_tool(
        self, command: str, output: Path, as_zip: bool, force: bool
    ) -> None:
        """Exports a tool package as a ZIP archive."""
        for scope, tool_service in self.tool_services.items():
            self.found_scope = scope
            try:
                tool_service.export_tool(command, output, as_zip, force)
                return
            except ValueError:
                continue
        raise ValueError(f"Tool '{command}' not found in any scope.")

    def remove_tool(self, command: str) -> None:
        """Removes a tool package from the registry."""
        for scope, tool_service in self.tool_services.items():
            self.found_scope = scope
            try:
                tool_service.remove_tool(command)
                return
            except ValueError:
                continue
        raise ValueError(f"Tool '{command}' not found in any scope.")

    def remove_group_tools(self, group: str) -> None:
        """Removes all tool packages in the specified group."""
        for scope, tool_service in self.tool_services.items():
            self.found_scope = scope
            try:
                tool_service.remove_group_tools(group)
                return
            except ValueError:
                continue
        raise ValueError(f"No tools found in group '{group}' to remove.")

    def list_tools(self, **filters: Dict[str, Optional[str]]) -> Dict[str, List[dict]]:
        """Returns a dictionary of tools matching the filters."""
        results = {}
        for self.found_scope, tool_service in self.tool_services.items():
            results[self.found_scope] = tool_service.list_tools(**filters)
        return results

    def get_tool_info(self, command: str) -> Optional[dict]:
        """Retrieves tool information by its unique command."""
        for scope, tool_service in self.tool_services.items():
            self.found_scope = scope
            try:
                return tool_service.get_tool_info(command)
            except ValueError:
                continue
        raise ValueError(f"Tool '{command}' not found in any scope.")

    def sync_tools(self) -> None:
        """
        Synchronizes all active tool packages by re-importing them from disk.
        """
        for scope, tool_service in self.tool_services.items():
            self.found_scope = scope
            tool_service.sync_tools()
            logger.info("Synced tools in scope '%s'.", scope)

