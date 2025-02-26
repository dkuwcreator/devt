param(
    [Parameter(Mandatory=$true, ValueFromRemainingArguments=$true)]
    [string[]]$CommitMessage
)

Write-Host "CWD: $pwd"

Write-Host "Committing changes..."
Write-Host "Commit message: $CommitMessage"

# Activate the virtual environment
. .\.venv\Scripts\Activate.ps1

# Update requirements file
pip freeze > requirements.txt

# Git operations
git add .
git commit -m "$CommitMessage"
git push