#!/usr/bin/env pwsh
param (
    [ValidateSet("major", "minor", "patch")]
    [string]$Part = "patch"
)

# A simple script to increment the version of the latest git tag
# Assumes tags are in the format vMAJOR.MINOR.PATCH

# Retrieve the latest tag from git
$t = git describe --tags --abbrev=0

if ($t) {
    # Remove the leading 'v' and split the version string
    $versionParts = $t.Substring(1).Split('.')
    
    if ($versionParts.Length -lt 3) {
        Write-Error "Tag format invalid; expected format 'vMAJOR.MINOR.PATCH'"
        exit 1
    }
    
    # Convert version parts to integers
    $major = [int]$versionParts[0]
    $minor = [int]$versionParts[1]
    $patch = [int]$versionParts[2]

    # Increment based on the specified part
    switch ($Part) {
        "major" {
            $major++
            $minor = 0
            $patch = 0
        }
        "minor" {
            $minor++
            $patch = 0
        }
        "patch" {
            $patch++
        }
    }
    
    # Reassemble version string with a leading 'v'
    $newTag = "v$major.$minor.$patch"
    Write-Output $newTag
    
    # Create and push the new tag
    git tag $newTag
    git push origin $newTag
} else {
    Write-Error "No tag found"
    exit 1
}