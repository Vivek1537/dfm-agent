#Requires -Version 5.1
<#
    app.ps1 - Windows equivalent of app.sh
    Starts the FastAPI backend and the Vite frontend.

    Requirements (checked below, with clear errors if missing):
      - 64-bit CPython 3.10, 3.11, 3.12 or 3.13   (cadquery-ocp wheel limit)
      - Node.js 20.19+ (22 LTS recommended)
#>

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Err($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red }
function Write-Ok($msg)  { Write-Host $msg -ForegroundColor Green }

# ---------------------------------------------------------------
# 0. Refuse ARM64 Windows early - no cadquery-ocp wheels exist
# ---------------------------------------------------------------
if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
    Write-Err "This machine is Windows on ARM64."
    Write-Host "cadquery-ocp publishes no ARM64 Windows wheels, so the backend"
    Write-Host "dependencies cannot be installed. Use an x64 machine, or run the"
    Write-Host "project under WSL instead."
    Read-Host "Press Enter to exit"
    exit 1
}

# ---------------------------------------------------------------
# 1. Find a compatible Python interpreter
# ---------------------------------------------------------------
function Find-CompatiblePython {
    $candidates = New-Object System.Collections.ArrayList

    # The py launcher is the reliable way to pick a version on Windows.
    # Preference order: best-tested first, 3.13 last.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.12", "3.11", "3.10", "3.13")) {
            [void]$candidates.Add(@{ Exe = "py"; Pre = @("-$v") })
        }
    }
    # Fall back to whatever "python" / "python3" resolve to.
    foreach ($c in @("python", "python3")) {
        if (Get-Command $c -ErrorAction SilentlyContinue) {
            [void]$candidates.Add(@{ Exe = $c; Pre = @() })
        }
    }

    $probe = "import sys;print('%d.%d %s' % (sys.version_info.major, sys.version_info.minor, 'x64' if sys.maxsize > 2**32 else 'x86'))"

    foreach ($cand in $candidates) {
        $out = $null
        try {
            $out = & $cand.Exe @($cand.Pre + @("-c", $probe)) 2>$null
        } catch { continue }

        # A missing Python often resolves to the Microsoft Store stub, which
        # prints nothing and opens the Store. Empty output = not usable.
        if (-not $out) { continue }

        $parts = ("$out".Trim() -split '\s+')
        if ($parts.Count -lt 2) { continue }

        $ver = $parts[0] -split '\.'
        if ($ver.Count -lt 2) { continue }
        $major = [int]$ver[0]
        $minor = [int]$ver[1]
        $arch  = $parts[1]

        if ($major -eq 3 -and $minor -ge 10 -and $minor -le 13 -and $arch -eq "x64") {
            return @{ Exe = $cand.Exe; Pre = $cand.Pre; Version = "$major.$minor" }
        }
    }
    return $null
}

