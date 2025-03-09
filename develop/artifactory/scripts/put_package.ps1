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

# Fetch latest tags and determine latest version
git fetch --tags

# Get sorted tags and choose the latest
$tags = git tag --sort=version:refname | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
if (-not $tags) {
    Write-Error "No tags found."
    exit 1
}

$latestTag = $tags[-1]
try {
    [version]$latestTag
} catch {
    Write-Error "Tag '$latestTag' is not a valid version."
    exit 1
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

# Determine package details for upload
$currentLocation = Get-Location
Write-Host "Current location: $currentLocation"
$zipFileName = "$latestTag.zip"

# Create a zip package (using external zip tool because Compress-Archive may drop file permissions)
zip -r "$currentLocation/$zipFileName" "dist"

# Define rest request parameters
$requestParams = @{
    Method  = 'PUT'
    Uri     = "https://artifactory.insim.biz/artifactory/devt/$latestTag"
    InFile  = "$currentLocation/$zipFileName"
    Headers = @{ Authorization = $credentialHeader }
}

# Optionally, log the request parameters (without exposing sensitive info)
Write-Host "Uploading package: $zipFileName"

# Invoke the REST method
Invoke-RestMethod @requestParams