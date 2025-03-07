# Retrieves the latest release tag from GitHub
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

# Determines the installer extension based on the platform
function Get-InstallerExtension {
    param(
        [string]$Platform
    )
    switch ($Platform.ToLower()) {
        "windows" { return ".exe" }
        default { return "" }
    }
}

$latestVersion = Get-LatestVersion

$platforms = @("windows", "macos", "linux")
$appTypes = @("", "-installer")
$appName = "devt"

$currentLocation = Get-Location
$installDir = Join-Path $currentLocation "dist"

# Ensure the installation directory exists.
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# Iterate through platforms and app types to build download URLs and fetch installers
foreach ($platform in $platforms) {
    $installerExtension = Get-InstallerExtension -Platform $platform

    foreach ($appType in $appTypes) {
        $versionName = "$latestVersion/$appName-$platform$appType$installerExtension"
        $downloadUrl = "https://github.com/dkuwcreator/devt/releases/download/$versionName"
        $destinationPath = Join-Path $installDir "$appName-$platform$appType$installerExtension"

        Write-Host "Downloading installer from: $downloadUrl"
        try {
            Invoke-WebRequest -Uri $downloadUrl -OutFile $destinationPath -UseBasicParsing -ErrorAction Stop
        }
        catch {
            Write-Host "Error downloading installer: $_"
            exit 1
        }
    }
}