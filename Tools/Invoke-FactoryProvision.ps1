$ErrorActionPreference = 'Stop'
try {
    & (Join-Path $PSScriptRoot 'Factory-Provision.ps1') @args
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
catch {
    Write-Host ('FACTORY PROVISION FAIL: ' + $_.Exception.Message) -ForegroundColor Yellow
    exit 1
}
