param([int]$GpuLayers = 22, [string]$Device = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$stateDirectory = Join-Path $PSScriptRoot 'backend\.state'
$runtimeDirectory = Join-Path $stateDirectory 'vision-runtime'
$modelDirectory = Join-Path $stateDirectory 'vision-model'
$serverExecutable = Join-Path $runtimeDirectory 'bin\llama-server.exe'
if (-not (Test-Path -LiteralPath $serverExecutable)) { throw 'Prepare the local vision runtime first; see WINDOWS_VISION.md.' }
foreach ($modelFile in @('Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf','mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf','circuit-adapter.gguf')) {
    if (-not (Test-Path -LiteralPath (Join-Path $modelDirectory $modelFile))) { throw "Missing $modelFile; see WINDOWS_VISION.md." }
}
if ((Get-Item -LiteralPath (Join-Path $modelDirectory 'Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf')).Length -ne 4683072032 -or
    (Get-Item -LiteralPath (Join-Path $modelDirectory 'mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf')).Length -ne 853119712) {
    throw 'The base model download is incomplete. Finish setup-vision.ps1 before starting vision.'
}
$keyFile = Join-Path $stateDirectory 'vision-api-key'
if (-not (Test-Path -LiteralPath $keyFile)) { throw 'The local vision API key has not been configured.' }
$visionHeaders = @{ Authorization = 'Bearer ' + (Get-Content -LiteralPath $keyFile -Raw).Trim() }
function Test-VisionReady {
    try {
        $models = Invoke-RestMethod -Uri 'http://127.0.0.1:11436/v1/models' -Headers $visionHeaders -TimeoutSec 5
        $adapters = Invoke-RestMethod -Uri 'http://127.0.0.1:11436/lora-adapters' -Headers $visionHeaders -TimeoutSec 5
        return @($models.data.id) -contains 'schematic2sdn-qwen-vl' -and @($adapters | Where-Object { $_.path -match 'circuit-adapter\.gguf$' -and $_.scale -gt 0 }).Count -gt 0
    } catch { return $false }
}
if (Get-NetTCPConnection -State Listen -LocalPort 11436 -ErrorAction SilentlyContinue) {
    if (Test-VisionReady) {
        Write-Host 'The supplied vision adapter is already loaded and available.'
        return
    }
    throw 'Port 11436 is in use, but the supplied adapter could not be verified. Check the existing server before restarting.'
}
if (-not $Device) {
    $deviceLines = & $serverExecutable --list-devices 2>&1
    foreach ($deviceLine in $deviceLines) {
        if ([string]$deviceLine -match '^\s*(Vulkan\d+):.*NVIDIA') { $Device = $Matches[1]; break }
    }
    if (-not $Device) { throw 'No NVIDIA Vulkan device was found. Check the graphics driver or pass -Device explicitly.' }
}
$arguments = @(
    '--model', 'backend/.state/vision-model/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf',
    '--mmproj', 'backend/.state/vision-model/mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf',
    '--lora', 'backend/.state/vision-model/circuit-adapter.gguf',
    '--alias', 'schematic2sdn-qwen-vl',
    '--host', '0.0.0.0', '--port', '11436',
    '--api-key-file', 'backend/.state/vision-api-key',
    '--device', $Device, '--gpu-layers', "$GpuLayers", '--fit', 'off', '--no-mmproj-offload',
    '--override-tensor', "output.weight=$Device",
    '--ctx-size', '8192', '--batch-size', '128', '--ubatch-size', '64',
    '--parallel', '1', '--threads', '4', '--threads-batch', '4',
    '--image-min-tokens', '1024', '--image-max-tokens', '1536',
    '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
    '--no-warmup', '--sleep-idle-seconds', '120', '--timeout', '900'
)
$serverProcess = Start-Process -FilePath $serverExecutable -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $stateDirectory 'vision-server.stdout.log') -RedirectStandardError (Join-Path $stateDirectory 'vision-server.stderr.log') -PassThru
$serverProcess.Id | Set-Content -LiteralPath (Join-Path $stateDirectory 'vision-server.pid')
Write-Host "Vision server started (PID $($serverProcess.Id)). Loading the supplied adapter may take a few minutes."
Write-Host 'Workbench: http://localhost:3100'
Write-Host 'Log: backend\.state\vision-server.stderr.log'
$readyDeadline = [DateTime]::UtcNow.AddMinutes(3)
while ([DateTime]::UtcNow -lt $readyDeadline) {
    if ($serverProcess.HasExited) { throw 'The vision process exited during loading. See backend\.state\vision-server.stderr.log.' }
    if (Test-VisionReady) { Write-Host 'The supplied vision adapter is loaded and available.'; return }
    Start-Sleep -Seconds 2
}
throw 'Vision loading did not complete within three minutes. Check the native server log before retrying.'
