$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../Tools/N6-DevCommon.ps1')

$cases = 0
foreach ($version in @('1', '9', '10', '11', '12', '99', '100', '4294967295')) {
    foreach ($ending in @("`n", "`r`n", "`r`r`n")) {
        foreach ($prefix in @('', "version`r`n", 'n6> ')) {
            $reply = $prefix + 'Firmware version: ' + $version + $ending
            # Exercise the production parser after every individual byte,
            # including all possible serial-read boundaries within the number.
            for ($length = 0; $length -lt $reply.Length; $length++) {
                $actual = Get-N6CompletedVersionResponse -Text $reply.Substring(0, $length)
                if ($null -ne $actual) {
                    throw "Accepted an incomplete reply for v$version at byte $length ($actual)."
                }
            }
            $actual = Get-N6CompletedVersionResponse -Text $reply
            if ($null -eq $actual -or $actual -ne [uint32]$version) {
                throw "Did not parse the completed v$version reply."
            }
            $cases++
        }
    }
}
foreach ($text in @("Application firmware version: 11`r`n", "Bootloader version: 11`n", "Firmware version: 11junk`n", "Firmware version:`n11`n", "Firmware version: 11`r", "Firmware version: `n")) {
    if ($null -ne (Get-N6CompletedVersionResponse -Text $text)) {
        throw 'Accepted malformed, incomplete or non-application version output.'
    }
}
# A complete older version remains distinguishable from the expected version.
$older = Get-N6CompletedVersionResponse -Text "Firmware version: 1`r`n"
if ($older -ne 1 -or $older -eq 11) { throw 'A real version mismatch was hidden.' }

# Reproduce the reported defect independently of any connected hardware.
$partial = 'Firmware version: 1'
$old = [regex]::Match($partial, 'Firmware version:\s*([0-9]+)').Groups[1].Value
if ($old -ne '1' -or $null -ne (Get-N6CompletedVersionResponse -Text $partial)) {
    throw 'Regression reproduction failed.'
}
Write-Host "PASS $cases streamed replies; partial v11 reproduction; malformed replies; real version mismatch preserved."
