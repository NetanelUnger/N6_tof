$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb'
$toolsDir = Join-Path $repo 'Tools'
$sourcePath = Join-Path $toolsDir 'Build-Xip.ps1'
$evidence = Join-Path $PSScriptRoot 'evidence\st67-cp3-20261028'
if ((& git -C $repo rev-parse HEAD) -ne '5432d4ae2b10ef7ecdfaedad586038792f0a4db5') {throw 'Baseline source changed'}
if ((& git -C $repo branch --show-current) -ne 'feature/n6-xip-ota-usb') {throw 'Wrong feature branch'}
if ($LASTEXITCODE -ne 0) {throw 'Ordinary Git denied; no trust override permitted'}
foreach ($context in @('FSBL','AppliSecure','AppliNonSecure')) {
    if (-not (Test-Path -LiteralPath (Join-Path $repo "$context\Debug\makefile"))) {throw 'Existing generated makefiles required; no IDE setup'}
}
$source = [IO.File]::ReadAllText($sourcePath)
$originalHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
# Restrict the historical tool's three Git calls to ordinary already-trusted
# worktree access. This removes overrides; it grants no Git trust/ACL permission.
if ([regex]::Matches($source,[regex]::Escape('git -c "safe.directory=$root" -C $root')).Count -ne 3) {throw 'Unexpected build-script shape'}
$source = $source.Replace('git -c "safe.directory=$root" -C $root','git -C $root')
$source = $source.Replace('$PSScriptRoot',("'" + $toolsDir.Replace("'","''") + "'"))
if ($source.Contains('safe.directory')) {throw 'Git override remains'}
[IO.File]::WriteAllText((Join-Path $evidence 'Build-Xip-effective.ps1'),$source,[Text.UTF8Encoding]::new($false))
[pscustomobject]@{originalScript=$sourcePath;originalSha256=$originalHash;adaptation='Only remove per-call Git trust override and bind original Tools directory';slot='B';version=52;install='NOT_REQUESTED_BY_THIS_BUILD';debugOutput=0;resourceDiagnostics=$true;watchdog=$true} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'build-invocation.json') -Encoding utf8
& ([scriptblock]::Create($source)) -Slot B -FirmwareVersion 52 -Label 'st67-known-baseline'
if ($LASTEXITCODE -ne 0) {throw 'Build command failed'}
