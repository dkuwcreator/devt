# Parse command-line arguments
param (
    [string]$UserPath = "",  # Allow empty, so it defaults to a logical location
    [switch]$Uninstall
)

# Constants
$OUTPUT_NAME = "devt"
$DEFAULT_INSTALL_DIR = Join-Path $env:USERPROFILE $OUTPUT_NAME  # Logical install location
$DOWNLOAD_URL = "https://github.com/dkuwcreator/devt/releases/latest/download/devt.exe"

# Determine installation directory
$INSTALL_DIR = if ($UserPath) { $UserPath } else { $DEFAULT_INSTALL_DIR }
$EXECUTABLE_PATH = Join-Path $INSTALL_DIR "$OUTPUT_NAME.exe"

# Function to update PATH environment variable
function Update-Path {
    param (
        [string]$TargetPath,
        [switch]$Remove
    )
    
    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if (-not $userPath) {
        $userPath = ""
    }

    if ($Remove) {
        if ($userPath -match [regex]::Escape($TargetPath)) {
            Write-Host "Removing $TargetPath from PATH..."
            $newPath = ($userPath -split ";" | Where-Object {$_ -ne $TargetPath}) -join ";"
            [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Write-Host "Removed $TargetPath from PATH. Restart your terminal or system for changes to take effect."
        }
    } else {
        if ($userPath -notmatch [regex]::Escape($TargetPath)) {
            Write-Host "Adding $TargetPath to PATH..."
            $newPath = if ($userPath) { "$userPath;$TargetPath" } else { $TargetPath }
            [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Write-Host "Added $TargetPath to PATH. Restart your terminal or system for changes to take effect."
        }
    }
}

# Function to install the executable
function Install-App {
    # Ensure the installation directory exists
    if (-not (Test-Path $INSTALL_DIR)) {
        New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
    }
    
    # Download the executable
    Write-Host "Downloading $OUTPUT_NAME from GitHub..."
    Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $EXECUTABLE_PATH -UseBasicParsing
    
    if (Test-Path $EXECUTABLE_PATH) {
        Write-Host "$OUTPUT_NAME successfully installed to $INSTALL_DIR"
    } else {
        Write-Host "Failed to download $OUTPUT_NAME. Check your network connection."
        exit 1
    }

    # Add directory to PATH
    Update-Path -TargetPath $INSTALL_DIR
    $env:PATH = "$env:PATH;$INSTALL_DIR"
    Write-Host "Installation complete. You may need to restart your terminal for PATH changes to take effect."
}

# Function to uninstall the executable
function Uninstall-App {
    if (Test-Path $EXECUTABLE_PATH) {
        Remove-Item -Path $EXECUTABLE_PATH -Force
        Write-Host "Removed $OUTPUT_NAME from $INSTALL_DIR."
    } else {
        Write-Host "$OUTPUT_NAME not found in $INSTALL_DIR. Skipping removal."
    }
    
    # Remove directory from PATH
    Update-Path -TargetPath $INSTALL_DIR -Remove
}

if ($Uninstall) {
    Uninstall-App
} else {
    Install-App
}

# Ensure PATH updates reflect immediately in the session
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
