param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$ExpectedSlot,
    [uint32]$ExpectedVersion = 0
)
$ErrorActionPreference = 'Stop'
$root=Split-Path -Parent $PSScriptRoot
$bytes=[IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Package))
if ($bytes.Length -lt 1288) { throw 'Truncated XIP package.' }
function U32([int]$Offset) { [BitConverter]::ToUInt32($bytes,$Offset) }
if ((U32 0) -ne 0x5055364e -or [BitConverter]::ToUInt16($bytes,4) -ne 1 -or
    [BitConverter]::ToUInt16($bytes,6) -ne 256 -or (U32 8) -ne 0x4e363537 -or (U32 12) -ne 1) {
    throw 'Unsupported manifest target/format.'
}
$imageSize=U32 16
$version=U32 20
$flag=if ($ExpectedSlot -eq 'A') {1} else {2}
$base=if ($ExpectedSlot -eq 'A') {0x70180000L} else {0x70280000L}
if ((U32 24) -ne $flag) { throw 'Signed execution slot differs from expected inactive slot.' }
if ($imageSize -gt 1MB -or $imageSize+256 -ne $bytes.Length -or $version -eq 0 -or
    ($ExpectedVersion -ne 0 -and $ExpectedVersion -ne $version)) { throw 'Invalid package size/version.' }
if ((U32 256) -ne 0x324d5453 -or (U32 (256+108))+0x240 -ne $imageSize) { throw 'Invalid STM32 image header.' }
$msp=U32 (256+0x400)
$reset=U32 (256+0x404)
if ($msp -le 0x24100000 -or $msp -gt 0x24200000 -or ($msp -band 7) -ne 0 -or
    ($reset -band 1) -eq 0 -or ($reset -band 4294967294L) -lt $base+0x400 -or
    ($reset -band 4294967294L) -ge $base+$imageSize) { throw 'Invalid XIP vectors.' }
$sha=[Security.Cryptography.SHA256]::Create()
$key=$null;$ecdsa=$null
try {
    $digest=$sha.ComputeHash($bytes,256,$imageSize)
    for ($i=0;$i -lt 32;$i++) { if ($digest[$i] -ne $bytes[28+$i]) { throw 'Image hash mismatch.' } }
    $publicHeader=[IO.File]::ReadAllText((Join-Path $root 'Common/Update/firmware_signing_public_key.h'))
    $blob=New-Object byte[] 72
    [Array]::Copy([BitConverter]::GetBytes([uint32]0x31534345),0,$blob,0,4)
    [Array]::Copy([BitConverter]::GetBytes([uint32]32),0,$blob,4,4)
    foreach ($axis in @('X','Y')) {
        $match=[regex]::Match($publicHeader,"FW_SIGNING_PUBLIC_KEY_$axis\[32\]\s*=\s*\{([^}]+)\}")
        $values=[regex]::Matches($match.Groups[1].Value,'0x([0-9a-fA-F]{2})')
        if ($values.Count -ne 32) { throw 'Invalid tracked P256 public key.' }
        $offset=if ($axis -eq 'X') {8} else {40}
        for ($i=0;$i -lt 32;$i++) { $blob[$offset+$i]=[Convert]::ToByte($values[$i].Groups[1].Value,16) }
    }
    $key=[Security.Cryptography.CngKey]::Import($blob,[Security.Cryptography.CngKeyBlobFormat]::EccPublicBlob)
    $ecdsa=[Security.Cryptography.ECDsaCng]::new($key)
    $manifestDigest=$sha.ComputeHash($bytes,0,60)
    $signature=New-Object byte[] 64
    [Array]::Copy($bytes,60,$signature,0,64)
    if (-not $ecdsa.VerifyHash($manifestDigest,$signature)) { throw 'Manifest signature mismatch.' }
    [pscustomobject]@{status='VERIFIED_OFFLINE';slot=$ExpectedSlot;version=$version;bytes=$bytes.Length;reset=('0x{0:X8}' -f $reset);sha256=([BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').ToLowerInvariant())}
} finally {
    if ($null -ne $ecdsa) {$ecdsa.Dispose()}
    if ($null -ne $key) {$key.Dispose()}
    $sha.Dispose()
}
