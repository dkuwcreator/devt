[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$SourcePath = (Get-Location).Path,

    [Parameter(Mandatory = $false)]
    [string]$DestinationPath,

    [Parameter(Mandatory = $false)]
    [switch]$IncludeDate
)

# Inform the user about the archiving process
Write-Host "Creating zip archive for: $SourcePath" -ForegroundColor Cyan

# Remove any trailing backslash
$trimmedSource = $SourcePath.TrimEnd('\')
$sourceName = Split-Path -Path $trimmedSource -Leaf

if ($IncludeDate) {
    $timestamp = Get-Date -Format 'yyyyMMddHHmmss'
    $zipFileBase = "$sourceName" + "_" + "$timestamp.zip"
}
else {
    $zipFileBase = "$sourceName.zip"
}

# Determine full destination file path
if ([string]::IsNullOrEmpty($DestinationPath)) {
    # Save the zip file in the same folder as the source
    $destFolder = Split-Path -Path $trimmedSource -Parent
}
else {
    $destFolder = $DestinationPath
}

$zipFileName = Join-Path -Path $destFolder -ChildPath $zipFileBase

try {
    # Create the zip archive using built-in Compress-Archive cmdlet
    Compress-Archive -Path $SourcePath -DestinationPath $zipFileName -Force
    Write-Host "Zip archive created: $zipFileName" -ForegroundColor Green
}
catch {
    Write-Error "Error creating zip archive: $($_.Exception.Message)"
}