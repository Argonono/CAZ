# CareAtZero - daily refresh of the saved copies (RAM pop-up clinics, HRSA, NC DHHS).
# RAM blocks downloads from cloud servers, so this runs on this PC and pushes the
# updated data/snapshots files to GitHub. The live app picks them up after the push.
# Started by the scheduled task that tools\setup_daily_refresh.ps1 creates.

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

# Settings saved by setup_daily_refresh.ps1 (kept inside .git, so they are never committed)
$ConfigFile = Join-Path $Repo ".git\caz-refresh.txt"
$LogDir = Join-Path $env:LOCALAPPDATA "CareAtZero"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("daily_refresh_" + (Split-Path -Leaf $Repo) + ".log")

function Write-Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $Log -Value $line
    Write-Output $line
}

Write-Log "---- Refresh started in $Repo"
if (-not (Test-Path $ConfigFile)) { Write-Log "STOPPED: run tools\setup_daily_refresh.ps1 first."; exit 1 }
$cfg = @{}
Get-Content $ConfigFile | ForEach-Object { $k, $v = $_ -split "=", 2; if ($k) { $cfg[$k.Trim()] = $v.Trim() } }
$Branch = $cfg["branch"]; $Remote = $cfg["remote"]; $RemoteBranch = $cfg["remote_branch"]; $python = $cfg["python"]

# 1. Only work on the app's branch, so nothing else gets pushed by accident.
$current = (git rev-parse --abbrev-ref HEAD).Trim()
if ($current -ne $Branch) {
    Write-Log "SKIPPED: the repo is on branch '$current', not '$Branch'. Switch back to '$Branch' and it will run next time."
    exit 0
}

# 2. Never push unfinished work, and never overwrite newer work on GitHub.
git fetch $Remote $RemoteBranch 2>&1 | Out-Null
$ahead  = [int](git rev-list --count "$Remote/$RemoteBranch..HEAD")
$behind = [int](git rev-list --count "HEAD..$Remote/$RemoteBranch")
if ($behind -gt 0) {
    Write-Log "SKIPPED: GitHub has $behind newer commit(s). Run 'git pull' in this folder, then it will run next time."
    exit 0
}

# 3. Download fresh copies (needs this PC's normal internet; RAM allows it from here).
$env:PYTHONIOENCODING = "utf-8"
& $python "tools/check_live_sources.py" *>> $Log
Write-Log "Check script finished (exit code $LASTEXITCODE; 1 just means at least one source failed today)."

# 4. Commit only the saved-copy files, and only if they changed.
git add -- "data/snapshots" 2>&1 | Out-Null
git diff --cached --quiet -- "data/snapshots"
if ($LASTEXITCODE -eq 0) {
    Write-Log "No changes in the saved copies. Nothing to push."
    exit 0
}
git commit -m ("Daily refresh of saved copies " + (Get-Date -Format "yyyy-MM-dd")) -- "data/snapshots" 2>&1 | Out-Null

if ($ahead -gt 0) {
    Write-Log "COMMITTED but NOT pushed: there were $ahead earlier local commit(s) not on GitHub yet. Push them yourself when ready: git push $Remote HEAD:$RemoteBranch"
    exit 0
}

git push $Remote "HEAD:$RemoteBranch" 2>&1 | ForEach-Object { Add-Content -Path $Log -Value "   $_" }
if ($LASTEXITCODE -eq 0) { Write-Log "Pushed to GitHub. The live app now has today's saved copies." }
else { Write-Log "PUSH FAILED (see lines above). Run 'git push $Remote HEAD:$RemoteBranch' by hand once to refresh your GitHub sign-in." }
