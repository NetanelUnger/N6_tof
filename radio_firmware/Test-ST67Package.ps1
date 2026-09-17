$ErrorActionPreference = 'Stop'
$RadioRoot = $PSScriptRoot
$contract = Get-Content -Raw -LiteralPath (Join-Path $RadioRoot 'contract.json') |
    ConvertFrom-Json

$manifest = Join-Path $RadioRoot 'vendor\MANIFEST.sha256'
foreach ($line in Get-Content -LiteralPath $manifest) {
    if ($line -notmatch '^([0-9A-F]{64})  (.+)$') {
        throw "Invalid vendor manifest line: $line"
    }
    $path = Join-Path (Join-Path $RadioRoot 'vendor') $Matches[2]
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing vendor file: $path"
    }
    $stream = [IO.File]::OpenRead($path)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $actual = [BitConverter]::ToString(
            $sha256.ComputeHash($stream)).Replace('-', '')
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
    if ($actual -cne $Matches[1]) {
        throw "Vendor manifest hash mismatch: $path"
    }
}
Write-Host '[OK] complete vendor manifest'

$items = @(
    @($contract.ncp_binary, $contract.ncp_binary_sha256),
    @($contract.boot2_binary, $contract.boot2_binary_sha256),
    @($contract.littlefs_binary, $contract.littlefs_binary_sha256)
)
foreach ($property in $contract.integrity.PSObject.Properties) {
    $items += ,@($property.Name, [string]$property.Value)
}

foreach ($item in $items) {
    $path = Join-Path $RadioRoot $item[0]
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing ST67 update file: $path"
    }
    $stream = [IO.File]::OpenRead($path)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $actual = [BitConverter]::ToString(
            $sha256.ComputeHash($stream)).Replace('-', '')
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
    if ($actual -cne $item[1]) {
        throw "Hash mismatch: $path"
    }
    Write-Host '[OK]' $item[0]
}

Write-Host "Package PASS: SDK $($contract.expected_sdk_version), profile $($contract.profile)"
