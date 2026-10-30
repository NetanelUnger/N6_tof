param(
    [Parameter(Mandatory = $true)]
    [string]$File,

    [string]$Port,

    [ValidateRange(1200, 3000000)]
    [int]$BaudRate = 115200,

    [ValidateRange(1, 60)]
    [int]$StartTimeoutSeconds = 20,

    [ValidateRange(1, 120)]
    [int]$BlockTimeoutSeconds = 30,

    [ValidateRange(10, 300)]
    [int]$FinalizeTimeoutSeconds = 120,

    [ValidateRange(1, 20)]
    [int]$MaxRetries = 10,

    [switch]$NoUpdateCommand,

    # Explicit HIL fault control; normal transfers are unchanged.
    [switch]$TimeoutFirstPacket
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')

function Get-XmodemCrc16 {
    param([Parameter(Mandatory = $true)][byte[]]$Data)

    [int]$crc = 0
    foreach ($value in $Data) {
        $crc = ($crc -bxor ([int]$value -shl 8)) -band 0xFFFF
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($crc -band 0x8000) -ne 0) {
                $crc = (($crc -shl 1) -bxor 0x1021) -band 0xFFFF
            }
            else {
                $crc = ($crc -shl 1) -band 0xFFFF
            }
        }
    }
    return [uint16]$crc
}

function Read-SerialByteUntil {
    param(
        [Parameter(Mandatory = $true)][IO.Ports.SerialPort]$Serial,
        [Parameter(Mandatory = $true)][DateTime]$Deadline
    )

    while ([DateTime]::UtcNow -lt $Deadline) {
        try {
            return $Serial.ReadByte()
        }
        catch [TimeoutException] {
            # Poll until the caller's complete deadline expires.
        }
    }
    return $null
}

function Test-XmodemPostAckDisconnect {
    param([Exception]$Exception)
    # Used only AFTER a received EOT ACK. Never turn a missing ACK into success.
    for ($inner = $Exception; $null -ne $inner; $inner = $inner.InnerException) {
        if (($inner -is [IO.IOException]) -or
            ($inner -is [InvalidOperationException]) -or
            ($inner -is [OperationCanceledException])) { return $true }
    }
    return $false
}

function Invoke-XmodemTimeoutControl {
    param($Serial, [byte[]]$Packet)
    if ($Packet.Length -lt 17) { throw 'Truncated-packet fixture is too short.' }
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $Serial.Write($Packet, 0, 17)
    $response = Wait-XmodemResponse -Serial $Serial -TimeoutSeconds 12
    $timer.Stop()
    if (($response -ne 0x15) -or ($timer.Elapsed.TotalSeconds -gt 12)) {
        throw 'Truncated first packet did not receive NAK within unchanged12s acceptance bound; no complete image packet sent.'
    }
    Write-Host ('XMODEM TIMEOUT CONTROL PASS: NAK after {0:F3} ms; same serial session retained.' -f $timer.Elapsed.TotalMilliseconds)
    return $timer.Elapsed.TotalMilliseconds
}

function Wait-XmodemStart {
    param(
        [Parameter(Mandatory = $true)][IO.Ports.SerialPort]$Serial,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][bool]$RequireWaitingText
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $text = [Text.StringBuilder]::new()
    $waitingSeen = -not $RequireWaitingText
    while ([DateTime]::UtcNow -lt $deadline) {
        $value = Read-SerialByteUntil -Serial $Serial -Deadline $deadline
        if ($null -eq $value) {
            break
        }

        if (($value -ge 0x20) -and ($value -le 0x7E)) {
            [void]$text.Append([char]$value)
            if ($text.Length -gt 8192) {
                [void]$text.Remove(0, $text.Length - 4096)
            }
            if ($text.ToString().Contains('Waiting: ')) {
                $waitingSeen = $true
            }
        }
        elseif (($value -eq 0x0D) -or ($value -eq 0x0A)) {
            [void]$text.Append([char]$value)
        }

        if ($waitingSeen -and ($value -eq 0x43)) {
            return
        }
    }

    $observed = $text.ToString().Trim()
    throw "Timed out waiting for the XMODEM CRC request. Device output: $observed"
}

