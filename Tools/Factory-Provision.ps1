param(
    [string]$Port,
    [switch]$BuildOnly,
    [switch]$SkipBuild,
    [switch]$SkipBootVerification,
    [switch]$ConfirmErase,
    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')

$firmwareVersion = Get-N6FirmwareVersion -ProjectRoot $ProjectRoot
$factoryManifestPath = Join-Path $ProjectRoot 'FlashImages\factory-manifest.json'

function Assert-FactoryArtifactsCurrent {
    if (-not (Test-Path -LiteralPath $factoryManifestPath -PathType Leaf)) {
        throw 'Factory manifest is missing. Rerun without -SkipBuild.'
    }
    $manifest = Get-Content -Raw -LiteralPath $factoryManifestPath |
        ConvertFrom-Json
    if ([uint32]$manifest.firmware_version -ne $firmwareVersion) {
        throw "Factory artifacts are stale: manifest version $($manifest.firmware_version), source version $firmwareVersion. Rerun without -SkipBuild."
    }
    foreach ($property in $manifest.sha256.PSObject.Properties) {
        $artifact = Join-Path $ProjectRoot (Join-Path 'FlashImages' $property.Name)
        if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
            throw "Factory artifact is missing: $artifact"
        }
        $actual = Get-N6FileSha256 -Path $artifact
        if ($actual -cne [string]$property.Value) {
            throw "Factory artifact hash mismatch: $artifact. Rerun without -SkipBuild."
        }
    }
    Write-Host "Factory manifest PASS: version $firmwareVersion and all image hashes match."
}

Write-Host '============================================================'
Write-Host 'FACTORY PROVISION: erase and rebuild the complete external NOR'
Write-Host '============================================================'
Write-Host 'This removes both application slots and both metadata copies.'
Write-Host 'It then writes and verifies FSBL, Secure, slot A, and metadata.'
Write-Host "The factory image will contain firmware version $firmwareVersion."
Write-Host ''

if ($BuildOnly -and $SkipBuild) {
    throw '-BuildOnly and -SkipBuild cannot be combined.'
}
if ($BuildOnly) {
    & (Join-Path $PSScriptRoot 'build_and_sign.ps1') `
        -FirmwareVersion $firmwareVersion `
        -IdeRoot $IdeRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Factory build/sign validation failed.'
    }
    Assert-FactoryArtifactsCurrent
    Write-Host 'BUILD-ONLY PASS: complete factory images are ready; hardware was not modified.'
    exit 0
}

if (-not $ConfirmErase) {
    $confirmation = Read-Host 'Type ERASE ALL to continue'
    if ($confirmation -cne 'ERASE ALL') {
        Write-Host 'Cancelled; the board was not modified.'
        exit 2
    }
}

if (-not $SkipBuild) {
    Write-Host 'Building and signing the complete boot chain...'
    & (Join-Path $PSScriptRoot 'build_and_sign.ps1') `
        -FirmwareVersion $firmwareVersion `
        -IdeRoot $IdeRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Complete build/sign step failed; external NOR was not erased.'
    }
}

Assert-FactoryArtifactsCurrent

Write-Host ''
Write-Host 'Set BOOT0=1-2 and BOOT1=2-3, connect ST-LINK, then press RESET.'
if (-not $ConfirmErase) {
    [void](Read-Host 'Press Enter only after the board is in development boot')
}

& (Join-Path $PSScriptRoot 'program_flash.ps1') `
    -FullErase `
    -IdeRoot $IdeRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Factory external-NOR programming failed.'
}

if (-not $SkipBootVerification) {
    Write-Host ''
    Write-Host 'Set BOOT0=1-2 and BOOT1=1-2, connect CN8, then press RESET.'
    if (-not $ConfirmErase) {
        [void](Read-Host 'Press Enter after Windows has enumerated the CN8 COM port')
    }
    Wait-N6RunningVersion `
        -RequestedPort $Port `
        -ExpectedVersion $firmwareVersion `
        -TimeoutSeconds 45
}

Write-Host ''
Write-Host 'FACTORY PROVISION PASS: full erase, programming, verification, and boot completed.'
