$InstallDir = "$env:APPDATA\Doxygen"

Write-Output "Removing Doxygen..."
Remove-Item -Recurse -Force -Path $InstallDir

Write-Output "Removing Doxygen from PATH..."
$DoxygenPath = "$InstallDir\doxygen-1.9.2.windows.x64\bin"
$CurrentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
$NewPath = $CurrentPath -replace [regex]::Escape(";$DoxygenPath"), ""
[System.Environment]::SetEnvironmentVariable("PATH", $NewPath, [System.EnvironmentVariableTarget]::User)

Write-Output "Uninstallation complete. Please restart your terminal."