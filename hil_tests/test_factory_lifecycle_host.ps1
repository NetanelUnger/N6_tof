$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
. (Join-Path $source 'Tools\N6-DevCommon.ps1')
. (Join-Path $source 'Tools\N6-FactoryValidation.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('N6 factory lifecycle ' + [guid]::NewGuid().ToString('N'))
$tools = Join-Path $root 'Tools'
New-Item -ItemType Directory -Path $tools -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $root 'training') | Out-Null
foreach ($name in @('Factory-Provision.ps1','Invoke-FactoryProvision.ps1','N6-FactoryValidation.ps1')) {
    Copy-Item -LiteralPath (Join-Path $source ('Tools\' + $name)) -Destination $tools
}
Copy-Item -LiteralPath (Join-Path $source 'training\13_FACTORY_PROVISION.bat') -Destination (Join-Path $root 'training')
$common = @'
function Get-N6FirmwareVersion { param($ProjectRoot) return 47 }
function Get-N6FileSha256 { param($Path) return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function Read-Host { param($Prompt) Add-Content -LiteralPath $env:N6_FACTORY_TRACE -Value ('prompt:' + $Prompt); return '' }
function Wait-N6RunningVersion {
 param($RequestedPort,$ExpectedVersion,$TimeoutSeconds)
 Add-Content -LiteralPath $env:N6_FACTORY_TRACE -Value 'verify'
 $count = @(Get-Content $env:N6_FACTORY_TRACE | Where-Object { $_ -eq 'verify' }).Count
 if ($env:N6_FACTORY_CASE -in @('absent','noninteractive','versionfail') -or ($env:N6_FACTORY_CASE -eq 'cold' -and $count -eq 1)) { throw 'simulated boot failure' }
}
function Wait-N6UsbCdcPort {
 param($RequestedPort,$TimeoutSeconds)
 if ($env:N6_FACTORY_CASE -eq 'versionfail') { return 'COM8' }
 throw 'simulated absent endpoint'
}
'@
[IO.File]::WriteAllText((Join-Path $tools 'N6-DevCommon.ps1'), $common)
[IO.File]::WriteAllText((Join-Path $tools 'program_flash.ps1'), @'
param([switch]$FullErase,[string]$IdeRoot)
Add-Content -LiteralPath $env:N6_FACTORY_TRACE -Value 'program'
$global:LASTEXITCODE = 0
'@)
$images = Join-Path $root 'FlashImages'
New-Item -ItemType Directory -Path $images | Out-Null
$hashes = [ordered]@{}
foreach ($name in @('N6_FSBL-trusted.bin','N6_AppliSecure-trusted.bin','N6_AppliNonSecure-trusted.bin','N6-BootMetadata.bin')) {
    [IO.File]::WriteAllText((Join-Path $images $name), 'fixture')
    $hashes[$name] = Get-N6FileSha256 (Join-Path $images $name)
}
$previousCase = $env:N6_FACTORY_CASE
$previousTrace = $env:N6_FACTORY_TRACE
$previousInteractive = $env:N6_NON_INTERACTIVE
try {
    $env:N6_NON_INTERACTIVE = '1'
    foreach ($case in @('success','cold','absent','versionfail','skipboot','noninteractive','cancel','partial')) {
        $manifest = [ordered]@{schema=2;firmware_version=47;source_sha256=(Get-N6FactorySourceHash $root);sha256=$hashes}
        if ($case -eq 'partial') { $manifest.sha256 = [ordered]@{} }
        [IO.File]::WriteAllText((Join-Path $images 'factory-manifest.json'), ($manifest | ConvertTo-Json -Depth 5))
        $env:N6_FACTORY_CASE = $case
        $env:N6_FACTORY_TRACE = Join-Path $root ($case + '.trace')
        $flags = '-SkipBuild -ConfirmErase'
        if ($case -eq 'skipboot') { $flags += ' -SkipBootVerification' }
        if ($case -eq 'noninteractive') { $flags += ' -NonInteractive' }
        if ($case -eq 'cancel') { $flags = '-SkipBuild' }
        $info = New-Object Diagnostics.ProcessStartInfo
        $info.FileName = $env:ComSpec
        $info.Arguments = '/d /c ""{0}" {1} < nul"' -f (Join-Path $root 'training\13_FACTORY_PROVISION.bat'), $flags
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $process = New-Object Diagnostics.Process
        $process.StartInfo = $info
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(15000)) { $process.Kill(); throw "Test timed out: $case" }
        $output = $stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult()
        $code = $process.ExitCode
        $process.Dispose()
        [IO.File]::WriteAllText((Join-Path $root ($case + '.log')), $output)
        $trace = @()
        if (Test-Path $env:N6_FACTORY_TRACE) { $trace = @(Get-Content $env:N6_FACTORY_TRACE) }
        $programCount = @($trace | Where-Object { $_ -eq 'program' }).Count
        $verifyCount = @($trace | Where-Object { $_ -eq 'verify' }).Count
        $promptCount = @($trace | Where-Object { $_ -like 'prompt:*' }).Count
        if ($case -in @('success','cold')) {
            if ($code -ne 0 -or $output -notmatch 'FACTORY PROVISION PASS') { throw "Success missing: $case" }
            if ($programCount -ne 1 -or $promptCount -lt 2) { throw "Prompts/program count wrong: $case" }
        } elseif ($case -eq 'skipboot') {
            if ($code -ne 0 -or $output -match 'FACTORY PROVISION PASS' -or $output -notmatch 'BOOT NOT VERIFIED' -or $verifyCount -ne 0 -or $promptCount -ne 1) { throw 'SkipBootVerification overclaims or skips DEV prompt' }
        } else {
            if ($code -eq 0 -or $output -match 'FACTORY PROVISION PASS') { throw "False success: $case" }
        }
        if ($case -in @('cold','absent') -and ($verifyCount -ne 2 -or $programCount -ne 1)) { throw 'Cold-power recovery reprogrammed or failed to retry verification' }
        if ($case -eq 'versionfail' -and $verifyCount -ne 1) { throw 'Present endpoint got unnecessary cold-power retry' }
        if ($case -eq 'noninteractive' -and $promptCount -ne 0) { throw 'NonInteractive prompted' }
        if ($case -in @('cancel','partial') -and $programCount -ne 0) { throw 'Cancellation/invalid manifest reached erase' }
        if ($output -match 'CategoryInfo|FullyQualifiedErrorId') { throw 'Raw stack trace escaped BAT boundary' }
        Write-Host "PASS: $case (exit $code, programming $programCount, checks $verifyCount, prompts $promptCount)"
    }
}
finally {
    $env:N6_FACTORY_CASE = $previousCase
    $env:N6_FACTORY_TRACE = $previousTrace
    $env:N6_NON_INTERACTIVE = $previousInteractive
}
Write-Host "Factory lifecycle host tests passed. Fixtures: $root"
