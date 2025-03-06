import logging
from pathlib import Path
from typing import Dict, List, Optional

import typer

from devt.cli.helpers import (
    get_scopes_to_query,
    get_package_from_registries,
)
from devt.config_manager import SCOPE_TO_REGISTRY_DIR, USER_REGISTRY_DIR, WORKSPACE_REGISTRY_DIR
from devt.registry.manager import RegistryManager
from devt.package.manager import PackageManager

logger = logging.getLogger(__name__)


class ToolService:
    """
    Manages tool packages across different registries.
    """

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "ToolService":
        scope = ctx.obj.get("scope")
        return cls(scope)

    def __init__(
        self,
        scope: str,
    ) -> None:
        self.registry = RegistryManager(scope)
        self.pkg_manager = PackageManager(scope)
        self.scope = scope

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
            return

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
            return

        for pkg_info in packages:
            self.update_tool(pkg_info["command"])

    def export_tool(self, command: str, output: Path) -> None:
        """Exports a tool package as a ZIP archive."""
        pkg_info = self.registry.package_registry.get_package(command)
        if not pkg_info:
            raise ValueError(f"Tool '{command}' not found in {self.scope} registry.")

        output_path = (Path.cwd() / output).resolve()
        self.pkg_manager.export_package(Path(pkg_info["location"]), output_path)
        logger.info("Exported tool '%s' to %s.", command, output_path)

    # -------------------------------------------
    # Tool Removal Operations
    # -------------------------------------------

    def remove_tool(self, command: str) -> None:
        """Removes a tool package from the registry."""
        existing_pkg = self.registry.retrieve_package(command)
        if not existing_pkg:
            logger.warning("Attempted to remove non-existent tool '%s'.", command)
            return

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

    def list_tools(self, filters: Dict[str, Optional[str]]) -> Dict[str, List[dict]]:
        """Returns a dictionary of tools matching the filters."""
        results = {}
        scopes = get_scopes_to_query(self.scope)
        for sc, reg in scopes.items():
            tools = reg.package_registry.list_packages(**filters)
            results[sc] = tools
            logger.info(
                "Found %d tools in %s registry with filters %s.",
                len(tools),
                sc,
                filters,
            )
        return results

    def get_tool_info(self, command: str, scope: Optional[str]) -> Optional[dict]:
        """Retrieves tool information by its unique command."""
        pkg, _ = get_package_from_registries(command, scope)
        return pkg

    # -------------------------------------------
    # Tool Sync Operations
    # -------------------------------------------

    def sync_tools(self) -> Dict[str, int]:
        """
        Synchronizes all active tool packages by re-importing them from disk.
        Returns a dictionary mapping scope names to the number of tools synced.
        """
        sync_counts = {}
        scopes = get_scopes_to_query(self.scope)
        for scope, reg in scopes.items():
            pkg_manager = PackageManager(scope)
            count = 0
            active_packages = reg.package_registry.list_packages(active=True)
            for pkg in active_packages:
                pkg_location = Path(pkg["location"])
                try:
                    new_pkg = pkg_manager.update_package(pkg_location, pkg["group"])
                    reg.register_package(new_pkg.to_dict(), force=True)
                    count += 1
                    logger.info(
                        "Synced tool '%s' in %s registry.", pkg.get("command"), scope
                    )
                except Exception as e:
                    logger.exception("Error syncing tool at %s: %s", pkg_location, e)
                    continue
            sync_counts[scope] = count
            logger.info("Completed syncing %d tools in %s registry.", count, scope)
        return sync_counts
