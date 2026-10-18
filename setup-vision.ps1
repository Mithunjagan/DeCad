$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$stateDirectory = Join-Path $PSScriptRoot 'backend\.state'
$environmentDirectory = Join-Path $stateDirectory 'vision-venv'
$visionPython = Join-Path $environmentDirectory 'Scripts\python.exe'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
if (-not (Test-Path -LiteralPath $visionPython)) {
    & python -m venv $environmentDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or newer, then retry.' }
}
& $visionPython -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the vision Python environment.' }
& $visionPython -m pip install -r training/requirements-windows-vision.txt
if ($LASTEXITCODE -ne 0) { throw 'Vision preparation dependencies could not be installed.' }
$runtimeDirectory = Join-Path $stateDirectory 'vision-runtime'
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$archive = Join-Path $runtimeDirectory 'llama-b11669-vulkan.zip'
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri 'https://github.com/ggml-org/llama.cpp/releases/download/b11669/llama-b11669-bin-win-vulkan-x64.zip' -OutFile $archive -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine '2c07574e7bde71321cb785282b20cc821e951132149eeceeea32ddebdbf0598e') {
    throw 'The native runtime checksum does not match the pinned official release.'
}
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $runtimeDirectory 'bin') -Force
& $visionPython -u training/prepare_windows_vision.py --configure
if ($LASTEXITCODE -ne 0) { throw 'Vision model download, checksum, or adapter conversion failed.' }
& ./start-vision.ps1
docker compose up -d --build --wait --wait-timeout 180 kicad frontend
if ($LASTEXITCODE -ne 0) { throw 'The DeCad containers could not start.' }
Write-Host 'Open http://localhost:3100 and wait for the Vision model installed indicator.'
