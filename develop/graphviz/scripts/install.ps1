param (
    [string]$Version = ""
)

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

# https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/12.2.1/windows_10_cmake_Release_Graphviz-12.2.1-win64.zip
$GraphvizUrl = "https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/$Version/windows_10_cmake_Release_Graphviz-$Version-win64.zip"
$TempZip = Join-Path $env:TEMP "graphviz.zip"
$InstallDir = Join-Path $env:ProgramFiles "Graphviz"

try {
    Write-Output "Downloading Graphviz version $Version..."
    Invoke-WebRequest -Uri $GraphvizUrl -OutFile $TempZip -UseBasicParsing

    Write-Output "Extracting Graphviz..."
    Expand-Archive -Path $TempZip -DestinationPath $InstallDir -Force

    Write-Output "Adding Graphviz to PATH..."
    $binPath = Join-Path $InstallDir "bin"
    $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::Machine)
    if ($currentPath -notlike "*$binPath*") {
        $newPath = "$currentPath;$binPath"
        [System.Environment]::SetEnvironmentVariable("PATH", $newPath, [System.EnvironmentVariableTarget]::Machine)
    }

    Write-Output "Cleaning up..."
    Remove-Item -Path $TempZip -Force

    Write-Output "Installation complete. Please restart your terminal or log off and log back in for the PATH changes to take effect."
}
catch {
    Write-Error "An error occurred: $_"
    exit 1
}
