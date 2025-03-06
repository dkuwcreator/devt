#!/bin/bash
set -e

# Default values
INSTALL_PATH=""

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--install-path)
            INSTALL_PATH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--install-path PATH]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# URL to your self-contained Python installer
INSTALLER_URL="https://example.com/devt_installer.py"
TEMP_INSTALLER="/tmp/devt_installer.py"

echo "Downloading installer from $INSTALLER_URL..."
curl -L -o "$TEMP_INSTALLER" "$INSTALLER_URL"
echo "Downloaded installer to $TEMP_INSTALLER"

echo "Running installer..."
if [[ -n "$INSTALL_PATH" ]]; then
    python3 "$TEMP_INSTALLER" install "$INSTALL_PATH"
else
    python3 "$TEMP_INSTALLER" install
fi

echo "Installation complete. You may need to restart your terminal for PATH changes to take effect."
