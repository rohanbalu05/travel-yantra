# Laptop runner for the second review. For every open PR on main whose head
# commit has no `second-review` status yet, it runs one read-only review,
# posts it as a PR review and sets the commit status.
# Usage: powershell -ExecutionPolicy Bypass -File review.ps1
param(
    [string]$Model = 'claude-opus-5-5',
    [string]$Effort = 'medium',
    [int]$PollSeconds = 90,
    [int]$TimeoutMinutes = 40
)
. "$PSScriptRoot\common.ps1"

$Wt = Join-Path $Script:Root 'review'
$LogName = 'review'
$host.UI.RawUI.WindowTitle = 'Second review'
if (-not (Test-Path $Wt)) { throw "Worktree $Wt is missing. Run setup.ps1 first." }

$all = Invoke-GhJson @('api', "repos/$Script:Repo/issues?labels=dispatch&state=open&per_page=20")
$Dispatch = [int](@($all | Where-Object { $_.title -eq '[dispatch] Second review' })[0].number)
Write-Log $LogName "Second review runner started. Dispatch issue #$Dispatch. Model $Model, effort $Effort."
$st = Get-State $LogName
$attempts = @{}

function Read-Commands {
    $comments = Invoke-GhJson @('api', "repos/$Script:Repo/issues/$Dispatch/comments?per_page=100")
    foreach ($c in @($comments | Sort-Object { [int64]$_.id })) {
        if ([int64]$c.id -le [int64]$st.lastCommentId) { continue }
        $st.lastCommentId = [int64]$c.id
        if ($c.user.login -ne $Script:Me) { continue }
        $first = (($c.body -split "`n")[0]).Trim()
        if ($first -match '^HQ:\s*pause') { $st.paused = $true; Add-IssueComment $Dispatch 'RUN review paused.' }
        elseif ($first -match '^HQ:\s*resume') { $st.paused = $false; Add-IssueComment $Dispatch 'RUN review resumed.' }
    }
    Save-State $LogName $st
}

function Get-Json([string]$Text) {
    if (-not $Text) { return $null }
    $m = [regex]::Match($Text, '```json\s*(\{[\s\S]*?\})\s*```')
    $s = $null
    if ($m.Success) { $s = $m.Groups[1].Value }
    else {
        $a = $Text.IndexOf('{'); $b = $Text.LastIndexOf('}')
        if ($a -ge 0 -and $b -gt $a) { $s = $Text.Substring($a, $b - $a + 1) }
    }
    if (-not $s) { return $null }
    try { return $s | ConvertFrom-Json } catch { return $null }
}

