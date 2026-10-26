# One-time laptop setup for the lane runners. Safe to run again.
# Usage (from C:\TravelYantra\main):
#   powershell -ExecutionPolicy Bypass -File infra\lanes\setup.ps1
. "$PSScriptRoot\common.ps1"
$ErrorActionPreference = 'Stop'

function Check([string]$What, [bool]$Ok, [string]$Fix) {
    if ($Ok) { Write-Host "[ok]   $What" -ForegroundColor Green }
    else { Write-Host "[STOP] $What -> $Fix" -ForegroundColor Red; exit 1 }
}

Check 'ANTHROPIC_API_KEY is not set' (-not $env:ANTHROPIC_API_KEY) 'Remove-Item Env:ANTHROPIC_API_KEY, and remove it from your user environment variables'
$auth = $null
try { $auth = (& claude auth status 2>$null) -join "`n" | ConvertFrom-Json } catch {}
Check 'Claude Code uses the claude.ai subscription login' ($auth -and $auth.authMethod -eq 'claude.ai') 'run: claude, then /login with your Max account'

$old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& gh auth status 2>$null | Out-Null; $ghOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $old
Check 'gh is logged in' $ghOk 'gh auth login'
Check 'main clone exists at C:\TravelYantra\main' (Test-Path (Join-Path $Script:Main '.git')) 'gh repo clone rohanbalu05/travel-yantra C:\TravelYantra\main'

& git -C $Script:Main config user.name 'Rohan Balu'
& git -C $Script:Main config user.email '117021386+rohanbalu05@users.noreply.github.com'
& git -C $Script:Main config commit.gpgsign false
& git -C $Script:Main config fetch.prune true
& git -C $Script:Main fetch origin -q
Write-Host '[ok]   git identity set (shared by all worktrees)' -ForegroundColor Green

foreach ($w in @('ty1', 'ty2', 'ty3', 'ty4', 'ty5', 'ty6', 'review')) {
    $path = Join-Path $Script:Root $w
    if (-not (Test-Path $path)) {
        & git -C $Script:Main worktree add --detach -q $path origin/main
        Write-Host "[ok]   worktree $path created" -ForegroundColor Green
    } else { Write-Host "[ok]   worktree $path exists" -ForegroundColor Green }
}

Write-Host 'Self-test: one tiny headless run (Sonnet, low effort)...'
$sys = Join-Path $Script:State 'selftest-system.md'
Write-Utf8 $sys 'Answer with exactly one word.'
$res = Invoke-Claude -WorkDir (Join-Path $Script:Root 'ty1') -Prompt 'Reply with the single word OK.' `
    -Model 'claude-sonnet-5-5' -Effort 'low' -SystemPromptFile $sys `
    -SettingsFile (Join-Path $Script:Lanes 'lane-settings.json') -LogName 'selftest' -TimeoutMinutes 3
Check 'headless run works' ($res -and ([string]$res.result) -match 'OK') "see C:\TravelYantra\logs\selftest-*.err"

Write-Host ''
Write-Host 'Setup done. Start everything with:' -ForegroundColor Cyan
Write-Host '  powershell -ExecutionPolicy Bypass -File C:\TravelYantra\main\infra\lanes\start-all.ps1' -ForegroundColor Cyan
