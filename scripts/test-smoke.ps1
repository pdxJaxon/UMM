[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $repositoryRoot "backend")
try {
    python -m pytest -m smoke -q
}
finally {
    Pop-Location
}

Push-Location (Join-Path $repositoryRoot "frontend\angular-app")
try {
    npm run build
}
finally {
    Pop-Location
}