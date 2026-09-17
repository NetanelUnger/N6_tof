param(
    [string]$Port,
    [switch]$ConfirmUpdate,
    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'
$RadioRoot = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $RadioRoot
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
$generatedConfig = Join-Path $ncpRoot 'mission_t01_flash_prog_cfg_auto.ini'
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
if (-not $ConfirmUpdate) {
    $confirmation = Read-Host 'Type UPDATE ST67 to continue'
    if ($confirmation -cne 'UPDATE ST67') {
        Write-Host 'Cancelled; neither STM32 flash nor the ST67 module was modified.'
        exit 2
    }
}

$template = Get-Content -LiteralPath $configTemplate
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
            & $qconn `
                --port $Port `
                --config $generatedConfig `
                "--efuse=$efuse"
            $qconnExit = $LASTEXITCODE
            if ($qconnExit -eq 0) {
                break
            }
            if ($attempt -eq 1) {
                Write-Warning 'QConn failed once; retrying after one second.'
                Start-Sleep -Seconds 1
            }
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
finally {
    if ($temporaryHostInstalled) {
        Wait-ForOperator 'Set BOOT0=1-2 and BOOT1=2-3, then press RESET so the project FSBL can be restored.'
        & $programmer `
            -c port=SWD mode=UR reset=HWrst `
            -el $externalLoader `
            -d $restoreFsbl 0x70000000 -v
        $restoreSucceeded = ($LASTEXITCODE -eq 0)
    }
    if (Test-Path -LiteralPath $generatedConfig) {
        Remove-Item -LiteralPath $generatedConfig -Force
    }
}

if (-not $restoreSucceeded) {
    throw 'The ST67 operation ended, but restoring/verifying the STM32 FSBL failed. Keep BOOT1 at 2-3 and rerun the updater.'
}
if (-not $ncpProgrammingSucceeded) {
    throw 'The original STM32 FSBL was restored, but the ST67 NCP update did not complete.'
}

Write-Host ''
Write-Host "ST67 UPDATE PASS: mission T01 SDK $($contract.expected_sdk_version) was programmed."
Write-Host 'Set BOOT0=1-2 and BOOT1=1-2, then press RESET.'
if ($restoreFsbl -eq $vendorRestoreFsbl) {
    Write-Host 'A project FSBL was not yet built, so the ST reference CLI FSBL was restored.'
    Write-Host 'Run training\13_FACTORY_PROVISION.bat next to install the complete project.'
} else {
    Write-Host 'Run training\10_LOAD_RAM.bat and 11_HIL.bat; Stage 11 re-verifies the live NCP version and BLE advertisement.'
}
