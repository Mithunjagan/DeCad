$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop first.' }
docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop first.' }
if ((Test-Path -LiteralPath '.env') -and (Select-String -LiteralPath '.env' -Pattern '^VISION_API_PROTOCOL=openai$' -Quiet)) {
 & ./start-vision.ps1
}
$memory = [long](docker info --format '{{.MemTotal}}')
if ($env:ENABLE_VISION -eq 'true' -and $memory -ge 7500000000) {
 $env:IMAGE_MODE='vision'
 if (-not $env:MODEL_MEMORY_LIMIT) {$env:MODEL_MEMORY_LIMIT='4g'}
}
New-Item -ItemType Directory -Force backend/workspaces,backend/.state,backend/datasets | Out-Null
docker compose build kicad
if ($LASTEXITCODE -ne 0) { throw 'Core build failed.' }
docker compose build frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
docker compose up -d kicad frontend
if ($LASTEXITCODE -ne 0) { throw 'Container build/start failed. See the output above.' }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) { Start-Process -FilePath $python.Source -ArgumentList @('bridge/desktop_bridge.py','--state','backend/.state') -WindowStyle Hidden }
else { Write-Host 'Desktop application opening requires Python 3.11+. Application bundles remain available.' }
$memory = [long](docker info --format '{{.MemTotal}}')
if (($env:ENABLE_AI -eq 'true' -or $env:ENABLE_VISION -eq 'true') -and $memory -ge 3700000000) {
 docker compose --profile vision up -d vision
 $ready=$false
 for ($i=0;$i -lt 30;$i++) { docker compose exec -T vision ollama list *> $null; if ($LASTEXITCODE -eq 0) {$ready=$true;break}; Start-Sleep -Seconds 1 }
 if ($ready) {
  $chatModel=if ($env:CHAT_MODEL) {$env:CHAT_MODEL} else {'qwen3:0.6b'}
  docker compose exec -T vision ollama pull $chatModel
  if ($env:ENABLE_VISION -eq 'true' -and $memory -ge 7500000000) {
   $visionModel=if ($env:VISION_MODEL) {$env:VISION_MODEL} else {'qwen3-vl:2b-instruct'}
   docker compose exec -T vision ollama pull $visionModel
  }
 }
}
Write-Host 'Workbench: http://localhost:3100'
Start-Process http://localhost:3100
