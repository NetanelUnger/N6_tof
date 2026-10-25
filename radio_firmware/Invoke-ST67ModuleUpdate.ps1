# Console boundary for the BAT: retain failure exit codes without a raw stack trace.
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding = $OutputEncoding
try {
    & (Join-Path $PSScriptRoot 'Update-ST67Module.ps1') @args
}
catch {
    Write-Host ('ST67 UPDATE FAIL: ' + $_.Exception.Message) -ForegroundColor Yellow
    exit 1
}
