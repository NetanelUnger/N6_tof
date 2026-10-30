param([Parameter(Mandatory=$true)][string]$Package)
$ErrorActionPreference='Stop'
$verifier=Join-Path $PSScriptRoot '../Tools/Test-XipPackage.ps1'
$original=[IO.File]::ReadAllBytes((Resolve-Path $Package))
$folder=Join-Path $env:TEMP ('n6-xip-negative-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $folder | Out-Null
try {
    & $verifier -Package $Package -ExpectedSlot B -ExpectedVersion 12 | Out-Null
    $cases=1
    foreach ($mutation in @('signature','payload','flags','length','version','vectors')) {
        $bytes=[byte[]]$original.Clone()
        switch($mutation) {
            signature {$bytes[60]=$bytes[60] -bxor 1}
            payload {$bytes[256+1500]=$bytes[256+1500] -bxor 1}
            flags {$bytes[24]=1}
            length {$bytes=$bytes[0..($bytes.Length-2)]}
            version {$bytes[20]=0}
            vectors {$bytes[256+0x404]=$bytes[256+0x404] -band 0xfe}
        }
        $path=Join-Path $folder "$mutation.n6fw"
        [IO.File]::WriteAllBytes($path,$bytes)
        $rejected=$false
        try { & $verifier -Package $path -ExpectedSlot B -ExpectedVersion 12 | Out-Null }
        catch {$rejected=$true}
        if (-not $rejected) {throw "Corrupt $mutation accepted"}
        $cases++;Write-Host "PASS reject $mutation"
    }
    # The creator must also refuse assigning an XIP-B binary to A or RAM.
    $trusted=Join-Path $folder 'trusted.bin';[IO.File]::WriteAllBytes($trusted,$original[256..($original.Length-1)])
    foreach ($mode in @('XIP-A','RAM')) {
        $output=Join-Path $folder "$mode.n6fw"
        $rejected=$false
        try { & (Join-Path $PSScriptRoot '../Tools/New-FirmwareUpdatePackage.ps1') -Image $trusted -FirmwareVersion 12 -ExecutionMode $mode -Output $output | Out-Null }
        catch {$rejected=$true}
        if (-not $rejected -or (Test-Path $output)) {throw 'Creator allowed incompatible vectors or produced output'}
        $cases++;Write-Host "PASS creator rejects $mode before output"
    }
    Write-Host "PASS $cases offline package cases; independent tracked public-key verification; no private-key export or hardware access"
} finally {
    $resolved=[IO.Path]::GetFullPath($folder)
    $tempRoot=[IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')+[IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase)) {throw 'Unsafe cleanup target'}
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
