$ErrorActionPreference = 'Stop'
# Runs the workbench without Docker, using the KiCad 10 Windows install (its bundled Python provides pcbnew).
Set-Location $PSScriptRoot
$nativeEnvironmentPath = Join-Path $PSScriptRoot 'backend\.env'
if (-not $env:S2SDN_KICAD_DIR -and (Test-Path -LiteralPath $nativeEnvironmentPath)) {
 $nativeKicadEntry = Get-Content -LiteralPath $nativeEnvironmentPath | Where-Object { $_ -match '^\s*S2SDN_KICAD_DIR\s*=' } | Select-Object -Last 1
 if ($nativeKicadEntry) { $env:S2SDN_KICAD_DIR = ($nativeKicadEntry -split '=', 2)[1].Trim().Trim('"').Trim("'") }
}
$kicad = if ($env:S2SDN_KICAD_DIR) { $env:S2SDN_KICAD_DIR } else { 'D:\KICAD' }
if (-not (Test-Path "$kicad\bin\kicad-cli.exe")) { throw "KiCad not found at $kicad. Set S2SDN_KICAD_DIR." }
$nativeProfile = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'backend\pipeline_profiles.json') -Raw | ConvertFrom-Json).hybrid_max_accuracy
$nativeCheckpoint = Join-Path $PSScriptRoot $nativeProfile.ocr_checkpoint
if (-not (Test-Path -LiteralPath $nativeCheckpoint -PathType Leaf)) { throw 'The accepted OCR checkpoint is missing. Follow docs/SETUP.md before starting the production profile.' }
if ((Get-FileHash -LiteralPath $nativeCheckpoint -Algorithm SHA256).Hash -ine $nativeProfile.ocr_checkpoint_sha256) { throw 'The OCR checkpoint digest does not match backend/pipeline_profiles.json. See docs/SETUP.md.' }
$env:KICAD_CLI = "$kicad\bin\kicad-cli.exe"
$env:KICAD_SYMBOL_DIR = "$kicad\share\kicad\symbols"
$env:KICAD_FOOTPRINT_DIR = "$kicad\share\kicad\footprints"
$env:KICAD_PYTHON = "$kicad\bin\python.exe"
$env:S2SDN_PIPELINE_PROFILE = 'hybrid_max_accuracy'
$env:IMAGE_MODE = 'hybrid_max_accuracy'
$py = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
 & $env:KICAD_PYTHON -m venv --system-site-packages backend\.venv
 if ($LASTEXITCODE -ne 0) { throw 'venv creation failed.' }
 # KiCad ships Python 3.11; the Docker pins for numpy/scipy need 3.12, so relax only those two.
 (Get-Content backend\requirements.txt) -replace '^numpy==.*','numpy>=2.2,<2.5' -replace '^scipy==.*','scipy>=1.14' | Set-Content -Encoding utf8 backend\.venv\req-native.txt
 & $py -m pip install -r backend\.venv\req-native.txt
 if ($LASTEXITCODE -ne 0) { throw 'Backend dependency install failed.' }
 & $py -m pip install --no-deps -r backend\requirements-ocr.txt
 if ($LASTEXITCODE -ne 0) { throw 'OCR dependency install failed.' }
}
if (-not (Test-Path 'frontend\node_modules\next')) {
 Push-Location frontend
 try { npm ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency install failed.' } }
 finally { Pop-Location }
}
New-Item -ItemType Directory -Force backend\workspaces,backend\.state | Out-Null
function Test-Port($port) { [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
# Servers run with no console window at all (Windows Terminal ignores -WindowStyle Hidden).
function Start-Background($dir, $command) {
 $si = New-Object System.Diagnostics.ProcessStartInfo 'cmd.exe', "/d /s /c `"$command`""
 $si.WorkingDirectory = Join-Path $PSScriptRoot $dir; $si.UseShellExecute = $false; $si.CreateNoWindow = $true
 [void][System.Diagnostics.Process]::Start($si)
}
# Already running (e.g. second double-click on the DeCad icon): only open the window.
if (-not (Test-Port 8100)) {
 Start-Background 'backend' "`"$py`" -m uvicorn app.main:app --host 127.0.0.1 --port 8100 > `"$PSScriptRoot\backend\.state\backend.log`" 2>&1"
}
if (-not (Test-Port 3100)) {
 Start-Background 'frontend' "npx next dev -p 3100 > `"$PSScriptRoot\backend\.state\frontend.log`" 2>&1"
}
Write-Host 'Workbench: http://localhost:3100 (API http://localhost:8100)'
# Next dev serves its assets to localhost only (not 127.0.0.1).
$url = 'http://localhost:3100'
$deadline = (Get-Date).AddMinutes(3)
$ready = $false
while ((Get-Date) -lt $deadline) {
 try {
  $apiReady = (Invoke-WebRequest 'http://127.0.0.1:8100/health' -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200
  if ($apiReady -and (Invoke-WebRequest "$url/manifest.webmanifest" -UseBasicParsing -TimeoutSec 60).StatusCode -eq 200) { $ready = $true; break }
 } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) { throw 'Workbench startup timed out. Inspect backend/.state/backend.log and frontend.log, fix the reported error, then run start-native.ps1 again.' }
# Open DeCad in its own app window (no tabs or address bar), like an installed web app.
$browser = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($browser) { Start-Process -FilePath $browser -ArgumentList "--app=$url", '--window-size=1500,950' } else { Start-Process $url }
