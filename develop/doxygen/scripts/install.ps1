param(
    [string]$Version = ""
)

function Get-LatestDoxygenVersion {
    try {
        $releases = Invoke-RestMethod -Uri "https://api.github.com/repos/doxygen/doxygen/releases" -UseBasicParsing
        return $releases | Sort-Object -Property created_at -Descending | Select-Object -First 1 -ExpandProperty tag_name
    }
    catch {
        Write-Error "Unable to fetch the latest Doxygen version: $_"
        exit 1
    }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $ReleaseVersion = Get-LatestDoxygenVersion
    $VersionUnderscore = $ReleaseVersion -replace "^Release_", ""
    $Version = $VersionUnderscore -replace "_", "."
    Write-Output "No version provided. Using latest version: $Version"
} else {
    $VersionUnderscore = $Version -replace "\.", "_"
    $ReleaseVersion = "Release_$Version"
    Write-Output "Using provided version: $Version"
}

$DoxygenUrl = "https://github.com/doxygen/doxygen/releases/download/$ReleaseVersion/doxygen-$Version.windows.x64.bin.zip"

$TempZip = Join-Path $env:TEMP "doxygen.zip"
$InstallDir = Join-Path $env:APPDATA "Doxygen"

try {
    Write-Output "Downloading Doxygen version $Version..."
    Invoke-WebRequest -Uri $DoxygenUrl -OutFile $TempZip -UseBasicParsing

    Write-Output "Extracting Doxygen..."
    Expand-Archive -Path $TempZip -DestinationPath $InstallDir -Force

    Write-Output "Adding Doxygen to PATH..."
    $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
    # If the path already contains the Doxygen bin directory, don't add it again
    if ($currentPath -notlike "*$InstallDir*") {
        $newPath = "$currentPath;$InstallDir"
        [System.Environment]::SetEnvironmentVariable("PATH", $newPath, [System.EnvironmentVariableTarget]::User)
    }
    
    Write-Output "Cleaning up..."
    Remove-Item -Path $TempZip -Force

    Write-Output "Installation complete. Please restart your terminal."
}
catch {
    Write-Error "An error occurred: $_"
    exit 1
}