# Laptop runner for one build lane. Polls the lane's dispatch issue for HQ
# commands, runs a fresh headless session per command, and posts the reply.
# Usage: powershell -ExecutionPolicy Bypass -File lane.ps1 -Lane ty3
param(
    [Parameter(Mandatory = $true)][ValidateSet('ty1', 'ty2', 'ty3', 'ty4', 'ty5', 'ty6')][string]$Lane,
    [string]$Model = 'claude-sonnet-5-5',
    [int]$PollSeconds = 60,
    [int]$TimeoutMinutes = 120,
    [int]$AutoEveryMinutes = 20,
    [switch]$NoAuto
)
. "$PSScriptRoot\common.ps1"

$names = @{ ty1 = 'core'; ty2 = 'guide'; ty3 = 'routes'; ty4 = 'web'; ty5 = 'channels'; ty6 = 'ops' }
$num = $Lane.Substring(2)
$Name = "TY$num $($names[$Lane])"
$Wt = Join-Path $Script:Root $Lane
$LogName = "lane-$Lane"
$host.UI.RawUI.WindowTitle = "Lane $Name"

if (-not (Test-Path $Wt)) { throw "Worktree $Wt is missing. Run setup.ps1 first." }

$found = Invoke-GhJson @('api', "repos/$Script:Repo/issues?labels=dispatch,lane:$Lane&state=open")
if (-not $found -or $found.Count -lt 1) { throw "No open dispatch issue labelled lane:$Lane." }
$Dispatch = [int]$found[0].number
Write-Log $LogName "Lane $Name runner started. Dispatch issue #$Dispatch. Model $Model."

$st = Get-State $LogName
if (-not $st.lastCommentId) {
    # First start: ignore commands posted before the runner existed except the newest one.
    $st.lastCommentId = 0
}

function Get-FixRuns([int]$Pr) {
    $k = "$Pr"
    if ($st.fixRuns -and $st.fixRuns.PSObject.Properties[$k]) { return [int]$st.fixRuns.$k }
    return 0
}
function Add-FixRun([int]$Pr) {
    $k = "$Pr"; $n = (Get-FixRuns $Pr) + 1
    if (-not $st.fixRuns -or $st.fixRuns -is [hashtable]) { $st.fixRuns = [pscustomobject]@{} }
    $st.fixRuns | Add-Member -NotePropertyName $k -NotePropertyValue $n -Force
}

function Get-NewCommand {
    $comments = Invoke-GhJson @('api', "repos/$Script:Repo/issues/$Dispatch/comments?per_page=100&sort=created&direction=desc")
    if (-not $comments) { return $null }
    $cmd = $null
    $sorted = $comments | Sort-Object { [int64]$_.id }
    foreach ($c in $sorted) {
        if ([int64]$c.id -le [int64]$st.lastCommentId) { continue }
        $st.lastCommentId = [int64]$c.id
        if ($c.user.login -ne $Script:Me) { continue }
        $first = (($c.body -split "`n")[0]).Trim()
        if ($first -match '^HQ:\s*pause') { $st.paused = $true; Add-IssueComment $Dispatch "RUN $Name paused." }
        elseif ($first -match '^HQ:\s*resume') { $st.paused = $false; Add-IssueComment $Dispatch "RUN $Name resumed." }
        elseif ($first -match '^(Work your queue.*|Fix PR #\d+.*|HQ task:.*)$') { $cmd = $Matches[1] }
    }
    Save-State $LogName $st
    return $cmd
}

