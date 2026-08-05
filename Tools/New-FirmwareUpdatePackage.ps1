param(
    [Parameter(Mandatory = $true)]
    [string]$Image,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, [uint32]::MaxValue)]
    [uint32]$FirmwareVersion,

    [Parameter(Mandatory = $true)]
    [string]$Output,

    [string]$PrivateKeyPath
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($PrivateKeyPath)) {
    $PrivateKeyPath = Join-Path $ProjectRoot '.local-dependencies\keys\firmware-update-p256-private.blob'
}

$imagePath = (Resolve-Path -LiteralPath $Image).Path
$keyPath = (Resolve-Path -LiteralPath $PrivateKeyPath).Path
$imageBytes = [System.IO.File]::ReadAllBytes($imagePath)

$slotSize = 0x00100000
$manifestSize = 256
if (($imageBytes.Length -lt 1032) -or ($imageBytes.Length -gt $slotSize)) {
    throw "Signed image size $($imageBytes.Length) is outside the update slot bounds."
}
if ([BitConverter]::ToUInt32($imageBytes, 0) -ne 0x324D5453) {
    throw 'The input is not an STM32 signed image (STM2 magic is absent).'
}
$encodedSize = [BitConverter]::ToUInt32($imageBytes, 108) + 0x240
if ($encodedSize -ne $imageBytes.Length) {
    throw "STM32 header size $encodedSize does not match file size $($imageBytes.Length)."
}

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$key = $null
$ecdsa = $null
try {
    $imageHash = $sha256.ComputeHash($imageBytes)
    $manifest = New-Object byte[] $manifestSize

    function Set-U16([byte[]]$Buffer, [int]$Offset, [uint16]$Value) {
        [Array]::Copy([BitConverter]::GetBytes($Value), 0, $Buffer, $Offset, 2)
    }
    function Set-U32([byte[]]$Buffer, [int]$Offset, [uint32]$Value) {
        [Array]::Copy([BitConverter]::GetBytes($Value), 0, $Buffer, $Offset, 4)
    }

    Set-U32 $manifest 0 0x5055364E
    Set-U16 $manifest 4 1
    Set-U16 $manifest 6 $manifestSize
    Set-U32 $manifest 8 0x4E363537
    Set-U32 $manifest 12 1
    Set-U32 $manifest 16 $imageBytes.Length
    Set-U32 $manifest 20 $FirmwareVersion
    Set-U32 $manifest 24 0
    [Array]::Copy($imageHash, 0, $manifest, 28, 32)

    $signedFields = New-Object byte[] 60
    [Array]::Copy($manifest, 0, $signedFields, 0, $signedFields.Length)
    $manifestHash = $sha256.ComputeHash($signedFields)

    $privateBlob = [System.IO.File]::ReadAllBytes($keyPath)
    $key = [System.Security.Cryptography.CngKey]::Import(
        $privateBlob,
        [System.Security.Cryptography.CngKeyBlobFormat]::EccPrivateBlob)
    $ecdsa = New-Object System.Security.Cryptography.ECDsaCng($key)
    $signature = $ecdsa.SignHash($manifestHash)
    if ($signature.Length -ne 64) {
        throw "Expected a 64-byte P-256 signature, received $($signature.Length)."
    }
    if (-not $ecdsa.VerifyHash($manifestHash, $signature)) {
        throw 'Local verification of the generated ECDSA signature failed.'
    }

    [Array]::Copy($signature, 0, $manifest, 60, 32)
    [Array]::Copy($signature, 32, $manifest, 92, 32)

    $outputDirectory = Split-Path -Parent $Output
    if (-not [string]::IsNullOrWhiteSpace($outputDirectory)) {
        New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    }
    $stream = [System.IO.File]::Open($Output, [System.IO.FileMode]::Create,
                                     [System.IO.FileAccess]::Write,
                                     [System.IO.FileShare]::None)
    try {
        $stream.Write($manifest, 0, $manifest.Length)
        $stream.Write($imageBytes, 0, $imageBytes.Length)
    }
    finally {
        $stream.Dispose()
    }
}
finally {
    if ($ecdsa -ne $null) { $ecdsa.Dispose() }
    if ($key -ne $null) { $key.Dispose() }
    $sha256.Dispose()
}

Write-Host "Signed firmware update package created: $Output"
Write-Host "Firmware version: $FirmwareVersion"
Write-Host "Package bytes: $($manifestSize + $imageBytes.Length)"
