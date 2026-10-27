# Open six windows, one per Travel Yantra lane (v3).
# Usage: powershell -ExecutionPolicy Bypass -File C:\TravelYantra\main\infra\lanes\start-all.ps1
$Ty = Join-Path $PSScriptRoot 'ty.ps1'
foreach ($Lane in @('TY1', 'TY2', 'TY3', 'TY4', 'TY5', 'TY6')) {
    Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $Ty, $Lane)
    Start-Sleep -Seconds 3
}
Write-Host 'Six lane windows opened. In each: accept the folder trust prompt once, wait for LANE UP, then paste that lane''s PROMPT from HQ.' -ForegroundColor Cyan
