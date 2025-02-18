import argparse
import logging
import shutil
import zipfile
from pathlib import Path

import yaml

from registry_manager import Registry
from package_manager import PackageManager, PackageBuilder

# Define global registry directories.
USER_REGISTRY_DIR = Path("./my_registry")
WORKSPACE_REGISTRY_DIR = Path("./workspace_registry")

def export_package(package_location: Path, output_path: Path):
    """
    Export a package folder as a zip archive.
    """
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in package_location.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(package_location))
    return output_path

def move_package(pm: PackageManager, source_registry: Registry, target_registry: Registry, package_command: str, logger: logging.Logger):
    """
    Move a package from one registry (source) to another (target).
    
    This function copies the package folder from the source registry into the target registry,
    re-reads the package (and its scripts) from the copied folder, adds it to the target registry,
    and then removes it from the source registry.
    """
    package = source_registry.get_package(package_command)
    if not package:
        logger.error("Package '%s' not found in the source registry.", package_command)
        return False

    target_tools_dir = target_registry.db_path / "tools"
    target_tools_dir.mkdir(parents=True, exist_ok=True)
    current_location = Path(package["location"])
    target_location = target_tools_dir / current_location.name

    try:
        shutil.copytree(current_location, target_location)
    except Exception as e:
        logger.error("Error copying package folder: %s", e)
        return False

    try:
        new_package = PackageBuilder(target_location).build_package()
        target_registry.add_package(
            new_package.command,
            new_package.name,
            new_package.description,
            str(new_package.location),
            new_package.dependencies,
        )
        for script_name, script in new_package.scripts.items():
            try:
                target_registry.add_script(new_package.command, script_name, script)
            except Exception as e:
                logger.error("Error adding script '%s' to target registry: %s", script_name, e)
    except Exception as e:
        logger.error("Error adding package to target registry: %s", e)
        return False

    try:
        pm.remove_package(package_command)
        shutil.rmtree(current_location)
        logger.info("Package '%s' moved successfully.", package_command)
        return True
    except Exception as e:
        logger.error("Error removing package from source registry: %s", e)
        return False

