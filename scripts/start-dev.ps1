param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 4201
)

$ErrorActionPreference = 'Stop'

function Stop-ProcessOnPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Host "No listener found on port $Port"
        return
    }

    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        if ($processId -le 0) {
            continue
        }

        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }

        Stop-Process -Id $processId -Force
        Write-Host "Stopped $($process.ProcessName) on port $Port (PID $processId)"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $repoRoot 'backend'
$frontendPath = Join-Path $repoRoot 'frontend/angular-app'
$nodePath = 'C:\Program Files\nodejs'

if (-not (Test-Path $backendPath)) {
    throw "Backend folder not found: $backendPath"
}

if (-not (Test-Path $frontendPath)) {
    throw "Frontend folder not found: $frontendPath"
}

if (-not (Test-Path (Join-Path $nodePath 'node.exe'))) {
    throw "Node.js was not found in $nodePath"
}

Stop-ProcessOnPort -Port $BackendPort
Stop-ProcessOnPort -Port $FrontendPort

$frontendCommand = "`$env:Path = '$nodePath;' + `$env:Path; cd '$frontendPath'; npm start -- --host 0.0.0.0 --port $FrontendPort"
$backendCommand = "`$ErrorActionPreference = 'Stop'; cd '$backendPath'; python -m app.db.initialize; if (`$LASTEXITCODE -ne 0) { exit `$LASTEXITCODE }; python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"

Start-Process powershell -ArgumentList '-NoExit', '-Command', $backendCommand -WorkingDirectory $backendPath
Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontendCommand -WorkingDirectory $frontendPath

Write-Host "Backend starting on http://127.0.0.1:$BackendPort"
Write-Host "Frontend starting on http://127.0.0.1:$FrontendPort"