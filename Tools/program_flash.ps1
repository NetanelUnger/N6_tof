param(
    [switch]$FullErase
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
$CubeProgrammerBin = Join-Path $IdeRoot 'plugins\com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_2.2.500.202603051304\tools\bin'
$Programmer = Join-Path $CubeProgrammerBin 'STM32_Programmer_CLI.exe'
$ExternalLoader = Join-Path $CubeProgrammerBin 'ExternalLoader\MX25UM51245G_STM32N6570-NUCLEO.stldr'
$ImageDir = Join-Path $ProjectRoot 'FlashImages'

$Fsbl = Join-Path $ImageDir 'N6_FSBL-trusted.bin'
$Secure = Join-Path $ImageDir 'N6_AppliSecure-trusted.bin'
$NonSecure = Join-Path $ImageDir 'N6_AppliNonSecure-trusted.bin'
$BootMetadata = Join-Path $ImageDir 'N6-BootMetadata.bin'

foreach ($required in @($Programmer, $ExternalLoader, $Fsbl, $Secure, $NonSecure, $BootMetadata)) {
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
