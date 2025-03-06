#!/usr/bin/env bash
#
# DevT Installer Bash Script
#
# This script downloads the latest devt-installer from GitHub and executes it.
# It supports an optional installation path and an uninstall flag.
#
# Usage:
#   ./install.sh [--install-path <path>] [--uninstall]
#

# --- Configuration and Defaults ---

INSTALLER_NAME="devt"
DEFAULT_INSTALL_DIR="$HOME/devt"

# Parse command-line arguments
INSTALL_PATH=""
UNINSTALL=0
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --install-path)
      INSTALL_PATH="$2"
      shift 2 ;;
    --uninstall)
      UNINSTALL=1
      shift ;;
    *)
      echo "Unknown parameter: $1"
      exit 1 ;;
  esac
done

# Use the provided install path or the default
if [[ -z "$INSTALL_PATH" ]]; then
  INSTALL_PATH="$DEFAULT_INSTALL_DIR"
fi

# --- Helper Functions ---

# Determine the OS-specific key.
# For Linux, returns "linux"; for Darwin (macOS), returns "macos"; otherwise, lowercases uname.
get_os_key() {
  local os
  os=$(uname)
  if [[ "$os" == "Darwin" ]]; then
    echo "macos"
  elif [[ "$os" == "Linux" ]]; then
    echo "linux"
  else
    echo "$(echo "$os" | tr '[:upper:]' '[:lower:]')"
  fi
}

# Retrieve the latest release version from GitHub.
# Returns the tag name if available; otherwise, returns "latest".
get_latest_version() {
  local api_url="https://api.github.com/repos/dkuwcreator/devt/releases/latest"
  local json
  json=$(curl -s -H "User-Agent: bash" "$api_url")
  
  # Use jq if available; fallback to grep/sed
  if command -v jq >/dev/null 2>&1; then
    local tag
    tag=$(echo "$json" | jq -r '.tag_name // empty')
    echo "${tag:-latest}"
  else
    local tag
    tag=$(echo "$json" | grep -oP '"tag_name":\s*"\K(.*?)(?=")')
    echo "${tag:-latest}"
  fi
}

# Download a file from a URL to a target path.
download_file() {
  local url="$1"
  local target="$2"
  
  echo "Downloading installer from: $url"
  curl -L -o "$target" "$url"
  if [[ $? -ne 0 ]]; then
    echo "Error downloading installer from: $url"
    exit 1
  fi
  if [[ ! -f "$target" ]]; then
    echo "Installer file was not found after download."
    exit 1
  fi
}

# --- Main Functions ---

# Install the application by downloading and executing the installer.
install_app() {
  # Create installation directory if it doesn't exist
  if [[ ! -d "$INSTALL_PATH" ]]; then
    mkdir -p "$INSTALL_PATH" || { echo "Error creating directory: $INSTALL_PATH"; exit 1; }
  fi
  
  local os_suffix
  os_suffix=$(get_os_key)
  
  local latest_version
  latest_version=$(get_latest_version)
  
  # Build the download URL.
  # Example: https://github.com/dkuwcreator/devt/releases/download/v0.0.54/devt-linux-installer
  local installer_url="${INSTALLER_NAME}-${os_suffix}-installer"
  installer_url="https://github.com/dkuwcreator/devt/releases/download/${latest_version}/${installer_url}"
  
  local installer_path="${INSTALL_PATH}/${INSTALLER_NAME}"
  
  download_file "$installer_url" "$installer_path"
  chmod +x "$installer_path"
  
  echo "Installer downloaded to: $installer_path"
  echo "Launching installer..."
  "$installer_path" "$INSTALL_PATH" || { echo "Failed to execute installer."; exit 1; }
}

# Uninstall the application by removing the installation directory.
uninstall_app() {
  if [[ -d "$INSTALL_PATH" ]]; then
    rm -rf "$INSTALL_PATH" || { echo "Error removing: $INSTALL_PATH"; exit 1; }
    echo "Successfully uninstalled application from: $INSTALL_PATH"
  else
    echo "Installation directory not found: $INSTALL_PATH. Nothing to uninstall."
  fi
}

# --- Execution Logic ---

if [[ "$UNINSTALL" -eq 1 ]]; then
  uninstall_app
else
  install_app
fi
