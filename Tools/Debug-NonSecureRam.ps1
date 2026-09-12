param(
    [switch]$NoBuild,

    [switch]$Run,

    [ValidateRange(1, 65535)]
    [int]$GdbPort = 61234,

    [ValidateRange(100, 50000)]
    [int]$SwdFrequencyKhz = 8000,

    [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')

function ConvertTo-GdbPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return ((Resolve-Path -LiteralPath $Path).Path -replace '\\', '/')
}

function Wait-GdbServer {
    param(
        [Parameter(Mandatory = $true)][Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 15
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "ST-LINK GDB server exited before accepting a connection (exit code $($Process.ExitCode))."
        }

        # Do not probe this port with TcpClient. ST-LINK GDB server treats the
        # probe as its first debugger session and exits when that probe closes.
        $listener = Get-NetTCPConnection `
            -LocalPort $Port `
            -State Listen `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.OwningProcess -eq $Process.Id } |
            Select-Object -First 1
        if ($null -ne $listener) {
            return
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Timed out waiting for the ST-LINK GDB server on port $Port."
}

$tools = Get-N6DevelopmentTools -IdeRoot $IdeRoot

$probeOutput = (& (Join-Path $tools.ProgrammerBin 'STM32_Programmer_CLI.exe') `
    -l stlink 2>&1) -join "`n"
if (($LASTEXITCODE -ne 0) -or ($probeOutput -match 'No ST-Link detected')) {
    throw 'No ST-LINK probe is connected. Connect the board through the ST-LINK USB connector.'
}

if (-not $NoBuild) {
    Invoke-N6SecureIncrementalBuild `
        -ProjectRoot $ProjectRoot `
        -Tools $tools
    Invoke-N6NonSecureIncrementalBuild `
        -ProjectRoot $ProjectRoot `
        -Tools $tools
}
else {
    Assert-N6NonSecureImage -ProjectRoot $ProjectRoot
}

$fsblElf = Join-Path $ProjectRoot 'FSBL\Debug\N6_FSBL.elf'
$secureElf = Join-Path $ProjectRoot 'AppliSecure\Debug\N6_AppliSecure.elf'
$secureBin = Join-Path $ProjectRoot 'AppliSecure\Debug\N6_AppliSecure.bin'
$nonSecureElf = Join-Path $ProjectRoot 'AppliNonSecure\Debug\N6_AppliNonSecure.elf'
$nonSecureBin = Join-Path $ProjectRoot 'AppliNonSecure\Debug\N6_AppliNonSecure.bin'
foreach ($required in @($fsblElf, $secureElf, $secureBin, $nonSecureElf, $nonSecureBin, $tools.Gdb, $tools.Nm)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required RAM-debug input was not found: $required"
    }
}

$fsblNmOutput = & $tools.Nm --defined-only --numeric-sort $fsblElf
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read symbols from the FSBL ELF.'
}
$fsblJumpMatch = $fsblNmOutput | Select-String `
    -Pattern '^([0-9a-fA-F]+)\s+[tT]\s+JumpToApplication$' |
    Select-Object -First 1
if ($null -eq $fsblJumpMatch) {
    throw 'The FSBL JumpToApplication symbol was not found.'
}
$fsblJumpToApplication = [Convert]::ToUInt32(
    $fsblJumpMatch.Matches[0].Groups[1].Value, 16)

$nmOutput = & $tools.Nm --defined-only --numeric-sort $secureElf
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read symbols from the Secure ELF.'
}
$secureMainMatch = $nmOutput | Select-String `
    -Pattern '^([0-9a-fA-F]+)\s+[tT]\s+main$' |
    Select-Object -First 1
if ($null -eq $secureMainMatch) {
    throw 'The Secure main symbol was not found.'
}
$secureMain = [Convert]::ToUInt32(
    $secureMainMatch.Matches[0].Groups[1].Value, 16)

