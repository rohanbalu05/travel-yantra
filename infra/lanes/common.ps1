# Shared helpers for the laptop lane runners. Windows PowerShell 5.1 compatible.
# Dot-source this file: . "$PSScriptRoot\common.ps1"

$Script:Repo  = 'rohanbalu05/travel-yantra'
$Script:Root  = 'C:\TravelYantra'
$Script:Main  = Join-Path $Script:Root 'main'
$Script:Lanes = Join-Path $Script:Main 'infra\lanes'
$Script:Logs  = Join-Path $Script:Root 'logs'
$Script:State = Join-Path $Script:Root 'state'
$Script:Me    = 'rohanbalu05'
$Script:Utf8  = New-Object System.Text.UTF8Encoding $false

foreach ($d in @($Script:Logs, $Script:State)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}

function Write-Log([string]$Name, [string]$Msg) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Msg
    Write-Host $line
    [IO.File]::AppendAllText((Join-Path $Script:Logs "$Name.log"), $line + "`r`n", $Script:Utf8)
}

function Write-Utf8([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, $Script:Utf8)
}

# Run gh and return parsed JSON (or $null). Never throws on gh stderr.
function Invoke-GhJson([string[]]$GhArgs) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $raw = & gh @GhArgs 2>$null
    $ErrorActionPreference = $old
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    try { return ($raw -join "`n") | ConvertFrom-Json } catch { return $null }
}

# Post a comment. The body goes through a UTF-8 file to avoid quoting problems.
function Add-IssueComment([int]$Number, [string]$Body) {
    $tmp = Join-Path $env:TEMP ("ty-comment-{0}.json" -f [guid]::NewGuid())
    Write-Utf8 $tmp ((@{ body = $Body } | ConvertTo-Json -Compress))
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & gh api -X POST "repos/$Script:Repo/issues/$Number/comments" --input $tmp 2>$null | Out-Null
    $ErrorActionPreference = $old
    Remove-Item $tmp -ErrorAction SilentlyContinue
}

function Get-State([string]$Name) {
    $p = Join-Path $Script:State "$Name.json"
    if (Test-Path $p) { try { return (Get-Content $p -Raw | ConvertFrom-Json) } catch {} }
    return [pscustomobject]@{ lastCommentId = 0; paused = $false; fixRuns = @{}; lastAutoAt = '' }
}

function Save-State([string]$Name, $Obj) {
    Write-Utf8 (Join-Path $Script:State "$Name.json") ($Obj | ConvertTo-Json -Depth 5)
}

# Run claude headless with a hard timeout. Returns the parsed JSON result or $null.
function Invoke-Claude {
    param([string]$WorkDir, [string]$Prompt, [string]$Model, [string]$Effort,
          [string]$SystemPromptFile, [string]$SettingsFile, [string]$LogName,
          [int]$TimeoutMinutes = 120, [string]$ExtraArgs = '')
    if ($env:ANTHROPIC_API_KEY) { throw 'ANTHROPIC_API_KEY is set: headless runs would bill the API. Remove it first.' }
    $claude = (Get-Command claude -ErrorAction Stop).Source
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $out = Join-Path $Script:Logs "$LogName-$stamp.json"
    $err = Join-Path $Script:Logs "$LogName-$stamp.err"
    $promptFile = Join-Path $Script:State "$LogName-prompt.txt"
    Write-Utf8 $promptFile $Prompt
    $mcp = Join-Path $Script:Lanes 'empty-mcp.json'
    # The prompt is passed on stdin so no quoting of user text is needed.
    $argList = @('-p', '--model', $Model, '--effort', $Effort,
                 '--output-format', 'json', '--permission-prompts', 'none',
                 '--strict-mcp-config', '--mcp-config', ('"{0}"' -f $mcp),
                 '--settings', ('"{0}"' -f $SettingsFile),
                 '--append-system-prompt-file', ('"{0}"' -f $SystemPromptFile)) -join ' '
    if ($ExtraArgs) { $argList = "$argList $ExtraArgs" }
    $p = Start-Process -FilePath $claude -ArgumentList $argList -WorkingDirectory $WorkDir `
        -RedirectStandardInput $promptFile -RedirectStandardOutput $out -RedirectStandardError $err `
        -NoNewWindow -PassThru
    if (-not $p.WaitForExit($TimeoutMinutes * 60 * 1000)) {
        try { $p.Kill() } catch {}
        Write-Log $LogName "TIMEOUT after $TimeoutMinutes min; killed. Log: $out"
        return $null
    }
    try { return (Get-Content $out -Raw | ConvertFrom-Json) } catch {
        Write-Log $LogName "Could not parse output. See $out and $err"
        return $null
    }
}

function Limit-Text([string]$Text, [int]$Max = 3000) {
    if (-not $Text) { return '' }
    if ($Text.Length -le $Max) { return $Text }
    return $Text.Substring(0, $Max) + "`n…(truncated; full log on the laptop)"
}
