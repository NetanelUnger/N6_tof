# Host-only integration tests. Run with Windows PowerShell 5.1 for Add-Type EXE support.
$ErrorActionPreference = 'Stop'
$sourceRadio = Split-Path -Parent $PSScriptRoot
$root = Join-Path ([IO.Path]::GetTempPath()) ('ST67 updater tests ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
Copy-Item -LiteralPath $sourceRadio -Destination $root -Recurse
$radio = Join-Path $root 'radio_firmware'
$tools = Join-Path $root 'Tools'
New-Item -ItemType Directory -Path (Join-Path $tools 'ExternalLoader') -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $tools 'N6-DevCommon.ps1'), 'function Get-N6DevelopmentTools { param([string]$IdeRoot) [pscustomobject]@{ ProgrammerBin = $IdeRoot } }')
[IO.File]::WriteAllText((Join-Path $tools 'ExternalLoader\MX25UM51245G_STM32N6570-NUCLEO.stldr'), 'test fixture')
$programmerCode = @'
using System;
using System.IO;
public class FakeProgrammer {
 public static int Main(string[] args) {
  string trace = Environment.GetEnvironmentVariable("ST67_TEST_TRACE");
  File.AppendAllText(trace, "programmer\n");
  int calls = File.ReadAllLines(trace).Length;
  if (Environment.GetEnvironmentVariable("ST67_TEST_CASE") == "restore_failure" && calls > 1) {
   Console.WriteLine("Simulated FSBL restore failure"); return 7;
  }
  Console.WriteLine("Download verified successfully"); return 0;
 }
}
'@
$qconnCode = @'
using System;
using System.IO;
public class FakeQConn {
 public static int Main(string[] args) {
  File.AppendAllText(Environment.GetEnvironmentVariable("ST67_TEST_TRACE"), "qconn\n");
  File.AppendAllText("chips/qcc743/eflash_loader/eflash_loader_cfg.ini", "test write");
  string scenario = Environment.GetEnvironmentVariable("ST67_TEST_CASE");
  if (scenario == "no_response" || scenario == "restore_failure") {
   Console.WriteLine("ack is b''");
   Console.WriteLine("========= ChipID:  =========");
   Console.WriteLine("CHIP IMG LOAD SHAKEHAND FAIL"); return 1;
  }
  Console.WriteLine("ack is b'OK'");
  Console.WriteLine("ChipID: ABC123");
  if (scenario == "write_failure") { Console.Error.WriteLine("Flash write failed"); return 1; }
  return 0;
 }
}
'@
$programmer = Join-Path $tools 'STM32_Programmer_CLI.exe'
$qconn = Join-Path $radio 'vendor\QConn_Flash\QConn_Flash_Cmd.exe'
# Delete only this explicitly copied fixture executable before compiling its replacement.
Remove-Item -LiteralPath $qconn
Add-Type -TypeDefinition $programmerCode -OutputAssembly $programmer -OutputType ConsoleApplication
Add-Type -TypeDefinition $qconnCode -OutputAssembly $qconn -OutputType ConsoleApplication
$fixtureHash = (Get-FileHash -LiteralPath $qconn -Algorithm SHA256).Hash
$manifestPath = Join-Path $radio 'vendor\MANIFEST.sha256'
$manifest = [IO.File]::ReadAllText($manifestPath)
$manifest = [regex]::Replace($manifest, '(?m)^[0-9A-F]{64}(  QConn_Flash/QConn_Flash_Cmd.exe)', ($fixtureHash + '$1'))
[IO.File]::WriteAllText($manifestPath, $manifest)
$contractPath = Join-Path $radio 'contract.json'
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json
$contract.integrity.'vendor/QConn_Flash/QConn_Flash_Cmd.exe' = $fixtureHash
[IO.File]::WriteAllText($contractPath, ($contract | ConvertTo-Json -Depth 10))
$message = -join ([char[]]@(0x05D0,0x05D9,0x05DF,0x0020,0x05EA,0x05D2,0x05D5,0x05D1,0x05D4,0x0020,0x05DE,0x05D4,0x05DE,0x05D5,0x05D3,0x05D5,0x05DC))
$previousCase = $env:ST67_TEST_CASE
$previousTrace = $env:ST67_TEST_TRACE
try {
 foreach ($scenario in @('no_response','write_failure','success','restore_failure')) {
  $env:ST67_TEST_CASE = $scenario
  $env:ST67_TEST_TRACE = Join-Path $root ($scenario + '.trace')
  $log = Join-Path $root ($scenario + '.log')
  $start = New-Object Diagnostics.ProcessStartInfo
  $start.FileName = $env:ComSpec
  $bat = Join-Path $radio '01_UPDATE_MODULE.bat'
  $start.Arguments = '/d /c ""{0}" -ConfirmUpdate -Port COM5 -IdeRoot "{1}" < nul"' -f $bat, $tools
  $start.UseShellExecute = $false
  $start.CreateNoWindow = $true
  $start.RedirectStandardOutput = $true
  $start.RedirectStandardError = $true
  $start.StandardOutputEncoding = [Text.Encoding]::UTF8
  $process = New-Object Diagnostics.Process
  $process.StartInfo = $start
  [void]$process.Start()
  $stdout = $process.StandardOutput.ReadToEndAsync()
  $stderr = $process.StandardError.ReadToEndAsync()
  if (-not $process.WaitForExit(30000)) { $process.Kill(); throw "Timed out: $scenario" }
  $output = $stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult()
  $code = $process.ExitCode
  $process.Dispose()
  [IO.File]::WriteAllText($log, $output)
  $trace = @(Get-Content -LiteralPath $env:ST67_TEST_TRACE)
  if ($trace[0] -ne 'programmer' -or $trace[-1] -ne 'programmer') { throw "Missing install/restore: $scenario" }
  if (@($trace | Where-Object { $_ -eq 'programmer' }).Count -ne 2) { throw "Wrong restore count: $scenario" }
  if ($output -match 'CategoryInfo|FullyQualifiedErrorId') { throw "Raw PowerShell error: $scenario" }
  if ($scenario -eq 'success') {
   if ($code -ne 0 -or $output -notmatch 'ST67 UPDATE PASS') { throw "Missing success: $log" }
  } else {
   if ($code -eq 0 -or $output -match 'ST67 UPDATE PASS') { throw "False success: $scenario" }
  }
  if ($scenario -in @('no_response','restore_failure')) {
   if (-not $output.Contains($message)) { throw "Missing Hebrew no-response message: $log" }
   if (@($trace | Where-Object { $_ -eq 'qconn' }).Count -ne 1) { throw 'No-response retried unexpectedly' }
  }
  if ($scenario -eq 'write_failure' -and $output.Contains($message)) { throw 'Write error misclassified' }
  if ($scenario -eq 'restore_failure' -and $output -notmatch 'restoring/verifying the STM32 FSBL failed') { throw 'Restore failure masked' }
  & (Join-Path $radio 'Test-ST67Package.ps1') | Out-Null
  Write-Host "PASS: $scenario; exit $code; source vendor manifest intact"
 }
}
finally {
 $env:ST67_TEST_CASE = $previousCase
 $env:ST67_TEST_TRACE = $previousTrace
}
Write-Host "Host-only integration tests passed. Fixtures and logs: $root"
