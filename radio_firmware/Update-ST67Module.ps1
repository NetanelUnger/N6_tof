param(
    [string]$Port,
    [switch]$ConfirmUpdate,
    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'
$RadioRoot = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $RadioRoot
& (Join-Path $RadioRoot 'Repair-ST67PackageLineEndings.ps1')
. (Join-Path $ProjectRoot 'Tools\N6-DevCommon.ps1')

function Assert-FileHash {
    param([string]$Path, [string]$Expected)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required ST67 update file is missing: $Path"
    }
    $stream = [IO.File]::OpenRead($Path)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $actual = [BitConverter]::ToString(
            $sha256.ComputeHash($stream)).Replace('-', '')
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
    if ($actual -cne $Expected) {
        throw "ST67 update file hash mismatch: $Path`nExpected: $Expected`nActual:   $actual"
    }
}

function Find-STLinkVcp {
    $ports = @(Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
        Where-Object {
            ($_.Name -match 'STLink Virtual COM Port') -and
            ($_.Name -match '\((COM[0-9]+)\)')
        })
    if ($ports.Count -ne 1) {
        $names = ($ports | ForEach-Object Name) -join '; '
        throw "Expected one ST-LINK VCP; found $($ports.Count). Pass -Port COMx explicitly. $names"
    }
    return [regex]::Match($ports[0].Name, '\((COM[0-9]+)\)').Groups[1].Value
}

function Wait-ForOperator {
    param([string]$Message)
    Write-Host $Message
    if (-not $ConfirmUpdate) {
        [void](Read-Host 'Press Enter when ready')
    }
}

$contractPath = Join-Path $RadioRoot 'contract.json'
$contract = Get-Content -Raw -LiteralPath $contractPath | ConvertFrom-Json
$tools = Get-N6DevelopmentTools -IdeRoot $IdeRoot
$programmer = Join-Path $tools.ProgrammerBin 'STM32_Programmer_CLI.exe'
$externalLoader = Join-Path $tools.ProgrammerBin 'ExternalLoader\MX25UM51245G_STM32N6570-NUCLEO.stldr'
$vendorRoot = Join-Path $RadioRoot 'vendor'
$ncpRoot = Join-Path $vendorRoot 'NCP_Binaries'
$ncpBinary = Join-Path $RadioRoot $contract.ncp_binary
$boot2Binary = Join-Path $RadioRoot $contract.boot2_binary
$littleFsBinary = Join-Path $RadioRoot $contract.littlefs_binary
$partition = Join-Path $ncpRoot 'partition.bin'
$efuse = Join-Path $ncpRoot 'efusedata.bin'
$configTemplate = Join-Path $ncpRoot 'mission_t01_flash_prog_cfg.ini'
$hostBootloader = Join-Path $vendorRoot 'NUCLEO-N657X0-Q_Binaries\Bootloader.bin'
$vendorRestoreFsbl = Join-Path $vendorRoot 'NUCLEO-N657X0-Q_Binaries\ST67W6X_CLI_FSBL.bin'
$qconn = Join-Path $vendorRoot 'QConn_Flash\QConn_Flash_Cmd.exe'
$projectFsbl = Join-Path $ProjectRoot 'FlashImages\N6_FSBL-trusted.bin'
$restoreFsbl = if (Test-Path -LiteralPath $projectFsbl -PathType Leaf) {
    $projectFsbl
} else {
    $vendorRestoreFsbl
}

$manifest = Join-Path $vendorRoot 'MANIFEST.sha256'
foreach ($line in Get-Content -LiteralPath $manifest) {
    if ($line -notmatch '^([0-9A-F]{64})  (.+)$') {
        throw "Invalid vendor manifest line: $line"
    }
    Assert-FileHash (Join-Path $vendorRoot $Matches[2]) $Matches[1]
}
Assert-FileHash $ncpBinary $contract.ncp_binary_sha256
Assert-FileHash $boot2Binary $contract.boot2_binary_sha256
Assert-FileHash $littleFsBinary $contract.littlefs_binary_sha256
foreach ($property in $contract.integrity.PSObject.Properties) {
    Assert-FileHash (Join-Path $RadioRoot $property.Name) ([string]$property.Value)
}
foreach ($required in @($programmer, $externalLoader, $configTemplate, $restoreFsbl)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required update tool/file is missing: $required"
    }
}

if ([string]::IsNullOrWhiteSpace($Port)) {
    $Port = Find-STLinkVcp
}
if ($Port -notmatch '^COM[0-9]+$') {
    throw "Invalid ST-LINK VCP name: $Port"
}

Write-Host '============================================================'
Write-Host "ST67W61 NCP update: mission T01 SDK $($contract.expected_sdk_version)"
Write-Host '============================================================'
Write-Host "ST-LINK VCP: $Port"
Write-Host "Restore FSBL: $restoreFsbl"
Write-Warning 'ST supplies this NCP image as a signed binary. Programming it can permanently lock an unlocked ST67 module.'
Write-Warning 'The STM32 external-NOR FSBL is temporarily replaced while the NCP is programmed.'
Write-Host 'UART update requires SB31 and SB34 CLOSED on X-NUCLEO-67W61M1.'
Write-Host 'With power disconnected, isolate/remove the ToF board first: PD8/PD9 are shared.'
Write-Host 'After the update, disconnect power and reopen SB31/SB34 before reconnecting ToF.'
if (-not $ConfirmUpdate) {
    $confirmation = Read-Host 'Type UPDATE ST67 to continue'
    if ($confirmation -cne 'UPDATE ST67') {
        Write-Host 'Cancelled; neither STM32 flash nor the ST67 module was modified.'
        exit 2
    }
}

