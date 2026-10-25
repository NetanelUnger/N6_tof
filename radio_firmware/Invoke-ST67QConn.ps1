param(
    [Parameter(Mandatory=$true)][string]$QConn,
    [Parameter(Mandatory=$true)][string]$Port,
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$Efuse,
    [Parameter(Mandatory=$true)][string]$LogPath
)

$ErrorActionPreference = 'Stop'
$info = New-Object Diagnostics.ProcessStartInfo
$info.FileName = $QConn
$info.WorkingDirectory = Split-Path -Parent $QConn
$info.Arguments = '--port "{0}" --config "{1}" "--efuse={2}"' -f $Port, $Config, $Efuse
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
$process = New-Object Diagnostics.Process
$process.StartInfo = $info
$lines = New-Object 'Collections.Generic.List[string]'
try {
    [void]$process.Start()
    # Drain stderr concurrently so the child cannot block on a full error pipe.
    $errorTextTask = $process.StandardError.ReadToEndAsync()
    while ($null -ne ($line = $process.StandardOutput.ReadLine())) {
        $lines.Add($line)
        Write-Host $line
    }
    $process.WaitForExit()
    $errorText = $errorTextTask.GetAwaiter().GetResult()
    if ($errorText) { $lines.Add($errorText); Write-Host $errorText }
    $exitCode = $process.ExitCode
}
finally {
    $process.Dispose()
    [IO.File]::WriteAllLines($LogPath, $lines.ToArray(), [Text.Encoding]::UTF8)
}
$output = $lines -join "`n"
$emptyAck = $output -match "ack is b''"
$handshakeFailed = $output -match 'CHIP IMG LOAD SHAKEHAND FAIL|shake hand fail'
$hasResponse = $false
foreach ($line in $lines) {
    if ($line -match 'ChipID:\s*([0-9A-Fa-f]+)\b' -or
        ($line -match 'ack is\s+(.+)' -and $Matches[1].Trim() -notin @("b''", 'b""'))) {
        $hasResponse = $true
    }
}
[pscustomobject]@{
    ExitCode = $exitCode
    NoResponse = ($emptyAck -and $handshakeFailed -and -not $hasResponse)
}
