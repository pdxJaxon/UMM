param(
    [Parameter(Mandatory = $true)]
    [int]$DraftYear,
    [string]$Directory,
    [string]$IdentityMap,
    [int]$MinProspects = 150,
    [switch]$Commit
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Directory) {
    $Directory = Join-Path $repoRoot 'data\prospects'
}
$Directory = (Resolve-Path -LiteralPath $Directory).Path
if (-not $IdentityMap) {
    $defaultMap = Join-Path $Directory "pff-identity-map-$DraftYear.json"
    if (Test-Path -LiteralPath $defaultMap -PathType Leaf) {
        $IdentityMap = $defaultMap
    }
    if ($IdentityMap) {
        $IdentityMap = (Resolve-Path -LiteralPath $IdentityMap).Path
    }
}
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project Python environment not found: $python"
}

$logDirectory = Join-Path $Directory 'import-logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory ("pff-import-{0}-{1}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $PID)
Start-Transcript -Path $logPath | Out-Null
Push-Location (Join-Path $repoRoot 'backend')
try {
    $jobArguments = @(
        '-m', 'app.jobs.import_pff_csv', '--directory', $Directory,
        '--draft-year', $DraftYear, '--min-prospects', $MinProspects
    )
    if ($Commit) {
        $jobArguments += '--commit'
    }
    if ($IdentityMap) {
        $jobArguments += @('--identity-map', $IdentityMap)
    }
    & $python @jobArguments
    if ($LASTEXITCODE -ne 0) {
        throw "PFF candidate ingestion failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    Stop-Transcript | Out-Null
}
