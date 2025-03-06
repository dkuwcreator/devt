#!/bin/bash
set -e

# Default values
INSTALL_PATH=""
UNINSTALL=0

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--install-path)
            INSTALL_PATH="$2"
            shift 2
            ;;
        -u|--uninstall)
            UNINSTALL=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--install-path PATH] [--uninstall]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Constants
OUTPUT_NAME="devt"
INSTALLER_NAME="devt_installer"
DEFAULT_INSTALL_DIR="$HOME/$OUTPUT_NAME"

# Determine installation directory
if [[ -z "$INSTALL_PATH" ]]; then
    INSTALL_DIR="$DEFAULT_INSTALL_DIR"
else
    INSTALL_DIR="$INSTALL_PATH"
fi

# Determine OS suffix using uname:
OS_TYPE=$(uname -s)
if [[ "$OS_TYPE" == "Linux" ]]; then
    OS_SUFFIX="linux"
elif [[ "$OS_TYPE" == "Darwin" ]]; then
    OS_SUFFIX="macos"
else
    echo "Unsupported OS: $OS_TYPE"
    exit 1
fi

# Function to get the latest version from GitHub
get_latest_version() {
    # Requires curl and jq installed.
    LATEST_VERSION=$(curl -s "https://api.github.com/repos/dkuwcreator/devt/releases/latest" \
                     -H "User-Agent: Bash Installer" | jq -r .tag_name)
    if [[ -z "$LATEST_VERSION" || "$LATEST_VERSION" == "null" ]]; then
        echo "latest"
    else
        echo "$LATEST_VERSION"
    fi
}

LATEST_VERSION=$(get_latest_version)
echo "Latest version is: $LATEST_VERSION"

# Build download URLs using the new naming convention:
# For example:
#   https://github.com/dkuwcreator/devt/releases/download/v0.0.54/devt-v0.0.54-linux
#   https://github.com/dkuwcreator/devt/releases/download/v0.0.54/devt_installer-v0.0.54-linux
DOWNLOAD_URL="https://github.com/dkuwcreator/devt/releases/download/${LATEST_VERSION}/${OUTPUT_NAME}-${LATEST_VERSION}-${OS_SUFFIX}"
INSTALLER_URL="https://github.com/dkuwcreator/devt/releases/download/${LATEST_VERSION}/${INSTALLER_NAME}-${LATEST_VERSION}-${OS_SUFFIX}"

# Target file paths (no extension for Linux/macOS)
EXECUTABLE_PATH="$INSTALL_DIR/$OUTPUT_NAME"
INSTALLER_PATH="$INSTALL_DIR/$INSTALLER_NAME"

# Function to update the User PATH in ~/.bashrc and ~/.zshrc if preferred
update_path() {
    local shell=("$HOME/.bashrc" "$HOME/.zshrc")
    for n in ${shell[@]};
    do
        if grep -q "$INSTALL_DIR" "$n"; then
            echo "$INSTALL_DIR is already in your PATH in $n."
        else
            echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$n"
            echo "Added $INSTALL_DIR to PATH in $n. Restart your terminal for changes to take effect."
        fi
    done
}

# Function to install the application
install_app() {
    mkdir -p "$INSTALL_DIR"
    echo "Installing to $INSTALL_DIR..."

    echo "Downloading $OUTPUT_NAME from:"
    echo "$DOWNLOAD_URL"
    curl -L -o "$EXECUTABLE_PATH" "$DOWNLOAD_URL" || { echo "Download failed for $OUTPUT_NAME"; exit 1; }

    echo "Downloading $INSTALLER_NAME from:"
    echo "$INSTALLER_URL"
    curl -L -o "$INSTALLER_PATH" "$INSTALLER_URL" || { echo "Download failed for $INSTALLER_NAME"; exit 1; }

    if [[ -f "$EXECUTABLE_PATH" && -f "$INSTALLER_PATH" ]]; then
        echo "$OUTPUT_NAME and $INSTALLER_NAME successfully installed to $INSTALL_DIR"
    else
        echo "Download completed, but files were not found."
        exit 1
    fi

    update_path
    echo "Installation complete."
}

# Function to uninstall the application
uninstall_app() {
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        echo "Removed $INSTALL_DIR and all its contents."
    else
        echo "$INSTALL_DIR not found. Skipping removal."
    fi
    echo "Please remove $INSTALL_DIR from your PATH if needed."
}

if [[ $UNINSTALL -eq 1 ]]; then
    uninstall_app
else
    install_app
fi