function Get-AutoCommand {
    $prs = Invoke-GhJson @('api', "repos/$Script:Repo/pulls?state=open&per_page=50")
    foreach ($pr in @($prs)) {
        if (-not $pr.head.ref.StartsWith("ty/$Lane-")) { continue }
        $n = [int]$pr.number; $sha = $pr.head.sha
        if ((Get-FixRuns $n) -ge 2) { continue }
        $status = Invoke-GhJson @('api', "repos/$Script:Repo/commits/$sha/status")
        $second = @($status.statuses | Where-Object { $_.context -eq 'second-review' })
        $codexOpen = $false
        $ics = Invoke-GhJson @('api', "repos/$Script:Repo/issues/$n/comments?per_page=100")
        foreach ($ic in @($ics)) {
            if ($ic.body -match 'codex-review-state:v1 (\{.*?\}) -->') {
                try {
                    $j = $Matches[1] | ConvertFrom-Json
                    if ($j.code_review.commit_sha -eq $sha -and $j.code_review.status -eq 'completed' -and $j.code_review.has_unresolved_findings) { $codexOpen = $true }
                } catch {}
            }
        }
        if (($second.Count -gt 0 -and $second[0].state -eq 'failure') -or $codexOpen) {
            Add-FixRun $n; Save-State $LogName $st
            return "Fix PR #$n"
        }
    }
    $due = $true
    if ($st.lastAutoAt) { $due = ((Get-Date) - [datetime]$st.lastAutoAt).TotalMinutes -ge $AutoEveryMinutes }
    if (-not $due) { return $null }
    $ready = Invoke-GhJson @('api', "repos/$Script:Repo/issues?labels=lane:$Lane,status:ready&state=open&per_page=5")
    $st.lastAutoAt = (Get-Date).ToString('o'); Save-State $LogName $st
    if ($ready -and @($ready).Count -gt 0) { return 'Work your queue' }
    return $null
}

function Reset-Worktree {
    for ($i = 0; $i -lt 3; $i++) {
        $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & git -C $Wt fetch origin --prune 2>$null | Out-Null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $old
        if ($ok) { break }
        Start-Sleep -Seconds (Get-Random -Minimum 3 -Maximum 12)
    }
    $dirty = & git -C $Wt status --porcelain
    if ($dirty) { & git -C $Wt stash push -u -m ("runner-" + (Get-Date -Format 'yyyyMMdd-HHmmss')) 2>$null | Out-Null }
    & git -C $Wt checkout --detach -q origin/main 2>$null | Out-Null
}

function Invoke-LaneRun([string]$Cmd) {
    $effort = 'medium'
    if ($Cmd -match 'effort:high') { $effort = 'high'; $Cmd = ($Cmd -replace '\s*effort:high', '').Trim() }
    Reset-Worktree
    $tpl = Get-Content (Join-Path $Script:Lanes 'prompts\lane.md') -Raw
    $sys = $tpl.Replace('{LANE}', $Lane).Replace('{N}', $num).Replace('{NAME}', $Name).Replace('{WORKTREE}', $Wt)
    $sysFile = Join-Path $Script:State "$LogName-system.md"
    Write-Utf8 $sysFile $sys
    Write-Log $LogName "Run start: $Cmd (effort $effort)"
    Add-IssueComment $Dispatch "RUN $Name started: $Cmd (effort $effort)"
    $res = Invoke-Claude -WorkDir $Wt -Prompt $Cmd -Model $Model -Effort $effort `
        -SystemPromptFile $sysFile -SettingsFile (Join-Path $Script:Lanes 'lane-settings.json') `
        -LogName $LogName -TimeoutMinutes $TimeoutMinutes
    if (-not $res) {
        Add-IssueComment $Dispatch "RUN $Name FAILED or timed out: $Cmd. Log on the laptop: C:\TravelYantra\logs\$LogName.log"
        return
    }
    $meta = "turns: $($res.num_turns); notional cost USD: $($res.total_cost_usd); session: $($res.session_id)"
    Write-Log $LogName "Run done: $Cmd | $meta"
    Add-IssueComment $Dispatch ("RUN $Name done: $Cmd`n`n" + (Limit-Text ([string]$res.result)) + "`n`n$meta")
}

while ($true) {
    try {
        $cmd = Get-NewCommand
        if (-not $st.paused) {
            if (-not $cmd -and -not $NoAuto) { $cmd = Get-AutoCommand }
            if ($cmd) { Invoke-LaneRun $cmd }
        }
    } catch {
        Write-Log $LogName "Loop error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $PollSeconds
}
