[CmdletBinding()]
param (
    [string]$InstallPath = "",
    [switch]$Uninstall
)

# Constants
$OUTPUT_NAME         = ".devt"
$INSTALLER_NAME      = "devt_installer"
$DEFAULT_INSTALL_DIR = Join-Path $env:USERPROFILE $OUTPUT_NAME  # Logical install location
$INSTALLER_URL       = "https://github.com/dkuwcreator/devt/releases/latest/download/devt_installer.exe"

# Determine installation directory for installation.
$INSTALL_DIR = if ($InstallPath) { $InstallPath } else { $DEFAULT_INSTALL_DIR }
$INSTALLER_PATH = Join-Path $INSTALL_DIR "$INSTALLER_NAME.exe"

function Install-App {
    if (-not (Test-Path $INSTALL_DIR)) {
        New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
    }

    Write-Host "Downloading installer from GitHub..."
    try {
        Invoke-WebRequest -Uri $INSTALLER_URL -OutFile $INSTALLER_PATH -UseBasicParsing -ErrorAction Stop
    }
    catch {
        Write-Host "Failed to download installer. Check your network connection."
        exit 1
    }

    if (Test-Path $INSTALLER_PATH) {
        Write-Host "Installer successfully downloaded to $INSTALL_DIR"
    }
    else {
        Write-Host "Download completed, but installer file was not found."
        exit 1
    }

    # Run the installer to install the tool.
    # For installation, pass the installation directory so the installer knows where to install.
    Write-Host "Running the installer..."
    & $INSTALLER_PATH install "$INSTALL_DIR"
    Write-Host "Installation complete. You may need to restart your terminal for PATH changes to take effect."
}

function Uninstall-App {
    # For uninstallation, we ignore any provided InstallPath and let the installer determine
    # the installation directory (via its get_install_dir function).
    Write-Host "Running the installer for uninstallation..."
    & $INSTALLER_PATH uninstall
}

if ($Uninstall) {
    Uninstall-App
}
else {
    Install-App
}
