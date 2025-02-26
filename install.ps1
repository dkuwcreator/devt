# Parse command-line arguments
param (
    [string]$InstallPath = "", # Allow empty, so it defaults to a logical location
    [switch]$Uninstall
)

# Constants
$OUTPUT_NAME = "devt"
$DEFAULT_INSTALL_DIR = Join-Path $env:USERPROFILE $OUTPUT_NAME  # Logical install location
$DOWNLOAD_URL = "https://github.com/dkuwcreator/devt/releases/latest/download/devt.exe"

# Determine installation directory
$INSTALL_DIR = if ($InstallPath) { $InstallPath } else { $DEFAULT_INSTALL_DIR }
$EXECUTABLE_PATH = Join-Path $INSTALL_DIR "$OUTPUT_NAME.exe"

# Function to update PATH environment variable
function Update-Path {
    param (
        [Parameter(Mandatory)]
        [string]$TargetPath,
        
        [switch]$Remove
    )
    
    # Get the current User PATH and ensure it's a string
    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User") -or ""
    
    # Split the PATH into an array for easier handling
    $pathArray = $userPath.Split(";") | Where-Object { $_ -ne "" }
    
    if ($Remove) {
        if ($pathArray -contains $TargetPath) {
            Write-Host "Removing $TargetPath from PATH..."
            $newPath = ($pathArray | Where-Object { $_ -ne $TargetPath }) -join ";"
            [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Write-Host "Removed $TargetPath from PATH. Restart your terminal or system for changes to take effect."
        }
    }
    else {
        if (-not ($pathArray -contains $TargetPath)) {
            Write-Host "Adding $TargetPath to PATH..."
            $newPath = if ($userPath) { "$TargetPath;$userPath" } else { $TargetPath }
            [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Write-Host "Added $TargetPath to PATH. Restart your terminal or system for changes to take effect."
        }
    }
    
    # Update the current session PATH from both Machine and User environment variables
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$machinePath;$userPath"
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
    }
    else {
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
    if (Test-Path $INSTALL_DIR) {
        Remove-Item -Path $INSTALL_DIR -Recurse -Force
        Write-Host "Removed $INSTALL_DIR and all its contents."
    }
    else {
        Write-Host "$INSTALL_DIR not found. Skipping removal."
    }
    
    # Remove directory from PATH
    Update-Path -TargetPath $INSTALL_DIR -Remove
}

if ($Uninstall) {
    Uninstall-App
}
else {
    Install-App
}