$nonSecureNmOutput = & $tools.Nm --defined-only --numeric-sort $nonSecureElf
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read symbols from the Non-Secure ELF.'
}
$nonSecureMainMatch = $nonSecureNmOutput | Select-String `
    -Pattern '^([0-9a-fA-F]+)\s+[tT]\s+main$' |
    Select-Object -First 1
if ($null -eq $nonSecureMainMatch) {
    throw 'The Non-Secure main symbol was not found.'
}
$nonSecureMain = [Convert]::ToUInt32(
    $nonSecureMainMatch.Matches[0].Groups[1].Value, 16)

$nonSecureBytes = [IO.File]::ReadAllBytes($nonSecureBin)
$secureBytes = [IO.File]::ReadAllBytes($secureBin)
if ($secureBytes.Length -lt 8) {
    throw 'The Secure binary is too small to contain a vector table.'
}
$expectedSecureMsp = [BitConverter]::ToUInt32($secureBytes, 0)
$expectedSecureResetHandler = [BitConverter]::ToUInt32($secureBytes, 4)
# The Secure linker owns SRAM1 at 0x34000400..0x340FFFFF.  Cortex-M stack
# pointers conventionally start one byte past the last RAM address, so the
# valid initial MSP is allowed to equal 0x34100000.
if (($expectedSecureMsp -lt 0x34000400) -or ($expectedSecureMsp -gt 0x34100000)) {
    throw ('Unexpected Secure MSP in the vector table: 0x{0:X8}' -f $expectedSecureMsp)
}
if (($expectedSecureResetHandler -lt 0x34000401) -or
    ($expectedSecureResetHandler -ge 0x34100000) -or
    (($expectedSecureResetHandler -band 1) -eq 0)) {
    throw ('Unexpected Secure Reset_Handler in the vector table: 0x{0:X8}' -f $expectedSecureResetHandler)
}
if ($nonSecureBytes.Length -lt 8) {
    throw 'The Non-Secure binary is too small to contain a vector table.'
}
$expectedMsp = [BitConverter]::ToUInt32($nonSecureBytes, 0)
$expectedResetHandler = [BitConverter]::ToUInt32($nonSecureBytes, 4)
if (($expectedMsp -lt 0x24100000) -or ($expectedMsp -gt 0x24200000)) {
    throw ('Unexpected Non-Secure MSP in the vector table: 0x{0:X8}' -f $expectedMsp)
}
if (($expectedResetHandler -lt 0x24100401) -or
    ($expectedResetHandler -ge 0x24200000) -or
    (($expectedResetHandler -band 1) -eq 0)) {
    throw ('Unexpected Non-Secure Reset_Handler in the vector table: 0x{0:X8}' -f $expectedResetHandler)
}

$logRoot = Join-Path $ProjectRoot 'Tools\.n6-debug'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$serverLog = Join-Path $logRoot 'stlink-gdbserver.log'
$serverStdout = Join-Path $logRoot 'stlink-gdbserver.stdout.log'
$serverStderr = Join-Path $logRoot 'stlink-gdbserver.stderr.log'

$serverArguments = @(
    '-p', $GdbPort,
    '-d',
    '-m', '1',
    '--frequency', $SwdFrequencyKhz,
    '-cp', $tools.ProgrammerBin,
    '-f', $serverLog,
    '-l', '8'
)

Write-Host ('Starting DEV-boot RAM debug through the known-good FSBL handoff at 0x{0:X8}. Local Secure main: 0x{1:X8}.' -f $fsblJumpToApplication, $secureMain)
Write-Host 'Both the locally built Secure runtime and Non-Secure application will be replaced in SRAM; external NOR is unchanged.'
Write-Host 'Required jumpers: BOOT0=1-2 and BOOT1=2-3. A reset returns to the DEV-boot ROM; rerun this script to restore the RAM build.'

$server = Start-Process `
    -FilePath $tools.GdbServer `
    -ArgumentList $serverArguments `
    -WindowStyle Hidden `
    -RedirectStandardOutput $serverStdout `
    -RedirectStandardError $serverStderr `
    -PassThru

try {
    try {
        Wait-GdbServer -Process $server -Port $GdbPort
    }
    catch {
        Start-Sleep -Milliseconds 100
        $serverStartupOutput = if (Test-Path -LiteralPath $serverStdout) {
            Get-Content -Raw -LiteralPath $serverStdout
        }
        else {
            ''
        }
        if ($serverStartupOutput -match 'Target connection failed|Target not halted|No device found') {
            throw "Unable to open STM32N6 debug access. Put BOOT0 at 1-2 and BOOT1 at 2-3, press RESET, and rerun. ST-LINK log: $serverStdout"
        }
        throw
    }

    $gdbFsblPath = ConvertTo-GdbPath $fsblElf
    $gdbSecureBinaryPath = ConvertTo-GdbPath $secureBin
    $gdbBinaryPath = ConvertTo-GdbPath $nonSecureBin
    $commands = @(
        'set confirm off',
        'set pagination off',
        'set mem inaccessible-by-default off',
        "target remote 127.0.0.1:$GdbPort",
        ('load "{0}"' -f $gdbFsblPath),
        # Stop in the locally loaded FSBL after it has copied and verified the
        # installed boot chain, but before it reads the Secure vector table.
        # This address belongs to our FSBL ELF and does not depend on the
        # version or layout of the Secure image currently installed in Flash.
        ('thbreak *0x{0:X8}' -f $fsblJumpToApplication),
        'set $sp = *(unsigned int*)0x34180400',
        'set $pc = *(unsigned int*)0x34180404',
        'continue',
        ('echo FSBL application handoff reached; replacing Secure with the local binary in SRAM1.\n'),
        ('restore {0} binary 0x34000400' -f $gdbSecureBinaryPath),
        ('if (*(unsigned int*)0x34000400 != 0x{0:X8})' -f $expectedSecureMsp),
        '  echo ERROR: RAM-load Secure MSP verification failed.\n',
        '  quit 2',
        'end',
        ('if (*(unsigned int*)0x34000404 != 0x{0:X8})' -f $expectedSecureResetHandler),
        '  echo ERROR: RAM-load Secure Reset_Handler verification failed.\n',
        '  quit 2',
        'end',
        ('thbreak *0x{0:X8}' -f $secureMain),
        'continue',
        ('echo Local Secure initialization reached; loading the new Non-Secure binary through the Secure SRAM2 alias.\n'),
        # Unlike `load`, GDB's `restore` command treats quotes as part of the
        # filename on Windows. This workspace path has no spaces.
        ('restore {0} binary 0x34100400' -f $gdbBinaryPath),
        ('if (*(unsigned int*)0x34100400 != 0x{0:X8})' -f $expectedMsp),
        '  echo ERROR: RAM-load MSP verification failed.\n',
        '  quit 2',
        'end',
        ('if (*(unsigned int*)0x34100404 != 0x{0:X8})' -f $expectedResetHandler),
        '  echo ERROR: RAM-load Reset_Handler verification failed.\n',
        '  quit 2',
        'end',
        ('thbreak *0x{0:X8}' -f $nonSecureMain),
        'continue',
        'echo Non-Secure RAM image reached main(). RISAF6 region 1 follows (CFGR/START/END/CID).\n',
        'x/4wx 0x5402B040',
        'thbreak NPU_SharedMemory_Clear',
        'continue',
        'echo HAL initialization completed; entering the SRAM3 clear.\n',
        'thbreak Debug_UART_Init',
        'continue',
        'echo SRAM3 clear completed; Debug UART initialization reached.\n',
        'thbreak MX_ThreadX_Init',
        'continue',
        'echo Peripheral initialization completed; ThreadX startup reached.\n'
    )

    if ($Run) {
        $commands += @('detach', 'quit')
    }

    $commandFile = Join-Path $logRoot 'ram-debug.gdb'
    [IO.File]::WriteAllLines(
        $commandFile,
        $commands,
        [Text.UTF8Encoding]::new($false))

    $gdbArguments = @('-q', $nonSecureElf, '-x', $commandFile)
    if ($Run) {
        $gdbArguments += '-batch'
    }

    & $tools.Gdb @gdbArguments
    if ($LASTEXITCODE -ne 0) {
        throw "GDB RAM-debug sequence failed with exit code $LASTEXITCODE. Logs: $logRoot"
    }
}
finally {
    if (($null -ne $server) -and (-not $server.HasExited)) {
        Stop-Process -Id $server.Id -Force
        $server.WaitForExit(5000) | Out-Null
    }
}

if ($Run) {
    Write-Host 'The locally built Secure and Non-Secure images are running from SRAM in DEV boot. External NOR was not modified.'
}
