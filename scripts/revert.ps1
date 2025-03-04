# Fetch latest tags from remote
git fetch --tags

# Get the latest tag from local (sorted by tag creation date)
$latestTag = git for-each-ref --sort=-creatordate --format '%(refname:short)' refs/tags | Select-Object -First 1

if ($latestTag) {
    Write-Output "Deleting local tag: $latestTag"
    git tag -d $latestTag

    Write-Output "Deleting remote tag: $latestTag"
    git push --delete origin $latestTag
} else {
    Write-Output "No tag found."
}

# git reset --hard HEAD~1

# git push --force