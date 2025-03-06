#!/usr/bin/env python3
"""
Common utility functions for DevT.

Provides generic helpers for:
  - Determining the OS key and suffix
  - Fetching JSON data over HTTPS
  - Downloading files
  - Resolving and validating release versions via the GitHub API
"""

import platform
import ssl
import json
import logging
from pathlib import Path

import urllib3
import truststore
from packaging import version as pkg_version

logger = logging.getLogger(__name__)

# Setup SSL context and HTTP manager (shared across functions)
ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
http = urllib3.PoolManager(ssl_context=ssl_context)

# Base URL for GitHub releases for DevT
GITHUB_API_BASE = "https://api.github.com/repos/dkuwcreator/devt/releases"


def get_os_key() -> str:
    """
    Return a normalized OS key for naming purposes.
    
    For example:
      - Windows → "windows"
      - Linux   → "linux"
      - Darwin  → "macos"
    """
    os_name = platform.system()
    if os_name == "Windows":
        return "windows"
    elif os_name == "Linux":
        return "linux"
    elif os_name == "Darwin":
        return "macos"
    return os_name.lower()


def get_os_suffix() -> str:
    """
    Return the OS-specific suffix for executables.
    
    For Windows, appends '.exe' (e.g. "windows.exe"); for other OSes, returns the OS key.
    """
    key = get_os_key()
    return key + ".exe" if platform.system() == "Windows" else key


def fetch_json(url: str, timeout_connect: float = 10.0, timeout_read: float = 10.0) -> dict:
    """
    Fetch JSON data from the given URL.
    
    Returns a dictionary or an empty dict if an error occurs.
    """
    try:
        response = http.request(
            "GET",
            url,
            timeout=urllib3.Timeout(connect=timeout_connect, read=timeout_read)
        )
        if response.status != 200:
            logger.error("Non-200 response from '%s': %s", url, response.status)
            return {}
        return json.loads(response.data.decode("utf-8"))
    except Exception as err:
        logger.error("Error fetching URL '%s': %s", url, err)
        return {}


def download_file(download_url: str, save_path: Path, timeout_connect: float = 10.0, timeout_read: float = 30.0) -> bool:
    """
    Download a file from the given URL and save it to the specified path.
    
    Returns True on success, False otherwise.
    """
    logger.info("Starting download from %s", download_url)
    try:
        response = http.request(
            "GET",
            download_url,
            timeout=urllib3.Timeout(connect=timeout_connect, read=timeout_read)
        )
        if response.status != 200:
            logger.error("Non-200 response while downloading '%s': %s", download_url, response.status)
            return False
        save_path.write_bytes(response.data)
        logger.info("Downloaded file saved to %s", save_path)
        return True
    except Exception as err:
        logger.error("Error downloading %s: %s", getattr(save_path, 'name', save_path), err)
        return False


def resolve_version(version_str: str = "latest") -> str:
    """
    Retrieve and validate a version from GitHub.
    
    If version_str is "latest" (case-insensitive), queries the GitHub API for the latest release tag.
    Otherwise, it validates that the provided version string is well-formed and exists.
    
    Returns the resolved version string, or an empty string if validation fails.
    """
    if version_str.lower() == "latest":
        api_url = f"{GITHUB_API_BASE}/latest"
        logger.info("Fetching latest version from GitHub API: %s", api_url)
        data = fetch_json(api_url)
        latest = data.get("tag_name", "latest")
        logger.info("Latest version retrieved: %s", latest)
        return latest

    try:
        pkg_version.parse(version_str)
    except Exception:
        logger.error("Invalid version string provided: %s", version_str)
        return ""
    
    release_url = f"{GITHUB_API_BASE}/tags/{version_str}"
    logger.info("Validating version %s with URL: %s", version_str, release_url)
    data = fetch_json(release_url)
    if data:
        logger.info("Version %s exists online.", version_str)
        return version_str
    logger.error("Version %s does not exist online.", version_str)
    return ""
