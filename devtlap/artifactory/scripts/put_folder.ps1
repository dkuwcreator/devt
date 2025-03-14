[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$UserName,

    [Parameter(Mandatory=$false)]
    [string]$AccessToken
)

if (-not $UserName) { 
    $UserName = $env:USERNAME 
    if (-not $UserName) {
        $UserName = Read-Host "Enter username"
    }
}

if (-not $AccessToken) { 
    $AccessToken = $env:ACCESSTOKEN
    if (-not $AccessToken) {
        $AccessToken = Read-Host "Enter accesstoken"
    }
}

# Create the basic authorization header
function Get-CredentialHeader {
    param(
        [string]$UserName,
        [string]$AccessToken
    )
    $rawCreds = "$UserName`:$AccessToken"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawCreds)
    $base64Creds = [System.Convert]::ToBase64String($bytes)
    return "Basic $base64Creds"
}

$credentialHeader = Get-CredentialHeader -UserName $UserName -AccessToken $AccessToken

# Fetch latest tags and determine latest version
git fetch --tags

# Get sorted tags and choose the latest
$tags = git tag --sort=version:refname | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
if (-not $tags) {
    Write-Error "No tags found."
    exit 1
}

$latestTag = $tags[-1]

$currentLocation = Get-Location
Write-Host "Current location: $currentLocation"

# Get the dist folder path
$distFolder = Join-Path $currentLocation "dist"
if (-not (Test-Path $distFolder)) {
    Write-Error "dist folder not found at: $distFolder"
    exit 1
}

# Loop over each file within the dist folder (including subdirectories if any)
$files = Get-ChildItem -Path $distFolder -File -Recurse
if (-not $files) {
    Write-Error "No files found in $distFolder"
    exit 1
}

foreach ($file in $files) {
    # Create a REST endpoint URL. The file name is appended to the URL.
    $uri = "https://artifactory.insim.biz/artifactory/devt/releases/download/$latestTag/$($file.Name)"
    Write-Host "Uploading file: $($file.FullName) to $uri"
    
    $requestParams = @{
        Method  = 'PUT'
        Uri     = $uri
        InFile  = $file.FullName
        Headers = @{ Authorization = $credentialHeader }
    }
    
    # Invoke the REST method to upload the file
    Invoke-RestMethod @requestParams
}
