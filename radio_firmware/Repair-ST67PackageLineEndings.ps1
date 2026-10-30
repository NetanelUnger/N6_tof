param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = 'Stop'
$vendorRoot = Join-Path $ProjectRoot 'radio_firmware\vendor'
$manifest = Join-Path $vendorRoot 'MANIFEST.sha256'
$encoding = [Text.Encoding]::GetEncoding(28591)
$sha = [Security.Cryptography.SHA256]::Create()
function Get-BytesHash([byte[]]$Bytes) {
    [BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace('-', '')
}
$repairs = @()
try {
    foreach ($line in Get-Content -LiteralPath $manifest) {
        if ($line -notmatch '^([0-9A-F]{64})  (.+)$') {
            throw "Invalid manifest line: $line"
        }
        $expected = $Matches[1]
        $relative = $Matches[2]
        $path = Join-Path $vendorRoot $relative
        $bytes = [IO.File]::ReadAllBytes($path)
        if ((Get-BytesHash $bytes) -ceq $expected) { continue }
        # Only consider known text files; never transform firmware or executables.
        if ($relative -notmatch '(?i)(\.(ini|conf|txt|pem)$|^LICENSE_BINARIES$)') {
            throw "Not a supported text-file mismatch: $relative. Restore from the same release."
        }
        # Latin-1 preserves every byte; only CR/LF bytes can change.
        $lf = $encoding.GetString($bytes).Replace("`r`n", "`n")
        $replacement = $null
        foreach ($candidate in @($lf, $lf.Replace("`n", "`r`n"))) {
            $candidateBytes = $encoding.GetBytes($candidate)
            if ((Get-BytesHash $candidateBytes) -ceq $expected) {
                $replacement = $candidateBytes
                break
            }
        }
        if ($null -eq $replacement) {
            throw "Line endings do not explain the mismatch: $relative. Restore from the same release."
        }
        $repairs += [pscustomobject]@{ Path = $path; Bytes = $replacement; Expected = $expected }
    }
    # Validate all candidates before writing any file.
    foreach ($repair in $repairs) {
        [IO.File]::WriteAllBytes($repair.Path, $repair.Bytes)
        if ((Get-BytesHash ([IO.File]::ReadAllBytes($repair.Path))) -cne $repair.Expected) {
            throw "Verification failed after writing: $($repair.Path)"
        }
        Write-Host '[FIXED]' $repair.Path
    }
    Write-Host "Vendor manifest PASS. Line-ending repairs: $($repairs.Count)."
}
finally {
    $sha.Dispose()
}
