function Get-N6FactorySourceHash {
    param([Parameter(Mandatory=$true)][string]$ProjectRoot)
    $records = New-Object 'Collections.Generic.List[string]'
    foreach ($folder in @('FSBL','AppliSecure','AppliNonSecure','Common','Drivers','Middlewares','Utilities','ThirdParty','Tools')) {
        $path = Join-Path $ProjectRoot $folder
        if (-not (Test-Path -LiteralPath $path)) { continue }
        foreach ($file in Get-ChildItem -LiteralPath $path -File -Recurse | Sort-Object FullName) {
            $relative = $file.FullName.Substring($ProjectRoot.TrimEnd('\').Length + 1).Replace('\','/')
            if ($relative -match '/(Debug|Release|\.git|\.settings)/') { continue }
            if ($file.Extension -notin @('.c','.h','.s','.ld','.a','.ioc','.ps1','.project','.cproject','.xml') -and
                $file.Name -notin @('.project','.cproject')) { continue }
            $records.Add($relative + ':' + (Get-N6FileSha256 -Path $file.FullName))
        }
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($records -join "`n")))).Replace('-','') }
    finally { $sha.Dispose() }
}

function Invoke-N6FactoryBuilder {
    param([string]$Builder, [string]$Workspace, [string]$Operation, [string]$Target, [string]$Log)
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $env:ComSpec
    $info.Arguments = '/d /s /c ""{0}" -data "{1}" {2} "{3}""' -f $Builder, $Workspace, $Operation, $Target
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    $lines = New-Object 'Collections.Generic.List[string]'
    try {
        [void]$process.Start()
        $stderr = $process.StandardError.ReadToEndAsync()
        while ($null -ne ($line = $process.StandardOutput.ReadLine())) { $lines.Add($line); Write-Host $line }
        $process.WaitForExit()
        $errors = $stderr.GetAwaiter().GetResult()
        if ($errors) { $lines.Add($errors); Write-Host $errors }
        $exitCode = $process.ExitCode
    }
    finally {
        $process.Dispose()
        [IO.File]::WriteAllLines($Log, $lines.ToArray())
    }
    [pscustomobject]@{ ExitCode = $exitCode; Output = $lines -join "`n" }
}

function Invoke-N6FactoryCleanBuild {
    param([string]$ProjectRoot, [string]$Builder, [string]$SessionRoot)
    $workspace = Join-Path $SessionRoot 'workspace'
    New-Item -ItemType Directory -Path $SessionRoot -Force | Out-Null
    $targets = @(@('FSBL','N6_FSBL'), @('AppliSecure','N6_AppliSecure'), @('AppliNonSecure','N6_AppliNonSecure'))
    foreach ($target in $targets) {
        $project = Join-Path $ProjectRoot $target[0]
        if (-not (Test-Path -LiteralPath (Join-Path $project '.project'))) { throw "Missing CubeIDE project: $project" }
        $log = Join-Path $SessionRoot ($target[0] + '-import.log')
        Write-Host "Importing CubeIDE project: $project"
        $result = Invoke-N6FactoryBuilder -Builder $Builder -Workspace $workspace -Operation '-import' -Target $project -Log $log
        if ($result.ExitCode -ne 0 -or $result.Output -match 'No Project matched|cannot import|failed to import|already exists') {
            throw "CubeIDE project import failed: $project. See $log"
        }
    }
    foreach ($target in $targets) {
        # CubeIDE may incrementally rebuild project references while cleaning
        # another target. Repair every generated dependency set between builds.
        foreach ($dependencyTarget in $targets) {
            $dependencyRoot = Join-Path $ProjectRoot ($dependencyTarget[0] + '\Debug')
            if (Test-Path -LiteralPath $dependencyRoot) {
                Repair-N6MakeDependencyFiles -BuildRoot $dependencyRoot -ProjectRoot $ProjectRoot
            }
        }
        $debug = Join-Path $ProjectRoot ($target[0] + '\Debug')
        $backup = Join-Path $SessionRoot ('previous-artifacts\' + $target[0])
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        # Preserve old final outputs, then require their recreation. A zero exit
        # without a matched target can never reuse yesterday's BIN/ELF/MAP.
        foreach ($ext in @('bin','elf','map')) {
            $artifact = Join-Path $debug ($target[1] + '.' + $ext)
            if (Test-Path -LiteralPath $artifact) { Move-Item -LiteralPath $artifact -Destination $backup }
        }
        $log = Join-Path $SessionRoot ($target[0] + '-build.log')
        Write-Host "Clean building $($target[1])/Debug. Logs: $log"
        $result = Invoke-N6FactoryBuilder -Builder $Builder -Workspace $workspace -Operation '-cleanBuild' -Target ($target[1] + '/Debug') -Log $log
        if ($result.ExitCode -ne 0 -or $result.Output -match 'No Project matched|BUILD FAILED|Build Finished\. [1-9][0-9]* errors') {
            throw "Clean build failed: $($target[1]). See $log"
        }
        foreach ($ext in @('bin','elf','map')) {
            $artifact = Join-Path $debug ($target[1] + '.' + $ext)
            if (-not (Test-Path -LiteralPath $artifact -PathType Leaf) -or (Get-Item -LiteralPath $artifact).Length -eq 0) {
                throw "Build did not create a new nonempty artifact: $artifact. See $log"
            }
        }
        Write-Host "Fresh build artifacts verified: $($target[1])/Debug"
    }
    foreach ($target in $targets) {
        Repair-N6MakeDependencyFiles -BuildRoot (Join-Path $ProjectRoot ($target[0] + '\Debug')) -ProjectRoot $ProjectRoot
    }
}

function Assert-N6FactoryManifest {
    param([string]$ProjectRoot, [uint32]$FirmwareVersion)
    $path = Join-Path $ProjectRoot 'FlashImages\factory-manifest.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Factory manifest missing. Rerun without -SkipBuild.' }
    $manifest = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 2 -or $manifest.firmware_version -ne $FirmwareVersion) {
        throw 'Factory manifest schema/version is stale. Rerun without -SkipBuild.'
    }
    $required = @('N6_FSBL-trusted.bin','N6_AppliSecure-trusted.bin','N6_AppliNonSecure-trusted.bin','N6-BootMetadata.bin')
    $names = @($manifest.sha256.PSObject.Properties | ForEach-Object Name)
    if ($names.Count -ne $required.Count -or @(Compare-Object $required $names -CaseSensitive).Count -ne 0) {
        throw 'Factory manifest must contain exactly FSBL, Secure, Non-Secure and boot metadata.'
    }
    foreach ($name in $required) {
        $artifact = Join-Path $ProjectRoot ('FlashImages\' + $name)
        $expected = [string]$manifest.sha256.$name
        if ($expected -cnotmatch '^[0-9A-F]{64}$' -or -not (Test-Path -LiteralPath $artifact -PathType Leaf) -or
            (Get-Item -LiteralPath $artifact).Length -eq 0 -or (Get-N6FileSha256 -Path $artifact) -cne $expected) {
            throw "Factory artifact missing, empty or hash mismatch: $name. Rerun without -SkipBuild."
        }
    }
    if ([string]$manifest.source_sha256 -cne (Get-N6FactorySourceHash -ProjectRoot $ProjectRoot)) {
        throw 'Factory build inputs changed since the verified build. Rerun without -SkipBuild.'
    }
    Write-Host "Factory manifest PASS: version $FirmwareVersion, four images and build input fingerprint match."
}
