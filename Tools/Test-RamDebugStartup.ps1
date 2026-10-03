# Hardware-free regression checks. Never launches ST-LINK or loads firmware.
$ErrorActionPreference = 'Stop'
$parseErrors = $null
$tokens = $null
$scriptAst = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'Debug-NonSecureRam.ps1'),
    [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) {
    throw ($parseErrors -join "`n")
}
foreach ($name in @('Resolve-N6GdbPort', 'Wait-GdbServer')) {
    $definition = $scriptAst.Find({
        param($node)
        ($node -is [Management.Automation.Language.FunctionDefinitionAst]) -and
        ($node.Name -eq $name)
    }, $false)
    if ($null -eq $definition) {
        throw "Missing startup function: $name"
    }
    . ([scriptblock]::Create($definition.Extent.Text))
}

$testPort = Resolve-N6GdbPort -PreferredPort 61234 -AllowFallback
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Any, $testPort)
$listener.Server.ExclusiveAddressUse = $true
$child = $null
try {
    $listener.Start()
    $fallback = Resolve-N6GdbPort -PreferredPort $testPort -AllowFallback
    if ($fallback -eq $testPort) {
        throw 'Occupied preferred port was selected.'
    }
    Write-Host 'PASS: occupied default port selects an available range.'

    $message = ''
    try { Resolve-N6GdbPort -PreferredPort $testPort | Out-Null }
    catch { $message = $_.Exception.Message }
    if ($message -notmatch 'occupied or reserved') {
        throw "Explicit occupied port was not rejected: $message"
    }
    Write-Host 'PASS: explicit occupied port fails with actionable diagnostics.'

    # Hold only the adjacent SWV port, keeping the requested GDB port free.
    $listener.Stop()
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Any, ($testPort + 1))
    $listener.Server.ExclusiveAddressUse = $true
    $listener.Start()
    $message = ''
    try { Resolve-N6GdbPort -PreferredPort $testPort | Out-Null }
    catch { $message = $_.Exception.Message }
    if ($message -notmatch 'occupied or reserved') {
        throw "Occupied adjacent port was not rejected: $message"
    }
    Write-Host 'PASS: adjacent server port conflicts are detected.'

    $listener.Stop()
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Any, $testPort)
    $listener.Server.ExclusiveAddressUse = $true
    $listener.Start()
    $child = Start-Process -FilePath "$PSHOME\powershell.exe" `
        -ArgumentList '-NoProfile -Command "Start-Sleep -Seconds 30"' `
        -WindowStyle Hidden -PassThru
    $message = ''
    try { Wait-GdbServer -Process $child -Port $testPort -TimeoutSeconds 1 }
    catch { $message = $_.Exception.Message }
    if ($message -notmatch 'Timed out waiting') {
        throw "Another process's listener incorrectly signaled readiness: $message"
    }
    Write-Host 'PASS: unrelated listener does not signal server readiness.'
    Stop-Process -Id $child.Id -Force
    $child.WaitForExit()
    $child = Start-Process -FilePath "$PSHOME\powershell.exe" `
        -ArgumentList '-NoProfile -Command "exit 23"' `
        -WindowStyle Hidden -PassThru
    $child.WaitForExit()
    $message = ''
    try { Wait-GdbServer -Process $child -Port $testPort -TimeoutSeconds 1 }
    catch { $message = $_.Exception.Message }
    if ($message -notmatch 'exited before accepting.*exit code (23|unavailable)') {
        throw "Early exit was not diagnosed: $message"
    }
    Write-Host 'PASS: early server exit reports a code or an explicit unavailable status.'
}
finally {
    $listener.Stop()
    if (($null -ne $child) -and (-not $child.HasExited)) {
        Stop-Process -Id $child.Id -Force
        $child.WaitForExit()
    }
}
