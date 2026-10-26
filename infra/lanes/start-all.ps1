# Opens one PowerShell window per lane runner plus the second-review runner.
# Starts are staggered so the headless sessions don't all log in at once.
# Usage: powershell -ExecutionPolicy Bypass -File start-all.ps1 [-Lanes ty1,ty3]
param([string[]]$Lanes = @('ty1', 'ty2', 'ty3', 'ty4', 'ty5', 'ty6'), [switch]$NoReview)
$dir = $PSScriptRoot

if (-not $NoReview) {
    Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$dir\review.ps1`"")
    Start-Sleep -Seconds 15
}
foreach ($l in $Lanes) {
    Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$dir\lane.ps1`"", '-Lane', $l)
    Start-Sleep -Seconds 15
}
Write-Host "Started: $(if (-not $NoReview) { 'review, ' })$($Lanes -join ', ')"
Write-Host 'Each window shows its log. Close a window to stop that runner. Logs: C:\TravelYantra\logs'
