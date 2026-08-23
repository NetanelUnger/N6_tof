param(
    [switch]$Clean,

    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')

$tools = Get-N6DevelopmentTools -IdeRoot $IdeRoot
Invoke-N6NonSecureIncrementalBuild `
    -ProjectRoot $ProjectRoot `
    -Tools $tools `
    -Clean:$Clean

Write-Host 'Incremental Non-Secure build completed successfully.'
