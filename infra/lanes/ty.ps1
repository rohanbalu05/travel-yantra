# Start one Travel Yantra lane in this window (v3).
# Usage:
#   powershell -ExecutionPolicy Bypass -File C:\TravelYantra\main\infra\lanes\ty.ps1 TY3
#   powershell -ExecutionPolicy Bypass -File C:\TravelYantra\main\infra\lanes\ty.ps1 TY3 resume
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('TY1', 'TY2', 'TY3', 'TY4', 'TY5', 'TY6')]
    [string]$Lane,
    [Parameter(Position = 1)]
    [ValidateSet('start', 'resume')]
    [string]$Mode = 'start'
)

$Root = 'C:\TravelYantra'
$Kit = Join-Path $Root 'main\infra\lanes'
$Project = 'project-cea09bbb-b5f7-4fc4-95b'

$Lanes = @{
    'TY1' = @{ Name = 'TY1-core';     Belt = 'back';  Dir = 'ty1' }
    'TY2' = @{ Name = 'TY2-guide';    Belt = 'back';  Dir = 'ty2' }
    'TY3' = @{ Name = 'TY3-routes';   Belt = 'back';  Dir = 'ty3' }
    'TY4' = @{ Name = 'TY4-web';      Belt = 'front'; Dir = 'ty4' }
    'TY5' = @{ Name = 'TY5-channels'; Belt = 'back';  Dir = 'ty5' }
    'TY6' = @{ Name = 'TY6-infra';    Belt = 'infra'; Dir = 'ty6' }
}
$L = $Lanes[$Lane]
$Work = Join-Path $Root $L.Dir

if (-not (Test-Path (Join-Path $Work '.git'))) {
    Write-Host "No worktree at $Work. Run infra\lanes\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# GitHub: the lanes' token, scoped to rohanbalu05/travel-yantra only. Never printed.
$Token = ([Environment]::GetEnvironmentVariable('TY_GH_TOKEN', 'User'), [Environment]::GetEnvironmentVariable('TY_GH_TOKEN', 'Machine') | Where-Object { $_ } | Select-Object -First 1)
if (-not $Token) {
    Write-Host 'TY_GH_TOKEN is not set in your user or system environment variables (Step A, item 5).' -ForegroundColor Red
    exit 1
}
$env:GH_TOKEN = $Token
Remove-Variable Token
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue

# Claude Code must use the Max subscription login, not an API key.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

# Google Cloud: only the secondary account's trial project, in its own config folder.
$env:CLOUDSDK_CONFIG = Join-Path $HOME '.gcloud-travel'
$env:CLOUDSDK_CORE_PROJECT = $Project
$env:GOOGLE_CLOUD_PROJECT = $Project
$env:GOOGLE_GENAI_USE_VERTEXAI = 'true'

$env:TY_LANE = $Lane
$host.UI.RawUI.WindowTitle = $L.Name
Set-Location $Work

Write-Host "Starting $($L.Name) in $Work (belt ty-$($L.Belt))" -ForegroundColor Cyan

& claude `
    --model claude-opus-5-5 `
    --name $L.Name `
    --permission-mode acceptEdits `
    --setting-sources project,local `
    --strict-mcp-config `
    --mcp-config (Join-Path $Kit "belts\$($L.Belt).mcp.json") `
    --settings (Join-Path $Kit "belts\$($L.Belt).settings.json") `
    "/ty-lane $Lane $Mode"
