param(
    [string[]]$PathsToRemove = @(),  # Provide one or more paths to remove
    [switch]$UpdatePath              # Switch to update PATH (if not provided, no change is made)
)

# Define known path replacements for shorthand environment variables
$pathReplacements = @{
    # "$env:APPDATA"      = "%APPDATA%"
    # "$env:LOCALAPPDATA" = "%LOCALAPPDATA%"
    # "$env:ProgramFiles"      = "%ProgramFiles%"
    # "$env:ProgramFiles(x86)" = "%ProgramFiles(x86)%"
    # "$env:USERPROFILE"       = "%USERPROFILE%"
    # "$env:SystemRoot"        = "%SystemRoot%"
}

# Get the current PATH variable from the user registry
$path = [System.Environment]::GetEnvironmentVariable("PATH", "User")
Write-Host "🔍 Original User PATH:"
Write-Host $path

# Split the PATH into individual paths
$paths = $path -split ';'

# Normalize paths to:
# 1. Use backslashes
# 2. Trim whitespace
# 3. Expand environment variables
$normalizedPaths = $paths | ForEach-Object { 
    $p = $_ -replace '/', '\' -replace '\\\\+', '\'  # Convert to backslashes, remove duplicate slashes
    $p = [System.Environment]::ExpandEnvironmentVariables($p)  # Expand environment variables
    $p.Trim()  # Remove extra spaces
}

# Expand paths to remove (for proper case-insensitive comparison)
$expandedPathsToRemove = $PathsToRemove | ForEach-Object { [System.Environment]::ExpandEnvironmentVariables($_).ToLower() }

# Filter out:
# - Empty paths
# - Non-existent paths
# - Paths in the predefined removal list (case-insensitive)
$filteredPaths = $normalizedPaths | Where-Object {
    ($_ -ne '') -and (Test-Path $_) -and ($expandedPathsToRemove -notcontains $_.ToLower())
} | Select-Object -Unique

# Replace full paths with environment variable equivalents
$shortenedPaths = $filteredPaths | ForEach-Object {
    $currentPath = $_
    foreach ($fullPath in $pathReplacements.Keys) {
        if ($currentPath -like "$fullPath*") {
            $currentPath = $currentPath -replace [regex]::Escape($fullPath), $pathReplacements[$fullPath]
            break
        }
    }
    $currentPath
}

Write-Host "`n✅ Cleaned and Shortened PATH:"
Write-Host $($shortenedPaths -join ';')

# Display removed paths
$removedPaths = $normalizedPaths | Where-Object {
    ($_ -eq '') -or (-not (Test-Path $_)) -or ($expandedPathsToRemove -contains $_.ToLower())
}

Write-Host "`n🔄 Removed or invalid paths:"
$removedPaths | ForEach-Object { Write-Host $_ }

if ($UpdatePath) {
    # Join the cleaned paths back together
    $updatedPath = $shortenedPaths -join ';'

    # Update the PATH variable in the user registry
    [System.Environment]::SetEnvironmentVariable("PATH", $updatedPath, "User")

    # Also update the current session PATH
    $env:Path = $updatedPath

    Write-Host "`n✔ PATH variable updated successfully!"
    Write-Host "Restart your terminal for the changes to fully apply."
}
else {
    Write-Host "`n✖ PATH variable update skipped. Use -UpdatePath to make changes."
}
