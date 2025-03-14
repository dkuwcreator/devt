param (
    [string]$Version = "",
    [switch]$Uninstall
)

$InstallDir = Join-Path $env:APPDATA "graphviz"
$binPath = Join-Path $InstallDir "bin"

if ($Uninstall) {
    try {
        if (Test-Path $InstallDir) {
            Write-Output "Removing Graphviz installation..."
            Remove-Item -Path $InstallDir -Recurse -Force
        } else {
            Write-Output "Graphviz is not installed."
        }
        
        Write-Output "Removing Graphviz from PATH..."
        $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
        $newPath = ($currentPath -split ";") -notmatch [regex]::Escape($binPath)
        [System.Environment]::SetEnvironmentVariable("PATH", ($newPath -join ";"), [System.EnvironmentVariableTarget]::User)
        $env:PATH = ($env:PATH -split ";") -notmatch [regex]::Escape($binPath) -join ";"
        
        Write-Output "Uninstallation complete. Please restart your terminal or log off and log back in for the PATH changes to take effect."
    } catch {
        Write-Error "An error occurred during uninstallation: $_"
        exit 1
    }
    exit 0
}

function Get-LatestGraphvizVersion {
    try {
        $downloadPage = Invoke-WebRequest -Uri "https://graphviz.org/download/" -UseBasicParsing
        $versionPattern = [regex]::Escape("graphviz-") + "(\d+\.\d+\.\d+)" + [regex]::Escape(" (64-bit) ZIP archive")
        $versionMatches = [regex]::Matches($downloadPage.Content, $versionPattern)
        if ($versionMatches.Count -gt 0) {
            return $versionMatches[0].Groups[1].Value
        } else {
            throw "No version information found on the download page."
        }
    }
    catch {
        Write-Error "Unable to fetch the latest Graphviz version: $_"
        exit 1
    }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-LatestGraphvizVersion
    Write-Output "No version provided. Using latest version: $Version"
} else {
    Write-Output "Using provided version: $Version"
}

$dirName = "Graphviz-$Version-win64"
$GraphvizUrl = "https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/$Version/windows_10_cmake_Release_$dirName.zip"
$TempZip = Join-Path $env:TEMP "graphviz.zip"
$TempDir = Join-Path $env:TEMP $dirName

try {
    Write-Output "Downloading Graphviz version $Version..."
    Invoke-WebRequest -Uri $GraphvizUrl -OutFile $TempZip -UseBasicParsing

    Write-Output "Extracting Graphviz..."
    Expand-Archive -Path $TempZip -DestinationPath $env:TEMP -Force

    Write-Output "Moving Graphviz to installation directory..."
    if (Test-Path $InstallDir) {
        Write-Output "Installation directory exists, removing it..."
        Remove-Item -Path $InstallDir -Recurse -Force
    }
    Move-Item -Path $TempDir -Destination $InstallDir -Force

    Write-Output "Adding Graphviz to PATH..."
    $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
    if ($currentPath -notlike "*$binPath*") {
        $newPath = "$currentPath;$binPath"
        [System.Environment]::SetEnvironmentVariable("PATH", $newPath, [System.EnvironmentVariableTarget]::User)
        $env:PATH = "$env:PATH;$binPath"
    }

    Write-Output "Cleaning up..."
    Remove-Item -Path $TempZip -Force

    Write-Output "Run 'dot -V' to verify installation."
    dot -V

    Write-Output "Installation complete."
    exit 0
}
catch {
    Write-Error "An error occurred: $_"
    exit 1
}
