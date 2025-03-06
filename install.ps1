param (
    [string]$InstallPath = ""
)

# URL to your self-contained Python installer
$installerUrl = "https://example.com/devt_installer.py"
$tempInstaller = "$env:TEMP\devt_installer.py"

Write-Host "Downloading installer from $installerUrl..."
try {
    Invoke-WebRequest -Uri $installerUrl -OutFile $tempInstaller -UseBasicParsing -ErrorAction Stop
} catch {
    Write-Error "Failed to download installer: $_"
    exit 1
}

Write-Host "Downloaded installer to $tempInstaller"
Write-Host "Running installer..."

# Build command line arguments
if ($InstallPath -ne "") {
    $arguments = "install", $InstallPath
} else {
    $arguments = "install"
}

# Run the installer using the Python interpreter
try {
    & python $tempInstaller @arguments
} catch {
    Write-Error "Error running installer: $_"
    exit 1
}

Write-Host "Installation complete. You may need to restart your terminal for PATH changes to take effect."
