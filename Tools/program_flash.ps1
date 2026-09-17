param(
    [switch]$FullErase,
    [switch]$FsblOnly,
    [switch]$BootChainOnly,
    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')
$DevelopmentTools = Get-N6DevelopmentTools -IdeRoot $IdeRoot
$Programmer = Join-Path $DevelopmentTools.ProgrammerBin 'STM32_Programmer_CLI.exe'
$ExternalLoader = Join-Path $DevelopmentTools.ProgrammerBin 'ExternalLoader\MX25UM51245G_STM32N6570-NUCLEO.stldr'
$ImageDir = Join-Path $ProjectRoot 'FlashImages'

$Fsbl = Join-Path $ImageDir 'N6_FSBL-trusted.bin'
$Secure = Join-Path $ImageDir 'N6_AppliSecure-trusted.bin'
$NonSecure = Join-Path $ImageDir 'N6_AppliNonSecure-trusted.bin'
$BootMetadata = Join-Path $ImageDir 'N6-BootMetadata.bin'

$SelectedModes = @($FullErase, $FsblOnly, $BootChainOnly) |
    Where-Object { $_ }
if ($SelectedModes.Count -gt 1) {
    throw 'FullErase, FsblOnly, and BootChainOnly are mutually exclusive.'
}

$RequiredFiles = @($Programmer, $ExternalLoader, $Fsbl)
if ($BootChainOnly) {
    $RequiredFiles += $Secure
}
elseif (-not $FsblOnly) {
    $RequiredFiles += @($Secure, $NonSecure, $BootMetadata)
}

foreach ($required in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file was not found: $required"
    }
}

Write-Host 'Programming the NUCLEO-N657X0-Q external NOR flash.'
Write-Host 'The board must be connected through ST-LINK.'
Write-Host 'For programming: set BOOT0=1-2 and BOOT1=2-3 (development boot), then press RESET.'
Write-Host 'After programming: set BOOT0=1-2 and BOOT1=1-2 (external-Flash boot), then press RESET.'

if ($FullErase) {
    Write-Host 'Erasing the complete external NOR flash before programming...'
    & $Programmer `
        -c port=SWD mode=UR reset=HWrst `
        -el $ExternalLoader `
        -e all

    if ($LASTEXITCODE -ne 0) {
        throw 'External NOR flash erase failed. Verify that BOOT1 is in position 2-3.'
    }
}

if ($FsblOnly) {
    Write-Host 'Programming only the FSBL; application slots and boot metadata will be preserved.'
    & $Programmer `
        -c port=SWD mode=UR reset=HWrst `
        -el $ExternalLoader `
        -d $Fsbl 0x70000000 -v

    if ($LASTEXITCODE -ne 0) {
        throw 'FSBL programming or verification failed.'
    }

    Write-Host 'FSBL programming and verification completed successfully.'
    Write-Host 'Set BOOT0 and BOOT1 to positions 1-2, then press RESET to resume the pending update.'
    exit 0
}

if ($BootChainOnly) {
    Write-Host 'Programming the FSBL and Secure runtime only.'
    Write-Host 'Application slots and A/B boot metadata will be preserved.'
    & $Programmer `
        -c port=SWD mode=UR reset=HWrst `
        -el $ExternalLoader `
        -d $Fsbl 0x70000000 -v `
        -d $Secure 0x70100000 -v

    if ($LASTEXITCODE -ne 0) {
        throw 'Boot-chain programming or verification failed.'
    }

    Write-Host 'FSBL and Secure programming completed successfully.'
    Write-Host 'Both application slots and the current update state were preserved.'
    Write-Host 'Set BOOT0 and BOOT1 to positions 1-2, then press RESET.'
    exit 0
}

& $Programmer `
    -c port=SWD mode=UR reset=HWrst `
    -el $ExternalLoader `
    -d $Fsbl 0x70000000 -v `
    -d $Secure 0x70100000 -v `
    -d $NonSecure 0x70180000 -v `
    -d $BootMetadata 0x703E0000 -v `
    -d $BootMetadata 0x703F0000 -v

if ($LASTEXITCODE -ne 0) {
    throw 'Flash programming or verification failed.'
}

Write-Host 'Programming and verification completed successfully.'
Write-Host 'Set BOOT0 and BOOT1 to positions 1-2, then press RESET to boot from external Flash.'
