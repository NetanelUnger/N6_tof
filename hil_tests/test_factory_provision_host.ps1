# Host-only tests: fake CubeIDE/programmer, no serial or debugger access.
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
. (Join-Path $source 'Tools\N6-DevCommon.ps1')
. (Join-Path $source 'Tools\N6-FactoryValidation.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('N6 factory test ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$targets = @(@('FSBL','N6_FSBL'),@('AppliSecure','N6_AppliSecure'),@('AppliNonSecure','N6_AppliNonSecure'))
foreach ($target in $targets) {
    $folder = Join-Path $root $target[0]
    New-Item -ItemType Directory -Path (Join-Path $folder 'Debug') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $folder '.project'), '<projectDescription/>')
    [IO.File]::WriteAllText((Join-Path $folder 'main.c'), 'source')
    foreach ($ext in @('bin','elf','map')) { [IO.File]::WriteAllText((Join-Path $folder ('Debug\' + $target[1] + '.' + $ext)), 'old') }
}
$builderPs = Join-Path $root 'fake-builder.ps1'
[IO.File]::WriteAllText($builderPs, @'
param([string]$data,[string]$import,[string]$cleanBuild)
if ($import) {
 Add-Content -LiteralPath ($env:N6_FACTORY_TEST_ROOT + '\imports.log') -Value $import
 Write-Host 'Imported project'; exit 0
}
if ($env:N6_FACTORY_TEST_MODE -eq 'no-match') { Write-Host 'No Project matched'; exit 0 }
if ($env:N6_FACTORY_TEST_MODE -eq 'silent') { exit 0 }
$name = $cleanBuild.Split('/')[0]
$folder = @{N6_FSBL='FSBL';N6_AppliSecure='AppliSecure';N6_AppliNonSecure='AppliNonSecure'}[$name]
foreach ($ext in @('bin','elf','map')) {
 [IO.File]::WriteAllText((Join-Path $env:N6_FACTORY_TEST_ROOT ($folder + '\Debug\' + $name + '.' + $ext)), 'fresh')
}
Write-Host 'Build Finished. 0 errors'; exit 0
'@)
$builder = Join-Path $root 'headless-build.bat'
[IO.File]::WriteAllText($builder, "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$builderPs`" %*`r`nexit /b %ERRORLEVEL%`r`n")
$previousRoot = $env:N6_FACTORY_TEST_ROOT
$previousMode = $env:N6_FACTORY_TEST_MODE
$env:N6_FACTORY_TEST_ROOT = $root
$dependency = Join-Path $root 'FSBL\Debug\test.d'
$escapedPrefix = ($root.Replace('\','/') + '/').Replace(' ', '\ ')
[IO.File]::WriteAllText($dependency, ('test.o: ' + $escapedPrefix + 'FSBL/main.c'))
Repair-N6MakeDependencyFiles -BuildRoot (Join-Path $root 'FSBL\Debug') -ProjectRoot $root
if ([IO.File]::ReadAllText($dependency) -ne 'test.o: ../../FSBL/main.c') { throw 'Windows spaced-path dependency repair failed' }
Write-Host 'PASS Windows make dependency repair with escaped spaces'
function Expect-Rejection([scriptblock]$Action, [string]$Label) {
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    if (-not $rejected) { throw "Accepted invalid case: $Label" }
    Write-Host "PASS rejected: $Label"
}
try {
    foreach ($mode in @('no-match','silent')) {
        $env:N6_FACTORY_TEST_MODE = $mode
        Expect-Rejection { Invoke-N6FactoryCleanBuild -ProjectRoot $root -Builder $builder -SessionRoot (Join-Path $root $mode) } $mode
    }
    $env:N6_FACTORY_TEST_MODE = 'success'
    Invoke-N6FactoryCleanBuild -ProjectRoot $root -Builder $builder -SessionRoot (Join-Path $root 'success')
    if (@(Get-Content (Join-Path $root 'imports.log')).Count -ne 9) { throw 'Not all three projects imported per run' }
    Write-Host 'PASS three fresh builds, automatic imports, zero-exit no-build rejection'
    $images = Join-Path $root 'FlashImages'
    New-Item -ItemType Directory -Path $images | Out-Null
    $names = @('N6_FSBL-trusted.bin','N6_AppliSecure-trusted.bin','N6_AppliNonSecure-trusted.bin','N6-BootMetadata.bin')
    $hashes = [ordered]@{}
    foreach ($name in $names) {
        $path = Join-Path $images $name
        [IO.File]::WriteAllText($path, 'image')
        $hashes[$name] = Get-N6FileSha256 -Path $path
    }
    $manifest = [ordered]@{schema=2;firmware_version=47;source_sha256=(Get-N6FactorySourceHash $root);sha256=$hashes}
    $manifestPath = Join-Path $images 'factory-manifest.json'
    function Save-Manifest { [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 5)) }
    Save-Manifest
    Assert-N6FactoryManifest -ProjectRoot $root -FirmwareVersion 47
    $manifest.sha256 = [ordered]@{}
    Save-Manifest
    Expect-Rejection { Assert-N6FactoryManifest $root 47 } 'empty manifest'
    $manifest.sha256 = [ordered]@{'N6_FSBL-trusted.bin'=$hashes['N6_FSBL-trusted.bin']}
    Save-Manifest
    Expect-Rejection { Assert-N6FactoryManifest $root 47 } 'FSBL-only manifest'
    $manifest.sha256 = $hashes
    Save-Manifest
    Expect-Rejection { Assert-N6FactoryManifest $root 48 } 'wrong version'
    [IO.File]::AppendAllText((Join-Path $root 'FSBL\main.c'), 'changed')
    Expect-Rejection { Assert-N6FactoryManifest $root 47 } 'changed source'
    $manifest.source_sha256 = Get-N6FactorySourceHash $root
    Save-Manifest
    [IO.File]::AppendAllText((Join-Path $images $names[2]), 'corrupt')
    Expect-Rejection { Assert-N6FactoryManifest $root 47 } 'corrupt artifact'
    Write-Host "Factory build/manifest host tests passed. Fixtures: $root"
}
finally {
    $env:N6_FACTORY_TEST_ROOT = $previousRoot
    $env:N6_FACTORY_TEST_MODE = $previousMode
}
