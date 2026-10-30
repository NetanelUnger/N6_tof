$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb'
$evidence = Join-Path $PSScriptRoot 'evidence\st67-cp3-20261028\headers'
New-Item -ItemType Directory -Path $evidence -ErrorAction Stop | Out-Null
$probeTemp = Join-Path ([IO.Path]::GetTempPath()) ('n6-manifest-only-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $probeTemp | Out-Null
$records = @()
foreach ($item in @(@{slot='A';build='v49-A-product-settings';hash='753b8cc6c2a4c9c8c393e6d78f0ad2c699787437195e0a3cf519d2486f33e3bc';version=49},
                    @{slot='B';build='v50-B-timed-demo-map';hash='2a7aedb4fcd156f8eafa0bd322116452cf8fbd1f1e4aec7989ed7e84b5d9e156';version=50})) {
    $original = Join-Path $repo ('.local-dependencies\xip\' + $item.build + '\N6-XIP-' + $item.slot + '-v' + $item.version + '.n6fw')
    if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.hash) {throw 'Original artifact changed'}
    $image = Join-Path (Split-Path -Parent $original) 'application-trusted.bin'
    $tempPackage = Join-Path $probeTemp ('NEVER-INSTALL-probe-' + $item.slot + '.n6fw')
    try {
        & (Join-Path $repo 'Tools\New-FirmwareUpdatePackage.ps1') -Image $image -FirmwareVersion 52 -ExecutionMode ('XIP-' + $item.slot) -Output $tempPackage
        $verified = & (Join-Path $repo 'Tools\Test-XipPackage.ps1') -Package $tempPackage -ExpectedSlot $item.slot -ExpectedVersion 52
        $bytes = [IO.File]::ReadAllBytes($tempPackage)
        $header = [byte[]]$bytes[0..255]
        $path = Join-Path $evidence ('NO-INSTALL-' + $item.slot + '-version52.manifest')
        [IO.File]::WriteAllBytes($path,$header)
        $records += [pscustomobject]@{slot=$item.slot;purpose='Header-only Begin/Abort diagnostic. Original image is NOT firmware52 and must never be installed as52.';originalPackage=$original;originalPackageSha256=$item.hash;headerBytes=$header.Length;headerSha256=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant();verification=$verified}
    } finally {
        if (Test-Path -LiteralPath $tempPackage) {
            if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($tempPackage)) -ne [IO.Path]::GetFullPath($probeTemp)) {throw 'Temporary package deletion scope mismatch'}
            Remove-Item -LiteralPath $tempPackage -ErrorAction Stop
        }
    }
}
$records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'headers.json') -Encoding utf8
Remove-Item -LiteralPath $probeTemp -ErrorAction Stop
Write-Output 'PASS offline signatures/vectors/hash; only two 256-byte noninstallable probe manifests retained; temporary full packages removed.'
