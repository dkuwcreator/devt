import os
import logging
import shutil
import zipfile
from pathlib import Path
from typing import List

from devt.config_manager import SCOPE_TO_REGISTRY_DIR
from devt.utils import find_file_type, load_manifest, merge_configs, save_manifest
from .builder import PackageBuilder, ToolPackage

logger = logging.getLogger(__name__)

class PackageManager:
    """
    Handles file system operations for packages, including importing, moving,
    copying, deleting, and exporting package directories.
    """
    def __init__(self, scope: str) -> None:
        """
        Initialize the PackageManager with a directory for storing packages.
        """
        registry_dir = SCOPE_TO_REGISTRY_DIR[scope]
        self.tools_dir: Path = registry_dir / "tools"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Initialized PackageManager. Tools directory set to: %s", self.tools_dir)

    def _copy_dir(self, source: Path, destination: Path) -> Path:
        """
        Copy the entire package directory from source to destination.
        """
        if source == destination:
            logger.warning("Attempted to copy directory to itself: %s", source)
            return destination
        logger.debug("Copying directory from '%s' to '%s'.", source, destination)
        try:
            shutil.copytree(source, destination)
            logger.debug("Successfully copied directory from '%s' to '%s'.", source, destination)
        except Exception:
            logger.exception("Failed to copy directory from '%s' to '%s'.", source, destination)
            raise
        return destination

    def _delete_dir(self, dir_path: Path) -> None:
        """
        Delete the specified directory and its contents.
        """
        logger.debug("Deleting directory: %s", dir_path)
        try:
            shutil.rmtree(dir_path)
            logger.debug("Successfully deleted directory: %s", dir_path)
        except Exception:
            logger.exception("Failed to delete directory: %s", dir_path)
            raise

    def move_package_to_tools_dir(self, package_dir: Path, group: str = "default", force: bool = False) -> Path:
        """
        Move a package directory into the tools directory under a specified group.
        """
        target_dir = self.tools_dir / group / package_dir.name
        logger.debug("Preparing to move package from '%s' to target '%s'.", package_dir, target_dir)
        if target_dir.exists():
            if target_dir == package_dir:
                logger.warning("Package directory is already in tools directory: %s", target_dir)
                return target_dir
            if force:
                logger.info("Force enabled: Overwriting existing package at '%s'.", target_dir)
                self._delete_dir(target_dir)
            else:
                error_msg = f"Target package directory already exists: {target_dir}"
                logger.error(error_msg)
                raise FileExistsError(error_msg)
        destination = self._copy_dir(package_dir, target_dir)
        logger.info("Package moved to tools directory at '%s'.", destination)
        return destination

    def import_packages(self, source: Path, group: str = None, force: bool = False) -> List[ToolPackage]:
        """
        Import package(s) from the specified source and return a list of ToolPackage objects.
        """
        packages: List[ToolPackage] = []
        errors: List[str] = []
        logger.info("Starting import of package(s) from source: %s", source)

        if source.suffix.lower() == ".zip":
            destination_dir = source.parent / source.stem
            logger.debug("Source is a zip file. Unpacking '%s' to '%s'.", source, destination_dir)
            source = self.unpack_package(source, destination_dir)

        if source.is_file() and source.suffix in [".json", ".yaml", ".yml"]:
            effective_group = group or "default"
            try:
                dest = self.move_package_to_tools_dir(source.parent, effective_group, force)
                pkg = PackageBuilder(dest, effective_group).build_package()
                packages.append(pkg)
                logger.info("Imported package from file '%s' into group '%s'.", source, effective_group)
            except Exception as e:
                error_msg = f"Error building package from '{source}': {e}"
                logger.exception(error_msg)
                errors.append(error_msg)
        elif source.is_dir():
            manifest = find_file_type("manifest", source)
            if manifest:
                effective_group = group or "default"
                try:
                    dest = self.move_package_to_tools_dir(source, effective_group, force)
                    pkg = PackageBuilder(dest, effective_group).build_package()
                    packages.append(pkg)
                    logger.info("Imported package from directory '%s' with manifest '%s'.", source, manifest.name)
                except Exception as e:
                    error_msg = f"Error building package from '{source}': {e}"
                    logger.exception(error_msg)
                    errors.append(error_msg)
            else:
                effective_group = group or source.name
                found_any = False
                for mf in source.rglob("manifest.*"):
                    found_any = True
                    try:
                        dest = self.move_package_to_tools_dir(mf.parent, effective_group, force)
                        pkg = PackageBuilder(dest, effective_group).build_package()
                        packages.append(pkg)
                        logger.info("Imported package from manifest '%s' in group '%s'.", mf.name, effective_group)
                    except Exception as e:
                        error_msg = f"Error building package from manifest '{mf}': {e}"
                        logger.exception(error_msg)
                        errors.append(error_msg)
                if not found_any:
                    warning_msg = f"No manifest found in directory '{source}'. Skipping package import."
                    logger.warning(warning_msg)
        else:
            error_msg = f"Unsupported source type: {source}"
            logger.error(error_msg)
            errors.append(error_msg)

        if errors:
            logger.warning("Completed package import with errors: %s", errors)
        else:
            logger.info("Successfully imported %d package(s) from source: %s", len(packages), source)
        return packages

    def overwrite_packages(self, source: Path, group: str = None) -> List[ToolPackage]:
        """
        Overwrite package(s) by re-importing them from the specified source and
        returning a new list of ToolPackage objects. This function assumes that the
        package directories are already located in the tools directory, so it builds
        the packages directly without moving them.
        """
        packages: List[ToolPackage] = []
        errors: List[str] = []
        logger.info("Starting overwrite of package(s) from source: %s", source)

        if source.suffix.lower() == ".zip":
            destination_dir = source.parent / source.stem
            logger.debug("Source is a zip file. Unpacking '%s' to '%s'.", source, destination_dir)
            source = self.unpack_package(source, destination_dir)

        if source.is_file() and source.suffix.lower() in [".json", ".yaml", ".yml"]:
            effective_group = group or "default"
            try:
                # Use the parent directory of the file as the package directory.
                pkg = PackageBuilder(source.parent, effective_group).build_package()
                packages.append(pkg)
                logger.info("Overwrote package from file '%s' in group '%s'.", source, effective_group)
            except Exception as e:
                error_msg = f"Error overwriting package from '{source}': {e}"
                logger.exception(error_msg)
                errors.append(error_msg)
        elif source.is_dir():
            manifest = find_file_type("manifest", source)
            if manifest:
                effective_group = group or "default"
                try:
                    pkg = PackageBuilder(source, effective_group).build_package()
                    packages.append(pkg)
                    logger.info("Overwrote package from directory '%s' with manifest '%s'.", source, manifest.name)
                except Exception as e:
                    error_msg = f"Error overwriting package from '{source}': {e}"
                    logger.exception(error_msg)
                    errors.append(error_msg)
            else:
                effective_group = group or source.name
                found_any = False
                for mf in source.rglob("manifest.*"):
                    found_any = True
                    try:
                        pkg = PackageBuilder(mf.parent, effective_group).build_package()
                        packages.append(pkg)
                        logger.info("Overwrote package from manifest '%s' in group '%s'.", mf.name, effective_group)
                    except Exception as e:
                        error_msg = f"Error overwriting package from manifest '{mf}': {e}"
                        logger.exception(error_msg)
                        errors.append(error_msg)
                if not found_any:
                    warning_msg = f"No manifest found in directory '{source}'. Skipping package overwrite."
                    logger.warning(warning_msg)
        else:
            error_msg = f"Unsupported source type: {source}"
            logger.error(error_msg)
            errors.append(error_msg)

        if errors:
            logger.warning("Completed package overwrite with errors: %s", errors)
        else:
            logger.info("Successfully overwrote %d package(s) from source: %s", len(packages), source)
        return packages

    def update_package(self, package_dir: Path, group: str = "default") -> ToolPackage:
        """
        Update a package directory by rebuilding the ToolPackage object.
        """
        logger.info("Updating package at directory: %s", package_dir)
        try:
            pkg = PackageBuilder(package_dir, group).build_package()
            logger.info("Package updated successfully for directory: %s", package_dir)
            return pkg
        except Exception as e:
            logger.exception("Failed to update package at '%s': %s", package_dir, e)
            raise

    def delete_package(self, package_dir: Path) -> bool:
        """
        Delete a package directory.
        """
        logger.info("Attempting to delete package directory: %s", package_dir)
        if package_dir.exists():
            try:
                self._delete_dir(package_dir)
                logger.info("Package directory '%s' deleted successfully.", package_dir)
                return True
            except Exception as e:
                logger.exception("Error deleting package directory '%s': %s", package_dir, e)
                return False
        else:
            logger.warning("Package directory '%s' does not exist. Nothing to delete.", package_dir)
            return True

    def export_package(self, package_location: Path, output_path: Path) -> Path:
        """
        Export a package folder as a zip archive.
        """
        if output_path.is_dir():
            output_path = output_path / f"{package_location.name}.zip"
        logger.info("Exporting package from '%s' to zip archive '%s'.", package_location, output_path)
        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in package_location.rglob("*"):
                    if file.is_file():
                        zf.write(file, file.relative_to(package_location))
            logger.info("Package exported successfully to '%s'.", output_path)
        except Exception:
            logger.exception("Failed to export package from '%s' to '%s'.", package_location, output_path)
            raise
        return output_path

    def unpack_package(self, zip_path: Path, destination_dir: Path) -> Path:
        """
        Unpack a package zip archive to the specified destination directory.
        """
        logger.info("Unpacking zip file '%s' to directory '%s'.", zip_path, destination_dir)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(destination_dir)
            logger.info("Unpacked zip file '%s' successfully.", zip_path)
        except Exception:
            logger.exception("Failed to unpack zip file '%s'.", zip_path)
            raise
        return destination_dir

    def update_manifest(self, package_dir: Path, manifest_data: dict) -> None:
        """
        Update the manifest file in the package directory with the specified data.
        """
        logger.info("Updating manifest for package directory: %s", package_dir)
        try:
            manifest_old = load_manifest(package_dir)
            manifest_new = merge_configs(manifest_old, manifest_data)
            save_manifest(package_dir, manifest_new)
            logger.info("Manifest updated successfully for directory: %s", package_dir)
        except Exception:
            logger.exception("Failed to update manifest for directory: %s", package_dir)
            raise
