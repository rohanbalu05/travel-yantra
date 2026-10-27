# One-time laptop setup for the v3 lanes. Safe to run again.
# Usage (any PowerShell window):
#   powershell -ExecutionPolicy Bypass -File C:\TravelYantra\main\infra\lanes\setup.ps1
# It never prints a token or key.

$ErrorActionPreference = 'Continue'
$Root = 'C:\TravelYantra'
$Main = Join-Path $Root 'main'
$Project = 'project-cea09bbb-b5f7-4fc4-95b'
$Failed = $false

function Ok([string]$What) { Write-Host "[ok]   $What" -ForegroundColor Green }
function Bad([string]$What, [string]$Fix) {
    Write-Host "[STOP] $What -> $Fix" -ForegroundColor Red
    $script:Failed = $true
}
function Has([string]$Cmd) { [bool](Get-Command $Cmd -ErrorAction SilentlyContinue) }

# 1. Tools
foreach ($t in @('git', 'gh', 'gcloud', 'node', 'npx', 'uv', 'pnpm', 'python', 'claude')) {
    if (Has $t) { Ok "$t is installed" } else { Bad "$t is missing" 'install it, then run setup again' }
}

# 2. Claude Code version (cross-session messages on Windows need 2.1.234+)
$ver = (& claude --version 2>$null | Out-String).Trim()
if ($ver -match '(\d+)\.(\d+)\.(\d+)') {
    $v = [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])"
    if ($v -ge [version]'2.1.234') { Ok "Claude Code $v" } else { Bad "Claude Code $v is older than 2.1.234" 'run: claude update' }
} else { Bad 'could not read claude --version' 'run: claude --version' }

# 3. Claude login is the Max subscription, not an API key
if ([Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User') -or $env:ANTHROPIC_API_KEY) {
    Bad 'ANTHROPIC_API_KEY is set' 'remove it from your user environment variables (lanes must use the Max login)'
} else { Ok 'no ANTHROPIC_API_KEY in the environment' }

# 4. The lanes' GitHub token (scoped to travel-yantra only)
$tok = ([Environment]::GetEnvironmentVariable('TY_GH_TOKEN', 'User'), [Environment]::GetEnvironmentVariable('TY_GH_TOKEN', 'Machine') | Where-Object { $_ } | Select-Object -First 1)
if (-not $tok) {
    Bad 'TY_GH_TOKEN is not set' 'Step A item 5: create the token and add the user environment variable'
} else {
    $env:GH_TOKEN = $tok
    $name = (& gh api repos/rohanbalu05/travel-yantra --jq .full_name 2>$null | Out-String).Trim()
    if ($name -eq 'rohanbalu05/travel-yantra') { Ok 'TY_GH_TOKEN reaches rohanbalu05/travel-yantra' }
    else { Bad 'TY_GH_TOKEN cannot read the repository' 'check the token''s repository access and permissions' }
    Remove-Item Env:GH_TOKEN
}
Remove-Variable tok -ErrorAction SilentlyContinue

# 5. gcloud: the secondary account's trial project, in its own config folder
$env:CLOUDSDK_CONFIG = Join-Path $HOME '.gcloud-travel'
$acct = (& gcloud config get-value account 2>$null | Out-String).Trim()
$proj = (& gcloud config get-value project 2>$null | Out-String).Trim()
if ($acct) { Ok 'gcloud-travel has an account logged in' } else { Bad 'no account in gcloud-travel' 'Step A item 2' }
if ($proj -eq $Project) { Ok "gcloud-travel project is $Project" } else { Bad "gcloud-travel project is '$proj'" "gcloud config set project $Project (with CLOUDSDK_CONFIG set)" }
Remove-Item Env:CLOUDSDK_CONFIG

# 6. Main checkout: up to date, Rohan's identity, hooks, gh credentials
if (-not (Test-Path (Join-Path $Main '.git'))) {
    Bad "no checkout at $Main" "gh repo clone rohanbalu05/travel-yantra $Main"
} else {
    & git -C $Main fetch origin -q
    & git -C $Main switch -q main 2>$null
    & git -C $Main pull --ff-only -q
    & git -C $Main config user.name 'Rohan Balu'
    & git -C $Main config user.email '117021386+rohanbalu05@users.noreply.github.com'
    & git -C $Main config commit.gpgsign false
    & git -C $Main config core.hooksPath .githooks
    & git -C $Main config fetch.prune true
    Ok 'main checkout updated; identity and hooks set (shared by every worktree)'
}

# 7. Lane worktrees on branches lane/ty1 .. lane/ty6 at origin/main
foreach ($n in 1..6) {
    $dir = Join-Path $Root "ty$n"
    $branch = "lane/ty$n"
    if (-not (Test-Path $dir)) {
        & git -C $Main worktree add -q -B $branch $dir origin/main
        Ok "worktree $dir created on $branch"
        continue
    }
    $dirty = (& git -C $dir status --porcelain 2>$null | Out-String).Trim()
    $cur = (& git -C $dir rev-parse --abbrev-ref HEAD 2>$null | Out-String).Trim()
    if ($cur -eq $branch) { Ok "worktree $dir is on $branch" }
    elseif ($dirty) { Bad "worktree $dir has uncommitted changes" "check it, then: git -C $dir stash, and run setup again" }
    else {
        & git -C $dir switch -q -C $branch origin/main
        Ok "worktree $dir switched to $branch at origin/main"
    }
}

# 8. A quick parse check of the lane flags (Haiku, one word; uses very little usage)
Push-Location (Join-Path $Root 'ty1')
$probe = (& claude -p 'Reply with the single word OK.' --model claude-haiku-5-5 --setting-sources project,local `
    --strict-mcp-config --mcp-config (Join-Path $Main 'infra\lanes\belts\back.mcp.json') `
    --settings (Join-Path $Main 'infra\lanes\belts\back.settings.json') 2>&1 | Out-String)
Pop-Location
if ($probe -match 'OK') { Ok 'Claude Code starts with the lane flags' } else { Bad 'Claude Code did not start with the lane flags' 'send HQ a screenshot of this window' }

Write-Host ''
if ($Failed) {
    Write-Host 'Setup found problems (red lines). Fix them and run setup again.' -ForegroundColor Red
} else {
    Write-Host 'Setup done. Open all six lanes with:' -ForegroundColor Cyan
    Write-Host '  powershell -ExecutionPolicy Bypass -File C:\TravelYantra\main\infra\lanes\start-all.ps1' -ForegroundColor Cyan
}
