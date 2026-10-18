$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
New-Item -ItemType File -Force backend/.state/bridge-stop | Out-Null
docker compose --profile vision stop
$visionPidPath=Join-Path $PSScriptRoot 'backend\.state\vision-server.pid'
if (Test-Path -LiteralPath $visionPidPath) {
 $visionProcessId=0
 if ([int]::TryParse((Get-Content -LiteralPath $visionPidPath -Raw).Trim(),[ref]$visionProcessId)) {
  $visionProcess=Get-Process -Id $visionProcessId -ErrorAction SilentlyContinue
  $expectedExecutable=Join-Path $PSScriptRoot 'backend\.state\vision-runtime\bin\llama-server.exe'
  if ($visionProcess -and $visionProcess.Path -ieq $expectedExecutable) { Stop-Process -Id $visionProcessId }
 }
}
