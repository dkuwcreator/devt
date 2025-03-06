<#
.SYNOPSIS
   Simplified installation script for DevT using the devt-installer.

.DESCRIPTION
   This script downloads the latest devt-installer from GitHub and executes it.
   It supports an optional installation path and an uninstallation option.
   The installer (downloaded from GitHub) is assumed to perform further configuration,
   such as setting environment variables and updating the PATH.

.PARAMETER InstallPath
   Optional installation directory for DevT. Defaults to "$env:USERPROFILE\devt".

.PARAMETER Uninstall
   Switch parameter to remove the installation directory.
#>

[CmdletBinding()]
param (
    [string]$InstallPath = "",
    [switch]$Uninstall
)

# Constants
$InstallerName      = "devt-installer"
$DefaultInstallDir  = Join-Path $env:USERPROFILE "devt"

# Function: Get-LatestVersion
function Get-LatestVersion {
    $apiUrl = "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
    try {
        # GitHub API requires a User-Agent header
        $releaseInfo = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing -Headers @{ "User-Agent" = "PowerShell" }
        if ($releaseInfo -and $releaseInfo.tag_name) {
            Write-Host "Latest version retrieved from GitHub: $($releaseInfo.tag_name)"
            return $releaseInfo.tag_name
        }
        else {
            Write-Host "API response did not contain a valid tag_name. Defaulting to 'latest'."
            return "latest"
        }
    }
    catch {
        Write-Host "Error retrieving latest version: $_"
        return "latest"
    }
}

# Function: Get-OSSuffix
function Get-OSSuffix {
    # For Windows, the installer file uses "windows.exe" as suffix.
    return "windows.exe"
}

# Determine OS-specific suffix and latest version
$osSuffix      = Get-OSSuffix
$latestVersion = Get-LatestVersion

# Build the download URL for the installer.
# Example: https://github.com/dkuwcreator/devt/releases/download/v0.0.54/devt-installer-v0.0.54-windows.exe
$installerUrl = "https://github.com/dkuwcreator/devt/releases/download/$latestVersion/$InstallerName-$osSuffix"

# Determine installation directory and installer file path
$installDir     = if ($InstallPath) { $InstallPath } else { $DefaultInstallDir }
$installerPath  = Join-Path $installDir "$InstallerName.exe"

function Invoke-Installer {
    # Ensure the installation directory exists.
    if (-not (Test-Path $installDir)) {
        New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    }
    
    Write-Host "Downloading installer from: $installerUrl"
    try {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing -ErrorAction Stop
    }
    catch {
        Write-Host "Error downloading installer: $_"
        exit 1
    }
    
    if (-not (Test-Path $installerPath)) {
        Write-Host "Installer file was not found after download."
        exit 1
    }
    
    Write-Host "Installer downloaded to: $installerPath"
    Write-Host "Launching installer..."
    
    try {
        # Execute the installer with the installation directory as an argument.
        & $installerPath $installDir
    }
    catch {
        Write-Host "Failed to launch installer: $_"
        exit 1
    }
}

function Uninstall-App {
    if (Test-Path $installDir) {
        try {
            Remove-Item -Path $installDir -Recurse -Force
            Write-Host "Successfully uninstalled application from: $installDir"
        }
        catch {
            Write-Host "Error during uninstallation: $_"
            exit 1
        }
    }
    else {
        Write-Host "Installation directory not found: $installDir. Nothing to uninstall."
    }
}

# Main logic: uninstall if requested; otherwise, install.
if ($Uninstall) {
    Uninstall-App
}
else {
    Invoke-Installer
}
