param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, [uint32]::MaxValue)]
    [uint32]$FirmwareVersion,

    [string]$Port,

    [switch]$PackageOnly,

    [switch]$Clean,

    [switch]$AllowVersionJump,

    [switch]$SkipBootVerification,

    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')

function Wait-N6InstalledVersion {
    param(
        [string]$RequestedPort,
        [uint32]$ExpectedVersion,
        [int]$TimeoutSeconds = 45
    )

    # Share the complete-line parser with the factory verifier. The common
    # verifier also waits for the trial confirmation window before querying.
    Wait-N6RunningVersion `
        -RequestedPort $RequestedPort `
        -ExpectedVersion $ExpectedVersion `
        -TimeoutSeconds $TimeoutSeconds `
        -WaitForTrialConfirmation
}

$tools = Get-N6DevelopmentTools -IdeRoot $IdeRoot
$key = Join-Path $ProjectRoot '.local-dependencies\keys\firmware-update-p256-private.blob'
if (-not (Test-Path -LiteralPath $key -PathType Leaf)) {
    throw "The private firmware-update key was not found: $key"
}
if (-not (Test-Path -LiteralPath $tools.SigningTool -PathType Leaf)) {
    throw "STM32 signing tool was not found: $($tools.SigningTool)"
}

$requestedPort = $Port
if (-not $PackageOnly) {
    Assert-N6InstalledBootChain -ProjectRoot $ProjectRoot
    # Fail before changing the tracked version header if the final-test cable
    # is not connected. The port is rediscovered after the device resets.
    $initialPort = Wait-N6UsbCdcPort -RequestedPort $requestedPort
    Write-Host "Active CN8 CDC port: $initialPort. It will be rediscovered immediately before transfer."
}

$currentVersion = Get-N6FirmwareVersion -ProjectRoot $ProjectRoot
$expectedVersion = [uint64]$currentVersion + 1
if ((-not $AllowVersionJump) -and ([uint64]$FirmwareVersion -ne $expectedVersion)) {
    throw "The final update version must be exactly current + 1 ($expectedVersion). Use -AllowVersionJump only for a deliberate recovery."
}

$versionHeader = Join-Path $ProjectRoot 'Common\Update\firmware_build_version.h'
$originalVersionHeader = Get-Content -Raw -LiteralPath $versionHeader
$keepNewVersion = $false
try {
    Write-Host "Advancing the release version explicitly from $currentVersion to $FirmwareVersion."
    Set-N6FirmwareVersion `
        -ProjectRoot $ProjectRoot `
        -FirmwareVersion $FirmwareVersion

    Invoke-N6NonSecureIncrementalBuild `
        -ProjectRoot $ProjectRoot `
        -Tools $tools `
        -Clean:$Clean

    $outputRoot = Join-Path $ProjectRoot 'FlashImages'
    New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
    $inputBinary = Join-Path $ProjectRoot 'AppliNonSecure\Debug\N6_AppliNonSecure.bin'
    $trustedImage = Join-Path $outputRoot `
        ("N6_AppliNonSecure-v{0}-trusted.bin" -f $FirmwareVersion)
    $package = Join-Path $outputRoot `
        ("N6-Firmware-v{0}.n6fw" -f $FirmwareVersion)

    foreach ($replaceable in @($trustedImage, $package)) {
        if (Test-Path -LiteralPath $replaceable -PathType Leaf) {
            (Get-Item -LiteralPath $replaceable).IsReadOnly = $false
        }
    }

    & $tools.SigningTool `
        -bin $inputBinary `
        -nk `
        -of 0x80000000 `
        -t fsbl `
        -o $trustedImage `
        -hv 2.3 `
        -align `
        -dump $trustedImage `
        -s
    if ($LASTEXITCODE -ne 0) {
        throw 'Non-Secure STM32 image signing failed.'
    }

    & (Join-Path $PSScriptRoot 'New-FirmwareUpdatePackage.ps1') `
        -Image $trustedImage `
        -FirmwareVersion $FirmwareVersion `
        -Output $package `
        -PrivateKeyPath $key
    if ($LASTEXITCODE -ne 0) {
        throw 'Authenticated .n6fw package generation failed.'
    }

    Write-Host "Incremental release package created: $package"
    if ($PackageOnly) {
        Write-Host 'PackageOnly was requested; no hardware was modified and the tracked version remains unchanged.'
    }
    else {
        & (Join-Path $PSScriptRoot 'Send-Xmodem.ps1') `
            -File $package `
            -Port $requestedPort
        if ($LASTEXITCODE -ne 0) {
            throw 'XMODEM installation failed.'
        }

        # An ACK for EOT means Secure committed pending metadata. Keep the new
        # source version even if the subsequent reboot verification exposes a
        # problem, because the target may already have consumed this version.
        $keepNewVersion = $true
        if (-not $SkipBootVerification) {
            Wait-N6InstalledVersion `
                -RequestedPort $requestedPort `
                -ExpectedVersion $FirmwareVersion
        }

        Write-Host "Firmware version $FirmwareVersion was installed through the inactive slot and booted after reset."
    }
}
finally {
    if (-not $keepNewVersion) {
        [IO.File]::WriteAllText(
            $versionHeader,
            $originalVersionHeader,
            [Text.UTF8Encoding]::new($false))
    }
}
