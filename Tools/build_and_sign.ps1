$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
$Builder = Join-Path $IdeRoot 'headless-build.bat'
$CubeProgrammerBin = Join-Path $IdeRoot 'plugins\com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_2.2.500.202603051304\tools\bin'
$SigningTool = Join-Path $CubeProgrammerBin 'STM32_SigningTool_CLI.exe'
$Workspace = Join-Path $WorkspaceRoot '.codex-cubeide-workspace'
$OutputDir = Join-Path $ProjectRoot 'FlashImages'
$UsbPdCore = Join-Path $ProjectRoot 'AppliNonSecure\USBPD\App\usbpd_dpm_core.c'

foreach ($required in @($Builder, $SigningTool)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required ST tool was not found: $required"
    }
}

# CubeMX owns usbpd_dpm_core.c and silently restores the STM32N6 CAD task to
# 1 KiB on Generate Code.  That size is known to overflow in the TCPP0203
# initialization path.  Refuse to build/sign a regressed image.
if (-not (Select-String -LiteralPath $UsbPdCore `
        -Pattern '^#define\s+OS_CAD_STACK_SIZE\s+N6_USBPD_CAD_STACK_SIZE\s*$' `
        -Quiet)) {
    throw 'Unsafe USB-PD CAD stack: restore OS_CAD_STACK_SIZE to N6_USBPD_CAD_STACK_SIZE after CubeMX Generate Code.'
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

foreach ($configuration in @(
    'N6_FSBL/Debug',
    'N6_AppliSecure/Debug',
    'N6_AppliNonSecure/Debug'
)) {
    & $Builder -data $Workspace -build $configuration
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed: $configuration"
    }
}

$images = @(
    @{
        Input = Join-Path $ProjectRoot 'FSBL\Debug\N6_FSBL.bin'
        Output = Join-Path $OutputDir 'N6_FSBL-trusted.bin'
        Maximum = 0x00100000
    },
    @{
        Input = Join-Path $ProjectRoot 'AppliSecure\Debug\N6_AppliSecure.bin'
        Output = Join-Path $OutputDir 'N6_AppliSecure-trusted.bin'
        Maximum = 0x00080000
    },
    @{
        Input = Join-Path $ProjectRoot 'AppliNonSecure\Debug\N6_AppliNonSecure.bin'
        Output = Join-Path $OutputDir 'N6_AppliNonSecure-trusted.bin'
        Maximum = 0x000FFC00
    }
)

foreach ($image in $images) {
    $inputFile = Get-Item -LiteralPath $image.Input
    if ($inputFile.Length -gt $image.Maximum) {
        throw "Image exceeds its reserved region: $($inputFile.FullName)"
    }

    & $SigningTool -bin $image.Input -nk -of 0x80000000 -t fsbl `
        -o $image.Output -hv 2.3 -align -dump $image.Output -s
    if ($LASTEXITCODE -ne 0) {
        throw "Signing failed: $($image.Input)"
    }
}

Write-Host "Build and signing completed. Images are in: $OutputDir"
