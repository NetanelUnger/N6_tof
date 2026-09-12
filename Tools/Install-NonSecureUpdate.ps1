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

    # The confirmation task intentionally waits five seconds before closing the
    # rollback window. Do not call a trial image verified before that point.
    Start-Sleep -Seconds 6
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = $null

    while ([DateTime]::UtcNow -lt $deadline) {
        $candidatePort = $RequestedPort
        $serial = $null
        try {
            if ([string]::IsNullOrWhiteSpace($candidatePort)) {
                $candidatePort = Find-N6UsbCdcPort
            }

            $serial = [IO.Ports.SerialPort]::new(
                $candidatePort,
                115200,
                [IO.Ports.Parity]::None,
                8,
                [IO.Ports.StopBits]::One)
            $serial.Handshake = [IO.Ports.Handshake]::None
            $serial.ReadTimeout = 200
            $serial.WriteTimeout = 3000
            $serial.DtrEnable = $true
            $serial.Open()
            Start-Sleep -Milliseconds 500
            $serial.DiscardInBuffer()
            $serial.Write("version`r")

            $text = [Text.StringBuilder]::new()
            $responseDeadline = [DateTime]::UtcNow.AddSeconds(5)
            while ([DateTime]::UtcNow -lt $responseDeadline) {
                try {
                    $value = $serial.ReadByte()
                    if ($value -ge 0) {
                        [void]$text.Append([char]$value)
                    }
                }
                catch [TimeoutException] {
                    # Continue until the complete response deadline.
                }

                $match = [regex]::Match(
                    $text.ToString(),
                    'Firmware version:\s*([0-9]+)')
                if ($match.Success) {
                    $observedVersion = [uint32]$match.Groups[1].Value
                    if ($observedVersion -ne $ExpectedVersion) {
                        throw "The board booted firmware version $observedVersion instead of expected version $ExpectedVersion."
                    }
                    Write-Host "Verified running firmware version $observedVersion after reset and the confirmation window."
                    return
                }
            }
            $lastError = "No version response was received from $candidatePort."
        }
        catch {
            $lastError = $_.Exception.Message
        }
        finally {
            if (($null -ne $serial) -and $serial.IsOpen) {
                $serial.Close()
            }
            if ($null -ne $serial) {
                $serial.Dispose()
            }
        }
        Start-Sleep -Milliseconds 500
    }

    throw "The updated application could not be verified after reset. Last error: $lastError"
}

$tools = Get-N6DevelopmentTools -IdeRoot $IdeRoot
$key = Join-Path $ProjectRoot '.local-dependencies\keys\firmware-update-p256-private.blob'
if (-not (Test-Path -LiteralPath $key -PathType Leaf)) {
    throw "The private firmware-update key was not found: $key"
}
if (-not (Test-Path -LiteralPath $tools.SigningTool -PathType Leaf)) {
    throw "STM32 signing tool was not found: $($tools.SigningTool)"
}

if (-not $PackageOnly -and [string]::IsNullOrWhiteSpace($Port)) {
    # Fail before changing the tracked version header if the final-test cable
    # is not connected. The port is rediscovered after the device resets.
    $Port = Find-N6UsbCdcPort
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
            -Port $Port
        if ($LASTEXITCODE -ne 0) {
            throw 'XMODEM installation failed.'
        }

        # An ACK for EOT means Secure committed pending metadata. Keep the new
        # source version even if the subsequent reboot verification exposes a
        # problem, because the target may already have consumed this version.
        $keepNewVersion = $true
        if (-not $SkipBootVerification) {
            Wait-N6InstalledVersion `
                -RequestedPort $Port `
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
