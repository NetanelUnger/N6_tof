# Hardware-free checks: no serial endpoint is opened and no bytes are sent.
$ErrorActionPreference = 'Stop'
foreach ($file in @('N6-DevCommon.ps1', 'Install-NonSecureUpdate.ps1', 'Send-Xmodem.ps1')) {
    $tokens = $null
    $parseErrors = $null
    [void][Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $PSScriptRoot $file), [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count -ne 0) { throw ($parseErrors -join "`n") }
}
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')
$presentPorts = @([IO.Ports.SerialPort]::GetPortNames())
$ghostPort = 'COM65000'
if ($ghostPort -in $presentPorts) { throw 'Test ghost port is unexpectedly present.' }

function Get-CimInstance {
    [CmdletBinding()]
    param([string]$ClassName)
    if ($script:denyCim) { throw 'Simulated CIM access denied.' }
    return $script:testDevices
}
function New-TestCdcDevice([string]$PortName) {
    [pscustomobject]@{ PNPDeviceID = 'USB\VID_0483&PID_5740\TEST'; Name = "N6 ($PortName)" }
}

$script:denyCim = $false
$script:testDevices = @(New-TestCdcDevice $ghostPort)
$message = ''
try { Find-N6UsbCdcPort | Out-Null }
catch { $message = $_.Exception.Message }
if ($message -notmatch 'was not found') { throw "Disconnected CIM device accepted: $message" }
Write-Host 'PASS: disconnected CIM identity is rejected.'

if ($presentPorts.Count -gt 0) {
    $script:testDevices = @((New-TestCdcDevice $ghostPort), (New-TestCdcDevice $presentPorts[0]))
    if ((Find-N6UsbCdcPort) -ne $presentPorts[0]) { throw 'Present identity was not selected.' }
    Write-Host 'PASS: present identity is selected while stale identities are ignored.'
}

function Test-Path {
    [CmdletBinding()]
    param([string]$LiteralPath)
    return $true
}
function Get-ChildItem {
    [CmdletBinding()]
    param([string]$LiteralPath, [switch]$Recurse)
    return [pscustomobject]@{ PSChildName = 'Device Parameters'; PSPath = 'mock-usb' }
}
function Get-ItemProperty {
    [CmdletBinding()]
    param([string]$LiteralPath, [string]$Name)
    return [pscustomobject]@{ PortName = $script:registryPort }
}
$script:denyCim = $true
$script:registryPort = $ghostPort
$message = ''
try { Find-N6UsbCdcPort | Out-Null }
catch { $message = $_.Exception.Message }
if ($message -notmatch 'was not found') { throw "Disconnected registry device accepted: $message" }
Write-Host 'PASS: disconnected registry fallback is rejected when CIM is denied.'

if ($presentPorts.Count -gt 0) {
    $script:registryPort = $presentPorts[0]
    if ((Find-N6UsbCdcPort) -ne $presentPorts[0]) { throw 'Present registry fallback was lost.' }
    Write-Host 'PASS: present registry fallback remains supported.'
}

$message = ''
try { Wait-N6UsbCdcPort -RequestedPort $ghostPort -TimeoutSeconds 1 | Out-Null }
catch { $message = $_.Exception.Message }
if ($message -notmatch 'not currently present') { throw "Missing explicit port accepted: $message" }
Write-Host 'PASS: missing explicit port times out before transfer.'

$script:discoveries = 0
function Find-N6UsbCdcPort {
    $script:discoveries++
    if ($script:discoveries -eq 1) { throw 'Endpoint not yet enumerated.' }
    return 'COM123'
}
if ((Wait-N6UsbCdcPort -TimeoutSeconds 2) -ne 'COM123' -or $script:discoveries -ne 2) {
    throw 'Enumeration was not retried.'
}
Write-Host 'PASS: auto discovery retries until enumeration completes.'
