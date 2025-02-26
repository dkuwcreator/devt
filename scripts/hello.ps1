[CmdletBinding()]
param (
    [Parameter()]
    $Name = 'World'
)

Write-Output "Hello, $Name!"