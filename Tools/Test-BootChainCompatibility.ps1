# No hardware access: exercise the release gate against temporary boot images.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')
$testParent = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.n6-debug'))
$testRoot = Join-Path $testParent ('bootchain-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $testRoot 'training/state'),
    (Join-Path $testRoot 'AppliSecure/Debug'), (Join-Path $testRoot 'FSBL/Debug') | Out-Null
$securePath = Join-Path $testRoot 'AppliSecure/Debug/N6_AppliSecure.bin'
$fsblPath = Join-Path $testRoot 'FSBL/Debug/N6_FSBL.bin'
$statePath = Join-Path $testRoot 'training/state/09_secure_bootstrap.json'
function Assert-Rejected([string]$Label) {
    $rejected = $false
    try { Assert-N6InstalledBootChain -ProjectRoot $testRoot }
    catch {
        if ($_.Exception.Message -notmatch '09_BOOTSTRAP_NPU_SWD') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "$Label was accepted." }
    Write-Host "PASS: $Label is rejected before release."
}
try {
    [IO.File]::WriteAllBytes($securePath, [byte[]](1, 2, 3))
    [IO.File]::WriteAllBytes($fsblPath, [byte[]](4, 5, 6))
    Assert-Rejected 'Missing installation record'
    $state = @{ status = 'complete'; details = @{} }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath
    Assert-Rejected 'Legacy complete record without image hashes'
    $state.details.secure_raw_sha256 = Get-N6FileSha256 -Path $securePath
    $state.details.fsbl_raw_sha256 = Get-N6FileSha256 -Path $fsblPath
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath
    Assert-N6InstalledBootChain -ProjectRoot $testRoot
    Write-Host 'PASS: both installed images match the build.'
    [IO.File]::WriteAllBytes($securePath, [byte[]](1, 2, 7))
    Assert-Rejected 'Changed Secure image / gateway addresses'
    [IO.File]::WriteAllBytes($securePath, [byte[]](1, 2, 3))
    [IO.File]::WriteAllBytes($fsblPath, [byte[]](4, 5, 8))
    Assert-Rejected 'Changed FSBL image'
}
finally {
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    if (-not $resolvedTestRoot.StartsWith($testParent + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup path.' }
    Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
}