function Wait-XmodemResponse {
    param(
        [Parameter(Mandatory = $true)][IO.Ports.SerialPort]$Serial,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $cancelCount = 0
    while ([DateTime]::UtcNow -lt $deadline) {
        $value = Read-SerialByteUntil -Serial $Serial -Deadline $deadline
        if ($null -eq $value) {
            return $null
        }
        if (($value -eq 0x06) -or ($value -eq 0x15)) {
            return $value
        }
        if ($value -eq 0x18) {
            $cancelCount++
            if ($cancelCount -ge 2) {
                return 0x18
            }
        }
        else {
            $cancelCount = 0
        }
        # Ignore queued 'C' bytes and any unrelated terminal bytes.
    }
    return $null
}

$crcSelfTest = Get-XmodemCrc16 -Data ([Text.Encoding]::ASCII.GetBytes('123456789'))
if ($crcSelfTest -ne 0x31C3) {
    throw ('Internal XMODEM CRC16 self-test failed: 0x{0:X4}' -f $crcSelfTest)
}

$filePath = (Resolve-Path -LiteralPath $File).Path
$fileBytes = [IO.File]::ReadAllBytes($filePath)
if ($fileBytes.Length -eq 0) {
    throw "XMODEM input file is empty: $filePath"
}

$Port = Wait-N6UsbCdcPort -RequestedPort $Port

$serial = [IO.Ports.SerialPort]::new(
    $Port,
    $BaudRate,
    [IO.Ports.Parity]::None,
    8,
    [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.ReadTimeout = 200
$serial.WriteTimeout = 5000
$serial.DtrEnable = $true
$serial.RtsEnable = $false

try {
    Write-Host "Opening $Port and preparing to send $($fileBytes.Length) bytes."
    try {
        $serial.Open()
    }
    catch {
        throw "Could not open active CDC port $Port before transfer; no firmware bytes were sent. Check CN8, close other terminals, and retry. $($_.Exception.Message)"
    }
    Start-Sleep -Milliseconds 500
    $serial.DiscardInBuffer()

    if (-not $NoUpdateCommand) {
        $serial.Write("update`r")
    }
    Wait-XmodemStart `
        -Serial $serial `
        -TimeoutSeconds $StartTimeoutSeconds `
        -RequireWaitingText:(-not $NoUpdateCommand)

    $blockSize = 1024
    $blockCount = [int][Math]::Ceiling($fileBytes.Length / [double]$blockSize)
    [int]$sequence = 1

    for ($blockIndex = 0; $blockIndex -lt $blockCount; $blockIndex++) {
        [byte[]]$payload = New-Object byte[] $blockSize
        for ($payloadIndex = 0; $payloadIndex -lt $payload.Length; $payloadIndex++) {
            $payload[$payloadIndex] = 0x1A
        }
        $offset = $blockIndex * $blockSize
        $copyLength = [Math]::Min($blockSize, $fileBytes.Length - $offset)
        [Array]::Copy($fileBytes, $offset, $payload, 0, $copyLength)

        $crc = Get-XmodemCrc16 -Data $payload
        [byte[]]$packet = New-Object byte[] ($blockSize + 5)
        $packet[0] = 0x02
        $packet[1] = [byte]$sequence
        $packet[2] = [byte](0xFF - $sequence)
        [Array]::Copy($payload, 0, $packet, 3, $blockSize)
        $packet[$blockSize + 3] = [byte](($crc -shr 8) -band 0xFF)
        $packet[$blockSize + 4] = [byte]($crc -band 0xFF)

        $accepted = $false
        if ($TimeoutFirstPacket -and ($blockIndex -eq 0)) {
            $timeoutControlElapsedMs = Invoke-XmodemTimeoutControl -Serial $serial -Packet $packet
        }
        for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
            $serial.Write($packet, 0, $packet.Length)
            $response = Wait-XmodemResponse `
                -Serial $serial `
                -TimeoutSeconds $BlockTimeoutSeconds
            if ($response -eq 0x06) {
                $accepted = $true
                break
            }
            if ($response -eq 0x18) {
                throw "The device cancelled the XMODEM transfer at block $($blockIndex + 1)."
            }
            Write-Warning "Retrying XMODEM block $($blockIndex + 1)/$blockCount (attempt $attempt/$MaxRetries)."
        }
        if (-not $accepted) {
            throw "XMODEM block $($blockIndex + 1) was not accepted after $MaxRetries attempts."
        }

        if ((($blockIndex + 1) % 16 -eq 0) -or ($blockIndex + 1 -eq $blockCount)) {
            $acceptedBytes = [Math]::Min(($blockIndex + 1) * $blockSize, $fileBytes.Length)
            $percent = [Math]::Floor(($acceptedBytes * 100.0) / $fileBytes.Length)
            Write-Host "XMODEM: $acceptedBytes/$($fileBytes.Length) bytes ($percent%)."
        }
        $sequence = ($sequence + 1) -band 0xFF
    }

    $finalized = $false
    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        $serial.Write([byte[]]@(0x04), 0, 1)
        $response = Wait-XmodemResponse `
            -Serial $serial `
            -TimeoutSeconds $FinalizeTimeoutSeconds
        if ($response -eq 0x06) {
            $finalized = $true
            break
        }
        if ($response -eq 0x18) {
            throw 'The device rejected the package during final authentication.'
        }
        Write-Warning "Retrying XMODEM EOT (attempt $attempt/$MaxRetries)."
    }
    if (-not $finalized) {
        throw 'The device did not acknowledge XMODEM finalization.'
    }
    Write-Host 'XMODEM EOT ACK RECEIVED; final status drain begins.'

    $finalText = [Text.StringBuilder]::new()
    $textDeadline = [DateTime]::UtcNow.AddSeconds(3)
    while ([DateTime]::UtcNow -lt $textDeadline) {
        try {
            $value = $serial.ReadByte()
            if ($value -ge 0) {
                [void]$finalText.Append([char]$value)
            }
        }
        catch [TimeoutException] {
            # Keep waiting for the final status line or the scheduled reset.
        }
        catch {
            if (Test-XmodemPostAckDisconnect -Exception $_.Exception) {
                # The scheduled reset may cancel the pending host read even
                # through a PowerShell MethodInvocationException wrapper.
                Write-Host 'XMODEM post-ACK USB read ended during automatic reboot.'
                break
            }
            throw
        }
    }
    if ($finalText.Length -ne 0) {
        Write-Host $finalText.ToString().Trim()
    }
    Write-Host 'XMODEM transfer and device-side finalization completed successfully.'
}
finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
}
