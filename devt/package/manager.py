# package_manager.py
import os
import logging
import shutil
import zipfile
from pathlib import Path
from typing import List

from devt.utils import find_file_type, load_manifest, merge_configs, save_manifest

from .builder import PackageBuilder, ToolPackage

logger = logging.getLogger(__name__)

class PackageManager:
    """
    Handles file system operations for packages, including importing, moving,
    copying, deleting, and exporting package directories.
    """
    def __init__(self, tools_dir: Path) -> None:
        """
        Initialize the PackageManager with a directory for storing packages.
        """
        self.tools_dir: Path = tools_dir / "tools"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Tools directory is set to: %s", self.tools_dir)

    def _copy_dir(self, source: Path, destination: Path) -> Path:
        """
        Copy the entire package directory from source to destination.
        """
        if source == destination:
            logger.warning("Source and destination are the same: %s", source)
            return destination
        logger.info("Copying package directory '%s' to '%s'", source, destination)
        shutil.copytree(source, destination)
        logger.info("Package directory copied successfully.")
        return destination

    def _delete_dir(self, dir_path: Path) -> None:
        """
        Delete the specified directory and its contents.
        """
        logger.info("Deleting package directory: %s", dir_path)
        shutil.rmtree(dir_path)
        logger.info("Package directory deleted successfully.")

    def move_package_to_tools_dir(self, package_dir: Path, group: str = "default", force: bool = False) -> Path:
        """
        Move a package directory into the tools directory under a specified group.
        """
        target_dir = self.tools_dir / group / package_dir.name
        if target_dir.exists():
            if force:
                logger.info("Overwriting existing package directory: %s", target_dir)
                self._delete_dir(target_dir)
            else:
                logger.error("Package directory already exists: %s", target_dir)
                raise FileExistsError(f"Package directory already exists: {target_dir}")
        return self._copy_dir(package_dir, target_dir)

    def import_package(self, source: Path, group: str = None, force: bool = False) -> List[ToolPackage]:
        """
        Import package(s) from the specified source and return a list of ToolPackage objects.
        """
        packages: List[ToolPackage] = []
        errors: List[str] = []

        if source.suffix.lower() == ".zip":
            destination_dir = source.parent / source.stem
            source = self.unpack_package(source, destination_dir)

        if source.is_file() and source.suffix in [".json", ".yaml", ".yml"]:
            effective_group = group or "default"
            try:
                dest = self.move_package_to_tools_dir(source.parent, effective_group, force)
                pkg = PackageBuilder(dest, effective_group).build_package()
                packages.append(pkg)
            except Exception as e:
                error_msg = f"Error building package from '{source}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        elif source.is_dir():
            manifest = None
            # First try the root directory for a manifest
            manifest = find_file_type("manifest", source)
            if manifest:
                effective_group = group or "default"
                try:
                    dest = self.move_package_to_tools_dir(source, effective_group, force)
                    pkg = PackageBuilder(dest, effective_group).build_package()
                    packages.append(pkg)
                except Exception as e:
                    error_msg = f"Error building package from '{source}': {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            else:
                effective_group = group or source.name
                for mf in source.rglob("manifest.*"):
                    try:
                        dest = self.move_package_to_tools_dir(mf.parent, effective_group, force)
                        pkg = PackageBuilder(dest, effective_group).build_package()
                        packages.append(pkg)
                    except Exception as e:
                        error_msg = f"Error building package from '{mf}': {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)
        else:
            error_msg = f"Unsupported source type: {source}"
            logger.error(error_msg)
            errors.append(error_msg)

        if errors:
            logger.warning("Encountered errors during package import: %s", errors)
        else:
            logger.info("Successfully imported %d package(s) from %s", len(packages), source)
        return packages
    
    def update_package(self, package_dir: Path, group: str = "default") -> ToolPackage:
        """
        Update a package directory by rebuilding the ToolPackage object.
        """
        try:
            logger.info("Updating package directory: %s", package_dir)
            pkg = PackageBuilder(package_dir, group).build_package()
            logger.info("Package directory updated successfully.")
            return pkg
        except Exception as e:
            logger.error("Error updating package directory: %s", e)
            raise

    def delete_package(self, package_dir: Path) -> bool:
        """
        Delete a package directory.
        """
        if package_dir.exists():
            try:
                self._delete_dir(package_dir)
                logger.info("Package directory '%s' deleted successfully.", package_dir)
                return True
            except Exception as e:
                logger.error("Error deleting package directory '%s': %s", package_dir, e)
                return False
        else:
            logger.warning("Package directory '%s' does not exist.", package_dir)
            return True

    def export_package(self, package_location: Path, output_path: Path) -> Path:
        """
        Export a package folder as a zip archive.
        """
        if output_path.is_dir():
            output_path = output_path / f"{package_location.name}.zip"
        logger.info("Exporting package from '%s' to zip file '%s'.", package_location, output_path)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in package_location.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(package_location))
        logger.info("Package exported successfully to '%s'.", output_path)
        return output_path

    def unpack_package(self, zip_path: Path, destination_dir: Path) -> Path:
        """
        Unpack a package zip archive to the specified destination directory.
        """
        logger.info("Unpacking package from zip file '%s' to directory '%s'.", zip_path, destination_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(destination_dir)
        logger.info("Package unpacked successfully to '%s'.", destination_dir)
        return destination_dir

    def update_manifest(self, package_dir: Path, manifest_data: dict) -> None:
        """
        Update the manifest file in the package directory with the specified data.
        """
        manifest_old = load_manifest(package_dir)
        manifest_new = merge_configs(manifest_old, manifest_data)
        save_manifest(package_dir, manifest_new)