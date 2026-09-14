$ErrorActionPreference = 'Stop'

function Resolve-N6PluginTool {
    param(
        [Parameter(Mandatory = $true)]
        [string]$IdeRoot,

        [Parameter(Mandatory = $true)]
        [string]$PluginPrefix,

        [Parameter(Mandatory = $true)]
        [string]$RelativeToolPath
    )

    $pluginsRoot = Join-Path $IdeRoot 'plugins'
    $plugin = Get-ChildItem -LiteralPath $pluginsRoot -Directory |
        Where-Object { $_.Name.StartsWith($PluginPrefix, [StringComparison]::OrdinalIgnoreCase) } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if ($null -eq $plugin) {
        throw "STM32CubeIDE plugin was not found: $PluginPrefix"
    }

    $tool = Join-Path $plugin.FullName $RelativeToolPath
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Required STM32 tool was not found: $tool"
    }
    return $tool
}

function Get-N6DevelopmentTools {
    param(
        [string]$IdeRoot = 'C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE'
    )

    if (-not (Test-Path -LiteralPath $IdeRoot -PathType Container)) {
        throw "STM32CubeIDE root was not found: $IdeRoot"
    }

    $gnuBin = Split-Path -Parent (Resolve-N6PluginTool `
        -IdeRoot $IdeRoot `
        -PluginPrefix 'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.' `
        -RelativeToolPath 'tools\bin\arm-none-eabi-gcc.exe')
    $make = Resolve-N6PluginTool `
        -IdeRoot $IdeRoot `
        -PluginPrefix 'com.st.stm32cube.ide.mcu.externaltools.make.win32_' `
        -RelativeToolPath 'tools\bin\make.exe'
    $programmer = Resolve-N6PluginTool `
        -IdeRoot $IdeRoot `
        -PluginPrefix 'com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_' `
        -RelativeToolPath 'tools\bin\STM32_Programmer_CLI.exe'
    $gdbServer = Resolve-N6PluginTool `
        -IdeRoot $IdeRoot `
        -PluginPrefix 'com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.win32_' `
        -RelativeToolPath 'tools\bin\ST-LINK_gdbserver.exe'

    return [pscustomobject]@{
        IdeRoot = $IdeRoot
        GnuBin = $gnuBin
        Make = $make
        Gdb = Join-Path $gnuBin 'arm-none-eabi-gdb.exe'
        Nm = Join-Path $gnuBin 'arm-none-eabi-nm.exe'
        ProgrammerBin = Split-Path -Parent $programmer
        SigningTool = Join-Path (Split-Path -Parent $programmer) 'STM32_SigningTool_CLI.exe'
        GdbServer = $gdbServer
    }
}

function Enable-N6DevelopmentToolPath {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Tools
    )

    $makeBin = Split-Path -Parent $Tools.Make
    $env:Path = "$($Tools.GnuBin);$makeBin;$env:Path"
}

