param(
    [string]$Output
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $ProjectRoot 'FlashImages\N6-BootMetadata.bin'
}

function Set-UInt32LittleEndian {
    param(
        [byte[]]$Buffer,
        [int]$Offset,
        [uint32]$Value
    )

    $encoded = [BitConverter]::GetBytes($Value)
    [Array]::Copy($encoded, 0, $Buffer, $Offset, 4)
}

function Get-Crc32 {
    param(
        [byte[]]$Buffer,
        [int]$Length
    )

    [uint64]$crc = 4294967295L
    for ($index = 0; $index -lt $Length; $index++) {
        $crc = ($crc -bxor [uint64]$Buffer[$index]) -band 4294967295L
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($crc -band 1) -ne 0) {
                $crc = (($crc -shr 1) -bxor 3988292384L) -band 4294967295L
            }
            else {
                $crc = ($crc -shr 1) -band 4294967295L
            }
        }
    }
    return [uint32](($crc -bxor 4294967295L) -band 4294967295L)
}

# FW_BootRecord_t, format version 1.  Version 0 deliberately denotes the
# factory image in Slot A; every remotely installed package starts at version 1.
$record = New-Object byte[] 1024
Set-UInt32LittleEndian $record 0 0x5242364E
Set-UInt32LittleEndian $record 4 1
Set-UInt32LittleEndian $record 8 0
Set-UInt32LittleEndian $record 12 1
Set-UInt32LittleEndian $record 16 0
Set-UInt32LittleEndian $record 20 0
Set-UInt32LittleEndian $record 24 ([uint32]::MaxValue)
Set-UInt32LittleEndian $record 28 0
Set-UInt32LittleEndian $record 1020 (Get-Crc32 $record 1020)

$parent = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $parent | Out-Null
[IO.File]::WriteAllBytes($Output, $record)
Write-Host "Factory boot metadata created: $Output"
