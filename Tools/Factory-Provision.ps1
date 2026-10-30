param(
    [string]$Port,
    [switch]$BuildOnly,
    [switch]$SkipBuild,
    [switch]$SkipBootVerification,
    [switch]$ConfirmErase,
    [switch]$NonInteractive,
    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')
. (Join-Path $PSScriptRoot 'N6-FactoryValidation.ps1')

$firmwareVersion = Get-N6FirmwareVersion -ProjectRoot $ProjectRoot

function Assert-FactoryArtifactsCurrent {
    Assert-N6FactoryManifest -ProjectRoot $ProjectRoot -FirmwareVersion $firmwareVersion
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
if ($NonInteractive -and -not $ConfirmErase -and -not $BuildOnly) {
    throw '-NonInteractive requires -ConfirmErase. ConfirmErase alone does not skip jumper/USB prompts.'
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

if (-not $ConfirmErase) {
    $confirmation = Read-Host 'Type ERASE ALL to continue'
    if ($confirmation -cne 'ERASE ALL') {
        Write-Host 'Cancelled; the board was not modified.'
        exit 2
    }
}

Write-Host ''
Write-Host 'Set BOOT0=1-2 and BOOT1=2-3, connect ST-LINK, then press RESET.'
if (-not $NonInteractive) {
    [void](Read-Host 'Press Enter only after the board is in development boot')
}

& (Join-Path $PSScriptRoot 'program_flash.ps1') `
    -FullErase `
    -IdeRoot $IdeRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Factory external-NOR programming failed.'
}

Write-Host 'Programming and write verification PASS. Boot has not been verified yet.'
if (-not $SkipBootVerification) {
    Write-Host ''
    Write-Host 'Set BOOT0=1-2 and BOOT1=1-2, connect CN8, then press RESET.'
    if (-not $NonInteractive) {
        [void](Read-Host 'Press Enter after changing BOOT, connecting CN8 and pressing RESET; USB detection will then wait up to 45 seconds')
    }
    try {
        Wait-N6RunningVersion -RequestedPort $Port -ExpectedVersion $firmwareVersion -TimeoutSeconds 45
    }
    catch {
        $bootError = $_.Exception.Message
        $cdcPresent = $false
        try {
            [void](Wait-N6UsbCdcPort -RequestedPort $Port -TimeoutSeconds 1)
            $cdcPresent = $true
        } catch { }
        if ($cdcPresent) { throw "Programming passed but application boot/version verification failed: $bootError" }
        Write-Host 'No CN8 USB CDC response. Do not erase or program again just for a missing COM port.'
        Write-Host 'Keep BOOT0=1-2 and BOOT1=1-2. Disconnect ALL power: ST-LINK USB, CN8 USB and any external supply.'
        Write-Host 'Wait until all LEDs are off, then reconnect ST-LINK and a CN8 USB DATA cable.'
        Write-Host 'This is a cold-power recovery check; the reason RESET was insufficient is not established.'
        if ($NonInteractive) { throw "Boot NOT VERIFIED; cold-power check needs the operator. $bootError" }
        [void](Read-Host 'Press Enter after the complete power disconnect/reconnect; no programming will be repeated')
        try {
            Wait-N6RunningVersion -RequestedPort $Port -ExpectedVersion $firmwareVersion -TimeoutSeconds 45
        }
        catch { throw "Programming passed but boot remains NOT VERIFIED after cold power. $($_.Exception.Message)" }
    }
} else {
    Write-Host 'FACTORY PROGRAMMING PASS: full erase, programming and write verification completed. BOOT NOT VERIFIED (-SkipBootVerification).'
    exit 0
}

Write-Host ''
Write-Host 'FACTORY PROVISION PASS: full erase, programming, verification, and boot completed.'
