param(
    [Parameter(Mandatory=$true)][string]$VendorRoot,
    [Parameter(Mandatory=$true)][string]$WorkRoot
)

$ErrorActionPreference = 'Stop'
$sessionRoot = Join-Path $WorkRoot ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $sessionRoot -Force | Out-Null
$sessionVendor = Join-Path $sessionRoot 'vendor'
Copy-Item -LiteralPath $VendorRoot -Destination $sessionVendor -Recurse
foreach ($line in Get-Content -LiteralPath (Join-Path $sessionVendor 'MANIFEST.sha256')) {
    if ($line -notmatch '^([0-9A-F]{64})  (.+)$') {
        throw "Invalid copied vendor manifest line: $line"
    }
    $expected = $Matches[1]
    $path = Join-Path $sessionVendor $Matches[2]
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -cne $expected) {
        throw "Copied vendor file hash mismatch: $path"
    }
}
[pscustomobject]@{
    Root = $sessionRoot
    QConn = Join-Path $sessionVendor 'QConn_Flash\QConn_Flash_Cmd.exe'
    ConfigTemplate = Join-Path $sessionVendor 'NCP_Binaries\mission_t01_flash_prog_cfg.ini'
    GeneratedConfig = Join-Path $sessionVendor 'NCP_Binaries\mission_t01_flash_prog_cfg_auto.ini'
    Efuse = Join-Path $sessionVendor 'NCP_Binaries\efusedata.bin'
}
