#Requires -Version 5.1
<#
    stop.ps1 - Windows equivalent of stop.sh
    Stops the backend and frontend started by app.ps1.

    uvicorn runs with --reload, which spawns a child reloader process, so the
    whole process TREE has to be killed - not just the recorded PID.
#>

$ErrorActionPreference = "SilentlyContinue"
Set-Location -Path $PSScriptRoot

function Stop-Tree($procId, $label) {
    if (-not $procId) { return $false }
    $running = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $running) { return $false }
    Write-Host "Stopping $label (PID $procId and children)..."
    # /T kills the tree, /F forces it.
    taskkill /PID $procId /T /F 2>$null | Out-Null
    return $true
}

function Stop-ByPort($port, $label) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return $false }
    $stopped = $false
    foreach ($procId in ($conns | Select-Object -ExpandProperty OwningProcess -Unique)) {
        if ($procId -and $procId -ne 0) {
            Write-Host "Stopping $label on port $port (PID $procId)..."
            taskkill /PID $procId /T /F 2>$null | Out-Null
            $stopped = $true
        }
    }
    return $stopped
}

# --- Backend ---
$backendStopped = $false
if (Test-Path ".backend.pid") {
    $bpid = (Get-Content ".backend.pid" | Select-Object -First 1).Trim()
    $backendStopped = Stop-Tree ([int]$bpid) "backend"
    Remove-Item ".backend.pid" -Force -ErrorAction SilentlyContinue
}
if (-not $backendStopped) { $backendStopped = Stop-ByPort 8000 "backend" }

# --- Frontend ---
$frontendStopped = $false
if (Test-Path ".frontend.pid") {
    $fpid = (Get-Content ".frontend.pid" | Select-Object -First 1).Trim()
    $frontendStopped = Stop-Tree ([int]$fpid) "frontend"
    Remove-Item ".frontend.pid" -Force -ErrorAction SilentlyContinue
}
# Vite falls back to 5174, 5175... if 5173 is taken, so sweep a few ports.
if (-not $frontendStopped) {
    foreach ($p in 5173, 5174, 5175) {
        if (Stop-ByPort $p "frontend") { $frontendStopped = $true; break }
    }
}

if (-not $backendStopped -and -not $frontendStopped) {
    Write-Host "Nothing appears to be running."
} else {
    Write-Host "Done."
}