if (-not (Test-Path ".venv")) {
    Write-Host "First time setup: looking for a compatible Python (3.10 - 3.13, 64-bit)..."
    $py = Find-CompatiblePython

    if ($null -eq $py) {
        Write-Err "No compatible Python found."
        Write-Host ""
        Write-Host "This project needs 64-bit CPython 3.10, 3.11, 3.12 or 3.13."
        Write-Host "The limit comes from cadquery-ocp, which only ships Windows"
        Write-Host "wheels for those versions. Python 3.14+ will fail with a"
        Write-Host "source-build error."
        Write-Host ""
        Write-Host "Download Python 3.12 (64-bit) from: https://www.python.org/downloads/"
        Write-Host "During install, tick 'Add python.exe to PATH'."
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Ok "Using Python $($py.Version) to create the virtual environment..."
    & $py.Exe @($py.Pre + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to create the virtual environment."; Read-Host "Press Enter to exit"; exit 1 }

    Write-Host "Installing backend requirements. This can take several minutes"
    Write-Host "(cadquery-ocp is a large download)..."
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install Python dependencies. See the pip output above."
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ---------------------------------------------------------------
# 2. Verify the venv actually works
#    (a venv created under a different path keeps its files but its
#     interpreter reference is dead)
# ---------------------------------------------------------------
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Err "The virtual environment is missing .venv\Scripts\python.exe."
    Write-Host "Delete the .venv folder and run this script again."
    Read-Host "Press Enter to exit"
    exit 1
}

# try/catch is required here: under Windows PowerShell 5.1 with
# ErrorActionPreference=Stop, redirected stderr from a native command is
# converted to ErrorRecords and the first one THROWS - i.e. a failing import
# would kill the script before reaching the friendly message below.
try { & $venvPy -c "import uvicorn" 2>$null | Out-Null } catch { }
if ($LASTEXITCODE -ne 0) {
    Write-Err "The virtual environment is broken (its Python or uvicorn is unusable)."
    Write-Host "This usually happens after moving or renaming the project folder."
    Write-Host "Delete the .venv folder and run this script again."
    Read-Host "Press Enter to exit"
    exit 1
}

# ---------------------------------------------------------------
# 3. Start the backend
# ---------------------------------------------------------------
# If something already listens on 8000, uvicorn would crash with "address in
# use" while the health check below happily answers from the OLD process -
# reporting success against a stale server. Refuse instead.
$portBusy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($portBusy) {
    Write-Err "Port 8000 is already in use - a backend is probably still running."
    Write-Host "Run stop.bat first, then start again."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Starting FastAPI backend..."

# Start-Process cannot redirect stdout and stderr to the SAME file,
# so the streams go to two separate logs.
$backend = Start-Process -FilePath $venvPy `
    -ArgumentList "-m", "uvicorn", "api:app", "--reload" `
    -RedirectStandardOutput "backend.log" `
    -RedirectStandardError  "backend.err.log" `
    -NoNewWindow -PassThru

$backend.Id | Out-File -FilePath ".backend.pid" -Encoding ascii

# Wait for the backend to actually answer, otherwise the frontend proxy
# just returns 500s and the real error stays buried in the log.
$up = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:8000/openapi.json" `
            -UseBasicParsing -TimeoutSec 2 | Out-Null
        $up = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $up) {
    Write-Err "Backend failed to start. Last lines of the logs:"
    if (Test-Path "backend.err.log") { Get-Content "backend.err.log" -Tail 20 }
    if (Test-Path "backend.log")     { Get-Content "backend.log"     -Tail 20 }
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Ok "Backend is up."

# ---------------------------------------------------------------
# 4. Frontend
# ---------------------------------------------------------------
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "Node.js was not found on PATH."
    Write-Host "Install Node.js 22 LTS from: https://nodejs.org/"
    Read-Host "Press Enter to exit"
    exit 1
}

# Vite 5.4 wants node ^18 || >=20, but camera-controls (via @react-three/drei)
# declares >=22 and the eslint toolchain wants >=20.19. 20.19 is the honest floor.
$nodeRaw = (& node -v).Trim().TrimStart('v')
$nodeParts = $nodeRaw -split '\.'
$nodeMajor = [int]$nodeParts[0]
$nodeMinor = if ($nodeParts.Count -gt 1) { [int]$nodeParts[1] } else { 0 }

if ($nodeMajor -lt 20 -or ($nodeMajor -eq 20 -and $nodeMinor -lt 19)) {
    Write-Err "Node.js $nodeRaw is too old for this project."
    Write-Host "Node 20.19 or newer is required (22 LTS recommended)."
    Write-Host "Download from: https://nodejs.org/"
    Write-Host "Stopping the backend that was just started..."
    & "$PSScriptRoot\stop.ps1"
    Read-Host "Press Enter to exit"
    exit 1
}

Set-Location -Path (Join-Path $PSScriptRoot "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "First time setup: installing frontend dependencies..."
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install frontend dependencies."
        Set-Location -Path $PSScriptRoot
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Host "Starting Vite frontend..."
$frontend = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -RedirectStandardOutput "frontend.log" `
    -RedirectStandardError  "frontend.err.log" `
    -NoNewWindow -PassThru

$frontend.Id | Out-File -FilePath (Join-Path $PSScriptRoot ".frontend.pid") -Encoding ascii

Set-Location -Path $PSScriptRoot

Write-Host ""
Write-Ok "Both servers are running in the background."
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://localhost:5173"
Write-Host ""
Write-Host "Logs: backend.log / backend.err.log, frontend\frontend.log / frontend\frontend.err.log"
Write-Host "To stop them, run stop.bat (or .\stop.ps1)"
Write-Host ""
Read-Host "Press Enter to close this window (servers keep running)"