def copy_package_to_workspace(pm, source_registry, target_registry, package_command, logger: logging.Logger):
    """
    Copy a package from the user registry to the workspace registry for customization,
    keeping the same command as the original.
    
    Steps:
      1. Retrieve the package from the source (user) registry.
      2. Copy its folder from the source registry's tools folder into the target registry's tools folder,
         keeping the same folder name.
      3. Re-read the package from the new folder, update its description to indicate customization,
         and add (or update) the package record (and its scripts) into the target registry.
      4. The original package remains intact in the user registry.
    """
    package = source_registry.get_package(package_command)
    if not package:
        logger.error("Package '%s' not found in source registry.", package_command)
        return False

    target_tools_dir = target_registry.db_path / "tools"
    target_tools_dir.mkdir(parents=True, exist_ok=True)
    current_location = Path(package["location"])
    # Keep the same folder name (and therefore command)
    target_location = target_tools_dir / current_location.name

    # Remove target location if it exists.
    if target_location.exists():
        shutil.rmtree(target_location)
    try:
        shutil.copytree(current_location, target_location)
    except Exception as e:
        logger.error("Error copying package folder: %s", e)
        return False

    try:
        # Re-read the package from the new location.
        new_pkg = PackageBuilder(target_location).build_package()
        # Keep the same command, but update the description to indicate customization.
        new_pkg.description = f"{new_pkg.description} (Customized)"
        
        # Add or update the package record in the target registry.
        try:
            target_registry.add_package(
                new_pkg.command,
                new_pkg.name,
                new_pkg.description,
                str(new_pkg.location),
                new_pkg.dependencies,
            )
        except Exception as e:
            logger.info("Package record already exists in target registry. Updating it.")
            target_registry.update_package(
                new_pkg.command,
                new_pkg.name,
                new_pkg.description,
                str(new_pkg.location),
                new_pkg.dependencies,
            )
        
        # Add or update each script.
        for script_name, script in new_pkg.scripts.items():
            existing = target_registry.get_script(new_pkg.command, script_name)
            if existing:
                target_registry.update_script(new_pkg.command, script_name, script)
                logger.info("Updated script '%s' for customized package.", script_name)
            else:
                target_registry.add_script(new_pkg.command, script_name, script)
                logger.info("Added script '%s' for customized package.", script_name)
    except Exception as e:
        logger.error("Error adding customized package to target registry: %s", e)
        return False

    logger.info("Package '%s' copied to workspace (customized) successfully.", package_command)
    return True

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description="Simple Package Manager")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # import subcommand.
    import_parser = subparsers.add_parser("import", help="Import a package from a manifest file")
    import_parser.add_argument("manifest", type=Path, help="Path to the package manifest file (YAML/JSON)")

    # list subcommand.
    list_parser = subparsers.add_parser("list", help="List all imported packages (user scope)")

    # run subcommand.
    run_parser = subparsers.add_parser("run", help="Run a script from a package")
    run_parser.add_argument("package_command", type=str, help="Package command (unique identifier)")
    run_parser.add_argument("script_name", type=str, help="Name of the script to run")
    run_parser.add_argument("--extra_args", nargs=argparse.REMAINDER, default=[],
                            help="Extra arguments to pass to the script")
    run_parser.add_argument("--scope", choices=["user", "workspace"], default=None,
                            help="Scope to search for the package. If not provided, search user then workspace.")

    # remove subcommand.
    remove_parser = subparsers.add_parser("remove", help="Remove a package from a registry")
    remove_parser.add_argument("package_command", type=str, help="Package command to remove")
    remove_parser.add_argument("--scope", choices=["user", "workspace"], default=None,
                               help="Scope from which to remove the package. Defaults to user, then workspace if not found.")

    # move subcommand.
    move_parser = subparsers.add_parser("move", help="Move a package between scopes")
    move_parser.add_argument("package_command", type=str, help="Package command to move")
    move_parser.add_argument("--to", dest="target_scope", choices=["user", "workspace"], required=True,
                             help="Target scope: 'user' or 'workspace'")

    # export subcommand.
    export_parser = subparsers.add_parser("export", help="Export a package as a zip archive")
    export_parser.add_argument("package_command", type=str, help="Package command to export")
    export_parser.add_argument("--output", type=Path, required=True, help="Output zip file path")

    # customize subcommand.
    customize_parser = subparsers.add_parser("customize", help="Copy a package from user to workspace for customization")
    customize_parser.add_argument("package_command", type=str, help="Package command to customize (from user registry)")
    customize_parser.add_argument("--new_command", type=str, default=None,
                                  help="New command for the customized package (default: original_command_custom)")

    # update subcommand.
    update_parser = subparsers.add_parser("update", help="Update a package in a registry")
    update_parser.add_argument("package_command", type=str, help="Package command to update")
    update_parser.add_argument("--manifest", type=Path, default=None,
                               help="Path to the updated manifest file. If not provided, "
                                    "the program will use <package_folder>/manifest.yaml")
    update_parser.add_argument("--scope", choices=["user", "workspace"], default="user",
                               help="Scope to update: 'user' (default) or 'workspace'")

    args = parser.parse_args()

    # Create registries.
    user_registry = Registry(USER_REGISTRY_DIR)
    workspace_registry = Registry(WORKSPACE_REGISTRY_DIR)
    pm = PackageManager(user_registry)

    if args.subcommand == "import":
        manifest_path = args.manifest
        if not manifest_path.exists():
            logger.error("Manifest file not found at %s", manifest_path)
            return
        logger.info("Importing package from %s", manifest_path)
        try:
            pm.import_package(manifest_path)
            logger.info("Package imported successfully into user registry.")
        except Exception as e:
            logger.error("Error importing package: %s", e)

    elif args.subcommand == "list":
        packages = pm.list_packages()
        if packages:
            logger.info("Registered packages in user registry: %s", packages)
        else:
            logger.info("No packages registered in user registry.")

    elif args.subcommand == "run":
        package_command = args.package_command
        script_name = args.script_name
        scope_arg = args.scope

        package = None
        used_scope = None
        pm_run = None

        if scope_arg:
            # Use the specified registry.
            if scope_arg == "user":
                package = user_registry.get_package(package_command)
                used_scope = "user"
                pm_run = PackageManager(user_registry)
            elif scope_arg == "workspace":
                workspace_reg = Registry(WORKSPACE_REGISTRY_DIR)
                package = workspace_reg.get_package(package_command)
                used_scope = "workspace"
                pm_run = PackageManager(workspace_reg)
        else:
            # By default, check workspace registry first.
            workspace_reg = Registry(WORKSPACE_REGISTRY_DIR)
            package = workspace_reg.get_package(package_command)
            if package:
                used_scope = "workspace"
                pm_run = PackageManager(workspace_reg)
            else:
                # If not found in workspace, then check user registry.
                package = user_registry.get_package(package_command)
                if package:
                    used_scope = "user"
                    pm_run = PackageManager(user_registry)

        if not package:
            logger.error("Package '%s' not found in any registry.", package_command)
            return

        base_dir = Path(package["location"])
        if not base_dir.exists():
            logger.error("The package base directory '%s' does not exist.", base_dir)
            return

        logger.info("Running script '%s' for package '%s' from %s registry using base_dir '%s'", 
                    script_name, package_command, used_scope, base_dir)
        try:
            pm_run.run_script(package_command, script_name, base_dir, extra_args=args.extra_args)
        except Exception as e:
            logger.error("Error running script: %s", e)

    elif args.subcommand == "remove":
        package_command = args.package_command
        scope_arg = args.scope
        package = None
        used_scope = None
        pm_remove = None

        if scope_arg:
            if scope_arg == "user":
                package = user_registry.get_package(package_command)
                used_scope = "user"
                pm_remove = PackageManager(user_registry)
            elif scope_arg == "workspace":
                workspace_reg = Registry(WORKSPACE_REGISTRY_DIR)
                package = workspace_reg.get_package(package_command)
                used_scope = "workspace"
                pm_remove = PackageManager(workspace_reg)
        else:
            package = user_registry.get_package(package_command)
            if package:
                used_scope = "user"
                pm_remove = PackageManager(user_registry)
            else:
                workspace_reg = Registry(WORKSPACE_REGISTRY_DIR)
                package = workspace_reg.get_package(package_command)
                if package:
                    used_scope = "workspace"
                    pm_remove = PackageManager(workspace_reg)

        if not package:
            logger.error("Package '%s' not found in any registry.", package_command)
            return

        logger.info("Removing package '%s' from %s registry...", package_command, used_scope)
        try:
            pm_remove.remove_package(package_command)
            logger.info("Package '%s' removed from registry.", package_command)
            package_folder = Path(package["location"])
            if package_folder.exists():
                shutil.rmtree(package_folder)
                logger.info("Removed package folder: %s", package_folder)
            else:
                logger.warning("Package folder %s does not exist.", package_folder)
        except Exception as e:
            logger.error("Error removing package: %s", e)

    elif args.subcommand == "move":
        package_command = args.package_command
        target_scope = args.target_scope
        logger.info("Moving package '%s' to '%s' scope...", package_command, target_scope)
        if target_scope == "workspace":
            success = move_package(pm, user_registry, workspace_registry, package_command, logger)
        else:  # Moving from workspace to user.
            source_registry = workspace_registry
            target_registry = user_registry
            pm_workspace = PackageManager(source_registry)
            success = move_package(pm_workspace, source_registry, target_registry, package_command, logger)
        if success:
            logger.info("Package '%s' moved successfully to %s scope.", package_command, target_scope)
        else:
            logger.error("Failed to move package '%s' to %s scope.", package_command, target_scope)

    elif args.subcommand == "export":
        package_command = args.package_command
        output_path = args.output
        if output_path.is_dir():
            output_path = output_path / f"{package_command}.zip"
        package = user_registry.get_package(package_command)
        scope = "user"
        if not package:
            workspace_reg = Registry(WORKSPACE_REGISTRY_DIR)
            package = workspace_reg.get_package(package_command)
            scope = "workspace"
        if not package:
            logger.error("Package '%s' not found in any registry.", package_command)
            return
        package_location = Path(package["location"])
        if not package_location.exists():
            logger.error("Package folder '%s' does not exist.", package_location)
            return
        try:
            export_package(package_location, output_path)
            logger.info("Exported package '%s' from %s registry to %s", package_command, scope, output_path)
        except Exception as e:
            logger.error("Error exporting package: %s", e)

    elif args.subcommand == "customize":
        package_command = args.package_command
        # In this version, we do not rename the tool.
        logger.info("Customizing package '%s' (keeping same command) into workspace...", package_command)
        success = copy_package_to_workspace(pm, user_registry, workspace_registry, package_command, logger)
        if success:
            logger.info("Package '%s' customized successfully in workspace.", package_command)
        else:
            logger.error("Failed to customize package '%s'.", package_command)

    elif args.subcommand == "update":
        package_command = args.package_command
        scope = args.scope
        # Determine which registry to update.
        if scope == "user":
            reg_to_update = user_registry
            pm_update = PackageManager(user_registry)
        else:
            reg_to_update = Registry(WORKSPACE_REGISTRY_DIR)
            pm_update = PackageManager(reg_to_update)
        
        # Retrieve the package record from the chosen registry.
        package = reg_to_update.get_package(package_command)
        if not package:
            logger.error("Package '%s' not found in %s registry.", package_command, scope)
            return
        
        # Determine the manifest file:
        # If the user provided a manifest via --manifest, use it.
        # Otherwise, assume the manifest is located at <package_folder>/manifest.yaml.
        if args.manifest:
            manifest_path = args.manifest
        else:
            manifest_path = Path(package["location"]) / "manifest.yaml"
        
        if not manifest_path.exists():
            logger.error("Manifest file not found at %s", manifest_path)
            return

        logger.info("Updating package '%s' from manifest %s in %s registry...", package_command, manifest_path, scope)
        try:
            pm_update.update_package(manifest_path)
            logger.info("Package updated successfully in %s registry.", scope)
        except Exception as e:
            logger.error("Error updating package: %s", e)

if __name__ == "__main__":
    main()
