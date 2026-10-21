# One-time setup: creates a Windows scheduled task that refreshes the saved copies every day.
# Run it from the repo folder, on the branch the live app is deployed from:
#     powershell -ExecutionPolicy Bypass -File tools\setup_daily_refresh.ps1
# It runs every day at 7:00 AM, or as soon as the PC is on if it was off at 7:00.

$ErrorActionPreference = "Stop"
$Repo   = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $PSScriptRoot "refresh_saved_copies.ps1"
Set-Location $Repo

# Which branch, and which GitHub branch it pushes to (its "upstream").
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$upstream = (git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null)
if (-not $upstream) {
    Write-Host "Branch '$branch' is not linked to a GitHub branch yet. Run:  git push -u origin $branch   then run this again." -ForegroundColor Red
    exit 1
}
$remote, $remoteBranch = $upstream.Trim() -split "/", 2

# The same Python you use in this terminal, so the task finds it without PATH tricks.
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py -or $py -like "*WindowsApps*") { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py -or $py -like "*WindowsApps*") {
    Write-Host "Could not find a real python.exe. Install Python from python.org (tick 'Add to PATH'), then run this again." -ForegroundColor Red
    exit 1
}

Set-Content -Path (Join-Path $Repo ".git\caz-refresh.txt") -Encoding ASCII -Value @(
    "branch=$branch", "remote=$remote", "remote_branch=$remoteBranch", "python=$py")

$TaskName = "CareAtZero daily refresh (" + (Split-Path -Leaf $Repo) + ")"
$action   = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`"" `
            -WorkingDirectory $Repo
$trigger  = New-ScheduledTaskTrigger -Daily -At 7:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Refreshes CareAtZero saved copies (RAM pop-up clinics) and pushes them to GitHub." -Force | Out-Null

Write-Host "Done. '$TaskName' will run every day at 7:00 AM." -ForegroundColor Green
Write-Host "Branch $branch -> pushes to $remote/$remoteBranch, using $py"
Write-Host "Test it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Log file:     $env:LOCALAPPDATA\CareAtZero\daily_refresh_$(Split-Path -Leaf $Repo).log"