function Invoke-Review($Pr) {
    $n = [int]$Pr.number; $sha = $Pr.head.sha
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & git -C $Wt fetch origin "+refs/pull/$n/head:refs/remotes/pr/$n" '+refs/heads/main:refs/remotes/origin/main' 2>$null | Out-Null
    & git -C $Wt checkout --detach -f -q "refs/remotes/pr/$n" 2>$null | Out-Null
    $diff = & git -C $Wt diff "origin/main...refs/remotes/pr/$n" 2>$null
    $ErrorActionPreference = $old

    $in = Join-Path $Wt '.review-input'
    if (Test-Path $in) { Remove-Item $in -Recurse -Force }
    New-Item -ItemType Directory -Path $in | Out-Null
    Write-Utf8 (Join-Path $in 'diff.patch') (($diff -join "`n"))
    Write-Utf8 (Join-Path $in 'pr.md') ("# $($Pr.title)`n`n$($Pr.body)")

    $codex = Invoke-GhJson @('api', "repos/$Script:Repo/pulls/$n/comments?per_page=100")
    $codexText = ($codex | Where-Object { $_.user.login -like 'chatgpt-codex-connector*' } |
        ForEach-Object { "## $($_.path):$($_.line) (commit $($_.commit_id.Substring(0,7)))`n$($_.body)`n" }) -join "`n"
    Write-Utf8 (Join-Path $in 'codex.md') $codexText

    $reviews = Invoke-GhJson @('api', "repos/$Script:Repo/pulls/$n/reviews?per_page=100")
    $prior = @($reviews | Where-Object { $_.body -like '*<!-- second-review:v1*' })
    $mode = 'full'
    if ($prior.Count -gt 0) {
        $mode = 'verify'
        Write-Utf8 (Join-Path $in 'previous.md') (($prior | ForEach-Object { $_.body }) -join "`n`n---`n`n")
    }

    $prompt = "Mode: $mode. Review PR #$n ($($Pr.title)) at commit $sha. Inputs are in .review-input/: pr.md, diff.patch, codex.md" +
        $(if ($mode -eq 'verify') { ', previous.md' } else { '' }) + '. Reply with the JSON object only.'
    Add-IssueComment $Dispatch "RUN review started: PR #$n ($mode) at $($sha.Substring(0,7))"
    $res = Invoke-Claude -WorkDir $Wt -Prompt $prompt -Model $Model -Effort $Effort `
        -SystemPromptFile (Join-Path $Script:Lanes 'prompts\review.md') `
        -SettingsFile (Join-Path $Script:Lanes 'review-settings.json') -LogName "review-pr$n" -TimeoutMinutes $TimeoutMinutes
    $j = $null
    if ($res) { $j = Get-Json ([string]$res.result) }
    if (-not $j) {
        $k = "$n-$sha"; $attempts[$k] = 1 + [int]$attempts[$k]
        Write-Log $LogName "PR #$n review produced no usable JSON (attempt $($attempts[$k]))."
        if ($attempts[$k] -ge 2) {
            Set-ReviewStatus $sha 'error' 'Second review could not run; HQ to check.'
            Add-IssueComment $Dispatch "RUN review ERROR on PR #$n at $($sha.Substring(0,7)); status set to error."
        }
        return
    }

    $findings = @($j.findings)
    $p0 = @($findings | Where-Object { $_.severity -eq 'P0' }).Count
    $p1 = @($findings | Where-Object { $_.severity -eq 'P1' }).Count
    $p2 = @($findings | Where-Object { $_.severity -eq 'P2' }).Count
    $pass = ($p0 + $p1) -eq 0
    $verdict = if ($pass) { 'PASS' } else { 'FAIL' }

    $lines = @("<!-- second-review:v1 sha=$sha verdict=$verdict mode=$mode -->",
        "### Second review ($mode) - $verdict", '', [string]$j.summary, '')
    foreach ($f in $findings) {
        $lines += "- **$($f.severity)** ``$($f.file):$($f.line)`` $($f.title)"
        $lines += "  $($f.detail)"
    }
    if ($findings.Count -eq 0) { $lines += 'No findings.' }
    $body = ($lines -join "`n")

    $tmp = Join-Path $env:TEMP ("ty-review-{0}.json" -f [guid]::NewGuid())
    Write-Utf8 $tmp ((@{ body = $body; event = 'COMMENT'; commit_id = $sha } | ConvertTo-Json -Compress))
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & gh api -X POST "repos/$Script:Repo/pulls/$n/reviews" --input $tmp 2>$null | Out-Null
    $ErrorActionPreference = $old
    Remove-Item $tmp -ErrorAction SilentlyContinue

    $state = if ($pass) { 'success' } else { 'failure' }
    Set-ReviewStatus $sha $state "P0 $p0, P1 $p1, P2 $p2 ($mode)"
    $meta = "notional cost USD: $($res.total_cost_usd); turns: $($res.num_turns)"
    Write-Log $LogName "PR #$n $mode $verdict (P0 $p0 P1 $p1 P2 $p2) $meta"
    Add-IssueComment $Dispatch "RUN review done: PR #$n ($mode) $verdict - P0 $p0, P1 $p1, P2 $p2. $meta"
}

function Set-ReviewStatus([string]$Sha, [string]$State, [string]$Desc) {
    $tmp = Join-Path $env:TEMP ("ty-status-{0}.json" -f [guid]::NewGuid())
    Write-Utf8 $tmp ((@{ state = $State; context = 'second-review'; description = $Desc } | ConvertTo-Json -Compress))
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & gh api -X POST "repos/$Script:Repo/statuses/$Sha" --input $tmp 2>$null | Out-Null
    $ErrorActionPreference = $old
    Remove-Item $tmp -ErrorAction SilentlyContinue
}

while ($true) {
    try {
        $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & git -C $Script:Main pull --ff-only -q 2>$null | Out-Null
        $ErrorActionPreference = $old
        Read-Commands
        if (-not $st.paused) {
            $prs = Invoke-GhJson @('api', "repos/$Script:Repo/pulls?state=open&per_page=50&sort=created&direction=asc")
            foreach ($pr in @($prs)) {
                if ($pr.draft -or $pr.base.ref -ne 'main' -or -not $pr.title.StartsWith('[')) { continue }
                $status = Invoke-GhJson @('api', "repos/$Script:Repo/commits/$($pr.head.sha)/status")
                if (@($status.statuses | Where-Object { $_.context -eq 'second-review' }).Count -gt 0) { continue }
                Invoke-Review $pr
                break
            }
        }
    } catch {
        Write-Log $LogName "Loop error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $PollSeconds
}
