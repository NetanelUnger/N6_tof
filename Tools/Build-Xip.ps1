param(
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Slot,
    [Parameter(Mandatory=$true)][ValidateRange(1,[uint32]::MaxValue)][uint32]$FirmwareVersion,
    [ValidatePattern("^[a-zA-Z0-9-]*$")][string]$Label = "",
    [switch]$FaultProbe,
    [switch]$RxBackpressure
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
function Assert-XipBranch {
    if ((& git -c "safe.directory=$root" -C $root branch --show-current) -ne 'feature/n6-xip-ota-usb') {
        throw 'XIP builds require feature/n6-xip-ota-usb. No main writes are permitted.'
    }
}
Assert-XipBranch
if ($RxBackpressure -and -not $FaultProbe) {throw 'Experimental RX backpressure requires the XIP fault probe.'}
. (Join-Path $PSScriptRoot 'N6-DevCommon.ps1')
$tools = Get-N6DevelopmentTools
Enable-N6DevelopmentToolPath $tools
Assert-N6NonSecureBuildSafety $root
$lockPath = Join-Path $root '.local-dependencies/xip-build.lock'
New-Item -ItemType Directory -Force (Split-Path -Parent $lockPath) | Out-Null
# All contexts share generated objects and temporary headers. Never build slots
# concurrently or steal an existing build marker after an interrupted process.
$buildLock = [IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {
$headers = @('Common/Update/firmware_build_version.h','AppliNonSecure/Core/Inc/w61_driver_config.h',
    'FSBL/.settings/language.settings.xml','AppliSecure/.settings/language.settings.xml',
    'AppliNonSecure/.settings/language.settings.xml','AppliNonSecure/Core/Inc/app_features.h')
$saved = @{}
foreach ($relative in $headers) { $saved[$relative] = [IO.File]::ReadAllBytes((Join-Path $root $relative)) }
$suffix = if ($Label) { "-$Label" } else { "" }
$output = Join-Path $root ".local-dependencies/xip/v$FirmwareVersion-$Slot$suffix"
if (Test-Path -LiteralPath $output) { throw 'Immutable build already exists; choose another version or archive explicitly.' }
New-Item -ItemType Directory -Force $output | Out-Null
$settings = [IO.File]::ReadAllText((Join-Path $root 'AppliNonSecure/Core/Inc/app_settings.h'))
if ($settings -notmatch '#define APP_SETTINGS_WRITES_ENABLED 0U' -or
    $settings -notmatch '#define APP_SETTINGS_TRANSITION_ENABLED 0U') { throw 'Settings writes must remain disabled.' }
try {
    Assert-XipBranch
    $versionText = [Text.Encoding]::UTF8.GetString($saved[$headers[0]])
    $versionText = [regex]::Replace($versionText,'(NATI_LAB_FIRMWARE_VERSION\s+\()\d+(UL\))',"`${1}$FirmwareVersion`${2}")
    $versionText = [regex]::Replace($versionText,'(NATI_LAB_FIRMWARE_VERSION_TEXT\s+")\d+(")',"`${1}$FirmwareVersion`${2}")
    [IO.File]::WriteAllText((Join-Path $root $headers[0]),$versionText,[Text.UTF8Encoding]::new($false))
    $config = [Text.Encoding]::UTF8.GetString($saved[$headers[1]])
    $config = $config.Replace('#define W61_CONFIG_PRESERVE       (0)','#define W61_CONFIG_PRESERVE       (1)')
    if ($config -notmatch '#define W61_CONFIG_PRESERVE\s+\(1\)') { throw 'Cannot establish preserve-settings build.' }
    [IO.File]::WriteAllText((Join-Path $root $headers[1]),$config,[Text.UTF8Encoding]::new($false))
    $featurePath = Join-Path $root 'AppliNonSecure/Core/Inc/app_features.h'
    $features = [IO.File]::ReadAllText($featurePath).Replace('#define APP_CLOUD_AUTO_MAP_ENABLED (1U)','#define APP_CLOUD_AUTO_MAP_ENABLED (0U)')
    if ($features -notmatch '#define APP_CLOUD_AUTO_MAP_ENABLED \(0U\)') { throw 'Cloud image auto-route must be disabled.' }
    [IO.File]::WriteAllText($featurePath,$features,[Text.UTF8Encoding]::new($false))
    # First use: generate makefiles in an isolated IDE workspace, never the main workspace.
    if (-not (Test-Path (Join-Path $root 'AppliNonSecure/Debug/makefile'))) {
        $workspace = Join-Path $root '.local-dependencies/ide-workspace'
        & (Join-Path $tools.IdeRoot 'headless-build.bat') -data $workspace `
            -import (Join-Path $root 'FSBL') -import (Join-Path $root 'AppliSecure') `
            -import (Join-Path $root 'AppliNonSecure') -build N6_FSBL/Debug `
            -build N6_AppliSecure/Debug -build N6_AppliNonSecure/Debug *> (Join-Path $output 'generate.log')
        # CubeIDE may trip on its generated Windows drive-colon dependencies.
        # The direct make steps below repair them and must independently succeed.
    }
    foreach ($context in @('FSBL','AppliSecure','AppliNonSecure')) {
        Assert-XipBranch
        $build = Join-Path $root "$context/Debug"
        $makeText = [IO.File]::ReadAllText((Join-Path $build 'makefile'))
        if (-not $makeText.Contains($root)) { throw "Build provenance does not match worktree: $context" }
        Repair-N6MakeDependencyFiles -BuildRoot $build -ProjectRoot $root
        Push-Location $build
        try {
            & $tools.Make -j8 "N6_$context.elf" "N6_$context.bin" *> (Join-Path $output "$context-build.log")
            if ($LASTEXITCODE -ne 0) { throw "Build failed: $context" }
        } finally { Pop-Location }
    }
    foreach ($context in @('FSBL','AppliSecure')) {
        if ($context -eq 'AppliSecure') {
            Assert-N6SecureGatewayAbi -Elf (Join-Path $root 'AppliSecure/Debug/N6_AppliSecure.elf') -Tools $tools |
                ConvertTo-Json | Set-Content (Join-Path $output 'secure-abi.json') -Encoding utf8
        }
        foreach ($extension in @('elf','map','bin')) {
            Copy-Item (Join-Path $root "$context/Debug/N6_$context.$extension") (Join-Path $output "$context.$extension")
        }
        & $tools.SigningTool -bin (Join-Path $output "$context.bin") -nk -of 0x80000000 -t fsbl -o (Join-Path $output "$context-trusted.bin") -hv 2.3 -align -dump (Join-Path $output "$context-trusted.bin") -s *> (Join-Path $output "$context-signing.log")
        if ($LASTEXITCODE -ne 0) { throw "Boot-chain signing failed: $context" }
    }
    # Keep this exact guarded RAM map for a like-for-like before/after budget.
    foreach ($extension in @('elf','bin','map')) {
        Copy-Item (Join-Path $root "AppliNonSecure/Debug/N6_AppliNonSecure.$extension") (Join-Path $output "ram.$extension")
    }
    $build = Join-Path $root 'AppliNonSecure/Debug'
    $base = if ($Slot -eq 'A') {'0x70180000'} else {'0x70280000'}
    $elf = Join-Path $output 'application.elf'
    $map = Join-Path $output 'application.map'
    $bin = Join-Path $output 'application.bin'
    Push-Location $build
    try {
        # Keep ordinary guarded RAM behavior/budget intact. Override only the
        # shared weak reset entry for XIP, with copied executable SRAM code.
        $resetObject = Join-Path $output 'xip-reset.o'
        & (Join-Path $tools.GnuBin 'arm-none-eabi-gcc.exe') -c (Join-Path $root 'Tools/xip_system_reset.c') `
            -o $resetObject -mcpu=cortex-m55 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard `
            -std=gnu11 -O3 -Wall -ffunction-sections -fdata-sections -DSTM32N657xx `
            '-I../Core/Inc' '-I../../Drivers/CMSIS/Device/ST/STM32N6xx/Include' '-I../../Drivers/CMSIS/Include' `
            *> (Join-Path $output 'xip-reset-build.log')
        if ($LASTEXITCODE -ne 0) { throw 'XIP reset override compilation failed.' }
        $objectResponse='@objects.list'
        $extraObjects=@($resetObject)
        if ($FaultProbe) {
            # Compile only the diagnostic XIP variants. Keep ordinary guarded
            # RAM objects/map unchanged and its369072-byte contract intact.
            $rule=([IO.File]::ReadAllLines((Join-Path $build 'Core/Src/subdir.mk')) |
                Where-Object {$_ -match 'arm-none-eabi-gcc.*-std=gnu11'} | Select-Object -First 1)
            if (-not $rule) {throw 'Cannot locate generated C compile flags.'}
            $projectFlags=@([regex]::Matches($rule,'-[DI][^\s]+') | ForEach-Object {$_.Value})
            $probeFlags=@('-mcpu=cortex-m55','-mthumb','-mfpu=fpv5-d16','-mfloat-abi=hard','-std=gnu11','-O3',
                '-Wall','-fstack-usage','-ffunction-sections','-fdata-sections','--specs=nano.specs','-DN6_XIP_FAULT_PROBE=1',('-I'+$PSScriptRoot))+$projectFlags
            if ($RxBackpressure) {$probeFlags+='-DN6_XIP_RX_BACKPRESSURE=1'}
            $probeSources=@('AppliNonSecure/Core/Src/spi_port.c','AppliNonSecure/Core/Src/firmware_update.c','Tools/xip_fault_probe.c')
            if ($RxBackpressure) {$probeSources+='ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c'}
            foreach ($relative in $probeSources) {
                Assert-XipBranch
                $name=[IO.Path]::GetFileNameWithoutExtension($relative)
                $probeObject=Join-Path $output "$name-probe.o"
                & (Join-Path $tools.GnuBin 'arm-none-eabi-gcc.exe') @probeFlags -c (Join-Path $root $relative) -o $probeObject `
                    *> (Join-Path $output "$name-probe-build.log")
                if ($LASTEXITCODE -ne 0) {throw "XIP diagnostic compilation failed: $relative"}
                $extraObjects+=$probeObject
            }
            $original=[IO.File]::ReadAllLines((Join-Path $build 'objects.list'))
            $remove=@('"./Core/Src/spi_port.o"','"./Core/Src/firmware_update.o"')
            if ($RxBackpressure) {$remove+='"./Middlewares/ST67W6X_Network_Driver/Driver/spi_iface.o"'}
            foreach ($line in $remove) {if (@($original | Where-Object {$_ -eq $line}).Count -ne 1) {throw 'Unexpected object-list shape.'}}
            $filtered=@($original | Where-Object {$_ -notin $remove})
            $probeList=Join-Path $output 'objects-probe.list'
            [IO.File]::WriteAllLines($probeList,$filtered,[Text.UTF8Encoding]::new($false))
            $objectResponse='@'+$probeList
        }
        $linkArgs = @('-o',$elf,$objectResponse,(Join-Path $root 'AppliSecure/Debug/secure_nsclib.o'))+$extraObjects+@(
            '-lm','-l:USBPDCORE_NOPD_CM55_wc32.a','-l:NetworkRuntime1201_CM55_GCC.a','-mcpu=cortex-m55',
            "-Wl,--defsym=N6_XIP_BASE=$base",'-T'+(Join-Path $root 'AppliNonSecure/STM32N657X0HXQ_XIP.ld'),
            '--specs=nosys.specs',"-Wl,-Map=$map",'-Wl,--gc-sections','-static',
            '-L../../Middlewares/ST/STM32_USBPD_Library/Core/lib','-L../AI/Lib','--specs=nano.specs',
            '-mfpu=fpv5-d16','-mfloat-abi=hard','-mthumb','-Wl,--start-group','-lc','-lm','-Wl,--end-group')
        & (Join-Path $tools.GnuBin 'arm-none-eabi-gcc.exe') @linkArgs *> (Join-Path $output 'xip-link.log')
        if ($LASTEXITCODE -ne 0) { throw 'XIP link failed.' }
        & (Join-Path $tools.GnuBin 'arm-none-eabi-objcopy.exe') -O binary $elf $bin
        if ($LASTEXITCODE -ne 0) { throw 'XIP binary generation failed.' }
        $resetSymbols = (& $tools.Nm --defined-only $elf) -join "`n"
        $resetMatch = [regex]::Match($resetSymbols,'(?m)^([0-9a-fA-F]+)\s+T\s+N6_SystemReset$')
        if (-not $resetMatch.Success) { throw 'Strong XIP reset override absent.' }
        $resetAddress = [Convert]::ToUInt32($resetMatch.Groups[1].Value,16)
        if ($resetAddress -lt 0x24100000 -or $resetAddress -ge 0x241FF800) {
            throw 'XIP reset implementation must execute from application SRAM.'
        }
        @{status='RAM_RESET_ENTRY_VERIFIED';address=('0x{0:X8}' -f $resetAddress);hardware_reset_test='NOT_RUN'} |
            ConvertTo-Json | Set-Content (Join-Path $output 'reset-entry.json') -Encoding utf8
    } finally { Pop-Location }
    # Measure actual linker capacity; this is not a live malloc/high-water claim.
    $budgets = [ordered]@{}
    foreach ($mode in @('ram','application')) {
        $text = [IO.File]::ReadAllText((Join-Path $output "$mode.map"))
        $endMatch = [regex]::Match($text,'(?m)^\s*(0x[0-9a-fA-F]+)\s+PROVIDE \(_end = \.\)')
        $stackMatch = [regex]::Match($text,'(?m)^\s*(0x[0-9a-fA-F]+)\s+_sstack = ')
        if (-not $endMatch.Success -or -not $stackMatch.Success) { throw 'Heap bounds absent from map.' }
        $heap = [Convert]::ToUInt64($stackMatch.Groups[1].Value.Substring(2),16) - [Convert]::ToUInt64($endMatch.Groups[1].Value.Substring(2),16)
        if ($heap -lt 369072) { throw 'Preserved guarded heap requirement369072 failed.' }
        $budgets[$mode] = @{heap_capacity_bytes=$heap;heap_start=$endMatch.Groups[1].Value;stack_limit=$stackMatch.Groups[1].Value}
    }
    $binaryBytes = [IO.File]::ReadAllBytes($bin)
    if ([Text.Encoding]::ASCII.GetString($binaryBytes).IndexOf("Firmware version: $FirmwareVersion") -lt 0) {
        throw 'Requested version does not appear in the compiled application.'
    }
    $trusted = Join-Path $output 'application-trusted.bin'
    & $tools.SigningTool -bin $bin -nk -of 0x80000000 -t fsbl -o $trusted -hv 2.3 -align -dump $trusted -s *> (Join-Path $output 'signing.log')
    if ($LASTEXITCODE -ne 0) { throw 'STM32 header signing failed.' }
    & (Join-Path $PSScriptRoot 'New-FirmwareUpdatePackage.ps1') -Image $trusted `
        -FirmwareVersion $FirmwareVersion -ExecutionMode "XIP-$Slot" `
        -Output (Join-Path $output "N6-XIP-$Slot-v$FirmwareVersion.n6fw")
    & (Join-Path $PSScriptRoot 'Test-XipPackage.ps1') -Package (Join-Path $output "N6-XIP-$Slot-v$FirmwareVersion.n6fw") -ExpectedSlot $Slot -ExpectedVersion $FirmwareVersion | Out-Null
    $sourceHashes = [ordered]@{}
    foreach ($relative in (& git -c "safe.directory=$root" -C $root ls-files FSBL AppliSecure AppliNonSecure Common Drivers Middlewares ThirdParty Secure_nsclib)) {
        if ($relative -match '/\.settings/') { continue }
        $sourceHashes[$relative] = Get-N6FileSha256 (Join-Path $root $relative)
    }
    $sourceHashes['AppliNonSecure/STM32N657X0HXQ_XIP.ld'] = Get-N6FileSha256 (Join-Path $root 'AppliNonSecure/STM32N657X0HXQ_XIP.ld')
    $sourceHashes['Tools/xip_system_reset.c'] = Get-N6FileSha256 (Join-Path $root 'Tools/xip_system_reset.c')
    if ($FaultProbe) {
        $sourceHashes['AppliNonSecure/Core/Src/spi_port.c']=Get-N6FileSha256 (Join-Path $root 'AppliNonSecure/Core/Src/spi_port.c')
        $sourceHashes['ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c']=Get-N6FileSha256 (Join-Path $root 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c')
        $sourceHashes['ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_port.h']=Get-N6FileSha256 (Join-Path $root 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_port.h')
        $sourceHashes['Tools/xip_fault_probe.c']=Get-N6FileSha256 (Join-Path $root 'Tools/xip_fault_probe.c')
        $sourceHashes['Tools/xip_fault_probe.h']=Get-N6FileSha256 (Join-Path $root 'Tools/xip_fault_probe.h')
    }
    $hashes = [ordered]@{}
    foreach ($item in Get-ChildItem $output -File | Where-Object Extension -in '.elf','.map','.bin','.n6fw') {
        $hashes[$item.Name] = @{sha256=Get-N6FileSha256 $item.FullName;bytes=$item.Length}
    }
    $result = [ordered]@{status='BUILT_NOT_INSTALLED';branch='feature/n6-xip-ota-usb';source_commit=(& git -c "safe.directory=$root" -C $root rev-parse HEAD);slot=$Slot;version=$FirmwareVersion;execution_base=$base;ncp_preserve=$true;settings_writes=$false;cloud_auto_map=$false;fault_probe=[bool]$FaultProbe;budgets=$budgets;source_sha256=$sourceHashes;hashes=$hashes}
    Assert-XipBranch
    $result['rx_backpressure']=[bool]$RxBackpressure
    [IO.File]::WriteAllText((Join-Path $output 'build.json'),($result | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
    Write-Host "XIP build/package ready: $output. Hardware installation and HIL have not run."
} finally {
    Assert-XipBranch
    foreach ($relative in $headers) { [IO.File]::WriteAllBytes((Join-Path $root $relative),$saved[$relative]) }
}

} finally {
    $buildLock.Dispose()
    [IO.File]::Delete($lockPath)
}