# QConn can rewrite its configuration and generated images even on failure.
# Run only a verified disposable copy; retain it for diagnosis and retries.
$work = & (Join-Path $RadioRoot 'New-ST67UpdateWorkspace.ps1') `
    -VendorRoot $vendorRoot `
    -WorkRoot (Join-Path $ProjectRoot '.local-dependencies\st67-updates')
$qconn = $work.QConn
$efuse = $work.Efuse
$generatedConfig = $work.GeneratedConfig
Write-Host "QConn working copy (logs retained): $($work.Root)"
$template = Get-Content -LiteralPath $work.ConfigTemplate
$ncpFileName = Split-Path -Leaf $ncpBinary
$generated = $template | ForEach-Object {
    if ($_ -match '^filedir\s*=\s*\./st67w611m_mission_t01_v.*\.bin\s*$') {
        "filedir = ./$ncpFileName"
    } else {
        $_
    }
}
[IO.File]::WriteAllLines(
    $generatedConfig,
    [string[]]$generated,
    [Text.Encoding]::ASCII)

$temporaryHostInstalled = $false
$ncpProgrammingSucceeded = $false
$restoreSucceeded = $false
$updateFailure = $null
$noUartResponse = $false
try {
    Wait-ForOperator 'Set BOOT0=1-2 and BOOT1=2-3, connect ST-LINK, then press RESET.'
    & $programmer `
        -c port=SWD mode=UR reset=HWrst `
        -el $externalLoader `
        -d $hostBootloader 0x70000000 -v
    if ($LASTEXITCODE -ne 0) {
        throw 'Temporary ST67 host bootloader programming/verification failed.'
    }
    $temporaryHostInstalled = $true

    Wait-ForOperator 'Set BOOT0=1-2 and BOOT1=1-2, press RESET, and leave the ST-LINK VCP unused.'
    Start-Sleep -Seconds 1

    Push-Location (Split-Path -Parent $qconn)
    try {
        $qconnExit = 1
        foreach ($attempt in 1..2) {
            Write-Host "Programming the ST67 NCP (attempt $attempt of 2)..."
            $result = & (Join-Path $RadioRoot 'Invoke-ST67QConn.ps1') `
                -QConn $qconn -Port $Port -Config $generatedConfig -Efuse $efuse `
                -LogPath (Join-Path $work.Root "qconn-attempt-$attempt.log")
            $qconnExit = $result.ExitCode
            $noUartResponse = $result.NoResponse
            if ($qconnExit -eq 0 -and -not $noUartResponse) {
                break
            }
            if ($noUartResponse) {
                Write-Host 'אין תגובה מהמודול' -ForegroundColor Yellow
                Write-Host 'Check SB31/SB34, UART connections, power, BOOT mode and RESET.'
                break
            }
            if ($attempt -eq 1) {
                Write-Warning 'QConn failed once; retrying after one second.'
                Start-Sleep -Seconds 1
            }
        }
        if ($noUartResponse) {
            throw 'אין תגובה מהמודול'
        }
        if ($qconnExit -ne 0) {
            throw "QConn ST67 programming failed twice (exit $qconnExit)."
        }
        $ncpProgrammingSucceeded = $true
    }
    finally {
        Pop-Location
    }
}
catch {
    $updateFailure = $_.Exception.Message
}
finally {
    if ($temporaryHostInstalled) {
        Wait-ForOperator 'Set BOOT0=1-2 and BOOT1=2-3, then press RESET so the project FSBL can be restored.'
        try {
            & $programmer `
                -c port=SWD mode=UR reset=HWrst `
                -el $externalLoader `
                -d $restoreFsbl 0x70000000 -v
            $restoreSucceeded = ($LASTEXITCODE -eq 0)
        }
        catch {
            Write-Host ('FSBL restore error: ' + $_.Exception.Message) -ForegroundColor Yellow
        }
        if ($restoreSucceeded) { Write-Host 'STM32 FSBL restore PASS (write verified).' }
    }
    Write-Host "QConn working files/logs retained: $($work.Root)"
}

if ($temporaryHostInstalled -and -not $restoreSucceeded) {
    if ($updateFailure) { Write-Host ('ST67 update error: ' + $updateFailure) -ForegroundColor Yellow }
    throw 'The ST67 operation ended, but restoring/verifying the STM32 FSBL failed. Keep BOOT1 at 2-3 and rerun the updater.'
}
if ($updateFailure) { throw $updateFailure }
if (-not $ncpProgrammingSucceeded) {
    throw 'The original STM32 FSBL was restored, but the ST67 NCP update did not complete.'
}

Write-Host ''
Write-Host "ST67 UPDATE PASS: mission T01 SDK $($contract.expected_sdk_version) was programmed."
Write-Host 'Disconnect all power. Reopen radio SB31/SB34, then reconnect the ToF board.'
Write-Host 'Reconnect power only after restoring the project wiring.'
Write-Host 'Set BOOT0=1-2 and BOOT1=1-2, then press RESET.'
if ($restoreFsbl -eq $vendorRestoreFsbl) {
    Write-Host 'A project FSBL was not yet built, so the ST reference CLI FSBL was restored.'
    Write-Host 'Run training\13_FACTORY_PROVISION.bat next to install the complete project.'
} else {
    Write-Host 'Run training\10_LOAD_RAM.bat and 11_HIL.bat; Stage 11 re-verifies the live NCP version and BLE advertisement.'
}
