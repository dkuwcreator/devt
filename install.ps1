[CmdletBinding()]
param (
    [string]$InstallPath = "",
    [switch]$Uninstall
)

# Constants
$OUTPUT_NAME          = "devt"
$INSTALLER_NAME       = "devt_installer"
$DEFAULT_INSTALL_DIR  = Join-Path $env:USERPROFILE $OUTPUT_NAME  # Logical install location

# Function to get the latest release version from GitHub
function Get-LatestVersion {
    $apiUrl = "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
    try {
        # GitHub API requires a User-Agent header; Use -UseBasicParsing for compatibility
        $ReleaseInfo = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing -Headers @{ "User-Agent" = "PowerShell" }
        if ($ReleaseInfo -and $ReleaseInfo.tag_name) {
            Write-Host "Latest version retrieved from GitHub: $($ReleaseInfo.tag_name)"
            return $ReleaseInfo.tag_name
        }
        else {
            Write-Host "Failed to parse latest version from API response."
            return "latest"
        }
    }
    catch {
        Write-Host "Error retrieving latest version: $_"
        return "latest"
    }
}

# Determine the OS-specific suffix (for Windows, we use "windows.exe")
function Get-OSSuffix {
    # This script is intended for Windows installation.
    return "windows.exe"
}

$osSuffix = Get-OSSuffix

# Get the latest version from GitHub
$LatestVersion = Get-LatestVersion

# Build download URLs using the new naming convention.
# Example: https://github.com/dkuwcreator/devt/releases/download/v0.0.54/devt-v0.0.54-windows.exe
$DOWNLOAD_URL  = "https://github.com/dkuwcreator/devt/releases/download/$LatestVersion/$OUTPUT_NAME-$LatestVersion-$osSuffix"
$INSTALLER_URL = "https://github.com/dkuwcreator/devt/releases/download/$LatestVersion/$INSTALLER_NAME-$LatestVersion-$osSuffix"

# Determine installation directory and target file paths
$INSTALL_DIR     = if ($InstallPath) { $InstallPath } else { $DEFAULT_INSTALL_DIR }
$EXECUTABLE_PATH = Join-Path $INSTALL_DIR "$OUTPUT_NAME.exe"        # We install main executable as devt.exe
$INSTALLER_PATH  = Join-Path $INSTALL_DIR "$INSTALLER_NAME.exe"     # And installer as devt_installer.exe

# Function to update the User PATH environment variable
function Update-UserPath {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory)]
        [string]$TargetPath,
        [switch]$Remove
    )

    $userPath  = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $userPath  = if ($userPath) { $userPath } else { "" }
    $pathArray = $userPath.Split([System.IO.Path]::PathSeparator) | Where-Object { $_ -ne "" }

    if ($Remove) {
        if ($pathArray -contains $TargetPath) {
            Write-Host "Removing $TargetPath from PATH..."
            $newPath = ($pathArray | Where-Object { $_ -ne $TargetPath }) -join ";"
            [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Write-Host "Removed $TargetPath from PATH. Restart your terminal for changes to take effect."
        }
    }
    else {
        if (-not ($pathArray -contains $TargetPath)) {
            Write-Host "Adding $TargetPath to PATH..."
            $newPath = if ($userPath) { "$userPath;$TargetPath" } else { $TargetPath }
            [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Write-Host "Added $TargetPath to PATH. Restart your terminal for changes to take effect."
        }
    }

    # Refresh the current session PATH using both Machine and User environment variables
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = "$machinePath;$userPath"
}

# Function to install the application
function Install-App {
    if (-not (Test-Path $INSTALL_DIR)) {
        New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
    }
    else {
        Write-Host "$INSTALL_DIR already exists. Checking for existing files..."
        if (Test-Path $EXECUTABLE_PATH) {
            Write-Host "File $EXECUTABLE_PATH exists and will be overwritten."
        }
        if (Test-Path $INSTALLER_PATH) {
            Write-Host "File $INSTALLER_PATH exists and will be overwritten."
        }
    }

    Write-Host "Downloading $OUTPUT_NAME from GitHub..."
    try {
        Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $EXECUTABLE_PATH -UseBasicParsing -ErrorAction Stop
        Invoke-WebRequest -Uri $INSTALLER_URL -OutFile $INSTALLER_PATH -UseBasicParsing -ErrorAction Stop
    }
    catch {
        Write-Host "Failed to download $OUTPUT_NAME or $INSTALLER_NAME. Check your network connection."
        exit 1
    }

    if ((Test-Path $EXECUTABLE_PATH) -and (Test-Path $INSTALLER_PATH)) {
        Write-Host "$OUTPUT_NAME successfully installed to $INSTALL_DIR"
        Write-Host "$INSTALLER_NAME successfully installed to $INSTALL_DIR"
    }
    else {
        Write-Host "Download completed, but files were not found."
        exit 1
    }

    # Add the installation directory to the User PATH
    Update-UserPath -TargetPath $INSTALL_DIR
    Write-Host "Installation complete. You may need to restart your terminal for PATH changes to take effect."
}

# Function to uninstall the application and remove PATH entry
function Uninstall-App {
    if (Test-Path $INSTALL_DIR) {
        Remove-Item -Path $INSTALL_DIR -Recurse -Force
        Write-Host "Removed $INSTALL_DIR and all its contents."
    }
    else {
        Write-Host "$INSTALL_DIR not found. Skipping removal."
    }

    Update-UserPath -TargetPath $INSTALL_DIR -Remove
}

if ($Uninstall) {
    Uninstall-App
}
else {
    Install-App
}
