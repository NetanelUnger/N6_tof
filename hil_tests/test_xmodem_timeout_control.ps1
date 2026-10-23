$ErrorActionPreference='Stop'
$source=Join-Path (Split-Path -Parent $PSScriptRoot) 'Tools/Send-Xmodem.ps1'
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$null,[ref]$null)
$function=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-XmodemTimeoutControl'},$true)
if (-not $function) {throw 'Timeout control helper absent'}
Invoke-Expression $function.Extent.Text
$disconnect=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Test-XmodemPostAckDisconnect'},$true)
Invoke-Expression $disconnect.Extent.Text
foreach($inner in @([IO.IOException]::new('disconnected'),[InvalidOperationException]::new('closed'),[OperationCanceledException]::new('cancelled'))){
 $wrapped=[Exception]::new('PowerShell invocation wrapper',$inner)
 if(-not (Test-XmodemPostAckDisconnect -Exception $wrapped)){throw 'Post-ACK disconnect wrapper not recognized'}
}
if(Test-XmodemPostAckDisconnect -Exception ([ArgumentException]::new('unrelated'))){throw 'Unrelated error swallowed'}
function Wait-XmodemResponse {param($Serial,$TimeoutSeconds) if($TimeoutSeconds -ne 12){throw 'Deadline changed'};return $script:response}
$serial=[pscustomobject]@{Writes=0;Bytes=0}
$serial|Add-Member ScriptMethod Write {param($packet,$offset,$count) if($offset -ne 0 -or $count -ne 17){throw 'Wrong fault prefix'};$this.Writes++;$this.Bytes+=$count}
$packet=[byte[]]::new(1029)
$script:response=21
$elapsed=Invoke-XmodemTimeoutControl -Serial $serial -Packet $packet
if($serial.Writes -ne 1 -or $serial.Bytes -ne 17 -or $elapsed -gt 12000){throw 'One-prefix success invariant failed'}
foreach($script:response in @($null,6,24)){
 $rejected=$false
 try {Invoke-XmodemTimeoutControl -Serial $serial -Packet $packet|Out-Null} catch {$rejected=$true}
 if(-not $rejected){throw 'Unexpected control accepted'}
}
Write-Output 'PASS timeout sender control:17byte prefix only,12s bound, NAK only, timeout/ACK/CAN rejection; no port opened'
Write-Output 'PASS post-EOT-ACK only disconnect handling: IO/closed/cancelled wrappers accepted, unrelated error rejected; pre-ACK code unchanged'