function Repair-N6MakeDependencyFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BuildRoot,

        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    # GCC 14.3 emits absolute Windows prerequisites such as C:/source.c for
    # linked CubeIDE resources.  GNU make then treats the drive colon in the
    # generated .d rule as another target separator and reports "multiple
    # target patterns" on the next incremental build.  This project's Debug
    # folders are exactly two levels below the project root, so convert both
    # raw and previously escaped absolute project prefixes to ../../ instead
    # of relying on make's inconsistent Windows drive-colon parsing.
    $resolvedBuildRoot = (Resolve-Path -LiteralPath $BuildRoot).Path.TrimEnd('\', '/')
    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\', '/')
    $expectedProjectRoot = Split-Path -Parent (Split-Path -Parent $resolvedBuildRoot)
    if (-not $expectedProjectRoot.Equals(
            $resolvedProjectRoot,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unexpected generated build path; cannot relativize dependencies: $resolvedBuildRoot"
    }

    $projectPrefix = ($resolvedProjectRoot -replace '\\', '/') + '/'
    $escapedProjectPrefix = $projectPrefix.Insert(1, '\')
    $extendedProjectPrefix = '\\?\' + $resolvedProjectRoot + '\'
    $repairedCount = 0
    $dependencyFiles = Get-ChildItem `
        -LiteralPath $BuildRoot `
        -Filter '*.d' `
        -File `
        -Recurse `
        -ErrorAction SilentlyContinue
    foreach ($dependencyFile in $dependencyFiles) {
        $text = [IO.File]::ReadAllText($dependencyFile.FullName)
        $repaired = $text.Replace($projectPrefix, '../../')
        $repaired = $repaired.Replace($escapedProjectPrefix, '../../')
        $repaired = $repaired.Replace($extendedProjectPrefix, '../../')
        $repaired = [regex]::Replace(
            $repaired,
            '\.\./\.\./[^ \t\r\n]+',
            { param($match) $match.Value.Replace('\', '/') })
        if ($repaired -ne $text) {
            [IO.File]::WriteAllText(
                $dependencyFile.FullName,
                $repaired,
                [Text.UTF8Encoding]::new($false))
            ++$repairedCount
        }
    }

    if ($repairedCount -gt 0) {
        Write-Host "Repaired $repairedCount generated make dependency files."
    }
}

function Assert-N6NonSecureBuildSafety {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $usbPdCore = Join-Path $ProjectRoot 'AppliNonSecure\USBPD\App\usbpd_dpm_core.c'
    if (-not (Select-String -LiteralPath $usbPdCore `
            -Pattern '^#define\s+OS_CAD_STACK_SIZE\s+N6_USBPD_CAD_STACK_SIZE\s*$' `
            -Quiet)) {
        throw 'Unsafe USB-PD CAD stack: restore OS_CAD_STACK_SIZE to N6_USBPD_CAD_STACK_SIZE after CubeMX Generate Code.'
    }
}

function Assert-N6NonSecureImage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $debugRoot = Join-Path $ProjectRoot 'AppliNonSecure\Debug'
    $elf = Join-Path $debugRoot 'N6_AppliNonSecure.elf'
    $binary = Join-Path $debugRoot 'N6_AppliNonSecure.bin'
    $map = Join-Path $debugRoot 'N6_AppliNonSecure.map'
    foreach ($required in @($elf, $binary, $map)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Non-Secure build output was not found: $required"
        }
    }

    $binaryFile = Get-Item -LiteralPath $binary
    $maximumBinarySize = 0x000FFC00
    if ($binaryFile.Length -gt $maximumBinarySize) {
        throw "Non-Secure image is $($binaryFile.Length) bytes; the maximum is $maximumBinarySize bytes."
    }

    $mapText = Get-Content -Raw -LiteralPath $map
    $npuFeatureHeader = Join-Path $ProjectRoot 'AppliNonSecure\Core\Inc\app_features.h'
    $npuEnabled = Select-String -LiteralPath $npuFeatureHeader `
        -Pattern '^#define\s+APP_RPS_NPU_ENABLED\s+\(1U\)\s*$' `
        -Quiet
    if ($npuEnabled) {
        foreach ($requiredSymbol in @(
            'rps_model_weights',
            'stai_rps_tof_run',
            'RPS_AI_ProcessDepth',
            '__snpu_shared_bss',
            '__enpu_shared_bss'
        )) {
            if ($mapText -notmatch ('\b' + [regex]::Escape($requiredSymbol) + '\b')) {
                throw "Neural-ART integration symbol is missing from the linked image: $requiredSymbol"
            }
        }
        $npuWorkspaceMatch = [regex]::Match(
            $mapText,
            '(?m)^\.npu_shared_bss\s*\r?\n\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)')
        if (-not $npuWorkspaceMatch.Success) {
            throw 'Unable to validate the NPU SRAM3 shared workspace placement.'
        }
        $npuWorkspaceStart = [Convert]::ToUInt64(
            $npuWorkspaceMatch.Groups[1].Value.Substring(2), 16)
        $npuWorkspaceSize = [Convert]::ToUInt64(
            $npuWorkspaceMatch.Groups[2].Value.Substring(2), 16)
        if (($npuWorkspaceStart -lt 0x24244000) -or
            (($npuWorkspaceStart + $npuWorkspaceSize) -gt 0x24270000)) {
            throw ('NPU shared workspace escaped its reserved SRAM3 window: ' +
                   ('start=0x{0:X8}, size={1}' -f $npuWorkspaceStart, $npuWorkspaceSize))
        }
        Write-Host ('Neural-ART image contract: embedded weights + runtime present; ' +
                    ('SRAM3 workspace {0} bytes at 0x{1:X8}.' -f $npuWorkspaceSize, $npuWorkspaceStart))
    }
    $radioPoolMatch = [regex]::Match(
        $mapText,
        '(?m)^\.radio_shared_bss\s*\r?\n\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)')
    if ($radioPoolMatch.Success) {
        $radioPoolStart = [Convert]::ToUInt64(
            $radioPoolMatch.Groups[1].Value.Substring(2), 16)
        $radioPoolSize = [Convert]::ToUInt64(
            $radioPoolMatch.Groups[2].Value.Substring(2), 16)
        if ($radioPoolSize -ne 0) {
            if (($radioPoolStart -ne 0x242D0000) -or
                ($radioPoolSize -gt 64KB) -or
                (($radioPoolStart + $radioPoolSize) -gt 0x242E0000)) {
                throw ('ST67 radio pool escaped its reserved SRAM4 window: ' +
                       ('start=0x{0:X8}, size={1}' -f $radioPoolStart, $radioPoolSize))
            }
            foreach ($requiredSymbol in @('__sradio_shared_bss',
                                           '__eradio_shared_bss')) {
                if ($mapText -notmatch ('\b' + [regex]::Escape($requiredSymbol) + '\b')) {
                    throw "ST67 radio-pool symbol is missing: $requiredSymbol"
                }
            }
            Write-Host ('ST67 memory contract: SRAM4 radio pool {0} bytes at 0x{1:X8}.' -f
                        $radioPoolSize, $radioPoolStart)
        }
    }
    $heapStartMatch = [regex]::Match(
        $mapText,
        '(?m)^\s*(0x[0-9a-fA-F]+)\s+PROVIDE \(_end = \.\)')
    $heapLimitMatch = [regex]::Match(
        $mapText,
        '(?m)^\s*(0x[0-9a-fA-F]+)\s+_sstack = ')
    if (-not $heapStartMatch.Success -or -not $heapLimitMatch.Success) {
        throw "Unable to determine the Non-Secure C heap capacity from: $map"
    }

    $heapStart = [Convert]::ToUInt64(
        $heapStartMatch.Groups[1].Value.Substring(2), 16)
    $heapLimit = [Convert]::ToUInt64(
        $heapLimitMatch.Groups[1].Value.Substring(2), 16)
    $availableHeapBytes = $heapLimit - $heapStart
    $minimumTofHeapBytes = 360KB
    if ($availableHeapBytes -lt $minimumTofHeapBytes) {
        throw "Insufficient Non-Secure C heap for VL53L9 transform: $availableHeapBytes bytes available, $minimumTofHeapBytes required."
    }

    Write-Host "Non-Secure binary: $($binaryFile.Length) bytes."
    Write-Host "Non-Secure C heap capacity: $availableHeapBytes bytes (minimum $minimumTofHeapBytes)."
}

function Invoke-N6NonSecureIncrementalBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,

        [Parameter(Mandatory = $true)]
        [pscustomobject]$Tools,

        [switch]$Clean
    )

    Assert-N6NonSecureBuildSafety -ProjectRoot $ProjectRoot
    Enable-N6DevelopmentToolPath -Tools $Tools

    $debugRoot = Join-Path $ProjectRoot 'AppliNonSecure\Debug'
    if (-not (Test-Path -LiteralPath (Join-Path $debugRoot 'makefile') -PathType Leaf)) {
        throw "Generated Non-Secure makefile was not found: $debugRoot"
    }

    Push-Location $debugRoot
    try {
        Repair-N6MakeDependencyFiles `
            -BuildRoot $debugRoot `
            -ProjectRoot $ProjectRoot
        if ($Clean) {
            Write-Host 'Cleaning the Non-Secure build because -Clean was requested.'
            & $Tools.Make clean
            if ($LASTEXITCODE -ne 0) {
                throw 'Non-Secure clean failed.'
            }
        }

        $jobs = [Math]::Max(1, [Environment]::ProcessorCount)
        Write-Host "Incrementally building Non-Secure with $jobs parallel jobs..."
        # The RAM and XMODEM lanes only need ELF, map, and raw binary outputs.
        # Building the generated `all` target also regenerates a multi-megabyte
        # disassembly listing, which adds latency without helping either lane.
        & $Tools.Make "-j$jobs" N6_AppliNonSecure.bin
        $buildExitCode = $LASTEXITCODE
        Repair-N6MakeDependencyFiles `
            -BuildRoot $debugRoot `
            -ProjectRoot $ProjectRoot
        if ($buildExitCode -ne 0) {
            throw 'Incremental Non-Secure build failed.'
        }
    }
    finally {
        Pop-Location
    }

    Assert-N6NonSecureImage -ProjectRoot $ProjectRoot
}

function Invoke-N6SecureIncrementalBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,

        [Parameter(Mandatory = $true)]
        [pscustomobject]$Tools
    )

    Enable-N6DevelopmentToolPath -Tools $Tools
    $debugRoot = Join-Path $ProjectRoot 'AppliSecure\Debug'
    if (-not (Test-Path -LiteralPath (Join-Path $debugRoot 'makefile') -PathType Leaf)) {
        throw "Generated Secure makefile was not found: $debugRoot"
    }

    Push-Location $debugRoot
    try {
        $jobs = [Math]::Max(1, [Environment]::ProcessorCount)
        Write-Host "Incrementally building Secure with $jobs parallel jobs..."
        Repair-N6MakeDependencyFiles `
            -BuildRoot $debugRoot `
            -ProjectRoot $ProjectRoot
        & $Tools.Make "-j$jobs" N6_AppliSecure.bin
        $buildExitCode = $LASTEXITCODE
        Repair-N6MakeDependencyFiles `
            -BuildRoot $debugRoot `
            -ProjectRoot $ProjectRoot
        if ($buildExitCode -ne 0) {
            throw 'Incremental Secure build failed.'
        }
    }
    finally {
        Pop-Location
    }
}

function Get-N6FirmwareVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $header = Join-Path $ProjectRoot 'Common\Update\firmware_build_version.h'
    $match = Select-String -LiteralPath $header `
        -Pattern '^#define\s+NATI_LAB_FIRMWARE_VERSION\s+\(([0-9]+)UL\)\s*$' |
        Select-Object -First 1
    if ($null -eq $match) {
        throw "Unable to read the current firmware version from: $header"
    }
    return [uint32]$match.Matches[0].Groups[1].Value
}

function Set-N6FirmwareVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,

        [Parameter(Mandatory = $true)]
        [uint32]$FirmwareVersion
    )

    $header = Join-Path $ProjectRoot 'Common\Update\firmware_build_version.h'
    $text = @"
#ifndef FIRMWARE_BUILD_VERSION_H
#define FIRMWARE_BUILD_VERSION_H

/* Generated by an N6 build helper before compiling the Non-Secure image. */
#define NATI_LAB_FIRMWARE_VERSION       (${FirmwareVersion}UL)
#define NATI_LAB_FIRMWARE_VERSION_TEXT  "$FirmwareVersion"

#endif /* FIRMWARE_BUILD_VERSION_H */
"@
    [IO.File]::WriteAllText(
        $header,
        $text,
        [Text.UTF8Encoding]::new($false))
}

function Find-N6UsbCdcPort {
    $devices = @(Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
        Where-Object {
            ($_.PNPDeviceID -match 'VID_0483&PID_5740') -and
            ($_.Name -match '\((COM[0-9]+)\)')
        })

    if ($devices.Count -eq 0) {
        throw 'The N6 USB CDC port (VID 0483, PID 5740) was not found. Connect CN8 and wait for Windows to enumerate it.'
    }
    if ($devices.Count -gt 1) {
        $names = ($devices | ForEach-Object Name) -join '; '
        throw "More than one N6-compatible USB CDC port was found. Pass -Port explicitly. Devices: $names"
    }

    $portMatch = [regex]::Match($devices[0].Name, '\((COM[0-9]+)\)')
    return $portMatch.Groups[1].Value
}
