param(
    [string]$Version = "",
    [switch]$Uninstall
)

$InstallDir = Join-Path $env:APPDATA "Doxygen"
$binPath = $InstallDir

# A function to update environment variables
function Update-Path {
    # Retrieve machine and user PATH variables
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::Machine)
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
    
    # Ensure paths are trimmed and free of extra semicolons
    $machinePath = $machinePath.Trim().TrimEnd(';')
    $userPath    = $userPath.Trim().TrimStart(';')
    
    # Combine the paths if both exist
    if (-not [string]::IsNullOrEmpty($machinePath) -and -not [string]::IsNullOrEmpty($userPath)) {
        $env:PATH = "$machinePath;$userPath"
    }
    elseif (-not [string]::IsNullOrEmpty($machinePath)) {
        $env:PATH = $machinePath
    }
    else {
        $env:PATH = $userPath
    }
}


if ($Uninstall) {
    try {
        if (Test-Path $InstallDir) {
            Write-Output "Removing Doxygen installation..."
            Remove-Item -Path $InstallDir -Recurse -Force
        } else {
            Write-Output "Doxygen is not installed."
        }
        
        Write-Output "Removing Doxygen from PATH..."
        $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
        $newPath = ($currentPath -split ";") -notmatch [regex]::Escape($binPath)
        [System.Environment]::SetEnvironmentVariable("PATH", ($newPath -join ";"), [System.EnvironmentVariableTarget]::User)
        Update-Path
        
        Write-Output "Uninstallation complete. Please restart your terminal or log off and log back in for the PATH changes to take effect."
    } catch {
        Write-Error "An error occurred during uninstallation: $_"
        exit 1
    }
    exit 0
}

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
    $VersionUnderscore = $Version -replace "\\.", "_"
    $ReleaseVersion = "Release_$Version"
    Write-Output "Using provided version: $Version"
}

$DoxygenUrl = "https://github.com/doxygen/doxygen/releases/download/$ReleaseVersion/doxygen-$Version.windows.x64.bin.zip"
$TempZip = Join-Path $env:TEMP "doxygen.zip"

try {
    Write-Output "Downloading Doxygen version $Version..."
    Invoke-WebRequest -Uri $DoxygenUrl -OutFile $TempZip -UseBasicParsing

    Write-Output "Extracting Doxygen..."
    Expand-Archive -Path $TempZip -DestinationPath $InstallDir -Force

    Write-Output "Adding Doxygen to PATH..."
    $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
    if ($currentPath -notlike "*$binPath*") {
        $newPath = "$currentPath;$binPath"
        [System.Environment]::SetEnvironmentVariable("PATH", $newPath, [System.EnvironmentVariableTarget]::User)
        Update-Path
    }
    
    Write-Output "Cleaning up..."
    Remove-Item -Path $TempZip -Force

    Write-Output "Run 'doxygen --version' to verify installation."
    doxygen --version

    Write-Output "Installation complete."
    exit 0
}
catch {
    Write-Error "An error occurred: $_"
    exit 1
}