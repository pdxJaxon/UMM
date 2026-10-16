[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $repositoryRoot "backend")
try {
    python -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=80
}
finally {
    Pop-Location
}

Push-Location (Join-Path $repositoryRoot "frontend\angular-app")
try {
    npm run test:unit
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend unit tests failed."
    }
    npm run build
}
finally {
    Pop-Location
}