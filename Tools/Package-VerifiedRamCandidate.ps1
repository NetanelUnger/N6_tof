param(
 [Parameter(Mandatory=$true)][string]$Binary,
 [Parameter(Mandatory=$true)][string]$OutputDirectory,
 [Parameter(Mandatory=$true)][uint32]$FirmwareVersion,
 [Parameter(Mandatory=$true)][string]$ExpectedSha256
)
$ErrorActionPreference='Stop'
function Get-CandidateSha256([string]$Path) {
 $algorithm=[Security.Cryptography.SHA256]::Create()
 try { return ([BitConverter]::ToString($algorithm.ComputeHash([IO.File]::ReadAllBytes($Path)))).Replace('-','').ToLowerInvariant() }
 finally { $algorithm.Dispose() }
}
$ProjectRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')
if ((Get-CandidateSha256 $Binary) -ine $ExpectedSha256) { throw 'Verified candidate binary changed.' }
$current=Get-N6FirmwareVersion -ProjectRoot $ProjectRoot
if ([uint64]$FirmwareVersion -ne ([uint64]$current+1)) { throw 'Package requires the explicitly HIL-tested current+1 version.' }
$key=Join-Path $ProjectRoot '.local-dependencies\keys\firmware-update-p256-private.blob'
if (-not (Test-Path -LiteralPath $key -PathType Leaf)) { throw 'BLOCKED: existing firmware update signing key is unavailable; no key will be created.' }
$tools=Get-N6DevelopmentTools -IdeRoot 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Inspect existing package outcome before retrying.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$trusted=Join-Path $OutputDirectory 'verified-trusted.bin'
$package=Join-Path $OutputDirectory ("N6-Firmware-v{0}.n6fw" -f $FirmwareVersion)
& $tools.SigningTool -bin $Binary -nk -of 0x80000000 -t fsbl -o $trusted -hv 2.3 -align -dump $trusted -s
if ($LASTEXITCODE -ne 0) { throw 'STM32 trusted-image packaging failed.' }
& (Join-Path $PSScriptRoot 'New-FirmwareUpdatePackage.ps1') -Image $trusted -FirmwareVersion $FirmwareVersion -Output $package -PrivateKeyPath $key
if ($LASTEXITCODE -ne 0) { throw 'Authenticated A/B update packaging failed.' }
if ((Get-CandidateSha256 $Binary) -ine $ExpectedSha256) { throw 'Input binary changed during packaging.' }
Write-Host "Package-only complete: $package. No build, version-header change, reset or persistent installation."
